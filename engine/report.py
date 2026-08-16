from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from engine.decision import Decisao, decidir_todos
from engine.growth import GrowthLens, growth_lens
from engine.quality import QualityIssue, avaliar_qualidade
from engine.stats_frequentist import ComparacaoPareada, calcular_margem, comparar_todos_os_grupos

COR_SURFACE = "#fcfcfb"
COR_TINTA_PRIMARIA = "#0b0b0b"
COR_TINTA_SECUNDARIA = "#52514e"
COR_TINTA_MUTED = "#898781"
COR_GRADE = "#e1e0d9"
COR_EIXO = "#c3c2b7"

# Paleta categórica validada (ordem fixa, nunca reatribuída por rank/valor) — ver skill dataviz.
PALETA_CATEGORICA = [
    "#2a78d6",  # azul
    "#eb6834",  # laranja
    "#1baf7a",  # aqua
    "#eda100",  # amarelo
    "#e87ba4",  # magenta
    "#008300",  # verde
    "#4a3aa7",  # violeta
    "#e34948",  # vermelho
]


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def _cor_por_grupo(grupos: list[str]) -> dict[str, str]:
    """Cor fixa por grupo em ordem alfabética dos rótulos — estável entre gráficos do
    mesmo parceiro, nunca atribuída por quem "ganhou" o teste."""
    ordenados = sorted(grupos)
    return {grupo: PALETA_CATEGORICA[i % len(PALETA_CATEGORICA)] for i, grupo in enumerate(ordenados)}


def gerar_grafico_margem_diaria(df: pd.DataFrame, parceiro: str, caminho_saida: Path) -> Path:
    df_parceiro = df[df["parceiro"] == parceiro].copy()
    df_parceiro["margem"] = calcular_margem(df_parceiro)
    grupos = sorted(df_parceiro["grupo"].unique())
    cores = _cor_por_grupo(grupos)

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=150)
    fig.patch.set_facecolor(COR_SURFACE)
    ax.set_facecolor(COR_SURFACE)

    for grupo in grupos:
        serie = df_parceiro[df_parceiro["grupo"] == grupo].sort_values("data")
        ax.plot(serie["data"], serie["margem"], label=grupo, color=cores[grupo], linewidth=2)

    ax.set_title(f"Margem diária por grupo — {parceiro}", color=COR_TINTA_PRIMARIA, fontsize=13, loc="left", pad=12)
    ax.set_ylabel("Margem (R$/dia)", color=COR_TINTA_SECUNDARIA, fontsize=10)
    ax.tick_params(colors=COR_TINTA_MUTED, labelsize=9)
    ax.grid(True, color=COR_GRADE, linewidth=0.8)
    for nome_spine, spine in ax.spines.items():
        if nome_spine in ("top", "right"):
            spine.set_visible(False)
        else:
            spine.set_color(COR_EIXO)
    ax.legend(frameon=False, labelcolor=COR_TINTA_SECUNDARIA, fontsize=9, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.autofmt_xdate()
    fig.tight_layout()

    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho_saida, facecolor=COR_SURFACE, bbox_inches="tight")
    plt.close(fig)
    return caminho_saida


def _formatar_moeda(valor: float) -> str:
    """Formata em R$ no padrão pt-BR (ponto de milhar, vírgula decimal) — o relatório é
    para um gestor brasileiro, formatação US ('R$ 1,200.00') soa estrangeira/errada."""
    sinal = "-" if valor < 0 else ""
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sinal}R$ {texto}"


def _frase_executiva(decisao: Decisao) -> str:
    if decisao.veredito == "escalar":
        return (
            f"**Decisão: escalar {decisao.grupo_variante}** — supera {decisao.grupo_baseline} com "
            f"significância estatística (confiança {decisao.confianca})."
        )
    if decisao.veredito == "manter_baseline":
        return (
            f"**Decisão: manter {decisao.grupo_baseline}** — {decisao.grupo_variante} teve desempenho "
            f"pior, com significância estatística (confiança {decisao.confianca})."
        )
    return (
        f"**Decisão: sem evidência suficiente** para diferenciar {decisao.grupo_variante} de "
        f"{decisao.grupo_baseline} (confiança {decisao.confianca})."
    )


def _paragrafo_racional(comparacao: ComparacaoPareada) -> str:
    direcao = "a mais" if comparacao.media_diferenca >= 0 else "a menos"
    return (
        f"No período comparável ({comparacao.n_dias_pareados} dias pareados), {comparacao.grupo_variante} "
        f"gerou em média {_formatar_moeda(abs(comparacao.media_diferenca))} de margem por dia {direcao} "
        f"que {comparacao.grupo_baseline} (intervalo de 95% de confiança: "
        f"{_formatar_moeda(comparacao.ic95_diferenca[0])} a {_formatar_moeda(comparacao.ic95_diferenca[1])})."
    )


def _paragrafo_growth(lente: GrowthLens) -> str:
    partes = []
    if lente.projecao_impacto is not None:
        projecao = lente.projecao_impacto
        limite_inferior, limite_superior = sorted(projecao.impacto_diario_ic95)
        partes.append(
            f"Se {projecao.grupo_variante} escalar para o volume de tráfego que hoje é dividido com "
            f"{projecao.grupo_baseline}, a projeção é de um impacto diário entre "
            f"{_formatar_moeda(limite_inferior)} e {_formatar_moeda(limite_superior)} de margem (faixa "
            "de incerteza, não um valor único)."
        )
    partes.append(f"Próximo teste sugerido: {lente.sugestao_proximo_teste}")
    return " ".join(partes)


def _secao_ressalvas(issues: list[QualityIssue]) -> str:
    if not issues:
        return "Nenhum problema de qualidade de dados identificado neste teste."
    return "\n".join(f"- {issue}" for issue in issues)


def _apendice_tecnico(comparacao: ComparacaoPareada) -> str:
    return (
        f"- **{comparacao.grupo_baseline} vs {comparacao.grupo_variante}** "
        f"(coluna: `{comparacao.coluna}`, n={comparacao.n_dias_pareados})\n"
        f"  - teste t pareado: estatística={comparacao.t_estatistica:.3f}, p={comparacao.t_p_valor:.4f}\n"
        f"  - Wilcoxon: estatística={comparacao.wilcoxon_estatistica:.3f}, p={comparacao.wilcoxon_p_valor:.4f}\n"
        f"  - IC95 da diferença: ({comparacao.ic95_diferenca[0]:.2f}, {comparacao.ic95_diferenca[1]:.2f})\n"
        f"  - médias: baseline={comparacao.media_baseline:.2f}, variante={comparacao.media_variante:.2f}"
    )


def gerar_relatorio_markdown(
    parceiro: str,
    resultados: list[tuple[ComparacaoPareada, Decisao, GrowthLens]],
    quality_issues: list[QualityIssue],
    caminho_grafico: Path,
    caminho_saida: Path,
) -> Path:
    caminho_grafico = Path(caminho_grafico)
    caminho_saida = Path(caminho_saida)

    linhas = [f"# Teste A/B — {parceiro}", "", "## Resumo executivo", ""]
    for _, decisao, _ in resultados:
        linhas.append(f"- {_frase_executiva(decisao)}")

    linhas += ["", f"![Margem diária por grupo]({caminho_grafico.name})", "", "## Racional", ""]
    for comparacao, _, lente in resultados:
        linhas.append(f"### {comparacao.grupo_baseline} vs {comparacao.grupo_variante}")
        linhas.append("")
        linhas.append(_paragrafo_racional(comparacao))
        linhas.append("")
        linhas.append(_paragrafo_growth(lente))
        linhas.append("")

    linhas += ["## Ressalvas", "", _secao_ressalvas(quality_issues), "", "## Apêndice técnico", ""]
    for comparacao, _, _ in resultados:
        linhas.append(_apendice_tecnico(comparacao))
        linhas.append("")

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    caminho_saida.write_text("\n".join(linhas), encoding="utf-8")
    return caminho_saida


def gerar_relatorio_completo(df: pd.DataFrame, diretorio_saida: Path = Path("reports")) -> Path:
    """Roda qualidade, estatística, decisão e growth lens sobre um DataFrame de um único
    parceiro (o formato natural de cada CSV carregado) e escreve gráfico + relatório."""
    parceiros = df["parceiro"].unique()
    if len(parceiros) != 1:
        raise ValueError(f"esperado um único parceiro no DataFrame, recebido: {sorted(parceiros)}")
    parceiro = parceiros[0]
    slug = _slug(parceiro)

    diretorio_saida = Path(diretorio_saida)
    caminho_grafico = diretorio_saida / f"grafico_{slug}.png"
    caminho_relatorio = diretorio_saida / f"relatorio_{slug}.md"

    gerar_grafico_margem_diaria(df, parceiro, caminho_grafico)

    quality_issues = avaliar_qualidade(df)
    comparacoes = comparar_todos_os_grupos(df)
    decisoes = decidir_todos(comparacoes)
    resultados = [
        (comparacao, decisao, growth_lens(df, decisao))
        for comparacao, decisao in zip(comparacoes, decisoes)
    ]

    return gerar_relatorio_markdown(parceiro, resultados, quality_issues, caminho_grafico, caminho_relatorio)
