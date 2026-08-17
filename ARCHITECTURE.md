# Arquitetura

## Visão geral

O motor de análise (`engine/`) é puro: nenhuma linha de I/O de interface (terminal, protocolo
MCP, HTTP) mora ali. Ele expõe funções que recebem um `DataFrame` (ou um caminho de CSV) e
devolvem dataclasses tipadas — nunca imprime nada, nunca decide como o resultado chega ao
usuário. Duas camadas finas consomem esse motor:

- **`mcp_server/server.py`** — servidor MCP, interface principal.
- **`cli.py`** — entrypoint manual, fallback para quem não tem cliente MCP configurado.

As duas chamam exatamente as mesmas funções de `engine/`, na mesma ordem, com o mesmo
tratamento de erro. Isso não é só organização: é a prova de que a lógica de análise é
reutilizável e testável isoladamente, sem depender de nenhuma das duas interfaces.

## Diagrama

```
                     ┌───────────────────────────────┐
                     │      data/*.csv (datasets)      │
                     └────────────────┬─────────────────┘
                                       │
                     ┌────────────────▼─────────────────┐
                     │              engine/                │
                     │  (nenhuma lógica de negócio vive     │
                     │   fora daqui — puro, sem I/O)        │
                     │                                      │
                     │  parsing.py    CSV pt-BR → DataFrame  │
                     │                validado               │
                     │  quality.py    7 checagens genéricas  │
                     │                de qualidade de dados  │
                     │  stats_frequentist.py                 │
                     │                t pareado + Wilcoxon    │
                     │                + correção BH           │
                     │  stats_robustness.py                  │
                     │                bootstrap em bloco      │
                     │  stats_bayesian.py                    │
                     │                posterior + expected    │
                     │                loss                    │
                     │  decision.py   reconcilia as 3 camadas │
                     │                numa Decisao única      │
                     │                (divergência nunca       │
                     │                 escondida)              │
                     │  growth.py     impacto R$/dia +        │
                     │                próximo teste sugerido  │
                     │  report.py     markdown + gráfico      │
                     │  tracking.py   CSV local + Google       │
                     │                Sheets (best-effort)     │
                     └──────┬─────────────────────┬──────────┘
                            │                      │
              ┌─────────────▼───────┐   ┌──────────▼────────────┐
              │   mcp_server/        │   │   cli.py                │
              │   server.py           │   │   entrypoint manual     │
              │                       │   │                         │
              │   tools:               │   │   $ python cli.py       │
              │   - listar_datasets    │   │   $ python cli.py \     │
              │   - analisar_teste_ab  │   │       data/x.csv        │
              │   - analisar_todos_    │   │                         │
              │     os_testes_ab       │   └─────────────────────────┘
              └─────────────┬─────────┘
                            │ stdio (protocolo MCP)
              ┌─────────────▼─────────────────┐
              │  Cliente MCP                    │
              │  (Claude Code, Cursor,          │
              │   Claude Desktop, ...)          │
              │  chama as tools a partir de      │
              │  um pedido em linguagem natural  │
              └──────────────────────────────────┘
```

`cli.py` e `mcp_server/server.py` têm cada um sua própria função `processar_dataset`, mas
ambas são finas de propósito: parsing → qualidade → comparação estatística → decisão →
growth lens → relatório → tracking, na mesma ordem, chamando as mesmas funções de `engine/`.
A diferença é só a forma da resposta — texto no terminal de um lado, `dict` estruturado
(virando JSON na borda do protocolo MCP) do outro.

## Por que MCP como interface principal (e não CLI + arquivo de instruções)

A alternativa mais óbvia para dar a um agente (Claude Code, Cursor, etc.) acesso a essa
análise seria um CLI robusto acompanhado de um arquivo de instruções (`AGENTS.md`/system
prompt) explicando quando e como chamar `python cli.py` via shell e como interpretar a
saída de texto. Essa abordagem foi descartada em favor de MCP por alguns motivos concretos:

- **Contrato tipado em vez de texto solto.** As tools MCP (`analisar_teste_ab`,
  `listar_datasets`, `analisar_todos_os_testes_ab`) têm assinatura, tipos e docstring —
  o cliente sabe exatamente quais parâmetros aceitar e o formato da resposta antes de
  chamar. Com shell-out, o agente precisaria parsear stdout formatado para humano, o que
  quebra a cada mudança de mensagem de log.
- **Erros estruturados, não scraping de stderr.** Um dataset ruim devolve
  `{"ok": False, "erro": "..."}`, não um exit code para o agente interpretar às cegas.
- **Descoberta nativa.** Um cliente MCP lista as tools disponíveis e lê a instrução do
  servidor (`mcp.instructions`) automaticamente — não depende de manter um arquivo de
  instruções em sincronia manual com as flags do CLI toda vez que uma muda.
- **Sem shell no caminho.** Não há necessidade de o agente montar uma linha de comando
  (com os riscos de injeção e de escaping que isso traz) para cada chamada — a chamada é
  uma invocação de função.
- **Composição.** O agente pode chamar `listar_datasets`, decidir o que processar, e então
  chamar `analisar_teste_ab` por arquivo — em vez de um único comando monolítico ou de
  múltiplos processos de CLI encadeados via shell.

O CLI não foi removido: ele é o modo manual/fallback, garante reprodutibilidade para quem
não quiser configurar um cliente MCP, e serve como segunda cobertura de teste de ponta a
ponta do mesmo `engine/` (ver `tests/test_cli.py` e `tests/test_mcp_server.py` — os dois
exercitam o mesmo motor por caminhos diferentes).

## Setup do cliente MCP

O repositório já inclui `.mcp.json` na raiz:

```json
{
  "mcpServers": {
    "ab-cashback-decision-engine": {
      "command": "python",
      "args": ["-m", "mcp_server.server"]
    }
  }
}
```

**Claude Code** detecta `.mcp.json` automaticamente ao abrir o repositório como diretório
de trabalho — não é preciso configurar nada além de ter as dependências instaladas
(`pip install -r requirements.txt`) no `python` que o comando acima resolve.

**Cursor** lê o mesmo formato de `.mcp.json`; se não detectar automaticamente, cole o
conteúdo acima em Settings → MCP → Add new global MCP server (ou no `.cursor/mcp.json`
do projeto).

**Claude Desktop** usa um arquivo de config separado (fora do repositório), com o mesmo
formato de entrada em `mcpServers`. Adicione a mesma entrada `ab-cashback-decision-engine`
em `claude_desktop_config.json`, apontando `args` para o caminho absoluto do repositório
se o processo do Desktop não herdar o `cwd` correto (ex.:
`["-m", "mcp_server.server"]` com `cwd` explícito, ou ajuste `command` para o Python do
virtualenv do projeto).

Depois de conectado, basta pedir em linguagem natural (“roda o teste A/B do parceiro B” ou
“lista os datasets disponíveis”) — o cliente resolve para a tool certa.

## Decisões de design que valem registrar

- **Divergência entre camadas nunca é escondida.** Quando a leitura bayesiana discorda do
  veredito frequentista, `Decisao.divergencia` é preenchida com uma frase explícita e o
  relatório a expõe — a reconciliação (`decision.py`) prioriza honestidade sobre um
  veredito limpo.
- **Google Sheets é best-effort por design.** `tracking.registrar` sempre grava o CSV local
  primeiro; a escrita no Sheets roda depois, dentro de um `try/except Exception` amplo e
  deliberado — qualquer falha (biblioteca ausente, credencial ausente, rede) é logada e
  engolida, nunca derruba o pipeline.
- **Um dataset ruim não derruba os outros.** Tanto `cli.py` quanto
  `mcp_server/server.py` capturam `SchemaError`/`ParDadosInsuficientesError` por dataset e
  seguem para o próximo — o mesmo comportamento nas duas interfaces, porque a decisão de
  isolar falhas vive em `engine/`, não em cada camada.
- **Nenhuma checagem de qualidade ou parâmetro estatístico é hardcoded para um parceiro.**
  `quality.py` e `stats_*.py` recebem `DataFrame`s genéricos com colunas `grupo`/`data`/
  `comissao`/`cashback`; os 3 datasets fornecidos passam pelo mesmo código sem nenhuma
  ramificação por nome de parceiro.
