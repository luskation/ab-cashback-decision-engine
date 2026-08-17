from pathlib import Path

import pytest

from engine.decision import decidir, decidir_todos
from engine.stats_bayesian import PosteriorBayesiano
from engine.stats_frequentist import ComparacaoPareada, CorrecaoMultipla
from engine.stats_robustness import BootstrapEmBloco


def _comparacao(media_diferenca, t_p_valor, wilcoxon_p_valor, ic95=(0.0, 0.0)) -> ComparacaoPareada:
    return ComparacaoPareada(
        parceiro="Parceiro X",
        grupo_baseline="Grupo 1",
        grupo_variante="Grupo 2",
        coluna="margem",
        n_dias_pareados=30,
        media_baseline=1000.0,
        media_variante=1000.0 + media_diferenca,
        media_diferenca=media_diferenca,
        desvio_padrao_diferenca=50.0,
        ic95_diferenca=ic95,
        t_estatistica=3.0,
        t_p_valor=t_p_valor,
        wilcoxon_estatistica=10.0,
        wilcoxon_p_valor=wilcoxon_p_valor,
    )


def _correcao(comparacao: ComparacaoPareada, significativo_corrigido: bool) -> CorrecaoMultipla:
    return CorrecaoMultipla(
        comparacao=comparacao,
        t_p_valor_ajustado=0.04 if significativo_corrigido else 0.20,
        wilcoxon_p_valor_ajustado=0.04 if significativo_corrigido else 0.20,
        significativo_corrigido=significativo_corrigido,
    )


def _bootstrap(comparacao: ComparacaoPareada, contem_zero: bool) -> BootstrapEmBloco:
    ic95 = (-10.0, 10.0) if contem_zero else (comparacao.media_diferenca - 5, comparacao.media_diferenca + 5)
    return BootstrapEmBloco(
        parceiro=comparacao.parceiro,
        grupo_baseline=comparacao.grupo_baseline,
        grupo_variante=comparacao.grupo_variante,
        coluna=comparacao.coluna,
        n_dias_pareados=comparacao.n_dias_pareados,
        tamanho_bloco=3,
        n_reamostragens=2000,
        media_diferenca=comparacao.media_diferenca,
        ic95_diferenca=ic95,
        contem_zero=contem_zero,
    )


def _posterior(comparacao: ComparacaoPareada, probabilidade_variante_melhor: float) -> PosteriorBayesiano:
    return PosteriorBayesiano(
        parceiro=comparacao.parceiro,
        grupo_baseline=comparacao.grupo_baseline,
        grupo_variante=comparacao.grupo_variante,
        coluna=comparacao.coluna,
        n_dias_pareados=comparacao.n_dias_pareados,
        media_diferenca=comparacao.media_diferenca,
        ic95_diferenca=comparacao.ic95_diferenca,
        probabilidade_variante_melhor=probabilidade_variante_melhor,
        perda_esperada_escalar=42.0,
        perda_esperada_manter=7.0,
    )


def test_decidir_escalar_quando_ambos_significativos_e_diferenca_positiva():
    decisao = decidir(_comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.002))
    assert decisao.veredito == "escalar"
    assert decisao.confianca == "alta"


def test_decidir_manter_baseline_quando_ambos_significativos_e_diferenca_negativa():
    decisao = decidir(_comparacao(media_diferenca=-200.0, t_p_valor=0.001, wilcoxon_p_valor=0.002))
    assert decisao.veredito == "manter_baseline"
    assert decisao.confianca == "alta"


def test_decidir_sem_evidencia_quando_ambos_nao_significativos():
    decisao = decidir(_comparacao(media_diferenca=10.0, t_p_valor=0.6, wilcoxon_p_valor=0.7))
    assert decisao.veredito == "sem_evidencia_suficiente"
    assert decisao.confianca == "alta"


def test_decidir_fica_inconclusivo_e_baixa_confianca_quando_testes_divergem():
    decisao = decidir(_comparacao(media_diferenca=150.0, t_p_valor=0.03, wilcoxon_p_valor=0.2))
    assert decisao.veredito == "sem_evidencia_suficiente"
    assert decisao.confianca == "baixa"


def test_decidir_respeita_alfa_customizado():
    comparacao = _comparacao(media_diferenca=100.0, t_p_valor=0.08, wilcoxon_p_valor=0.09)
    assert decidir(comparacao, alfa=0.05).veredito == "sem_evidencia_suficiente"
    assert decidir(comparacao, alfa=0.10).veredito == "escalar"


def test_decidir_sem_camadas_extras_nao_exige_que_existam():
    decisao = decidir(_comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001))
    assert decisao.camadas_extras == {}
    assert decisao.correcao is None
    assert decisao.bootstrap is None
    assert decisao.posterior is None
    assert decisao.divergencia is None


def test_decidir_correcao_bh_substitui_significancia_crua_para_nao_significativo():
    comparacao = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001)
    correcao = _correcao(comparacao, significativo_corrigido=False)
    decisao = decidir(comparacao, correcao=correcao)
    assert decisao.veredito == "sem_evidencia_suficiente"
    assert decisao.confianca == "alta"
    assert decisao.camadas_extras["correcao_multipla"] is correcao


def test_decidir_correcao_bh_confirma_significancia_crua():
    comparacao = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001)
    correcao = _correcao(comparacao, significativo_corrigido=True)
    decisao = decidir(comparacao, correcao=correcao)
    assert decisao.veredito == "escalar"
    assert decisao.confianca == "alta"


def test_decidir_bootstrap_discordando_derruba_confianca_para_baixa():
    comparacao = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.002)
    bootstrap = _bootstrap(comparacao, contem_zero=True)
    decisao = decidir(comparacao, bootstrap=bootstrap)
    assert decisao.veredito == "escalar"
    assert decisao.confianca == "baixa"
    assert "bootstrap" in decisao.justificativa.lower()


def test_decidir_bootstrap_concordando_mantem_confianca_alta():
    comparacao = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.002)
    bootstrap = _bootstrap(comparacao, contem_zero=False)
    decisao = decidir(comparacao, bootstrap=bootstrap)
    assert decisao.veredito == "escalar"
    assert decisao.confianca == "alta"


def test_decidir_posterior_divergente_marca_divergencia_e_baixa_confianca():
    comparacao = _comparacao(media_diferenca=10.0, t_p_valor=0.6, wilcoxon_p_valor=0.7)
    posterior = _posterior(comparacao, probabilidade_variante_melhor=0.99)
    decisao = decidir(comparacao, posterior=posterior)
    assert decisao.veredito == "sem_evidencia_suficiente"  # bayesiano não sobrescreve o veredito
    assert decisao.confianca == "baixa"
    assert decisao.divergencia is not None
    assert "bayesiana" in decisao.divergencia.lower()


def test_decidir_posterior_concordante_nao_marca_divergencia():
    comparacao = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.002)
    posterior = _posterior(comparacao, probabilidade_variante_melhor=0.99)
    decisao = decidir(comparacao, posterior=posterior)
    assert decisao.veredito == "escalar"
    assert decisao.divergencia is None
    assert decisao.confianca == "alta"


def test_decidir_posterior_ambiguo_nao_conta_como_divergencia():
    comparacao = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.002)
    posterior = _posterior(comparacao, probabilidade_variante_melhor=0.6)  # abaixo do limiar de confiança
    decisao = decidir(comparacao, posterior=posterior)
    assert decisao.veredito == "escalar"
    assert decisao.divergencia is None


def test_decidir_todos_casa_camadas_extras_por_parceiro_e_grupo_variante():
    comparacao_significativa = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001)
    comparacao_fraca = _comparacao(media_diferenca=-50.0, t_p_valor=0.5, wilcoxon_p_valor=0.6)
    comparacao_fraca.grupo_variante = "Grupo 3"

    correcao = _correcao(comparacao_significativa, significativo_corrigido=False)
    posterior = _posterior(comparacao_fraca, probabilidade_variante_melhor=0.02)

    decisoes = decidir_todos(
        [comparacao_significativa, comparacao_fraca],
        correcoes=[correcao],
        posteriores=[posterior],
    )

    decisao_significativa = next(d for d in decisoes if d.grupo_variante == "Grupo 2")
    decisao_fraca = next(d for d in decisoes if d.grupo_variante == "Grupo 3")

    assert decisao_significativa.veredito == "sem_evidencia_suficiente"  # BH reverteu a significância
    assert decisao_fraca.posterior is posterior
    assert decisao_fraca.divergencia is not None  # bayesiano aponta baseline melhor, freq. é inconclusivo


def test_decidir_todos_aplica_a_lista_de_comparacoes():
    comparacoes = [
        _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001),
        _comparacao(media_diferenca=-50.0, t_p_valor=0.5, wilcoxon_p_valor=0.6),
    ]
    decisoes = decidir_todos(comparacoes)
    assert [d.veredito for d in decisoes] == ["escalar", "sem_evidencia_suficiente"]


def test_decisao_preserva_dados_da_comparacao_original():
    comparacao = _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001, ic95=(50.0, 350.0))
    decisao = decidir(comparacao)
    assert decisao.parceiro == "Parceiro X"
    assert decisao.grupo_baseline == "Grupo 1"
    assert decisao.grupo_variante == "Grupo 2"
    assert decisao.ic95_diferenca == (50.0, 350.0)


@pytest.mark.parametrize("arquivo", [
    "dataset_01_parceiroA.csv",
    "dataset_02_parceiroB.csv",
    "dataset_03_parceiroC.csv",
])
def test_decidir_todos_roda_sem_erro_nos_datasets_reais(arquivo):
    from engine.parsing import carregar_csv
    from engine.stats_frequentist import comparar_todos_os_grupos

    df, _ = carregar_csv(Path(__file__).parent.parent / "data" / arquivo)
    comparacoes = comparar_todos_os_grupos(df)
    decisoes = decidir_todos(comparacoes)
    assert len(decisoes) == len(comparacoes)
    for decisao in decisoes:
        assert decisao.veredito in {"escalar", "manter_baseline", "sem_evidencia_suficiente"}
        assert decisao.confianca in {"alta", "baixa"}
