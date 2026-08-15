# Plano de construção — Análise de Testes A/B de Cashback (Méliuz)

> Documento-guia para alimentar o Claude Code (VS Code) na construção do repositório novo.
> Cada decisão de escopo está classificada por nível de prioridade e justificada com base no
> texto do teste técnico — não é uma lista de "ideias legais", é uma lista com motivo e risco
> explícitos para cada item, para que decisões sob pressão de prazo não precisem ser reinventadas.
> Não é o README final — o README é escrito por último, descrevendo o que de fato foi construído.

---

## 0. Os dois critérios de avaliação (texto literal do enunciado)

> "Esse teste avalia duas capacidades simultaneamente:
> - Capacidade de construção: arquitetar uma solução reutilizável, parametrizada, robusta a dados ruins.
> - Capacidade analítica: ler dados de teste A/B com olho crítico, identificar problemas, e tomar decisão acionável."

Toda decisão de escopo na seção 2 é avaliada contra essas duas frases. Se uma decisão não reforça
nenhuma das duas, ela é luxo, não prioridade — e some do plano ou vira Nível 3 explicitamente marcado.

## 1. Sistema de priorização

- **Nível 1 — exigência literal do enunciado.** Sem isso, a entrega está incompleta, independente de qualidade.
- **Nível 2 — inferido de frase explícita do enunciado.** Risco baixo, ancorado em texto real, não é aposta.
- **Nível 3 — diferenciação por iniciativa própria.** Não pedida, maior risco (técnico e/ou de comunicação).
  Primeira coisa a cortar se o prazo apertar. Cada item de Nível 3 tem justificativa própria — nunca
  "porque é impressionante", sempre porque resolve algo específico.

**Regra de engenharia derivada disso:** nenhuma fase de Nível 1 ou 2 pode depender de uma fase de
Nível 3 existir. `decision.py` (seção 2.9) é desenhado para funcionar só com o resultado frequentista
(Nível 1) e incorporar bootstrap/bayesiano/correção múltipla (Nível 3) *se* estiverem presentes — nunca
como dependência obrigatória. Isso é o que torna o corte de emergência (seção 5) seguro.

---

## 2. Decisões, uma a uma — nível, motivo, risco

### 2.1 Motor de análise (`engine/`) desacoplado de interface — **Nível 1**
- Motivo: "solução reutilizável, parametrizada" é texto literal do critério de construção. Sem separar
  lógica de interface, não tem como provar reutilização sem duplicar código.
- Risco se cortado: não é cortável — é a exigência central do teste inteiro.

### 2.2 Parsing defensivo (moeda pt-BR, linhas ruins, schema) — **Nível 1**
- Motivo: "robusta a dados ruins" é texto literal.
- Risco se cortado: não é cortável.

### 2.3 CLI (`cli.py`) — **Nível 1**
- Motivo: é o modo de execução mínimo garantido — "processa os 3 datasets sem alteração de código"
  precisa funcionar mesmo que nenhuma interface mais sofisticada exista.
- Risco se cortado: não é cortável — é o fallback de tudo o mais nesta lista.

### 2.4 Seis checagens de qualidade (5 originais + colapso de volume) — **Nível 2**
- Motivo: ancorado em "robusta a dados ruins" (construção) *e* "identificar problemas" (analítica) —
  as duas frases de avaliação ao mesmo tempo.
- A 6ª (colapso de volume isolado por grupo, achada no Grupo 2 do Parceiro C: 122→130→41→58→57→26→27
  compradores nos últimos dias, sem mudança de % cashback, e ausente no Grupo 1 do mesmo parceiro e em
  A/B) tem motivo extra: é evidência **verificável pelo próprio avaliador** de leitura manual dos dados,
  não de rodar um pipeline genérico.
- Risco se cortado: perde a evidência mais direta e conferível de capacidade analítica.
- Risco se mal implementada: qualquer checagem com nome de parceiro/grupo hardcoded vira o oposto do
  que o enunciado pede — "Nunca hardcode nomes de parceiro... a ferramenta já é genérica".

### 2.5 Estatística baseline: t pareado + Wilcoxon — **Nível 1**
- Motivo: é o método mínimo necessário para responder à pergunta central do enunciado
  ("qual variante escalar pra 100%"). Sem alguma comparação estatística, não existe "decisão acionável".
- Risco se cortado: não é cortável.

### 2.6 Gráficos embutidos no relatório — **Nível 2**
- Motivo: ancorado literalmente em "precisa ser apresentável para um gestor".
- Risco se cortado: relatório fica só texto/tabela — atende a letra do enunciado, fraco no espírito dele.
- Risco se mal implementado: gráfico com estilo default do matplotlib (grade cinza, cores aleatórias)
  comunica o oposto de "profissional" — exige atenção a rótulos, cores e limpeza visual, não é
  só "chamar `plt.plot()`".

### 2.7 Growth lens (impacto projetado em R$ + sugestão de próximo teste) — **Nível 2**
- Motivo: ancorado em "pensamento de growth" (descrição da vaga) e "decisão acionável" (critério de avaliação).
- Risco se cortado: decisão fica só binária ("escale ou não"), sem contextualizar tamanho de impacto.
- Risco se mal implementado: projeção de impacto sem intervalo de incerteza (só um número seco) soa como
  promessa exagerada — sempre reportar como faixa (ex: "R$X a R$Y por dia"), nunca um valor único.

### 2.8 Escrita direta no Google Sheets via API — **Nível 2**
- Motivo: o enunciado chama isso **literalmente de "diferencial"** — não é inferência.
- Risco se cortado: nenhum crítico — CSV é "o mínimo aceito", também texto literal do enunciado.
- Risco se mal implementado: se a escrita no Sheets falhar (rede, permissão) e travar o pipeline, isso é
  pior do que não ter Sheets — por isso é *best-effort*: loga erro, mas o CSV local sempre é gravado antes.

### 2.9 `decision.py` — reconciliação em camadas opcionais — **Nível 1** (o encaixe é obrigatório;
      o que ele reconcilia depende de quais camadas de Nível 3 abaixo existirem)
- Motivo: é o módulo que garante a regra de engenharia da seção 1 — funciona só com o resultado
  frequentista, e incorpora as camadas extras (2.10 a 2.12) se estiverem presentes.
- Risco se mal implementado: se depender rigidamente de todas as camadas existirem, um corte de
  emergência em qualquer uma delas quebra o pipeline inteiro — por isso este módulo é Nível 1 mesmo
  reconciliando itens de Nível 3.

### 2.10 Correção de múltiplas comparações (Benjamini-Hochberg) — **Nível 3**
- Motivo: não pedido no enunciado. Justificativa própria: o contexto descrito é "dezenas de testes por
  mês" — nesse volume, não corrigir infla a taxa de falso positivo ao longo do tempo. Para os 3 datasets
  isolados fornecidos, o ganho é teórico, não visível.
- Risco se cortado: nenhum para os 3 datasets fornecidos isoladamente.
- Risco se mal implementado: baixo — fórmula bem definida, fácil de testar unitariamente.
- **Prioridade de corte: 1º item a cair** dentro do Nível 3 — é o de menor "prova visível" no relatório
  final (o efeito é sutil, aparece como número ligeiramente diferente, não como funcionalidade nova).

### 2.11 Bootstrap em bloco (robustez à autocorrelação) — **Nível 3**
- Motivo: não pedido. Justificativa própria: os dados diários têm autocorrelação visível (o Parceiro A
  tem um pico sincronizado de 4 dias) — o teste pareado assume independência, suposição frágil aqui.
- Risco se cortado: a análise continua válida (é o que o projeto original já fazia), só menos rigorosa.
- Risco se mal implementado: médio — blocos pequenos demais ou poucas reamostragens dão resultado
  instável e viram motivo de dúvida em vez de confiança.
- **Prioridade de corte: 2º item a cair.**

### 2.12 Camada bayesiana + expected loss (prior de Jeffreys → posterior Student-t) — **Nível 3, maior risco do plano**
- Motivo: não pedido. Justificativa própria: reformula "é significativo?" para "qual a chance de acerto
  e quanto custa errar?" — mais alinhado à pergunta central ("qual variante escalar"), que é uma decisão,
  não um teste de hipótese.
- **Modelo (corrigido e validado contra dados reais durante o planejamento, script reproduzível abaixo)**:
  seja `d` o vetor de diferenças diárias de margem
  pareada (variante − baseline), `n = len(d)`, `d̄ = média(d)`, `s = desvio-padrão amostral(d)`,
  `se = s / √n`. Sob o **prior de referência de Jeffreys** para média e variância desconhecidas de uma
  normal (a mesma suposição de normalidade que o teste t pareado já faz — nenhuma suposição nova), a
  posterior marginal da diferença média real `μ` é:

  ```
  μ | dados  ~  Student-t(df = n − 1, loc = d̄, scale = se)
  ```

  Isso é fórmula fechada — `scipy.stats.t(df=n-1, loc=d_mean, scale=se)` — sem MCMC, sem PyMC. Dessa
  posterior calcula-se:
  - `P(μ > 0 | dados)` — via CDF direto: `1 - posterior.cdf(0)`.
  - Intervalo de credibilidade 95% — via `posterior.interval(0.95)` (**numericamente igual ao IC do teste
    t frequentista** — validado abaixo; a diferença está na interpretação, não na conta).
  - *Expected loss* — via amostragem direta da posterior conhecida (não é MCMC, é `posterior.rvs(size=200_000)`,
    instantâneo e sem risco de não-convergência):
    `perda_de_escalar = média(max(0, −amostras))`, `perda_de_manter = média(max(0, amostras))`.
  - **Validação real** (Parceiro A, Grupo 2 vs Grupo 1, janela pré-mudança-de-patamar, n=53 dias):
    IC bayesiano `(-1119.59, -443.05)` bateu exatamente com o IC do teste t; P(Grupo 2 pior) ≈ 100%;
    perda esperada de escalar = R$ 781,71/dia; perda esperada de manter baseline = R$ 0,00/dia.
- Risco se cortado: nenhum tecnicamente — t pareado + Wilcoxon já respondem à pergunta central sozinhos.
- **Risco se mal implementado — o mais sério do plano inteiro**: se aparecer no relatório em linguagem
  técnica ("probabilidade posterior", "expected loss") sem tradução em português de negócio, ela **viola
  diretamente** a exigência explícita de "apresentável para um gestor". Nesse caso a adição piora a nota
  em vez de melhorar.
- **Mitigação obrigatória, não opcional**: toda saída bayesiana no corpo principal do relatório vem como
  frase de negócio — ex. *"há 100% de chance de o Grupo 2 ser pior; se escalássemos por engano, a perda
  esperada seria de R$781,71/dia"*. Jargão técnico (posterior, prior, expected loss) só no apêndice técnico.
- **Prioridade de corte: 1º item a cair do projeto inteiro** se o prazo apertar de verdade — maior custo
  de implementação e maior risco de comunicação, para a menor exigência literal atendida.

### 2.13 Servidor MCP local + CLI como fallback — **Nível 3**
- Motivo: o enunciado pede explicitamente "Como você estrutura isso por dentro é decisão sua... queremos
  ver qual arquitetura você considera ideal" — pede julgamento arquitetural, não uma arquitetura específica.
- Por que MCP e não só CLI+AGENTS.md: é a forma nativa dos clientes citados no enunciado (Claude Code,
  Cursor, GPT, Gemini) chamarem ferramentas — mais alinhado ao "como você estrutura" do que um wrapper de
  instruções em Markdown (caminho mais óbvio, provável escolha da maioria dos candidatos).
- Risco se cortado: nenhum — a CLI (2.3, Nível 1) já atende sozinha a exigência de "roda os 3 datasets
  sem mudar código".
- Risco se mal implementado: um avaliador sem cliente MCP configurado pode não testar ao vivo — mitigado
  por a CLI nunca depender do MCP para funcionar.
- **Prioridade de corte: 3º item a cair.** Se cortado, documentar a decisão de MCP como "considerada,
  não implementada por prazo" no `ARCHITECTURE.md` — ainda demonstra o julgamento arquitetural pedido,
  só não a execução.

---

## 3. Estrutura de pastas

```
ab-cashback-decision-engine/
├── engine/
│   ├── __init__.py
│   ├── parsing.py             # 2.2 — Nível 1
│   ├── quality.py             # 2.4 — Nível 2 (inclui a 6ª checagem)
│   ├── stats_frequentist.py   # 2.5 — Nível 1 (t pareado + Wilcoxon)
│   │                          #   + 2.10 — Nível 3 (correção múltipla, isolada em função própria)
│   ├── stats_robustness.py    # 2.11 — Nível 3 (bootstrap em bloco)
│   ├── stats_bayesian.py      # 2.12 — Nível 3 (Jeffreys → posterior Student-t + expected loss)
│   ├── decision.py            # 2.9 — Nível 1 (reconcilia o que estiver disponível)
│   ├── growth.py              # 2.7 — Nível 2
│   ├── report.py              # 2.6 — Nível 2 (markdown + gráfico embutido)
│   └── tracking.py            # 2.8 — Nível 2 (CSV sempre Nível 1; Sheets é a parte Nível 2)
├── mcp_server/
│   └── server.py              # 2.13 — Nível 3
├── cli.py                     # 2.3 — Nível 1
├── tests/
│   ├── test_parsing.py
│   ├── test_quality.py
│   ├── test_stats_frequentist.py
│   ├── test_stats_robustness.py
│   ├── test_stats_bayesian.py
│   ├── test_decision.py
│   └── fixtures/               # CSVs sintéticos: schema errado, moeda quebrada, coluna espelhada, etc.
├── data/                       # os 3 datasets fornecidos, não alterar
├── reports/                    # relatórios .md + gráficos .png gerados
├── tracking/                   # testes_ab.csv
├── requirements.txt
├── README.md
├── ARCHITECTURE.md             # diagrama + justificativa do MCP + registro do que foi cortado, se algo for
└── .mcp.json                   # config pra Claude Code/Cursor conectarem no servidor MCP
```

---

## 4. Fases de construção, com commits sugeridos

Convenção: [Conventional Commits](https://www.conventionalcommits.org/) com **prefixo em inglês**
(`feat`, `fix`, `test`, `docs`, `chore`) e **mensagem em português**. Cada commit deixa o repositório
num estado que roda. **A ordem abaixo entrega Nível 1 e 2 completos antes de qualquer item de Nível 3**
— se o prazo estourar em qualquer ponto a partir da Fase 9, o que já existe é uma entrega completa e
coerente por si só.

### Bloco A — Nível 1 e 2: motor essencial (semana 1)

**Fase 1 — Scaffold** *(2.1)*
- Commit: `chore: estrutura inicial do projeto e dependências`

**Fase 2 — Parsing defensivo** *(2.2)*
- Commit 1: `feat(engine): parsing defensivo de CSV para moeda pt-BR e linhas malformadas`
- Commit 2: `test(engine): casos de borda do parsing (duplicatas, negativos, schema inválido)`

**Fase 3 — Checagens de qualidade (5 originais)** *(2.4)*
- Commit 1: `feat(engine): checagens genéricas de qualidade de dados (bug de instrumentação, mudança de patamar, desequilíbrio de população)`
- Commit 2: `test(engine): checagens de qualidade contra fixtures sintéticas`

**Fase 3.1 — 6ª checagem: colapso de volume no fim da série** *(2.4)*
- O quê: checagem **estatística, não número mágico** — calcula o z-score da média de `compradores` dos
  últimos *k* dias (parametrizável, ex. últimos 10% da série) contra a média e o desvio-padrão do
  restante da série; sinaliza se passar de um limiar (ex. -2 desvios) **e** a queda não for replicada
  nos demais grupos do mesmo teste no mesmo período (o que descartaria evento externo/sazonalidade, já
  coberto pela checagem de picos simultâneos). Nenhum limiar foi calibrado pra bater com o Parceiro C
  especificamente — é a mesma regra estatística que dispararia em qualquer dataset com esse padrão
  (prova disso na Fase 9.1, com dado sintético nunca visto). Sem hardcode de parceiro/grupo.
- Commit 1: `feat(engine): checagem de colapso de volume no fim da série, isolado por grupo (via z-score)`
- Commit 2: `test(engine): checagem de colapso de volume contra fixture baseada no padrão do Parceiro C`

**Fase 4 — Estatística baseline** *(2.5)*
- Commit: `feat(engine): motor de comparação pareada (teste t + Wilcoxon)`

**Fase 5 — Decisão (versão mínima, só frequentista)** *(2.9)*
- O quê: `decision.py` já funcional só com o resultado da Fase 4 — decide baseado em t+Wilcoxon
  concordando, expõe uma interface pronta para receber camadas extras depois, sem exigir que existam.
- Commit: `feat(engine): decisão baseada no resultado frequentista, com interface aberta a camadas extras`

**Fase 6 — Growth lens** *(2.7)*
- O quê: a sugestão de próximo teste tem que ser **calculada a partir do dataset carregado**, nunca texto
  pronto — ex: "maior % de cashback já testado neste histórico foi X%, considerar testar acima disso" é
  uma regra que lê o dado; "considerar testar acima de 5%" fixo no código é hardcoding disfarçado de
  insight e não pode sobreviver à Fase 9.1.
- Commit: `feat(engine): projeção de impacto de growth e sugestão de próximo teste`

**Fase 7 — Relatório com gráfico** *(2.6)*
- O quê: gerador de markdown apresentável a gestor (decisão em uma frase no topo → gráfico → racional →
  ressalvas → apêndice técnico), gráfico de margem diária por grupo em PNG embutido.
- Commit 1: `feat(report): gerador de relatório markdown para gestor`
- Commit 2: `feat(report): gráfico de margem diária por grupo embutido no relatório`

**Fase 8 — Tracking** *(2.8)*
- Commit: `feat(tracking): escrita em CSV local e Google Sheets (best-effort)`

**Fase 9 — CLI + testes ponta a ponta contra os 3 datasets** *(2.3)*
- Commit 1: `feat(cli): entrypoint manual reaproveitando o motor compartilhado`
- Commit 2: `test: execução ponta a ponta contra os 3 datasets fornecidos`

**Fase 9.1 — Prova de generalização: dataset sintético nunca visto** *(2.4 — mitigação direta do risco
de overfitting aos 3 datasets fornecidos)*
- O quê: construir um **4º dataset sintético** (`tests/fixtures/dataset_04_sintetico.csv`), com schema
  idêntico mas números, parceiro, datas, número de grupos e até uma armadilha diferentes das 3 já vistas
  — gerado *depois* de todo o motor estar pronto, sem ajustar nenhum limiar/checagem pra ele passar.
  Rodar o pipeline completo (CLI, e depois MCP se a Fase 14 existir) sem alteração de código nenhuma e
  conferir que o relatório sai coerente. Este dataset **não é um dos "testes analisados"** do enunciado —
  é evidência de engenharia, mora em `tests/fixtures/`, não em `data/` nem em `reports/` como entregável
  oficial (mas pode ser citado no README como prova de generalização).
- Se alguma checagem ou regra falhar em generalizar (ex: threshold que só funcionava por coincidência
  nos 3 datasets originais), **este é o momento de corrigir** — antes de entregar, não depois.
- Commit 1: `test(fixtures): dataset sintético não fornecido, com schema válido e armadilha inédita`
- Commit 2: `test: execução ponta a ponta contra o dataset sintético, sem alteração de código`

> **Checkpoint do Bloco A: entrega completa e coerente por si só.** Tudo abaixo (Bloco B) é Nível 3 —
> soma valor, mas nada aqui depende disso para estar pronto.

### Bloco B — Nível 3: diferenciação (semana 2, na ordem inversa de prioridade de corte)

**Fase 10 — Correção de múltiplas comparações** *(2.10)*
- Commit: `feat(engine): correção de Benjamini-Hochberg para múltiplas comparações`

**Fase 11 — Bootstrap em bloco** *(2.11)*
- Commit 1: `feat(engine): bootstrap em bloco para intervalos robustos à autocorrelação`
- Commit 2: `test(engine): bootstrap contra séries sintéticas com correlação conhecida`

**Fase 12 — Camada bayesiana** *(2.12 — fórmulas e exemplo validado com dados reais na seção 2.12)*
- Commit 1: `feat(engine): posterior Student-t (prior de Jeffreys) para diferenças de margem pareadas`
- Commit 2: `feat(engine): probabilidade posterior de vitória e expected loss por variante`
- Commit 3: `test(engine): saídas do modelo bayesiano contra dados sintéticos de efeito conhecido e contra o teste t (IC deve coincidir)`
- Commit 4: `feat(report): tradução das saídas bayesianas em linguagem de negócio no relatório principal`
  *(commit obrigatório — ver mitigação em 2.12, nunca pular)*

**Fase 13 — Reconciliação completa** *(2.9, versão final)*
- O quê: `decision.py` passa a incorporar as três camadas extras quando presentes, reportando
  divergência entre frequentista e bayesiano explicitamente quando ocorrer.
- Commit: `feat(engine): reconciliação completa entre camadas frequentista, robustez e bayesiana`

**Fase 14 — Servidor MCP** *(2.13)*
- Commit 1: `feat(mcp): expõe o motor de análise como tools MCP`
- Commit 2: `test: execução ponta a ponta via MCP contra os 3 datasets`

**Fase 15 — Documentação final**
- Commit: `docs: README, justificativa de arquitetura e instruções de setup do MCP`

**Fase 16 — Polimento final**
- Commit: `chore: polimento final e entregáveis gerados`

---

## 5. Plano de corte de emergência

Se o prazo apertar, cortar **nesta ordem exata** (a mais cara e arriscada primeiro, a mais barata e
segura por último) — cada corte é uma fase inteira, nunca deixar uma fase pela metade:

1. Camada bayesiana (Fase 12) — maior custo, maior risco de comunicação.
2. Servidor MCP (Fase 14) — documentar como "considerado, não implementado" no `ARCHITECTURE.md`.
3. Bootstrap em bloco (Fase 11).
4. Correção de múltiplas comparações (Fase 10).

O Bloco A nunca é cortado — é a entrega mínima completa que já atende os dois critérios de avaliação.

---

## 6. Esqueleto do README (conteúdo final vem depois de tudo pronto)

1. **Título + uma frase de propósito** — tom direto, sem badges/emoji em excesso.
2. **A pergunta que a ferramenta responde** — mantém a pergunta central do enunciado.
3. **Como rodar** — dois caminhos: (a) conectar como MCP em Claude Code/Cursor e pedir em linguagem
   natural *(se a Fase 14 foi implementada)*; (b) CLI manual, um comando (sempre disponível).
4. **Arquitetura** — diagrama simples do `engine/` servindo `mcp_server/` e `cli.py`; link pro
   `ARCHITECTURE.md`, incluindo registro de qualquer corte de emergência aplicado.
5. **Checagens de qualidade de dados** — as 6 checagens genéricas, com destaque pra 6ª (colapso de
   volume isolado por grupo) e a nota de que foi achada inspecionando os CSVs manualmente.
6. **Metodologia estatística** — em linguagem de gestor: o que cada camada implementada resolve, e
   como o relatório trata divergência entre elas quando mais de uma camada existir.
7. **Growth lens** — o que a ferramenta sugere além da decisão binária.
8. **Resultados dos 3 testes fornecidos** — tabela-resumo.
9. **Limitações** — o que a ferramenta não cobre, dito com todas as letras.
10. **Planilha de tracking** — link.
11. **Nota breve sobre o processo de construção** — uso de IA como par de programação, sem exagero
    nem esconder.

---

## 7. Checklist final antes de enviar

- [ ] Repositório novo está público (testado em janela anônima)
- [ ] Repositório antigo está privado
- [ ] Planilha de tracking é nova, pública (leitura), com as 3 linhas preenchidas
- [ ] Os 3 datasets processados sem alteração de código entre eles
- [ ] `README.md` explica como rodar (via MCP se implementado, e sempre via CLI)
- [ ] Testes automatizados rodam (`pytest`) e cobrem casos de dado ruim
- [ ] Relatórios dos 3 testes estão em `reports/`, revisados manualmente por você antes de enviar
- [ ] Se a camada bayesiana foi implementada: toda saída dela no relatório principal está em
      linguagem de negócio, sem jargão técnico fora do apêndice
- [ ] Se algum item de Nível 3 foi cortado: está registrado no `ARCHITECTURE.md`, não simplesmente ausente sem explicação
- [ ] Nenhuma credencial (Google Sheets, etc.) commitada
- [ ] Pipeline rodou sem alteração de código contra o dataset sintético da Fase 9.1 (prova de generalização)
