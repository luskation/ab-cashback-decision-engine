# Análise de Testes A/B de Cashback — Méliuz

Motor de análise de testes A/B de cashback do Méliuz. Recebe o CSV de um teste, avalia a
qualidade dos dados, compara as variantes contra a baseline e devolve uma decisão sobre qual
grupo escalar, com o racional, as ressalvas e o impacto de negócio estimado.

## A pergunta que a ferramenta responde

> "Dado esse teste A/B, qual variante de cashback devemos escalar pra 100% do tráfego?"

## Como pensei este projeto

Ao acessar o case técnico da Méliuz, não tive dúvida sobre por onde começar: primeiro explorei
os datasets, com a mentalidade de um analista de dados, buscando entender padrões antes de
propor qualquer solução. Só depois de compreender o problema a fundo comecei a pensar em como
pôr a mão na massa.

O enunciado perguntava "qual arquitetura você considera ideal?". Em vez de entregar uma CLI
acompanhada de um arquivo de instruções para uma IA seguir, expus o motor de análise como um
servidor MCP, que é o mesmo protocolo que ferramentas como Claude Code e Cursor já usam
nativamente. Sem dúvida, era a resposta mais honesta à pergunta, mas não a mais simples de
implementar. Mantive a CLI como modo manual, garantindo que a ferramenta sempre rode mesmo sem
um cliente MCP configurado.

Na análise estatística, fui além do Teste T e do Teste de Wilcoxon, os mais clássicos,
funcionais, mas cabia algo diferente. Adicionei correção para múltiplas comparações, pensando
em uma ferramenta que rodaria dezenas (talvez centenas) de testes por mês, não apenas os 3
datasets fornecidos. Além disso, apliquei bootstrap em bloco, para não depender de uma
suposição de independência entre dias que claramente não se sustentava nos dados.

Cabe destacar também que adicionei uma camada bayesiana, trocando a pergunta "isso é
estatisticamente significativo?" por "qual a chance de eu estar certo, e quanto custa errar?".
Tomei cuidado para não transformar isso em complexidade desnecessária: escolhi o modelo
bayesiano mais simples que resolvia o problema (fórmula fechada, sem simulação), e toda saída
era traduzida para português de negócio no relatório final, nunca jargão estatístico solto, que
serve apenas para fingir alto conhecimento, sem praticidade.

Eu não disse que li os CSVs linha por linha? Foi assim que identifiquei uma queda de tráfego
brusca e isolada no Grupo 2 do Parceiro C, nos últimos dias da série. Em vez de apenas relatar
a observação, generalizei-a numa checagem estatística formal via z-score, transformando um
"reparei nisso" em um achado defensável.

Para não construir algo que funcionasse apenas nos 3 datasets já conhecidos, montei um quarto
dataset sintético, nunca usado durante o teste técnico, com uma lógica diferente das três
originais, e rodei a ferramenta contra ele sem alterar uma linha de código. Foi minha forma de
provar generalização de verdade.

Quanto ao uso de IA: foi fundamental ao longo do processo. Debatendo com o Claude Code,
consegui chegar a conclusões que demandariam horas de estudo e análise em poucos minutos, além
da facilidade para corrigir código, completar espaços de digitação e me auxiliar no "por onde
começar?". As decisões, no entanto, foram sempre um fator humano! Vale destacar: com um bom uso
de IA, sendo apenas uma auxiliar e não uma muleta, ferramentas que demandariam meses podem ser
produzidas em poucos dias, com funcionalidades que humanos não pensariam de cara.

No fim, o case me comprovou que algo que enxergo é valioso: não é sobre confiar que "está tudo
certo", é sobre construir formas de checar isso de verdade. É preciso identificar
inconsistências antes que virem problema, transformar observação em checagem estruturada e usar
automação para que tarefas repetitivas gerem mais tempo pra análise.

## Decisão dos testes fornecidos

| Teste | Decisão | Racional |
|---|---|---|
| **Parceiro A** | Manter **Grupo 1** | Grupo 2 e Grupo 3 perdem margem diária (-R$ 512,96/dia e -R$ 1.526,35/dia) com significância estatística: teste t, Wilcoxon, correção de múltiplas comparações e bootstrap em bloco concordam. |
| **Parceiro B** | Manter **Grupo 1** | Grupo 2 e Grupo 3 perdem margem diária (-R$ 2.351,03/dia e -R$ 3.835,69/dia), mesma robustez nas 4 camadas estatísticas. Há aviso de desequilíbrio populacional (Grupo 1 tem 1,6x mais compradores/dia que Grupo 3); a decisão se mantém mesmo considerando essa ressalva. |
| **Parceiro C** | Manter **Grupo 1** | Grupo 2 perde -R$ 772,64/dia. Ressalvas importantes: o Grupo 2 repassa ~100% da comissão como cashback (margem próxima de zero por desenho, não por efeito do teste) e tem um colapso de volume de compradores nos últimos 5 dias da série, isolado a esse grupo. Vale investigar antes de confiar cegamente no resultado, embora a decisão não mude nem na leitura mais cética. |

Relatórios completos, com números, ressalvas e apêndice técnico: [`reports/`](reports/)

## Como rodar

A mesma lógica (`engine/`) é exposta de duas formas, nenhuma reimplementa a outra.

### Opção A: MCP (uso em linguagem natural)

O repositório já inclui `.mcp.json`. Em Claude Code, Cursor ou outro cliente MCP, abra este
repositório e peça em português, ex: *"analisa o teste A/B em `data/dataset_01_parceiroA.csv`
e me diz qual variante escalar"*. As tools disponíveis:

- `listar_datasets()`: lista os CSVs em `data/`.
- `analisar_teste_ab(caminho, ...)`: processa um dataset específico.
- `analisar_todos_os_testes_ab(...)`: processa todos os CSVs de `data/` de uma vez.

Setup detalhado por cliente (Claude Code, Cursor, Claude Desktop): [`ARCHITECTURE.md`](ARCHITECTURE.md#setup-do-cliente-mcp).

### Opção B: CLI (modo manual, sempre disponível)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt

python cli.py                                    # processa todos os CSVs em data/
python cli.py data/dataset_01_parceiroA.csv       # processa um dataset específico
python cli.py --sheet-id <ID_DA_PLANILHA>         # também escreve no Google Sheets
```

Cada execução gera, por dataset, um relatório em `reports/relatorio_<parceiro>.md` (com gráfico
embutido) e uma linha em `tracking/testes_ab.csv`.

Testes automatizados: `pytest -q`.

## Arquitetura

```
engine/          motor de análise puro, nenhuma lógica de interface aqui
  parsing.py         leitura defensiva do CSV (moeda pt-BR, linhas ruins, schema)
  quality.py         7 checagens genéricas de qualidade de dados
  stats_frequentist.py   teste t pareado + Wilcoxon + correção de múltiplas comparações
  stats_robustness.py    bootstrap em bloco (robustez à autocorrelação)
  stats_bayesian.py      posterior Student-t (prior de Jeffreys) + expected loss
  decision.py         reconcilia as 4 camadas acima num veredito único, divergência nunca escondida
  growth.py           projeção de impacto (R$) + sugestão de próximo teste
  report.py           relatório Markdown com gráfico embutido
  tracking.py         CSV local + Google Sheets (best-effort)
mcp_server/server.py   expõe o engine como tools MCP
cli.py                 entrypoint manual, chama o mesmo engine
```

`engine/` não depende de `mcp_server/` nem de `cli.py`: a mesma lógica atende os dois
consumidores sem duplicação, e processar um dataset novo nunca exige alterar código, só
apontar o caminho do arquivo. Diagrama completo e a justificativa de MCP como interface
principal: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Checagens de qualidade de dados

Todas genéricas, nenhuma tem nome de parceiro, grupo ou data fixado no código:

| Checagem | O que detecta |
|---|---|
| `checar_bug_instrumentacao` | Valores logicamente impossíveis (cashback > vendas), coluna zerada o tempo todo, ou métrica "congelada" (mesmo valor por muitos dias seguidos). |
| `checar_repasse_total_de_cashback` | Cashback aproximadamente igual à comissão na maioria dos dias: margem próxima de zero por desenho, não por efeito do teste. |
| `checar_mudanca_de_patamar` | Quebra de nível no meio da série, dentro de um único grupo. |
| `checar_pico_sincronizado` | Dias de pico simultâneo em todos os grupos: evento externo, não efeito da variante. |
| `checar_desequilibrio_populacional` | Volume médio de compradores muito diferente entre grupos do mesmo teste. |
| `checar_cobertura_de_datas` | Grupos do mesmo teste com períodos diferentes ou buracos na série. |
| `checar_colapso_de_volume_no_fim_da_serie` | Queda abrupta e sustentada de volume nos últimos dias, isolada a um grupo específico (via z-score). Achada inspecionando manualmente os 3 datasets fornecidos, não é uma checagem de livro-texto. |

## Metodologia estatística

A decisão (`veredito`: escalar, manter baseline ou sem evidência suficiente) reconcilia 4
camadas sobre a diferença diária de margem (comissão menos cashback) pareada por data entre
variante e baseline:

1. **Teste t pareado + Wilcoxon**: vencedor só se os dois concordarem, proteção barata contra
   outliers.
2. **Correção de Benjamini-Hochberg** para múltiplas comparações: a significância corrigida
   substitui a crua como base do veredito quando há mais de uma variante no mesmo teste.
3. **Bootstrap em bloco**: se o IC do bootstrap discordar da leitura do teste pareado, a
   confiança da decisão cai para "baixa", sinal de que autocorrelação temporal pode estar
   inflando o resultado.
4. **Camada bayesiana** (prior de Jeffreys, posterior Student-t, fórmula fechada, sem MCMC):
   dela saem a probabilidade de cada variante ser a melhor e a perda esperada de escalar a
   errada. Aparece no relatório como leitura de risco em linguagem de negócio, nunca com
   jargão técnico fora do apêndice. Divergência entre a leitura bayesiana e o veredito
   frequentista é sempre reportada, nunca fica implícita.

Nos 3 datasets fornecidos as 4 camadas concordaram em todos os casos.

## Growth lens

Além do veredito, o relatório inclui, quando há vencedor, a projeção de impacto diário em R$
de escalar a variante (sempre como faixa, nunca um número seco) e uma sugestão de próximo
patamar de cashback a testar, calculada a partir do histórico do próprio dataset carregado
(nunca um percentual fixo no código).

## Planilha de tracking

[Google Sheets: Testes A/B rodados](https://docs.google.com/spreadsheets/d/1EhYgAZDi0m2gAmAGJVol5i1OaTF1OIBjA-q679ilO44/edit?gid=999010554#gid=999010554)

## Stack

Python 3.10+, pandas, numpy, scipy, matplotlib, gspread + google-auth (opcionais, só para o
Sheets), mcp. Ver [`requirements.txt`](requirements.txt).
