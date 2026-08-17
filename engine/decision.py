from __future__ import annotations

from dataclasses import dataclass, field

from engine.stats_bayesian import PosteriorBayesiano
from engine.stats_frequentist import ComparacaoPareada, CorrecaoMultipla
from engine.stats_robustness import BootstrapEmBloco

ALFA_PADRAO = 0.05

# Limiar de probabilidade posterior para considerar a leitura bayesiana "confiante" o
# suficiente para comparar com o veredito frequentista — abaixo disso é tratado como
# "bayesiano também inconclusivo", não como divergência.
LIMIAR_CONFIANCA_BAYESIANA = 0.95


@dataclass
class Decisao:
    """Veredito para um grupo variante, com a justificativa que levou a ele.

    `correcao`, `bootstrap` e `posterior` são o encaixe para as camadas opcionais das
    Fases 10-12: quando ausentes (None), o veredito é puramente frequentista, igual à
    versão mínima (Fase 5). Quando presentes, `decidir` (Fase 13) reconcilia cada uma
    contra o resultado frequentista antes de fechar o veredito e a confiança.
    """

    parceiro: str
    grupo_baseline: str
    grupo_variante: str
    veredito: str  # "escalar" | "manter_baseline" | "sem_evidencia_suficiente"
    confianca: str  # "alta" (camadas disponíveis concordam) | "baixa" (alguma diverge)
    media_diferenca: float
    ic95_diferenca: tuple[float, float]
    t_p_valor: float
    wilcoxon_p_valor: float
    alfa: float
    justificativa: str
    divergencia: str | None = None
    correcao: CorrecaoMultipla | None = None
    bootstrap: BootstrapEmBloco | None = None
    posterior: PosteriorBayesiano | None = None
    camadas_extras: dict = field(default_factory=dict)


def _leitura_bayesiana(posterior: PosteriorBayesiano) -> str:
    """Classifica a posterior num veredito comparável ao frequentista, exigindo alta
    confiança (LIMIAR_CONFIANCA_BAYESIANA) pra não tratar uma leitura ambígua como
    divergência real."""
    p = posterior.probabilidade_variante_melhor
    if p >= LIMIAR_CONFIANCA_BAYESIANA:
        return "escalar"
    if p <= 1 - LIMIAR_CONFIANCA_BAYESIANA:
        return "manter_baseline"
    return "sem_evidencia_suficiente"


def decidir(
    comparacao: ComparacaoPareada,
    alfa: float = ALFA_PADRAO,
    correcao: CorrecaoMultipla | None = None,
    bootstrap: BootstrapEmBloco | None = None,
    posterior: PosteriorBayesiano | None = None,
) -> Decisao:
    """Decide o veredito de um grupo variante a partir do resultado frequentista (Fase 4),
    reconciliado com as camadas extras opcionais quando presentes (Fase 13):

    - `correcao` (Benjamini-Hochberg, Fase 10): quando informada, a significância corrigida
      (`significativo_corrigido`) substitui a significância crua de t/Wilcoxon como base do
      veredito — um lote grande de testes exige o critério mais conservador.
    - `bootstrap` (Fase 11): quando informado, se o IC do bootstrap em bloco discordar da
      conclusão frequentista (contém zero onde o frequentista viu significância, ou vice-versa),
      a confiança cai para "baixa" — sinal de que a autocorrelação pode estar inflando o
      resultado do teste pareado.
    - `posterior` (Bayesiano, Fase 12): quando informado, compara a leitura bayesiana (P(variante
      melhor) acima/abaixo de `LIMIAR_CONFIANCA_BAYESIANA`) com o veredito frequentista. Se
      divergirem, `Decisao.divergencia` é preenchido com uma frase explícita — nunca fica
      implícito no relatório.

    Sem nenhuma camada extra, o comportamento é idêntico à versão mínima (Fase 5).
    """
    t_significativo = comparacao.t_p_valor < alfa
    w_significativo = comparacao.wilcoxon_p_valor < alfa

    if correcao is not None:
        significativo = correcao.significativo_corrigido
        base_justificativa = (
            f"após correção de Benjamini-Hochberg para múltiplas comparações (t ajustado="
            f"{correcao.t_p_valor_ajustado:.4f}, Wilcoxon ajustado={correcao.wilcoxon_p_valor_ajustado:.4f})"
        )
    elif t_significativo and w_significativo:
        significativo = True
        base_justificativa = (
            f"teste t (p={comparacao.t_p_valor:.4f}) e Wilcoxon (p={comparacao.wilcoxon_p_valor:.4f}) "
            "concordam"
        )
    elif not t_significativo and not w_significativo:
        significativo = False
        base_justificativa = (
            f"teste t (p={comparacao.t_p_valor:.4f}) e Wilcoxon (p={comparacao.wilcoxon_p_valor:.4f}) "
            "concordam"
        )
    else:
        significativo = False
        base_justificativa = None

    if significativo:
        confianca = "alta"
        veredito = "escalar" if comparacao.media_diferenca > 0 else "manter_baseline"
        justificativa = (
            f"{base_justificativa}: diferença média de {comparacao.media_diferenca:+.2f} é "
            "estatisticamente significativa."
        )
    elif base_justificativa is not None:
        confianca = "alta"
        veredito = "sem_evidencia_suficiente"
        justificativa = f"{base_justificativa}: sem diferença estatisticamente significativa."
    else:
        confianca = "baixa"
        veredito = "sem_evidencia_suficiente"
        justificativa = (
            f"teste t (p={comparacao.t_p_valor:.4f}) e Wilcoxon (p={comparacao.wilcoxon_p_valor:.4f}) "
            "divergem sobre significância — tratado como inconclusivo até haver mais dados ou uma "
            "camada de robustez adicional para desempatar."
        )

    if bootstrap is not None:
        bootstrap_concorda = (
            (significativo and not bootstrap.contem_zero)
            or (not significativo and bootstrap.contem_zero)
        )
        if not bootstrap_concorda:
            confianca = "baixa"
            justificativa += (
                f" Ressalva: o bootstrap em bloco (robusto a autocorrelação) deu IC95 "
                f"({bootstrap.ic95_diferenca[0]:.2f}, {bootstrap.ic95_diferenca[1]:.2f}), que "
                f"{'contém' if bootstrap.contem_zero else 'não contém'} zero — diverge da leitura "
                "do teste pareado, possível sinal de autocorrelação inflando o resultado."
            )

    divergencia = None
    if posterior is not None:
        leitura_bayesiana = _leitura_bayesiana(posterior)
        if leitura_bayesiana != veredito and leitura_bayesiana != "sem_evidencia_suficiente":
            p = posterior.probabilidade_variante_melhor
            chance, quem = (p, comparacao.grupo_variante) if p >= 0.5 else (1 - p, comparacao.grupo_baseline)
            divergencia = (
                f"divergência entre camadas: o veredito frequentista foi '{veredito}', mas a "
                f"leitura bayesiana aponta {chance:.1%} de chance de {quem} ser melhor "
                f"(≥{LIMIAR_CONFIANCA_BAYESIANA:.0%} de confiança) — reconciliar manualmente antes "
                "de agir sobre esta decisão."
            )
            confianca = "baixa"

    camadas_extras: dict = {}
    if correcao is not None:
        camadas_extras["correcao_multipla"] = correcao
    if bootstrap is not None:
        camadas_extras["bootstrap"] = bootstrap
    if posterior is not None:
        camadas_extras["bayesiano"] = posterior

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
        divergencia=divergencia,
        correcao=correcao,
        bootstrap=bootstrap,
        posterior=posterior,
        camadas_extras=camadas_extras,
    )


def decidir_todos(
    comparacoes: list[ComparacaoPareada],
    alfa: float = ALFA_PADRAO,
    correcoes: list[CorrecaoMultipla] | None = None,
    bootstraps: list[BootstrapEmBloco] | None = None,
    posteriores: list[PosteriorBayesiano] | None = None,
) -> list[Decisao]:
    """Aplica `decidir` a cada comparação, casando as camadas extras opcionais (se
    informadas) por `(parceiro, grupo_variante)` — a mesma chave usada por
    `comparar_todos_os_grupos`, `corrigir_multiplas_comparacoes`, `bootstrap_todos_os_grupos`
    e `posterior_todos_os_grupos`, então as listas não precisam estar na mesma ordem nem
    ter a mesma cobertura da lista de comparações."""

    def _chave(obj) -> tuple[str, str]:
        return (obj.parceiro, obj.grupo_variante) if hasattr(obj, "grupo_variante") else (
            obj.comparacao.parceiro,
            obj.comparacao.grupo_variante,
        )

    mapa_correcoes = {_chave(c): c for c in correcoes} if correcoes else {}
    mapa_bootstraps = {_chave(b): b for b in bootstraps} if bootstraps else {}
    mapa_posteriores = {_chave(p): p for p in posteriores} if posteriores else {}

    return [
        decidir(
            comparacao,
            alfa=alfa,
            correcao=mapa_correcoes.get((comparacao.parceiro, comparacao.grupo_variante)),
            bootstrap=mapa_bootstraps.get((comparacao.parceiro, comparacao.grupo_variante)),
            posterior=mapa_posteriores.get((comparacao.parceiro, comparacao.grupo_variante)),
        )
        for comparacao in comparacoes
    ]
