"""Coleta de itens brutos: feeds RSS, banco do DAAD e páginas monitoradas."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup

from .prazos import datas_no_texto

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
TIMEOUT = 25
sessao = requests.Session()
sessao.headers.update({"User-Agent": UA, "Accept-Language": "en,pt;q=0.8"})


@dataclass
class ItemBruto:
    titulo: str
    url: str
    fonte: str
    texto: str = ""          # resumo + conteúdo, usado para pontuar
    publicado: str = ""      # ISO 8601, quando a fonte informa
    prazo_bruto: str = ""    # texto de prazo vindo da fonte, se houver
    bonus: int = 0
    tematica: bool = False
    extras: dict = field(default_factory=dict)


def normalizar_url(url: str) -> str:
    """Tira parâmetros de rastreamento, fragmento e barra final."""
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    caminho = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), caminho, urlencode(query), ""))


def id_de(url: str) -> str:
    return hashlib.sha1(normalizar_url(url).encode()).hexdigest()[:16]


def html_para_texto(html: str, principal: bool = False) -> str:
    sopa = BeautifulSoup(html or "", "html.parser")
    for tag in sopa(["script", "style", "noscript", "nav", "footer", "header", "form", "svg", "aside"]):
        tag.decompose()
    if principal:
        # Em agregadores, a barra lateral lista outras oportunidades e polui a pontuação.
        sopa = sopa.find("article") or sopa.find("main") or sopa
    return re.sub(r"\s+", " ", sopa.get_text(" ")).strip()


def baixar(url: str) -> requests.Response | None:
    try:
        r = sessao.get(url, timeout=TIMEOUT)
        return r
    except requests.RequestException as e:
        log.warning("falha ao baixar %s: %s", url, e)
        return None


def texto_da_pagina(url: str) -> str:
    r = baixar(url)
    if r is None or r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return ""
    return html_para_texto(r.text, principal=True)


# ---------------------------------------------------------------- RSS

def coletar_rss(fonte: dict) -> list[ItemBruto]:
    r = baixar(fonte["url"])
    if r is None or r.status_code != 200:
        status = r.status_code if r is not None else "sem resposta"
        raise RuntimeError(f"HTTP {status}")
    feed = feedparser.parse(r.content)
    itens = []
    for e in feed.entries:
        if not e.get("link") or not e.get("title"):
            continue
        partes = [e.get("summary", "")]
        partes += [c.get("value", "") for c in e.get("content", [])]
        texto = html_para_texto(" ".join(partes))
        publicado = ""
        if e.get("published_parsed"):
            publicado = "%04d-%02d-%02d" % tuple(e.published_parsed[:3])
        itens.append(ItemBruto(
            titulo=html_para_texto(e.title),
            url=e.link,
            fonte=fonte["nome"],
            texto=texto,
            publicado=publicado,
            bonus=fonte.get("bonus", 0),
            tematica=fonte.get("tematica", False),
        ))
    return itens


# ---------------------------------------------------------------- DAAD

DAAD_DADOS = "https://www2.daad.de/bundles/daadstipendiendatenbanklsh/data/a/js/"
DAAD_DETALHE = ("https://www2.daad.de/deutschland/stipendium/datenbank/en/"
                "21148-scholarship-database/?detail={}")


def _taffy(nome: str) -> list[dict]:
    r = baixar(DAAD_DADOS + nome)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"DAAD {nome}: sem resposta")
    s = r.text
    return json.loads(s[s.index("(") + 1:s.rindex(")")])


def coletar_daad(conf: dict) -> list[ItemBruto]:
    """Programas do banco do DAAD abertos a brasileiros no nível e nas áreas pedidas."""
    programas = _taffy("scholarships.js")
    prazos = {p["id"]: p for p in _taffy("deadlines.js")}
    status, areas = set(conf["status"]), set(conf["areas"])
    itens = []
    for p in programas:
        if conf["origem"] not in p.get("origin", []):
            continue
        if not status & set(p.get("status", [])) or not areas & set(p.get("subjectGrps", [])):
            continue
        intro = p.get("introduction") or {}
        intro = intro.get("en", "") if isinstance(intro, dict) else str(intro)
        prazo = prazos.get(p["sapProgid"], {})
        # `countries` é {código do país: [{"de": ..., "en": ...}]}; a lista vazia significa "nenhum".
        por_pais = prazo.get("countries") or {}
        textos = [t.get("en", "") for t in por_pais.get(str(conf["origem"]), [])]
        textos.append((prazo.get("general") or {}).get("en", ""))
        prazo_txt = " ".join(f"Deadline: {t}" for t in textos if t)
        # `qEn` é o índice de busca do DAAD e lista todos os países; não entra na pontuação.
        mobilidade = re.search(conf.get("tematica_se_titulo", r"$^"), p["nameEn"], re.I)
        itens.append(ItemBruto(
            titulo=p["nameEn"],
            url=DAAD_DETALHE.format(p["sapProgid"]),
            fonte="DAAD",
            texto=html_para_texto(intro),
            prazo_bruto=html_para_texto(prazo_txt),
            bonus=conf.get("bonus", 0),
            tematica=bool(mobilidade),
        ))
    return itens


# ---------------------------------------------------------------- páginas monitoradas

FRASES_DE_EDITAL = re.compile(
    r"[^.]{0,120}\b(deadline|call for|applications? (are )?(now )?(open|closed?)|apply (now|by)|"
    r"next (round|call)|closing date|inscriç|edital|prazo)\b[^.]{0,160}",
    re.I,
)


def assinatura_da_pagina(texto: str, hoje: date | None = None) -> tuple[list[str], list[str]]:
    """Só as partes que importam: datas futuras e frases sobre inscrição.

    Menus, banners e "projetos em destaque" com datas passadas mudam o tempo
    todo e não dizem nada sobre o próximo edital, então ficam de fora.
    """
    hoje = hoje or date.today()
    datas = sorted({d.isoformat() for _, d in datas_no_texto(texto) if d >= hoje})
    frases = sorted({re.sub(r"\s+", " ", m.group(0)).strip()[:240] for m in FRASES_DE_EDITAL.finditer(texto)})
    return datas, frases


def verificar_pagina(url: str, hoje: date | None = None) -> dict:
    r = baixar(url)
    if r is None:
        return {"status": "sem resposta"}
    if r.status_code != 200:
        return {"status": f"HTTP {r.status_code}"}
    texto = html_para_texto(r.text)
    datas, frases = assinatura_da_pagina(texto, hoje)
    return {"status": "ok", "datas": datas, "frases": frases[:12], "texto": texto}
