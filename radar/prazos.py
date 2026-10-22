"""Encontra datas de prazo em texto livre (inglês e português)."""
from __future__ import annotations

import re
from datetime import date

MESES = {
    # inglês
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # português
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
    "fev": 2, "abr": 4, "mai": 5, "ago": 8, "set": 9, "out": 10, "dez": 12,
}
_MES = "|".join(sorted(MESES, key=len, reverse=True))
_DIA = r"(\d{1,2})(?:st|nd|rd|th|º)?"
_ANO = r"(20\d{2})"

# Cada padrão devolve (dia, mês, ano) na ordem dada por `ordem`.
_PADROES = [
    (re.compile(rf"\b{_DIA}\s+(?:de\s+)?({_MES})\.?,?\s+(?:de\s+)?{_ANO}\b", re.I), "dma"),
    (re.compile(rf"\b({_MES})\.?\s+{_DIA},?\s+{_ANO}\b", re.I), "mda"),
    (re.compile(rf"\b{_ANO}-(\d{{2}})-(\d{{2}})\b"), "amd"),
    (re.compile(rf"\b(\d{{1,2}})[/.](\d{{1,2}})[/.]{_ANO}\b"), "dma"),  # 30/10/2026 e 30.10.2026: dia primeiro
]

GATILHOS = re.compile(
    r"deadline|closing date|closes?\b|close on|apply by|applications? (are )?(due|close)|"
    r"due (date|by)|submi(t|ssion)s? (by|before|until)|until|no later than|"
    r"prazo|inscriç(ões|ão)|até\b|encerra",
    re.I,
)
CONTINUO = re.compile(r"rolling (basis|deadline|applications)|no deadline|open year[- ]round|"
                      r"fluxo contínuo|ongoing", re.I)

JANELA = 160  # caracteres depois do gatilho onde a data precisa aparecer


def _monta(grupos: tuple[str, ...], ordem: str) -> date | None:
    partes = dict(zip(ordem, grupos))
    try:
        dia = int(partes["d"])
        mes = partes["m"]
        mes = int(mes) if mes.isdigit() else MESES[mes.lower().rstrip(".")]
        return date(int(partes["a"]), mes, dia)
    except (ValueError, KeyError):
        return None


def datas_no_texto(texto: str) -> list[tuple[int, date]]:
    """Todas as datas do texto, com a posição onde começam."""
    achadas = []
    for padrao, ordem in _PADROES:
        for m in padrao.finditer(texto):
            d = _monta(m.groups(), ordem)
            if d:
                achadas.append((m.start(), d))
    return sorted(achadas)


def extrair_prazo(texto: str, hoje: date | None = None) -> tuple[date | None, str]:
    """Devolve (prazo, rótulo).

    O prazo é a data mais próxima ainda no futuro, entre as que aparecem logo
    depois de uma palavra como "deadline" ou "prazo". O rótulo é "contínuo"
    para inscrições em fluxo contínuo, ou "" quando nada foi encontrado.
    """
    hoje = hoje or date.today()
    texto = re.sub(r"\s+", " ", texto or "")
    datas = datas_no_texto(texto)
    candidatas = []
    for g in GATILHOS.finditer(texto):
        # Só a primeira data depois do gatilho: em "Deadline: X. Event on Y", Y não é prazo.
        seguinte = next(((pos, d) for pos, d in datas if pos >= g.start()), None)
        if seguinte and seguinte[0] <= g.end() + JANELA and seguinte[1] >= hoje:
            candidatas.append(seguinte[1])
    if candidatas:
        return min(candidatas), ""
    if CONTINUO.search(texto):
        return None, "contínuo"
    return None, ""
