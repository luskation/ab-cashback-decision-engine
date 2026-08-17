from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from engine.decision import Decisao, decidir_todos
from engine.growth import GrowthLens, growth_lens
from engine.parsing import SchemaError, carregar_csv
from engine.quality import avaliar_qualidade
from engine.report import gerar_relatorio_completo
from engine.stats_bayesian import posterior_todos_os_grupos
from engine.stats_frequentist import (
    ParDadosInsuficientesError,
    comparar_todos_os_grupos,
    corrigir_multiplas_comparacoes,
)
from engine.stats_robustness import bootstrap_todos_os_grupos
from engine.tracking import registrar

DATA_DIR_PADRAO = Path("data")
REPORTS_DIR_PADRAO = Path("reports")
TRACKING_CSV_PADRAO = Path("tracking/testes_ab.csv")

mcp = FastMCP(
    "ab-cashback-decision-engine",
    instructions=(
        "Motor de análise de testes A/B de cashback do Méliuz. Responde à pergunta central "
        "'qual variante escalar?' a partir de um CSV de teste — qualidade de dados, comparação "
        "estatística pareada, decisão e growth lens (impacto projetado + próximo teste sugerido). "
        "Reaproveita o mesmo motor (engine/) que a CLI (cli.py) usa; se este servidor não estiver "
        "disponível no seu cliente, `python cli.py` faz o mesmo processamento pela linha de comando."
    ),
)


def _listar_csvs(diretorio: Path = DATA_DIR_PADRAO) -> list[Path]:
    if not diretorio.exists():
        return []
    return sorted(diretorio.glob("*.csv"))


def _decisao_para_dict(decisao: Decisao, lente: GrowthLens) -> dict:
    projecao = lente.projecao_impacto
    return {
        "parceiro": decisao.parceiro,
        "grupo_baseline": decisao.grupo_baseline,
        "grupo_variante": decisao.grupo_variante,
        "veredito": decisao.veredito,
        "confianca": decisao.confianca,
        "media_diferenca": decisao.media_diferenca,
        "ic95_diferenca": list(decisao.ic95_diferenca),
        "justificativa": decisao.justificativa,
        "divergencia": decisao.divergencia,
        "impacto_diario_estimado": projecao.impacto_diario_estimado if projecao else None,
        "impacto_diario_ic95": list(projecao.impacto_diario_ic95) if projecao else None,
        "sugestao_proximo_teste": lente.sugestao_proximo_teste,
    }


def processar_dataset(
    caminho: str | Path,
    alfa: float = 0.05,
    diretorio_saida: str | Path = REPORTS_DIR_PADRAO,
    caminho_tracking: str | Path = TRACKING_CSV_PADRAO,
    sheet_id: str | None = None,
) -> dict:
    """Processa um dataset de teste A/B ponta a ponta e devolve um resumo estruturado.

    Reaproveita o mesmo motor de análise (engine/) que `cli.processar_dataset` usa — nenhuma
    lógica de negócio vive aqui, só a tradução do resultado para um dict que um cliente MCP
    consegue consumir. Um dataset ruim não lança exceção: devolve `{"ok": False, "erro": ...}`,
    igual à CLI, que também pula datasets ruins sem derrubar o processamento dos demais.
    """
    caminho = Path(caminho)
    diretorio_saida = Path(diretorio_saida)
    caminho_tracking = Path(caminho_tracking)

    try:
        df, parse_report = carregar_csv(caminho)
    except SchemaError as exc:
        return {"ok": False, "arquivo": caminho.name, "erro": str(exc)}
    except FileNotFoundError as exc:
        return {"ok": False, "arquivo": caminho.name, "erro": str(exc)}

    if df.empty:
        return {
            "ok": False,
            "arquivo": caminho.name,
            "erro": "nenhuma linha válida após parsing — nada a processar.",
        }

    issues = avaliar_qualidade(df)

    try:
        comparacoes = comparar_todos_os_grupos(df)
    except ParDadosInsuficientesError as exc:
        return {"ok": False, "arquivo": caminho.name, "erro": str(exc)}

    if not comparacoes:
        return {"ok": False, "arquivo": caminho.name, "erro": "só um grupo presente, nada a comparar."}

    correcoes = corrigir_multiplas_comparacoes(comparacoes, alfa=alfa)
    bootstraps = bootstrap_todos_os_grupos(df)
    posteriores = posterior_todos_os_grupos(df)
    decisoes = decidir_todos(
        comparacoes, alfa=alfa, correcoes=correcoes, bootstraps=bootstraps, posteriores=posteriores
    )
    lentes = [growth_lens(df, decisao) for decisao in decisoes]

    caminho_relatorio = gerar_relatorio_completo(
        df,
        diretorio_saida=diretorio_saida,
        alfa=alfa,
        quality_issues=issues,
        comparacoes=comparacoes,
        correcoes=correcoes,
        bootstraps=bootstraps,
        posteriores_lista=posteriores,
        decisoes=decisoes,
    )
    registrar(decisoes, lentes, caminho_csv=caminho_tracking, planilha_id=sheet_id)

    return {
        "ok": True,
        "arquivo": caminho.name,
        "parsing": str(parse_report),
        "ressalvas_qualidade": [str(issue) for issue in issues],
        "decisoes": [_decisao_para_dict(d, lente) for d, lente in zip(decisoes, lentes)],
        "relatorio": str(caminho_relatorio),
        "tracking": str(caminho_tracking),
    }


@mcp.tool()
def listar_datasets() -> list[str]:
    """Lista os CSVs de teste A/B de cashback disponíveis em data/."""
    return [str(p) for p in _listar_csvs()]


@mcp.tool()
def analisar_teste_ab(
    caminho: str,
    alfa: float = 0.05,
    diretorio_saida: str | None = None,
    caminho_tracking: str | None = None,
    sheet_id: str | None = None,
) -> dict:
    """Processa um dataset de teste A/B de cashback (CSV) ponta a ponta: avalia qualidade
    dos dados, compara cada variante contra o baseline (teste t pareado + Wilcoxon), decide
    se escalar/manter baseline/aguardar mais dados, projeta impacto de growth em R$ e sugere
    o próximo teste. Gera relatório em Markdown com gráfico embutido (padrão: reports/) e
    registra o resultado em tracking/testes_ab.csv (e no Google Sheets, best-effort, se
    `sheet_id` for informado).
    """
    return processar_dataset(
        caminho,
        alfa=alfa,
        diretorio_saida=Path(diretorio_saida) if diretorio_saida else REPORTS_DIR_PADRAO,
        caminho_tracking=Path(caminho_tracking) if caminho_tracking else TRACKING_CSV_PADRAO,
        sheet_id=sheet_id,
    )


@mcp.tool()
def analisar_todos_os_testes_ab(
    alfa: float = 0.05,
    diretorio_saida: str | None = None,
    caminho_tracking: str | None = None,
    sheet_id: str | None = None,
) -> dict:
    """Roda `analisar_teste_ab` para todos os CSVs encontrados em data/ — o mesmo fluxo de
    `python cli.py` sem argumentos, devolvendo um resumo estruturado por dataset em vez de
    imprimir no terminal."""
    resultados = [
        processar_dataset(
            caminho,
            alfa=alfa,
            diretorio_saida=Path(diretorio_saida) if diretorio_saida else REPORTS_DIR_PADRAO,
            caminho_tracking=Path(caminho_tracking) if caminho_tracking else TRACKING_CSV_PADRAO,
            sheet_id=sheet_id,
        )
        for caminho in _listar_csvs()
    ]
    return {
        "total": len(resultados),
        "sucesso": sum(1 for r in resultados if r["ok"]),
        "resultados": resultados,
    }


if __name__ == "__main__":
    mcp.run()
