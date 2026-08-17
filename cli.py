from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from engine.decision import decidir_todos
from engine.growth import growth_lens
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

logger = logging.getLogger("cli")

DATA_DIR_PADRAO = Path("data")
REPORTS_DIR_PADRAO = Path("reports")
TRACKING_CSV_PADRAO = Path("tracking/testes_ab.csv")


def _descobrir_csvs(caminhos: list[str] | None) -> list[Path]:
    if caminhos:
        return [Path(c) for c in caminhos]
    if not DATA_DIR_PADRAO.exists():
        return []
    return sorted(DATA_DIR_PADRAO.glob("*.csv"))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Processa datasets de teste A/B de cashback: qualidade, estatística, "
            "decisão, growth lens, relatório e tracking."
        ),
    )
    parser.add_argument(
        "datasets", nargs="*", help="Caminhos dos CSVs a processar (padrão: todos os CSVs em data/)."
    )
    parser.add_argument(
        "--output-dir", default=str(REPORTS_DIR_PADRAO),
        help="Diretório de saída dos relatórios/gráficos (padrão: reports/).",
    )
    parser.add_argument(
        "--tracking-csv", default=str(TRACKING_CSV_PADRAO),
        help="Caminho do CSV de tracking (padrão: tracking/testes_ab.csv).",
    )
    parser.add_argument(
        "--sheet-id", default=None,
        help="ID da planilha do Google Sheets para escrita best-effort (opcional).",
    )
    parser.add_argument(
        "--alfa", type=float, default=0.05, help="Nível de significância para as decisões (padrão: 0.05)."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nível DEBUG.")
    return parser.parse_args(argv)


def processar_dataset(
    caminho: Path,
    diretorio_saida: Path,
    caminho_tracking: Path,
    planilha_id: str | None,
    alfa: float,
) -> bool:
    """Processa um dataset ponta a ponta. Retorna True se concluiu sem erro fatal —
    um dataset ruim não pode derrubar o processamento dos demais."""
    print(f"\n=== {caminho.name} ===")
    try:
        df, parse_report = carregar_csv(caminho)
    except SchemaError as exc:
        logger.error("falha de schema em %s: %s", caminho.name, exc)
        return False

    print(parse_report)
    if df.empty:
        logger.error("%s: nenhuma linha válida após parsing — nada a processar.", caminho.name)
        return False

    issues = avaliar_qualidade(df)
    if issues:
        print(f"\n{len(issues)} ressalva(s) de qualidade:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\nNenhuma ressalva de qualidade.")

    try:
        comparacoes = comparar_todos_os_grupos(df)
    except ParDadosInsuficientesError as exc:
        logger.error("%s: %s", caminho.name, exc)
        return False

    if not comparacoes:
        logger.warning("%s: só um grupo presente, nada a comparar.", caminho.name)
        return False

    correcoes = corrigir_multiplas_comparacoes(comparacoes, alfa=alfa)
    bootstraps = bootstrap_todos_os_grupos(df)
    posteriores = posterior_todos_os_grupos(df)
    decisoes = decidir_todos(
        comparacoes, alfa=alfa, correcoes=correcoes, bootstraps=bootstraps, posteriores=posteriores
    )
    lentes = [growth_lens(df, decisao) for decisao in decisoes]

    print("\nDecisões:")
    for decisao in decisoes:
        print(
            f"  {decisao.grupo_variante} vs {decisao.grupo_baseline}: "
            f"{decisao.veredito} (confiança {decisao.confianca})"
        )
        if decisao.divergencia:
            print(f"    divergência: {decisao.divergencia}")

    caminho_relatorio = gerar_relatorio_completo(df, diretorio_saida=diretorio_saida, alfa=alfa)
    print(f"\nRelatório: {caminho_relatorio}")

    registrar(decisoes, lentes, caminho_csv=caminho_tracking, planilha_id=planilha_id)
    print(f"Tracking: {caminho_tracking}")

    return True


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s"
    )

    caminhos = _descobrir_csvs(args.datasets)
    if not caminhos:
        print("Nenhum dataset encontrado. Informe caminhos ou coloque CSVs em data/.", file=sys.stderr)
        return 1

    diretorio_saida = Path(args.output_dir)
    caminho_tracking = Path(args.tracking_csv)

    resultados = [
        processar_dataset(caminho, diretorio_saida, caminho_tracking, args.sheet_id, args.alfa)
        for caminho in caminhos
    ]

    total, sucesso = len(resultados), sum(resultados)
    print(f"\n{sucesso}/{total} dataset(s) processado(s) com sucesso.")
    return 0 if sucesso == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
