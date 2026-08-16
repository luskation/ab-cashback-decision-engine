from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from scipy import stats


class ParDadosInsuficientesError(ValueError):
    """Não há dias suficientes com dado válido em ambos os grupos para comparar."""


def calcular_margem(df: pd.DataFrame) -> pd.Series:
    """Margem líquida diária: comissão recebida do parceiro menos cashback pago ao usuário."""
    return df["comissao"] - df["cashback"]


@dataclass
class ComparacaoPareada:
    """Resultado bruto da comparação estatística entre um grupo variante e seu baseline.

    Não decide nada — só expõe os números. A decisão (Fase 5, `decision.py`) é quem
    interpreta `t_p_valor`/`wilcoxon_p_valor` junto de outras camadas opcionais.
    """

    parceiro: str
    grupo_baseline: str
    grupo_variante: str
    coluna: str
    n_dias_pareados: int
    media_baseline: float
    media_variante: float
    media_diferenca: float
    desvio_padrao_diferenca: float
    ic95_diferenca: tuple[float, float]
    t_estatistica: float
    t_p_valor: float
    wilcoxon_estatistica: float
    wilcoxon_p_valor: float


def inferir_grupo_baseline(grupos: list[str]) -> str:
    """Sem convenção explícita no dataset, assume o grupo de menor rótulo em ordem natural
    (ex: 'Grupo 1' antes de 'Grupo 2') como baseline. Não depende de nome de parceiro/grupo
    específico — funciona para qualquer rotulagem consistente entre os testes."""
    return sorted(grupos)[0]


def _parear_por_data(df_parceiro: pd.DataFrame, baseline: str, variante: str, coluna: str) -> pd.DataFrame:
    serie_base = df_parceiro[df_parceiro["grupo"] == baseline].set_index("data")[coluna]
    serie_var = df_parceiro[df_parceiro["grupo"] == variante].set_index("data")[coluna]
    pareado = pd.concat(
        [serie_base.rename("baseline"), serie_var.rename("variante")], axis=1, join="inner"
    ).dropna()
    return pareado


def comparar_grupo(
    df: pd.DataFrame,
    parceiro: str,
    grupo_variante: str,
    grupo_baseline: str | None = None,
    coluna: str = "margem",
) -> ComparacaoPareada:
    """Compara um grupo variante contra o baseline do mesmo parceiro, pareado por data."""
    df_parceiro = df[df["parceiro"] == parceiro].copy()
    if coluna == "margem" and "margem" not in df_parceiro.columns:
        df_parceiro["margem"] = calcular_margem(df_parceiro)

    if grupo_baseline is None:
        grupo_baseline = inferir_grupo_baseline(df_parceiro["grupo"].unique().tolist())
    if grupo_baseline == grupo_variante:
        raise ValueError(f"grupo_baseline e grupo_variante são o mesmo grupo: '{grupo_variante}'")

    pareado = _parear_por_data(df_parceiro, grupo_baseline, grupo_variante, coluna)
    n = len(pareado)
    if n < 2:
        raise ParDadosInsuficientesError(
            f"{parceiro}: apenas {n} dia(s) com '{coluna}' válido em ambos "
            f"'{grupo_baseline}' e '{grupo_variante}' — não dá para comparar."
        )

    diffs = pareado["variante"] - pareado["baseline"]

    t_estatistica, t_p_valor = stats.ttest_rel(pareado["variante"], pareado["baseline"])
    erro_padrao = stats.sem(diffs)
    if erro_padrao > 0:
        ic95 = stats.t.interval(0.95, df=n - 1, loc=diffs.mean(), scale=erro_padrao)
    else:
        ic95 = (float(diffs.mean()), float(diffs.mean()))

    wilcoxon_estatistica, wilcoxon_p_valor = stats.wilcoxon(pareado["variante"], pareado["baseline"])

    return ComparacaoPareada(
        parceiro=parceiro,
        grupo_baseline=grupo_baseline,
        grupo_variante=grupo_variante,
        coluna=coluna,
        n_dias_pareados=n,
        media_baseline=float(pareado["baseline"].mean()),
        media_variante=float(pareado["variante"].mean()),
        media_diferenca=float(diffs.mean()),
        desvio_padrao_diferenca=float(diffs.std(ddof=1)),
        ic95_diferenca=(float(ic95[0]), float(ic95[1])),
        t_estatistica=float(t_estatistica),
        t_p_valor=float(t_p_valor),
        wilcoxon_estatistica=float(wilcoxon_estatistica),
        wilcoxon_p_valor=float(wilcoxon_p_valor),
    )


def comparar_todos_os_grupos(
    df: pd.DataFrame, coluna: str = "margem", grupo_baseline: str | None = None
) -> list[ComparacaoPareada]:
    """Roda `comparar_grupo` para cada grupo variante de cada parceiro presente no dataset.

    Cobre testes com mais de duas variantes (ex: Grupo 1/2/3) sem exigir configuração —
    cada grupo não-baseline vira uma comparação independente contra o mesmo baseline.
    """
    resultados = []
    for parceiro, df_parceiro in df.groupby("parceiro"):
        grupos = df_parceiro["grupo"].unique().tolist()
        if len(grupos) < 2:
            continue
        baseline = grupo_baseline or inferir_grupo_baseline(grupos)
        for grupo in grupos:
            if grupo == baseline:
                continue
            resultados.append(
                comparar_grupo(df, parceiro, grupo, grupo_baseline=baseline, coluna=coluna)
            )
    return resultados
