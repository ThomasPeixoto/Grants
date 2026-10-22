"""Uma execução diária: coleta, filtra, guarda e devolve o que é novidade."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import coletores
from .pontuacao import Pontuador, classificar_tipo
from .prazos import extrair_prazo

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config"
DADOS = RAIZ / "data"

LEMBRETES = {14, 7, 3, 1}   # dias antes do prazo em que o item volta à newsletter
GUARDAR_ENCERRADOS = 60     # dias depois do prazo até sair do arquivo
GUARDAR_SEM_PRAZO = 365     # dias desde que foi encontrado, para itens sem prazo
GUARDAR_VISTOS = 400


@dataclass
class Relatorio:
    hoje: date
    primeira_execucao: bool
    novos: list[dict] = field(default_factory=list)
    prazos_proximos: list[dict] = field(default_factory=list)
    paginas_mudaram: list[dict] = field(default_factory=list)
    fontes: dict = field(default_factory=dict)


def _ler(nome: str, padrao):
    p = DADOS / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else padrao


def _gravar(nome: str, valor) -> None:
    DADOS.mkdir(exist_ok=True)
    (DADOS / nome).write_text(json.dumps(valor, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8")


def chave_titulo(titulo: str) -> str:
    """Título sem acentos, pontuação e anos, para achar o mesmo edital em agregadores diferentes."""
    t = unicodedata.normalize("NFKD", titulo.lower()).encode("ascii", "ignore").decode()
    t = re.sub(r"\b20\d{2}(/\d{2,4})?\b", " ", t)
    t = re.sub(r"\b(call for (applications|proposals)|apply now|deadline.*|fully funded)\b", " ", t)
    return " ".join(re.findall(r"[a-z0-9]+", t))


def coletar_tudo(fontes: dict) -> tuple[list[coletores.ItemBruto], dict]:
    itens, saude = [], {}
    tarefas = [(f["nome"], lambda f=f: coletores.coletar_rss(f))
               for f in fontes.get("rss", []) if f.get("ativo", True)]
    if fontes.get("daad", {}).get("ativo"):
        tarefas.append(("DAAD", lambda: coletores.coletar_daad(fontes["daad"])))
    for nome, tarefa in tarefas:
        try:
            achados = tarefa()
            saude[nome] = {"status": "ok", "itens": len(achados)}
            itens += achados
            log.info("%-45s %3d itens", nome, len(achados))
        except Exception as e:  # uma fonte quebrada não pode derrubar as outras
            saude[nome] = {"status": "erro", "erro": str(e)[:200]}
            log.warning("%-45s ERRO %s", nome, e)
    return itens, saude


def executar(hoje: date | None = None, baixar_paginas: bool = True) -> Relatorio:
    hoje = hoje or date.today()
    perfil = yaml.safe_load((CONFIG / "perfil.yaml").read_text(encoding="utf-8"))
    fontes = yaml.safe_load((CONFIG / "fontes.yaml").read_text(encoding="utf-8"))
    programas = yaml.safe_load((CONFIG / "programas.yaml").read_text(encoding="utf-8"))["programas"]
    pontuador = Pontuador(perfil)

    oportunidades: dict[str, dict] = {o["id"]: o for o in _ler("oportunidades.json", [])}
    vistos: dict[str, str] = _ler("vistos.json", {})
    paginas: dict[str, dict] = _ler("paginas.json", {})
    rel = Relatorio(hoje=hoje, primeira_execucao=not vistos)

    itens, rel.fontes = coletar_tudo(fontes)
    por_titulo = {chave_titulo(o["titulo"]): o for o in oportunidades.values()}
    orcamento_paginas = fontes.get("max_paginas_por_execucao", 40) if baixar_paginas else 0

    for item in itens:
        oid = coletores.id_de(item.url)
        if oid in vistos:
            if oid in oportunidades and item.prazo_bruto:
                # O DAAD atualiza os prazos dos mesmos programas a cada ciclo.
                prazo, rotulo = extrair_prazo(item.prazo_bruto, hoje)
                if prazo:
                    oportunidades[oid]["prazo"], oportunidades[oid]["prazo_rotulo"] = prazo.isoformat(), rotulo
            continue
        vistos[oid] = hoje.isoformat()

        chave = chave_titulo(item.titulo)
        repetida = por_titulo.get(chave)
        if repetida and len(chave) > 15:
            if item.fonte not in repetida["fontes"]:
                repetida["fontes"].append(item.fonte)
            continue

        if not pontuador.parece_chamada(item.titulo):
            continue
        texto = f"{item.titulo}. {item.texto}"
        r = pontuador.pontuar(texto, item.bonus, item.tematica)
        if not r.aceito:
            continue

        prazo, rotulo = extrair_prazo(f"{item.prazo_bruto} {texto}", hoje)
        if not prazo and orcamento_paginas > 0:
            # O feed quase nunca traz o prazo; ele costuma estar no corpo do anúncio.
            orcamento_paginas -= 1
            pagina = coletores.texto_da_pagina(item.url)
            if pagina:
                prazo, rotulo = extrair_prazo(pagina, hoje)
                # Restrições de nacionalidade quase sempre ficam no corpo do texto.
                r = pontuador.pontuar(f"{texto} {pagina[:6000]}", item.bonus, item.tematica)
                if not r.aceito:
                    continue

        registro = {
            "id": oid,
            "titulo": item.titulo,
            "url": item.url,
            "fontes": [item.fonte],
            "publicado": item.publicado,
            "encontrado": hoje.isoformat(),
            "prazo": prazo.isoformat() if prazo else "",
            "prazo_rotulo": rotulo,
            "pontos": r.pontos,
            "motivos": r.motivos,
            "destaque": r.destaque,
            "tipo": classificar_tipo(item.titulo) if classificar_tipo(item.titulo) != "outro"
                    else classificar_tipo(texto),
            "resumo": item.texto[:420],
        }
        oportunidades[oid] = registro
        por_titulo[chave] = registro
        rel.novos.append(registro)

    # Páginas de programas recorrentes
    for prog in programas:
        if not prog.get("monitorar"):
            continue
        anterior = paginas.get(prog["url"], {})
        agora = coletores.verificar_pagina(prog["url"], hoje)
        estado = {**anterior, "status": agora["status"], "verificado": hoje.isoformat()}
        if agora["status"] == "ok":
            estado.update(datas=agora["datas"], frases=agora["frases"])
            # Só conta como mudança uma data futura nova ou frase de inscrição diferente;
            # uma data que ficou no passado não é novidade.
            datas_novas = sorted(set(agora["datas"]) - set(anterior.get("datas", [])))
            frases_mudaram = set(agora["frases"]) != set(anterior.get("frases", []))
            if "frases" in anterior and (datas_novas or frases_mudaram):
                estado["mudou"] = hoje.isoformat()
                prazo, _ = extrair_prazo(agora["texto"], hoje)
                rel.paginas_mudaram.append({
                    **prog,
                    "datas_novas": datas_novas,
                    "prazo": prazo.isoformat() if prazo else "",
                })
        paginas[prog["url"]] = estado

    # Lembretes de prazo para o que já foi enviado antes, só em alguns marcos,
    # para o mesmo edital não aparecer todo dia.
    ids_novos = {o["id"] for o in rel.novos}
    rel.prazos_proximos = sorted(
        (o for o in oportunidades.values()
         if o["prazo"] and o["id"] not in ids_novos
         and (date.fromisoformat(o["prazo"]) - hoje).days in LEMBRETES),
        key=lambda o: o["prazo"],
    )

    # Limpeza
    def manter(o: dict) -> bool:
        if o["prazo"]:
            return o["prazo"] >= (hoje - timedelta(days=GUARDAR_ENCERRADOS)).isoformat()
        return o["encontrado"] >= (hoje - timedelta(days=GUARDAR_SEM_PRAZO)).isoformat()

    corte_vistos = (hoje - timedelta(days=GUARDAR_VISTOS)).isoformat()
    _gravar("oportunidades.json", sorted((o for o in oportunidades.values() if manter(o)),
                                         key=lambda o: (o["encontrado"], o["pontos"]), reverse=True))
    _gravar("vistos.json", {k: v for k, v in vistos.items() if v >= corte_vistos})
    _gravar("paginas.json", paginas)
    _gravar("fontes.json", {"atualizado": hoje.isoformat(), "fontes": rel.fontes})

    rel.novos.sort(key=lambda o: (not o["destaque"], -o["pontos"]))
    return rel


def carregar_programas() -> list[dict]:
    programas = yaml.safe_load((CONFIG / "programas.yaml").read_text(encoding="utf-8"))["programas"]
    paginas = _ler("paginas.json", {})
    return [{**p, "estado": paginas.get(p["url"], {})} for p in programas]
