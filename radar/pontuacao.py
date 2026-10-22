"""Pontuação por palavras-chave, com o motivo de cada ponto."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Resultado:
    pontos: int
    motivos: list[str] = field(default_factory=list)
    grupos: set[str] = field(default_factory=set)
    aceito: bool = False
    destaque: bool = False


class Pontuador:
    def __init__(self, perfil: dict):
        self.limiar = perfil["limiar_inclusao"]
        self.limiar_destaque = perfil["limiar_destaque"]
        self.exige = set(perfil.get("exige_algum_de", []))
        uniao = lambda chave: re.compile("|".join(perfil[chave]), re.I) if perfil.get(chave) else None
        self.titulo_exige = uniao("titulo_exige")
        self.titulo_exclui = uniao("titulo_exclui")
        self.grupos = {
            nome: (g["peso"], g.get("max_termos", 2), [re.compile(t, re.I) for t in g["termos"]])
            for nome, g in perfil["grupos"].items()
        }
        self.penalidades = [
            (p["motivo"], p["peso"], [re.compile(t, re.I) for t in p["termos"]],
             re.compile(p["exceto"], re.I) if p.get("exceto") else None)
            for p in perfil.get("penalidades", [])
        ]

    def parece_chamada(self, titulo: str) -> bool:
        if self.titulo_exclui and self.titulo_exclui.search(titulo):
            return False
        return not self.titulo_exige or bool(self.titulo_exige.search(titulo))

    def pontuar(self, texto: str, bonus: int = 0, tematica: bool = False) -> Resultado:
        r = Resultado(pontos=bonus)
        if bonus:
            r.motivos.append(f"fonte {bonus:+d}")
        for nome, (peso, maximo, termos) in self.grupos.items():
            achados = []
            for t in termos:
                m = t.search(texto)
                if m:
                    achados.append(m.group(0).lower())
                if len(achados) == maximo:
                    break
            if achados:
                r.grupos.add(nome)
                r.pontos += peso * len(achados)
                r.motivos.append(f"{nome}: {', '.join(dict.fromkeys(achados))}")
        for motivo, peso, termos, exceto in self.penalidades:
            if exceto and exceto.search(texto):
                continue
            if any(t.search(texto) for t in termos):
                r.pontos += peso
                r.motivos.append(f"{motivo} ({peso})")
        tem_tema = tematica or not self.exige or bool(self.exige & r.grupos)
        r.aceito = tem_tema and r.pontos >= self.limiar
        r.destaque = r.aceito and r.pontos >= self.limiar_destaque
        return r


TIPOS = [
    ("sanduiche", re.compile(r"sandwich|sanduíche|visiting (phd|student|scholar|research)|"
                             r"research (stay|visit|exchange|mobility)|exchange (program|grant)|"
                             r"cotutelle|split[- ]site|mobility", re.I)),
    ("pesquisa", re.compile(r"(small|research|seed|field|project) grants?|fieldwork|expedition|"
                            r"research fund|conservation (grant|fund|award)", re.I)),
    ("bolsa", re.compile(r"scholarships?|fellowships?|studentships?|\bbolsas?\b", re.I)),
    ("evento", re.compile(r"summer school|winter school|workshop|training course|conference|"
                          r"\bcurso\b|escola de (verão|inverno)", re.I)),
]


def classificar_tipo(texto: str) -> str:
    for nome, padrao in TIPOS:
        if padrao.search(texto):
            return nome
    return "outro"
