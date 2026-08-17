from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.stats_frequentist import (
    ComparacaoPareada,
    ParDadosInsuficientesError,
    calcular_margem,
    comparar_grupo,
    comparar_todos_os_grupos,
    corrigir_benjamini_hochberg,
    corrigir_multiplas_comparacoes,
    inferir_grupo_baseline,
)


def _dataset(parceiro: str, grupos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    partes = []
    for grupo, parcial in grupos.items():
        parcial = parcial.copy()
        parcial["grupo"] = grupo
        parcial["parceiro"] = parceiro
        partes.append(parcial)
    return pd.concat(partes, ignore_index=True)


def _serie_base(datas, compradores, comissao, cashback, vendas_totais=None) -> pd.DataFrame:
    n = len(datas)
    return pd.DataFrame({
        "data": pd.to_datetime(datas),
        "compradores": compradores,
        "comissao": comissao,
        "cashback": cashback,
        "vendas_totais": vendas_totais if vendas_totais is not None else [5000.0] * n,
    })


def test_calcular_margem_e_comissao_menos_cashback():
    df = pd.DataFrame({"comissao": [100.0, 200.0], "cashback": [30.0, 50.0]})
    margem = calcular_margem(df)
    assert margem.tolist() == [70.0, 150.0]


def test_inferir_grupo_baseline_pega_o_menor_rotulo():
    assert inferir_grupo_baseline(["Grupo 2", "Grupo 1", "Grupo 3"]) == "Grupo 1"


def test_comparar_grupo_detecta_variante_melhor():
    datas = pd.date_range("2024-01-01", periods=40)
    rng = np.random.default_rng(7)
    comissao_base = 1000 + rng.normal(0, 15, 40)
    comissao_var = comissao_base + 200  # variante gera bem mais margem, diferença estável
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 40, comissao=comissao_base, cashback=[300.0] * 40),
        "Grupo 2": _serie_base(datas, compradores=[100] * 40, comissao=comissao_var, cashback=[300.0] * 40),
    })
    resultado = comparar_grupo(df, "Parceiro X", "Grupo 2")
    assert resultado.grupo_baseline == "Grupo 1"
    assert resultado.grupo_variante == "Grupo 2"
    assert resultado.n_dias_pareados == 40
    assert resultado.media_diferenca == pytest.approx(200, abs=5)
    assert resultado.t_p_valor < 0.01
    assert resultado.wilcoxon_p_valor < 0.01
    assert resultado.ic95_diferenca[0] > 0  # variante melhor com confiança


def test_comparar_grupo_nao_significativo_quando_e_so_ruido():
    datas = pd.date_range("2024-01-01", periods=30)
    rng = np.random.default_rng(1)
    comissao_base = 1000 + rng.normal(0, 50, 30)
    comissao_var = 1000 + rng.normal(0, 50, 30)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 30, comissao=comissao_base, cashback=[200.0] * 30),
        "Grupo 2": _serie_base(datas, compradores=[100] * 30, comissao=comissao_var, cashback=[200.0] * 30),
    })
    resultado = comparar_grupo(df, "Parceiro X", "Grupo 2")
    assert resultado.t_p_valor > 0.05


def test_comparar_grupo_pareia_so_datas_em_comum():
    datas_base = pd.date_range("2024-01-01", periods=10)
    datas_var = pd.date_range("2024-01-05", periods=10)  # só 6 dias em comum
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas_base, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
        "Grupo 2": _serie_base(datas_var, compradores=[100] * 10, comissao=[1100.0] * 10, cashback=[200.0] * 10),
    })
    resultado = comparar_grupo(df, "Parceiro X", "Grupo 2")
    assert resultado.n_dias_pareados == 6


def test_comparar_grupo_levanta_erro_com_dados_insuficientes():
    datas_base = pd.date_range("2024-01-01", periods=10)
    datas_var = pd.date_range("2024-02-01", periods=1)  # nenhum dia em comum
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas_base, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
        "Grupo 2": _serie_base(datas_var, compradores=[100], comissao=[1000.0], cashback=[200.0]),
    })
    with pytest.raises(ParDadosInsuficientesError):
        comparar_grupo(df, "Parceiro X", "Grupo 2")


def test_comparar_grupo_baseline_igual_variante_levanta_erro():
    datas = pd.date_range("2024-01-01", periods=5)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 5, comissao=[1000.0] * 5, cashback=[200.0] * 5),
    })
    with pytest.raises(ValueError):
        comparar_grupo(df, "Parceiro X", "Grupo 1", grupo_baseline="Grupo 1")


def test_comparar_grupo_com_diferencas_todas_zero_nao_quebra():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
        "Grupo 2": _serie_base(datas, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
    })
    resultado = comparar_grupo(df, "Parceiro X", "Grupo 2")
    assert resultado.media_diferenca == 0
    # scipy não trata "todas as diferenças zero" como erro — devolve p=1.0 (sem evidência de diferença).
    assert resultado.wilcoxon_p_valor == 1.0


def test_comparar_todos_os_grupos_cobre_teste_com_tres_variantes():
    datas = pd.date_range("2024-01-01", periods=15)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 15, comissao=[1000.0] * 15, cashback=[200.0] * 15),
        "Grupo 2": _serie_base(datas, compradores=[100] * 15, comissao=[1100.0] * 15, cashback=[200.0] * 15),
        "Grupo 3": _serie_base(datas, compradores=[100] * 15, comissao=[900.0] * 15, cashback=[200.0] * 15),
    })
    resultados = comparar_todos_os_grupos(df)
    variantes = {r.grupo_variante for r in resultados}
    assert variantes == {"Grupo 2", "Grupo 3"}
    assert all(r.grupo_baseline == "Grupo 1" for r in resultados)


def test_comparar_todos_os_grupos_ignora_parceiro_com_um_grupo_so():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro Y", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
    })
    assert comparar_todos_os_grupos(df) == []


def _comparacao_dummy(parceiro: str, grupo_variante: str, t_p_valor: float, wilcoxon_p_valor: float) -> ComparacaoPareada:
    """Constrói uma ComparacaoPareada só com os campos relevantes pra correção múltipla —
    os demais são preenchidos com valores neutros, sem afetar o resultado do teste."""
    return ComparacaoPareada(
        parceiro=parceiro,
        grupo_baseline="Grupo 1",
        grupo_variante=grupo_variante,
        coluna="margem",
        n_dias_pareados=30,
        media_baseline=1000.0,
        media_variante=1050.0,
        media_diferenca=50.0,
        desvio_padrao_diferenca=10.0,
        ic95_diferenca=(10.0, 90.0),
        t_estatistica=2.5,
        t_p_valor=t_p_valor,
        wilcoxon_estatistica=100.0,
        wilcoxon_p_valor=wilcoxon_p_valor,
    )


def test_corrigir_benjamini_hochberg_lista_vazia():
    assert corrigir_benjamini_hochberg([]) == []


def test_corrigir_benjamini_hochberg_valor_unico_fica_igual():
    p_ajustado, significativo = corrigir_benjamini_hochberg([0.03])[0]
    assert p_ajustado == pytest.approx(0.03)
    assert significativo is True


def test_corrigir_benjamini_hochberg_contra_calculo_manual():
    # p = [0.001, 0.002, 0.003, 0.9], m=4 — q(i) = p(i)*m/i em ordem: 0.004, 0.004, 0.004, 0.9
    # (cummin do maior rank pro menor não altera nada aqui, já é monótono)
    resultado = corrigir_benjamini_hochberg([0.001, 0.002, 0.003, 0.9], alfa=0.05)
    ajustados = [p for p, _ in resultado]
    assert ajustados[0] == pytest.approx(0.004)
    assert ajustados[1] == pytest.approx(0.004)
    assert ajustados[2] == pytest.approx(0.004)
    assert ajustados[3] == pytest.approx(0.9)
    assert [sig for _, sig in resultado] == [True, True, True, False]


def test_corrigir_benjamini_hochberg_desfaz_significancia_isolada_em_lote_ruidoso():
    # um p-valor aparentemente significativo (0.03) sozinho, cercado de 4 testes claramente
    # sem efeito (0.5) — é exatamente o cenário que a correção existe para pegar: rodando
    # "dezenas de testes por mês", 1 em 5 "significativo" isolado é mais coerente com falso
    # positivo do que com efeito real.
    p_valores = [0.03, 0.5, 0.5, 0.5, 0.5]
    resultado = corrigir_benjamini_hochberg(p_valores, alfa=0.05)
    p_ajustado_isolado, significativo_isolado = resultado[0]
    assert p_ajustado_isolado > 0.05  # não sobrevive à correção
    assert significativo_isolado is False
    assert p_ajustado_isolado > p_valores[0]  # correção sempre infla ou mantém, nunca reduz


def test_corrigir_multiplas_comparacoes_lista_vazia():
    assert corrigir_multiplas_comparacoes([]) == []


def test_corrigir_multiplas_comparacoes_exige_concordancia_entre_t_e_wilcoxon():
    comparacoes = [
        _comparacao_dummy("Parceiro X", "Grupo 2", t_p_valor=0.01, wilcoxon_p_valor=0.01),
        _comparacao_dummy("Parceiro Y", "Grupo 2", t_p_valor=0.01, wilcoxon_p_valor=0.5),  # diverge
        _comparacao_dummy("Parceiro Z", "Grupo 2", t_p_valor=0.5, wilcoxon_p_valor=0.5),
    ]
    resultado = corrigir_multiplas_comparacoes(comparacoes, alfa=0.05)
    assert len(resultado) == 3
    assert resultado[1].significativo_corrigido is False  # t e wilcoxon divergem
    assert resultado[2].significativo_corrigido is False  # nenhum dos dois é significativo
    assert resultado[0].comparacao is comparacoes[0]


@pytest.mark.parametrize("arquivo", [
    "dataset_01_parceiroA.csv",
    "dataset_02_parceiroB.csv",
    "dataset_03_parceiroC.csv",
])
def test_comparar_todos_os_grupos_roda_sem_erro_nos_datasets_reais(arquivo):
    from engine.parsing import carregar_csv

    df, _ = carregar_csv(Path(__file__).parent.parent / "data" / arquivo)
    resultados = comparar_todos_os_grupos(df)
    assert len(resultados) >= 1
    for r in resultados:
        assert r.n_dias_pareados > 0
        assert isinstance(r.t_p_valor, float)
