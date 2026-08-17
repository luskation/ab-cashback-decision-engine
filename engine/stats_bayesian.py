from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from engine.stats_frequentist import (
    ParDadosInsuficientesError,
    _parear_por_data,
    calcular_margem,
    inferir_grupo_baseline,
)

N_AMOSTRAS_PADRAO = 200_000


@dataclass
class PosteriorBayesiano:
    """Posterior da diferença média real de margem (variante − baseline), sob o prior de
    referência de Jeffreys para média e variância desconhecidas de uma normal — a mesma
    suposição de normalidade que o teste t pareado (Fase 4) já faz, nenhuma suposição nova.

    Fórmula fechada, sem MCMC: μ | dados ~ Student-t(df=n-1, loc=d̄, scale=erro_padrao).
    Reformula "é significativo?" (frequentista) para "qual a chance de acerto e quanto custa
    errar?" — mais alinhado à decisão real ("escalar ou não"), não a um teste de hipótese.
    Não decide nada sozinha; `decision.py` (Fase 13) é quem reconcilia isso com as demais
    camadas opcionais.
    """

    parceiro: str
    grupo_baseline: str
    grupo_variante: str
    coluna: str
    n_dias_pareados: int
    media_diferenca: float
    ic95_diferenca: tuple[float, float]
    probabilidade_variante_melhor: float  # P(μ > 0 | dados)
    perda_esperada_escalar: float  # custo esperado/dia se escalar a variante e ela for pior
    perda_esperada_manter: float  # custo esperado/dia se manter o baseline e a variante for melhor


def posterior_diferenca_margem(
    df: pd.DataFrame,
    parceiro: str,
    grupo_variante: str,
    grupo_baseline: str | None = None,
    coluna: str = "margem",
    n_amostras: int = N_AMOSTRAS_PADRAO,
    seed: int = 42,
) -> PosteriorBayesiano:
    """Posterior bayesiana da diferença de margem, pareada por data como em `comparar_grupo`
    (Fase 4) — mesma preparação de dados, camada de interpretação adicional."""
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
    d_media = float(diffs.mean())
    erro_padrao = float(stats.sem(diffs))

    if erro_padrao == 0:
        # todas as diferenças idênticas: sem variância amostral, posterior degenerada em d_media.
        probabilidade = 1.0 if d_media > 0 else (0.0 if d_media < 0 else 0.5)
        return PosteriorBayesiano(
            parceiro=parceiro,
            grupo_baseline=grupo_baseline,
            grupo_variante=grupo_variante,
            coluna=coluna,
            n_dias_pareados=n,
            media_diferenca=d_media,
            ic95_diferenca=(d_media, d_media),
            probabilidade_variante_melhor=probabilidade,
            perda_esperada_escalar=max(0.0, -d_media),
            perda_esperada_manter=max(0.0, d_media),
        )

    posterior = stats.t(df=n - 1, loc=d_media, scale=erro_padrao)
    probabilidade_variante_melhor = float(1 - posterior.cdf(0))
    ic95 = posterior.interval(0.95)

    rng = np.random.default_rng(seed)
    amostras = posterior.rvs(size=n_amostras, random_state=rng)
    perda_esperada_escalar = float(np.mean(np.maximum(0.0, -amostras)))
    perda_esperada_manter = float(np.mean(np.maximum(0.0, amostras)))

    return PosteriorBayesiano(
        parceiro=parceiro,
        grupo_baseline=grupo_baseline,
        grupo_variante=grupo_variante,
        coluna=coluna,
        n_dias_pareados=n,
        media_diferenca=d_media,
        ic95_diferenca=(float(ic95[0]), float(ic95[1])),
        probabilidade_variante_melhor=probabilidade_variante_melhor,
        perda_esperada_escalar=perda_esperada_escalar,
        perda_esperada_manter=perda_esperada_manter,
    )


def posterior_todos_os_grupos(
    df: pd.DataFrame,
    coluna: str = "margem",
    grupo_baseline: str | None = None,
    n_amostras: int = N_AMOSTRAS_PADRAO,
    seed: int = 42,
) -> list[PosteriorBayesiano]:
    """Roda `posterior_diferenca_margem` para cada grupo variante de cada parceiro — mesma
    cobertura de `comparar_todos_os_grupos` (Fase 4), camada opcional em paralelo."""
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
                posterior_diferenca_margem(
                    df,
                    parceiro,
                    grupo,
                    grupo_baseline=baseline,
                    coluna=coluna,
                    n_amostras=n_amostras,
                    seed=seed,
                )
            )
    return resultados
