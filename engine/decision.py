from __future__ import annotations

from dataclasses import dataclass, field

from engine.stats_frequentist import ComparacaoPareada

ALFA_PADRAO = 0.05


@dataclass
class Decisao:
    """Veredito para um grupo variante, com a justificativa que levou a ele.

    `camadas_extras` é o encaixe para bootstrap/bayesiano/correção múltipla (Fases 10-12):
    nesta versão mínima elas só ficam anexadas para consulta/relatório, sem influenciar o
    veredito — a reconciliação completa entre camadas é a Fase 13.
    """

    parceiro: str
    grupo_baseline: str
    grupo_variante: str
    veredito: str  # "escalar" | "manter_baseline" | "sem_evidencia_suficiente"
    confianca: str  # "alta" (t e Wilcoxon concordam) | "baixa" (divergem)
    media_diferenca: float
    ic95_diferenca: tuple[float, float]
    t_p_valor: float
    wilcoxon_p_valor: float
    alfa: float
    justificativa: str
    camadas_extras: dict = field(default_factory=dict)


def decidir(
    comparacao: ComparacaoPareada,
    alfa: float = ALFA_PADRAO,
    camadas_extras: dict | None = None,
) -> Decisao:
    """Decide o veredito de um grupo variante usando só o resultado frequentista (Fase 4).

    Exige que t pareado e Wilcoxon concordem sobre significância antes de declarar um
    vencedor — se divergirem, o veredito fica inconclusivo em vez de arriscar uma decisão
    que depende de qual teste você escolheu rodar.
    """
    t_significativo = comparacao.t_p_valor < alfa
    w_significativo = comparacao.wilcoxon_p_valor < alfa

    if t_significativo and w_significativo:
        confianca = "alta"
        veredito = "escalar" if comparacao.media_diferenca > 0 else "manter_baseline"
        justificativa = (
            f"teste t (p={comparacao.t_p_valor:.4f}) e Wilcoxon (p={comparacao.wilcoxon_p_valor:.4f}) "
            f"concordam: diferença média de {comparacao.media_diferenca:+.2f} é estatisticamente "
            "significativa."
        )
    elif not t_significativo and not w_significativo:
        confianca = "alta"
        veredito = "sem_evidencia_suficiente"
        justificativa = (
            f"teste t (p={comparacao.t_p_valor:.4f}) e Wilcoxon (p={comparacao.wilcoxon_p_valor:.4f}) "
            "concordam: não há diferença estatisticamente significativa entre variante e baseline."
        )
    else:
        confianca = "baixa"
        veredito = "sem_evidencia_suficiente"
        justificativa = (
            f"teste t (p={comparacao.t_p_valor:.4f}) e Wilcoxon (p={comparacao.wilcoxon_p_valor:.4f}) "
            "divergem sobre significância — tratado como inconclusivo até haver mais dados ou uma "
            "camada de robustez adicional para desempatar."
        )

    return Decisao(
        parceiro=comparacao.parceiro,
        grupo_baseline=comparacao.grupo_baseline,
        grupo_variante=comparacao.grupo_variante,
        veredito=veredito,
        confianca=confianca,
        media_diferenca=comparacao.media_diferenca,
        ic95_diferenca=comparacao.ic95_diferenca,
        t_p_valor=comparacao.t_p_valor,
        wilcoxon_p_valor=comparacao.wilcoxon_p_valor,
        alfa=alfa,
        justificativa=justificativa,
        camadas_extras=camadas_extras or {},
    )


def decidir_todos(comparacoes: list[ComparacaoPareada], alfa: float = ALFA_PADRAO) -> list[Decisao]:
    return [decidir(comparacao, alfa=alfa) for comparacao in comparacoes]
