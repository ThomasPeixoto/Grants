"""Monta e envia o e-mail diário."""
from __future__ import annotations

import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from html import escape

from .pipeline import Relatorio

TIPOS = {
    "sanduiche": "Sanduíche / estadia",
    "pesquisa": "Financiamento de pesquisa",
    "bolsa": "Bolsa / fellowship",
    "evento": "Curso / evento",
    "outro": "Outros",
    "equipamento": "Equipamento",
}
MAX_ITENS = 30
MAX_PRIMEIRA = 25

COR = {"texto": "#1f2a24", "suave": "#5d6b63", "linha": "#dfe5e1", "acento": "#1d6b4f",
       "fundo_destaque": "#eef6f1", "alerta": "#a14a12"}


def _prazo(o: dict, hoje: date) -> str:
    if o.get("prazo"):
        d = date.fromisoformat(o["prazo"])
        falta = (d - hoje).days
        quando = "hoje" if falta == 0 else "amanhã" if falta == 1 else f"em {falta} dias"
        return f"prazo {d.strftime('%d/%m/%Y')} ({quando})"
    if o.get("prazo_rotulo"):
        return f"prazo {o['prazo_rotulo']}"
    return "prazo não identificado"


def _cartao(o: dict, hoje: date) -> str:
    urgente = o.get("prazo") and (date.fromisoformat(o["prazo"]) - hoje).days <= 14
    fundo = COR["fundo_destaque"] if o.get("destaque") else "#ffffff"
    cor_prazo = COR["alerta"] if urgente else COR["suave"]
    motivos = "; ".join(m for m in o.get("motivos", []) if not m.startswith("fonte"))
    fontes = ", ".join(o.get("fontes", []))
    return f"""
<tr><td style="padding:12px 14px;border-bottom:1px solid {COR['linha']};background:{fundo}">
  <a href="{escape(o['url'])}" style="color:{COR['acento']};font-weight:600;font-size:15px;text-decoration:none">{escape(o['titulo'])}</a>
  <div style="font-size:12px;color:{cor_prazo};margin-top:3px">{TIPOS.get(o['tipo'], o['tipo'])} · {_prazo(o, hoje)} · {escape(fontes)}</div>
  <div style="font-size:13px;color:{COR['texto']};margin-top:6px;line-height:1.45">{escape(o.get('resumo', '')[:260])}{'…' if len(o.get('resumo', '')) > 260 else ''}</div>
  <div style="font-size:11px;color:{COR['suave']};margin-top:5px">Por que apareceu ({o['pontos']} pts): {escape(motivos)}</div>
</td></tr>"""


def _secao(titulo: str, corpo: str, subtitulo: str = "") -> str:
    sub = f'<div style="font-size:12px;color:{COR["suave"]};font-weight:400">{subtitulo}</div>' if subtitulo else ""
    return f"""
<tr><td style="padding:22px 14px 8px;font-size:17px;font-weight:700;color:{COR['texto']}">{titulo}{sub}</td></tr>
{corpo}"""


def montar(rel: Relatorio, url_site: str = "") -> tuple[str, str, str]:
    """Devolve (assunto, html, texto simples)."""
    hoje = rel.hoje
    novos = rel.novos[: MAX_PRIMEIRA if rel.primeira_execucao else MAX_ITENS]
    destaques = [o for o in novos if o["destaque"]]
    demais = [o for o in novos if not o["destaque"]]

    partes = []
    if rel.primeira_execucao:
        partes.append(f'<tr><td style="padding:14px;font-size:13px;color:{COR["texto"]}">'
                      f"Primeira execução: este é o retrato inicial, com as {len(novos)} oportunidades mais "
                      f"relevantes entre {len(rel.novos)} encontradas. A partir de amanhã chega só o que for novo."
                      "</td></tr>")
    if destaques:
        partes.append(_secao("Destaques", "".join(_cartao(o, hoje) for o in destaques)))
    if rel.prazos_proximos:
        partes.append(_secao("Prazos chegando", "".join(_cartao(o, hoje) for o in rel.prazos_proximos),
                             "Lembrete de oportunidades já enviadas que fecham em 14, 7, 3 ou 1 dia"))
    if rel.paginas_mudaram:
        linhas = []
        for p in rel.paginas_mudaram:
            extra = f" · prazo encontrado: {date.fromisoformat(p['prazo']).strftime('%d/%m/%Y')}" if p.get("prazo") else ""
            datas = ", ".join(date.fromisoformat(d).strftime("%d/%m/%Y") for d in p["datas_novas"][:4])
            datas = f" · datas novas: {datas}" if datas else ""
            linhas.append(f"""
<tr><td style="padding:10px 14px;border-bottom:1px solid {COR['linha']}">
  <a href="{escape(p['url'])}" style="color:{COR['acento']};font-weight:600;text-decoration:none">{escape(p['nome'])}</a>
  <div style="font-size:12px;color:{COR['suave']};margin-top:3px">{escape(p.get('nota', ''))}{extra}{datas}</div>
</td></tr>""")
        partes.append(_secao("Páginas de programas que mudaram", "".join(linhas),
                             "A página mudou nas datas ou nas frases sobre inscrição; vale conferir"))
    if demais:
        partes.append(_secao("Outras novidades", "".join(_cartao(o, hoje) for o in demais)))

    quebradas = [n for n, s in rel.fontes.items() if s["status"] != "ok"]
    rodape = f"{len(rel.fontes) - len(quebradas)} de {len(rel.fontes)} fontes responderam hoje."
    if quebradas:
        rodape += " Sem resposta: " + ", ".join(quebradas) + "."
    if url_site:
        rodape += f' <a href="{escape(url_site)}" style="color:{COR["acento"]}">Abrir o radar completo</a>.'

    n_total = len(rel.novos)
    assunto = f"Radar de oportunidades · {hoje.strftime('%d/%m')} · "
    assunto += f"{n_total} nova{'s' if n_total != 1 else ''}" if n_total else "sem novidades"
    if destaques:
        assunto += f", {len(destaques)} em destaque"
    if rel.prazos_proximos:
        assunto += f" · {len(rel.prazos_proximos)} prazo{'s' if len(rel.prazos_proximos) > 1 else ''} chegando"

    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="margin:0;background:#f4f6f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f5"><tr><td align="center" style="padding:16px 8px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border:1px solid {COR['linha']};border-radius:8px">
<tr><td style="padding:18px 14px 4px;font-size:20px;font-weight:700;color:{COR['texto']}">Radar de oportunidades</td></tr>
<tr><td style="padding:0 14px 6px;font-size:12px;color:{COR['suave']}">{hoje.strftime('%d/%m/%Y')} · ecologia + IA · sanduíche e financiamento internacional</td></tr>
{''.join(partes) or f'<tr><td style="padding:14px;color:{COR["suave"]}">Nada novo hoje.</td></tr>'}
<tr><td style="padding:16px 14px;font-size:11px;color:{COR['suave']}">{rodape}</td></tr>
</table></td></tr></table></body></html>"""

    linhas_txt = [assunto, ""]
    for o in novos + rel.prazos_proximos:
        linhas_txt += [o["titulo"], f"  {_prazo(o, hoje)} · {', '.join(o['fontes'])}", f"  {o['url']}", ""]
    for p in rel.paginas_mudaram:
        linhas_txt += [f"[página mudou] {p['nome']}", f"  {p['url']}", ""]
    return assunto, html, "\n".join(linhas_txt)


def tem_conteudo(rel: Relatorio) -> bool:
    return bool(rel.novos or rel.prazos_proximos or rel.paginas_mudaram)


def enviar(assunto: str, html: str, texto: str) -> None:
    """Envia pelo SMTP do Gmail. Lê tudo de variáveis de ambiente (segredos do GitHub)."""
    remetente = os.environ["EMAIL_REMETENTE"]
    senha = os.environ["EMAIL_SENHA_APP"]
    destino = os.environ.get("EMAIL_DESTINO") or remetente
    servidor = os.environ.get("SMTP_SERVIDOR", "smtp.gmail.com")
    porta = int(os.environ.get("SMTP_PORTA", "465"))

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, f"Radar de oportunidades <{remetente}>", destino
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(servidor, porta, context=ssl.create_default_context(), timeout=60) as s:
        s.login(remetente, senha)
        s.send_message(msg)
