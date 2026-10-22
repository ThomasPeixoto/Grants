"""Gera site/dados.json, lido pela página estática site/index.html."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .pipeline import DADOS, RAIZ, carregar_programas

SITE = RAIZ / "site"


def gerar() -> None:
    oportunidades = json.loads((DADOS / "oportunidades.json").read_text(encoding="utf-8"))
    fontes = json.loads((DADOS / "fontes.json").read_text(encoding="utf-8"))
    programas = [
        {k: p.get(k) for k in ("nome", "url", "tipo", "nota", "monitorar")}
        | {k: p["estado"].get(k) for k in ("status", "verificado", "mudou", "datas")}
        for p in carregar_programas()
    ]
    dados = {
        "gerado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "oportunidades": oportunidades,
        "programas": programas,
        "fontes": fontes["fontes"],
    }
    SITE.mkdir(exist_ok=True)
    (SITE / "dados.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
