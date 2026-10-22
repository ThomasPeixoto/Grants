"""python -m radar [--sem-email] [--previa arquivo.html] [--sem-paginas]"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from . import newsletter, pipeline, site


def main() -> None:
    ap = argparse.ArgumentParser(description="Radar diário de oportunidades")
    ap.add_argument("--sem-email", action="store_true", help="não envia o e-mail")
    ap.add_argument("--previa", type=Path, help="grava o HTML da newsletter neste arquivo")
    ap.add_argument("--sem-paginas", action="store_true",
                    help="não abre as páginas dos anúncios para procurar prazo (mais rápido)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    rel = pipeline.executar(baixar_paginas=not args.sem_paginas)
    site.gerar()

    url_site = os.environ.get("URL_SITE", "")
    assunto, html, texto = newsletter.montar(rel, url_site)
    logging.info("%s", assunto)
    if args.previa:
        args.previa.write_text(html, encoding="utf-8")
        logging.info("prévia gravada em %s", args.previa)

    if args.sem_email:
        return
    if not os.environ.get("EMAIL_REMETENTE"):
        logging.info("e-mail desligado (sem EMAIL_REMETENTE); só o site foi atualizado")
        return
    if newsletter.tem_conteudo(rel) or os.environ.get("ENVIAR_SEMPRE") == "1":
        newsletter.enviar(assunto, html, texto)
        logging.info("e-mail enviado")
    else:
        logging.info("nada novo; e-mail não enviado")


if __name__ == "__main__":
    main()
