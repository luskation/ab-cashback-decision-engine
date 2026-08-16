from pathlib import Path

import pytest

from engine.decision import decidir, decidir_todos
from engine.stats_frequentist import ComparacaoPareada


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


def test_decidir_carrega_camadas_extras_sem_exigir_que_existam():
    sem_extras = decidir(_comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001))
    assert sem_extras.camadas_extras == {}

    com_extras = decidir(
        _comparacao(media_diferenca=200.0, t_p_valor=0.001, wilcoxon_p_valor=0.001),
        camadas_extras={"bayesiano": {"p_variante_melhor": 0.98}},
    )
    assert com_extras.camadas_extras == {"bayesiano": {"p_variante_melhor": 0.98}}


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
