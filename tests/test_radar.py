from datetime import date
from pathlib import Path

import yaml

from radar.coletores import assinatura_da_pagina, normalizar_url
from radar.pipeline import chave_titulo
from radar.pontuacao import Pontuador, classificar_tipo
from radar.prazos import extrair_prazo

HOJE = date(2026, 10, 22)
PERFIL = yaml.safe_load((Path(__file__).parent.parent / "config" / "perfil.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- prazos

def test_prazo_formatos_em_ingles():
    assert extrair_prazo("Deadline: 30 October 2026", HOJE)[0] == date(2026, 10, 30)
    assert extrair_prazo("Applications close on November 15, 2026.", HOJE)[0] == date(2026, 11, 15)
    assert extrair_prazo("deadline 1st Dec 2026", HOJE)[0] == date(2026, 12, 1)
    assert extrair_prazo("Closing date: 2027-01-15", HOJE)[0] == date(2027, 1, 15)


def test_prazo_formatos_em_portugues_e_daad():
    assert extrair_prazo("Inscrições até 5 de dezembro de 2026", HOJE)[0] == date(2026, 12, 5)
    assert extrair_prazo("Prazo: 10/11/2026", HOJE)[0] == date(2026, 11, 10)
    assert extrair_prazo("Deadline: 16.11.2026 Selection in 2027", HOJE)[0] == date(2026, 11, 16)


def test_prazo_ignora_datas_passadas_e_sem_gatilho():
    # Data passada perto de "deadline" não conta; a data futura sem gatilho também não.
    assert extrair_prazo("Deadline: 3 September 2026. Event on 5 May 2027.", HOJE) == (None, "")


def test_prazo_escolhe_a_mais_proxima():
    texto = "Stage 1 deadline: 12 November 2026. Stage 2 deadline: 20 January 2027."
    assert extrair_prazo(texto, HOJE)[0] == date(2026, 11, 12)


def test_prazo_continuo():
    assert extrair_prazo("Applications are accepted on a rolling basis.", HOJE) == (None, "contínuo")


# ---------------------------------------------------------------- pontuação

def test_pontua_sanduiche_em_ecologia_com_ia():
    p = Pontuador(PERFIL)
    r = p.pontuar("Visiting PhD fellowship in marine ecology and machine learning, "
                  "open to applicants from Latin America")
    assert r.aceito and r.destaque
    assert {"ecologia", "ia", "etapa", "elegibilidade"} <= r.grupos


def test_rejeita_fora_do_tema():
    r = Pontuador(PERFIL).pontuar("PhD scholarship in corporate finance and accounting")
    assert not r.aceito


def test_fonte_tematica_dispensa_tema():
    r = Pontuador(PERFIL).pontuar("Small grants for PhD students, apply now", bonus=3, tematica=True)
    assert r.aceito


def test_penaliza_restricao_de_cidadania():
    p = Pontuador(PERFIL)
    texto = "Research grants for PhD students in ecology and conservation"
    assert p.pontuar(texto + ". Open to US citizens only.").pontos < p.pontuar(texto).pontos


def test_mestrado_e_doutorado_nao_penaliza():
    p = Pontuador(PERFIL)
    r = p.pontuar("Scholarships for master's degree and PhD students in ecology")
    assert not any("mestrado" in m for m in r.motivos)


def test_titulo_precisa_parecer_chamada():
    p = Pontuador(PERFIL)
    assert p.parece_chamada("Rufford Small Grants 2027")
    assert p.parece_chamada("Call for Proposals: Blue Charter Incubator")
    assert not p.parece_chamada("Sharks at your service: trevally fish risk it all")
    assert not p.parece_chamada("Podcast | Inside Operation Wallacea")
    assert not p.parece_chamada("The winner of the Ocean Storytelling Film Grant is announced!")


def test_tipo():
    assert classificar_tipo("Short-term research stay for doctoral candidates") == "sanduiche"
    assert classificar_tipo("Small grants for fieldwork") == "pesquisa"
    assert classificar_tipo("Summer school on biodiversity") == "evento"


# ---------------------------------------------------------------- deduplicação e monitor

def test_mesmo_edital_em_agregadores_diferentes():
    assert chave_titulo("Rufford Small Grants 2026 – Apply Now") == chave_titulo("Rufford Small Grants (2027)")


def test_normaliza_url():
    assert (normalizar_url("https://www.Exemplo.org/bolsa/?utm_source=x&id=3#topo")
            == normalizar_url("https://exemplo.org/bolsa?id=3"))


def test_assinatura_ignora_ruido_e_datas_passadas():
    base = "Menu Home. Applications are now open. Deadline: 15 January 2027."
    a = assinatura_da_pagina(base + " Featured project, 2 Jul 2025. Visitors: 120", HOJE)
    b = assinatura_da_pagina(base + " Featured project, 11 Aug 2025. Visitors: 999", HOJE)
    c = assinatura_da_pagina(base.replace("15 January", "15 March"), HOJE)
    assert a == b
    assert a != c
    assert a[0] == ["2027-01-15"]
