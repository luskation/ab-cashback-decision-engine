from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from engine.decision import Decisao
from engine.stats_frequentist import calcular_margem, comparar_grupo


@dataclass
class ProjecaoImpacto:
    """Impacto diário estimado de escalar a variante vencedora para o volume de tráfego
    que hoje está dividido entre baseline e variante — sempre como faixa (IC95), nunca um
    número seco, porque uma projeção sem intervalo soa como promessa exagerada."""

    parceiro: str
    grupo_baseline: str
    grupo_variante: str
    margem_por_comprador_baseline: float
    margem_por_comprador_variante: float
    diferenca_margem_por_comprador: float
    compradores_medios_dia_teste: float
    impacto_diario_estimado: float
    impacto_diario_ic95: tuple[float, float]


@dataclass
class GrowthLens:
    parceiro: str
    veredito: str
    projecao_impacto: ProjecaoImpacto | None
    sugestao_proximo_teste: str


def projetar_impacto(
    df: pd.DataFrame, parceiro: str, grupo_baseline: str, grupo_variante: str
) -> ProjecaoImpacto:
    """Projeta o ganho/perda diário de escalar `grupo_variante` para o volume de tráfego
    que hoje é atendido por `grupo_baseline` + `grupo_variante` juntos."""
    df_parceiro = df[df["parceiro"] == parceiro].copy()
    compradores_seguro = df_parceiro["compradores"].where(df_parceiro["compradores"] > 0)
    df_parceiro["margem_por_comprador"] = calcular_margem(df_parceiro) / compradores_seguro

    comparacao = comparar_grupo(
        df_parceiro, parceiro, grupo_variante, grupo_baseline=grupo_baseline, coluna="margem_por_comprador"
    )

    compradores_medios_dia_teste = float(df_parceiro.groupby("data")["compradores"].sum().mean())

    return ProjecaoImpacto(
        parceiro=parceiro,
        grupo_baseline=grupo_baseline,
        grupo_variante=grupo_variante,
        margem_por_comprador_baseline=comparacao.media_baseline,
        margem_por_comprador_variante=comparacao.media_variante,
        diferenca_margem_por_comprador=comparacao.media_diferenca,
        compradores_medios_dia_teste=compradores_medios_dia_teste,
        impacto_diario_estimado=comparacao.media_diferenca * compradores_medios_dia_teste,
        impacto_diario_ic95=(
            comparacao.ic95_diferenca[0] * compradores_medios_dia_teste,
            comparacao.ic95_diferenca[1] * compradores_medios_dia_teste,
        ),
    )


def _percentual_cashback_por_grupo(df: pd.DataFrame, parceiro: str) -> pd.Series:
    df_parceiro = df[df["parceiro"] == parceiro]
    vendas_seguro = df_parceiro["vendas_totais"].where(df_parceiro["vendas_totais"] > 0)
    percentual = df_parceiro["cashback"] / vendas_seguro
    return percentual.groupby(df_parceiro["grupo"]).mean().dropna().sort_values()


def sugerir_proximo_teste(df: pd.DataFrame, parceiro: str) -> str:
    """Deriva uma sugestão de próximo patamar de cashback a partir do histórico do próprio
    dataset — nunca um percentual fixo escrito no código. Com um único patamar testado, só
    sugere abrir um segundo; com dois ou mais, usa o passo já validado entre eles."""
    niveis = _percentual_cashback_por_grupo(df, parceiro)
    if niveis.empty:
        return "histórico insuficiente para sugerir um próximo patamar de cashback."

    maior_pct = niveis.iloc[-1]
    if len(niveis) < 2:
        return (
            f"até agora só um patamar de cashback foi testado neste histórico ({maior_pct:.1%}) — "
            "considere testar um segundo patamar para começar a mapear a curva de resposta."
        )

    passo = float(niveis.diff().dropna().median())
    proximo_pct = maior_pct + passo
    return (
        f"os patamares de cashback já testados neste histórico vão até {maior_pct:.1%}, em passos de "
        f"~{passo:.1%} — considere testar um próximo patamar por volta de {proximo_pct:.1%}, mantendo "
        "o incremento já validado no próprio histórico."
    )


def growth_lens(df: pd.DataFrame, decisao: Decisao) -> GrowthLens:
    """Combina projeção de impacto (só quando há vencedor) e sugestão de próximo teste
    (sempre, a partir do histórico do parceiro) para uma decisão já tomada."""
    projecao = None
    if decisao.veredito == "escalar":
        projecao = projetar_impacto(
            df, decisao.parceiro, decisao.grupo_baseline, decisao.grupo_variante
        )
    return GrowthLens(
        parceiro=decisao.parceiro,
        veredito=decisao.veredito,
        projecao_impacto=projecao,
        sugestao_proximo_teste=sugerir_proximo_teste(df, decisao.parceiro),
    )
