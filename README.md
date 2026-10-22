# Radar de oportunidades

Todo dia às 7h (horário de Brasília), o radar lê feeds de financiadores e agregadores, o banco de
bolsas do DAAD e as páginas de programas recorrentes. Ele filtra o que interessa a um doutorando
em ecologia + IA que busca **sanduíche e financiamento internacional**. O resultado vai para um site
com o histórico e filtros e, se você quiser, para um e-mail diário.

Não usa IA nem serviço pago: a seleção é feita por palavras-chave, com pesos editáveis, e cada item
mostra o motivo de ter aparecido.

## O que o e-mail traz (quando ligado)

- **Destaques e outras novidades:** editais vistos pela primeira vez, com o prazo quando o
  anúncio informa.
- **Prazos chegando:** lembretes de editais já enviados, a 14, 7, 3 e 1 dia do prazo.
- **Páginas que mudaram:** programas sem feed (Rufford, EDGE, Swiss Excellence, ELAP etc.) cuja
  página ganhou data nova ou mudou as frases sobre inscrição.

## Colocar no ar

1. **Repositório público no GitHub.** O GitHub Pages gratuito exige repositório público.
2. **Ative o site:** *Settings → Pages → Build and deployment → Source: GitHub Actions*.
3. **Rode a primeira vez:** *Actions → Radar diário → Run workflow*. Depois disso, ele roda sozinho
   todo dia às 7h.

O site fica em `https://SEU_USUARIO.github.io/NOME_DO_REPO/`.

### E-mail diário (opcional)

Sem os segredos abaixo, o radar só atualiza o site. Quando quiser receber a newsletter:

1. **Crie uma senha de app do Gmail.** Ela exige verificação em duas etapas ativa. Gere em
   <https://myaccount.google.com/apppasswords>. É uma senha só para o radar, que pode ser revogada
   a qualquer momento, e não é a senha da sua conta.
2. **Cadastre os segredos** em *Settings → Secrets and variables → Actions → New repository secret*:
   | Nome | Valor |
   |---|---|
   | `EMAIL_REMETENTE` | o Gmail que envia |
   | `EMAIL_SENHA_APP` | a senha de app do passo 1 |
   | `EMAIL_DESTINO` | onde receber (opcional; sem ele, vai para o remetente) |

O envio começa na execução seguinte. Nos dias sem nada novo, nenhum e-mail é enviado.

## Ajustar ao seu interesse

Tudo fica em `config/`, sem mexer em código:

- **`perfil.yaml`:** os termos e pesos de cada grupo (ecologia, IA, etapa, financiamento,
  elegibilidade), as penalidades (cidadania restrita, graduação, vaga de emprego…) e os limiares
  de inclusão e destaque. Se aparecer muito ruído, suba `limiar_inclusao`. Se faltar coisa, baixe.
- **`fontes.yaml`:** os feeds lidos. Para incluir um feed, basta nome e URL. Fontes que só publicam
  coisas do tema levam `tematica: true`. Para desligar uma sem apagar, use `ativo: false`.
- **`programas.yaml`:** os programas recorrentes. Com `monitorar: true`, a página é verificada todo
  dia. Use `false` para sites que bloqueiam robôs; eles aparecem só como link no site.

A seção "Por que apareceu", em cada item, mostra quais termos pontuaram. É o melhor guia para
calibrar.

## Rodar no seu computador

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q tests
.venv/bin/python -m radar --sem-email --previa previa.html   # gera site/dados.json e uma prévia do e-mail
.venv/bin/python -m http.server 8000 --directory site        # abre o site em http://localhost:8000
```

Rodar localmente grava em `data/`. Para não misturar com o estado do GitHub, apague `data/*.json` antes de
fazer commit.

## Limitações conhecidas

- **Vários sites bloqueiam robôs** (BES, National Geographic, WWF EFN, GBIF, WILDLABS, STRI):
  eles ficam só como links na aba *Programas recorrentes*, para checar à mão de vez em quando.
- **O prazo é procurado no texto do anúncio**, perto de palavras como *deadline* e *prazo*.
  Quando o anúncio não traz data, o item aparece como "prazo não identificado". Confira sempre o
  edital original.
- **O banco do DAAD** entra filtrado para brasileiros, doutorandos e ciências naturais ou agrárias.
  Programas do DAAD só aparecem se tiverem tema de ecologia ou IA, ou se forem de estadia curta ou
  cotutela.
- **O GitHub desativa workflows agendados** depois de 60 dias sem atividade no repositório. Se o site
  parar de atualizar, reative em *Actions*.

## Estrutura

```
config/      perfil, fontes e programas (o que você edita)
radar/       coletores.py, pontuacao.py, prazos.py, pipeline.py, newsletter.py, site.py
data/        estado entre execuções (o que já foi visto), gravado pelo próprio workflow
site/        index.html, mais o dados.json gerado a cada execução
tests/       testes do extrator de prazos, da pontuação e do monitor de páginas
```
