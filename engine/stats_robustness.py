from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.stats_frequentist import (
    ParDadosInsuficientesError,
    _parear_por_data,
    calcular_margem,
    inferir_grupo_baseline,
)

N_REAMOSTRAGENS_PADRAO = 2000


@dataclass
class BootstrapEmBloco:
    """Intervalo de confiança da diferença de margem via bootstrap em bloco (moving block
    bootstrap) — robusto a autocorrelação de curto prazo que o teste t pareado (Fase 4) ignora
    ao assumir observações independentes.
    """

    parceiro: str
    grupo_baseline: str
    grupo_variante: str
    coluna: str
    n_dias_pareados: int
    tamanho_bloco: int
    n_reamostragens: int
    media_diferenca: float
    ic95_diferenca: tuple[float, float]
    contem_zero: bool


def _tamanho_bloco_padrao(n: int) -> int:
    """Sem tamanho de bloco explícito, cresce devagar com o tamanho da série (raiz cúbica) —
    grande o suficiente para capturar autocorrelação de curto prazo (ex: um pico sincronizado
    de poucos dias), sem virar blocos tão grandes que a reamostragem perde variabilidade."""
    return max(2, min(n, round(n ** (1 / 3))))


def _reamostrar_em_blocos(diffs: np.ndarray, tamanho_bloco: int, rng: np.random.Generator) -> np.ndarray:
    """Uma reamostragem: concatena blocos contíguos sorteados da série original até cobrir o
    tamanho original, preservando a correlação entre dias vizinhos dentro de cada bloco —
    o que uma reamostragem dia-a-dia (i.i.d.) destruiria."""
    n = len(diffs)
    n_blocos_possiveis = n - tamanho_bloco + 1
    n_blocos_necessarios = -(-n // tamanho_bloco)  # ceil division
    inicios = rng.integers(0, n_blocos_possiveis, size=n_blocos_necessarios)
    blocos = [diffs[i : i + tamanho_bloco] for i in inicios]
    return np.concatenate(blocos)[:n]


def bootstrap_em_bloco(
    df: pd.DataFrame,
    parceiro: str,
    grupo_variante: str,
    grupo_baseline: str | None = None,
    coluna: str = "margem",
    tamanho_bloco: int | None = None,
    n_reamostragens: int = N_REAMOSTRAGENS_PADRAO,
    seed: int = 42,
) -> BootstrapEmBloco:
    """Intervalo de confiança de 95% para a diferença de margem via bootstrap em bloco,
    pareado por data como em `comparar_grupo` (Fase 4) — mesma preparação de dados, camada
    de robustez adicional, nunca substitui o resultado frequentista."""
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

    diffs = (pareado["variante"] - pareado["baseline"]).to_numpy()
    bloco = min(tamanho_bloco, n) if tamanho_bloco else _tamanho_bloco_padrao(n)

    rng = np.random.default_rng(seed)
    medias_reamostradas = np.array(
        [_reamostrar_em_blocos(diffs, bloco, rng).mean() for _ in range(n_reamostragens)]
    )
    ic95 = np.percentile(medias_reamostradas, [2.5, 97.5])

    return BootstrapEmBloco(
        parceiro=parceiro,
        grupo_baseline=grupo_baseline,
        grupo_variante=grupo_variante,
        coluna=coluna,
        n_dias_pareados=n,
        tamanho_bloco=bloco,
        n_reamostragens=n_reamostragens,
        media_diferenca=float(diffs.mean()),
        ic95_diferenca=(float(ic95[0]), float(ic95[1])),
        contem_zero=bool(ic95[0] <= 0 <= ic95[1]),
    )


def bootstrap_todos_os_grupos(
    df: pd.DataFrame,
    coluna: str = "margem",
    grupo_baseline: str | None = None,
    tamanho_bloco: int | None = None,
    n_reamostragens: int = N_REAMOSTRAGENS_PADRAO,
    seed: int = 42,
) -> list[BootstrapEmBloco]:
    """Roda `bootstrap_em_bloco` para cada grupo variante de cada parceiro — mesma cobertura
    de `comparar_todos_os_grupos` (Fase 4), camada opcional em paralelo."""
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
                bootstrap_em_bloco(
                    df,
                    parceiro,
                    grupo,
                    grupo_baseline=baseline,
                    coluna=coluna,
                    tamanho_bloco=tamanho_bloco,
                    n_reamostragens=n_reamostragens,
                    seed=seed,
                )
            )
    return resultados
