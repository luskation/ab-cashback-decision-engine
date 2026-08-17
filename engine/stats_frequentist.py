from __future__ import annotations

import re
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


def _chave_ordenacao_natural(rotulo: str) -> list:
    """Divide o rótulo em pedaços texto/número para comparar números pelo valor, não como
    string — sem isso, 'Grupo 10' viria antes de 'Grupo 2' (comparação lexicográfica)."""
    return [int(parte) if parte.isdigit() else parte.lower() for parte in re.split(r"(\d+)", rotulo)]


def inferir_grupo_baseline(grupos: list[str]) -> str:
    """Sem convenção explícita no dataset, assume o grupo de menor rótulo em ordem natural
    (ex: 'Grupo 1' antes de 'Grupo 2', e 'Grupo 2' antes de 'Grupo 10') como baseline. Não
    depende de nome de parceiro/grupo específico — funciona para qualquer rotulagem
    consistente entre os testes."""
    return min(grupos, key=_chave_ordenacao_natural)


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


def corrigir_benjamini_hochberg(p_valores: list[float], alfa: float = 0.05) -> list[tuple[float, bool]]:
    """Correção de Benjamini-Hochberg (FDR) para um lote de p-valores.

    Contexto (seção 2.10 do plano): rodando "dezenas de testes por mês", não corrigir infla a
    taxa de falso positivo ao longo do tempo — um p-valor isolado abaixo de 0.05 dentro de um
    lote maior tem mais chance de ser ruído do que o mesmo p-valor visto sozinho.

    Devolve, na mesma ordem de entrada, (p_valor_ajustado, significativo_apos_correcao).
    Genérica sobre qualquer lista de p-valores — sem acoplamento a `ComparacaoPareada`.

    p-valores NaN (ex: teste com variância zero na diferença diária) são excluídos do
    cálculo e devolvidos como (nan, False) — nunca participam do ranking nem podem herdar
    por acidente o valor ajustado de um p-valor vizinho, o que os marcaria como
    "significativo" sem nenhuma evidência estatística real por trás.
    """
    m = len(p_valores)
    if m == 0:
        return []

    indices_validos = [i for i in range(m) if pd.notna(p_valores[i])]
    p_ajustados: list[float] = [float("nan")] * m
    significativos = [False] * m

    m_validos = len(indices_validos)
    if m_validos > 0:
        ordem = sorted(indices_validos, key=lambda i: p_valores[i])
        menor_ate_agora = 1.0
        for rank in range(m_validos, 0, -1):
            idx = ordem[rank - 1]
            candidato = p_valores[idx] * m_validos / rank
            menor_ate_agora = min(menor_ate_agora, candidato, 1.0)
            p_ajustados[idx] = menor_ate_agora
            significativos[idx] = menor_ate_agora < alfa

    return list(zip(p_ajustados, significativos))


@dataclass
class CorrecaoMultipla:
    """Resultado da correção de Benjamini-Hochberg para uma comparação dentro de um lote.

    Não decide nada sozinha — `decision.py` (Fase 13) é quem reconcilia isso com as demais
    camadas opcionais. Até lá, fica disponível para quem quiser consultar/reportar.
    """

    comparacao: ComparacaoPareada
    t_p_valor_ajustado: float
    wilcoxon_p_valor_ajustado: float
    significativo_corrigido: bool


def corrigir_multiplas_comparacoes(
    comparacoes: list[ComparacaoPareada], alfa: float = 0.05
) -> list[CorrecaoMultipla]:
    """Aplica Benjamini-Hochberg separadamente sobre t e Wilcoxon de um lote de comparações
    (ex: todos os testes A/B processados numa mesma rodada), exigindo que os dois concordem
    sobre significância após a correção — mesmo critério de concordância já usado em
    `decision.py` para o resultado sem correção, aplicado aqui à versão corrigida.
    """
    if not comparacoes:
        return []

    t_corrigidos = corrigir_benjamini_hochberg([c.t_p_valor for c in comparacoes], alfa=alfa)
    w_corrigidos = corrigir_benjamini_hochberg([c.wilcoxon_p_valor for c in comparacoes], alfa=alfa)

    return [
        CorrecaoMultipla(
            comparacao=comparacao,
            t_p_valor_ajustado=t_ajustado,
            wilcoxon_p_valor_ajustado=w_ajustado,
            significativo_corrigido=t_significativo and w_significativo,
        )
        for comparacao, (t_ajustado, t_significativo), (w_ajustado, w_significativo) in zip(
            comparacoes, t_corrigidos, w_corrigidos
        )
    ]


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
