import numpy as np
import pandas as pd
import pytest

from engine.stats_bayesian import (
    posterior_diferenca_margem,
    posterior_todos_os_grupos,
)
from engine.stats_frequentist import ParDadosInsuficientesError, comparar_grupo


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


def test_posterior_diferenca_margem_ic95_coincide_com_teste_t():
    # a seção 2.12 do plano afirma que o IC bayesiano é numericamente igual ao IC do teste t
    # frequentista — mesma suposição de normalidade, fórmula fechada equivalente.
    datas = pd.date_range("2024-01-01", periods=40)
    rng = np.random.default_rng(7)
    comissao_base = 1000 + rng.normal(0, 15, 40)
    comissao_var = comissao_base + 200
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 40, comissao=comissao_base, cashback=[300.0] * 40),
        "Grupo 2": _serie_base(datas, compradores=[100] * 40, comissao=comissao_var, cashback=[300.0] * 40),
    })
    freq = comparar_grupo(df, "Parceiro X", "Grupo 2")
    bayes = posterior_diferenca_margem(df, "Parceiro X", "Grupo 2")

    assert bayes.ic95_diferenca[0] == pytest.approx(freq.ic95_diferenca[0], abs=1e-6)
    assert bayes.ic95_diferenca[1] == pytest.approx(freq.ic95_diferenca[1], abs=1e-6)
    assert bayes.media_diferenca == pytest.approx(freq.media_diferenca)


def test_posterior_diferenca_margem_efeito_positivo_claro():
    datas = pd.date_range("2024-01-01", periods=53)
    rng = np.random.default_rng(3)
    comissao_base = 1000 + rng.normal(0, 20, 53)
    comissao_var = comissao_base - 500  # variante bem pior, diferença estável
    df = _dataset("Parceiro A", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 53, comissao=comissao_base, cashback=[0.0] * 53),
        "Grupo 2": _serie_base(datas, compradores=[100] * 53, comissao=comissao_var, cashback=[0.0] * 53),
    })
    resultado = posterior_diferenca_margem(df, "Parceiro A", "Grupo 2", n_amostras=200_000, seed=1)

    assert resultado.probabilidade_variante_melhor < 0.01  # quase certeza de que Grupo 2 é pior
    assert resultado.perda_esperada_escalar > 0  # escalar o pior grupo custa caro...
    assert resultado.perda_esperada_manter == pytest.approx(0.0, abs=1.0)  # ...manter não custa quase nada


def test_posterior_diferenca_margem_sem_efeito_probabilidade_e_meio():
    # diferença construída com média amostral exatamente zero (ruído menos sua própria média)
    # em vez de confiar em cancelamento por sorte do RNG — com d_media=0 a posterior Student-t
    # fica centrada em 0, então P(mu>0|dados) = 0.5 exato, sem depender de seed.
    datas = pd.date_range("2024-01-01", periods=60)
    rng = np.random.default_rng(11)
    ruido = rng.normal(0, 50, 60)
    diffs = ruido - ruido.mean()
    comissao_base = 1000 + rng.normal(0, 5, 60)
    comissao_var = comissao_base + diffs
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 60, comissao=comissao_base, cashback=[0.0] * 60),
        "Grupo 2": _serie_base(datas, compradores=[100] * 60, comissao=comissao_var, cashback=[0.0] * 60),
    })
    resultado = posterior_diferenca_margem(df, "Parceiro X", "Grupo 2")
    assert resultado.probabilidade_variante_melhor == pytest.approx(0.5, abs=1e-6)


def test_posterior_diferenca_margem_diferencas_identicas_nao_quebra():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
        "Grupo 2": _serie_base(datas, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
    })
    resultado = posterior_diferenca_margem(df, "Parceiro X", "Grupo 2")
    assert resultado.media_diferenca == 0
    assert resultado.probabilidade_variante_melhor == 0.5
    assert resultado.perda_esperada_escalar == 0.0
    assert resultado.perda_esperada_manter == 0.0


def test_posterior_diferenca_margem_levanta_erro_com_dados_insuficientes():
    datas_base = pd.date_range("2024-01-01", periods=10)
    datas_var = pd.date_range("2024-02-01", periods=1)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas_base, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
        "Grupo 2": _serie_base(datas_var, compradores=[100], comissao=[1000.0], cashback=[200.0]),
    })
    with pytest.raises(ParDadosInsuficientesError):
        posterior_diferenca_margem(df, "Parceiro X", "Grupo 2")


def test_posterior_diferenca_margem_baseline_igual_variante_levanta_erro():
    datas = pd.date_range("2024-01-01", periods=5)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 5, comissao=[1000.0] * 5, cashback=[200.0] * 5),
    })
    with pytest.raises(ValueError):
        posterior_diferenca_margem(df, "Parceiro X", "Grupo 1", grupo_baseline="Grupo 1")


def test_posterior_todos_os_grupos_cobre_teste_com_tres_variantes():
    datas = pd.date_range("2024-01-01", periods=15)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 15, comissao=[1000.0] * 15, cashback=[200.0] * 15),
        "Grupo 2": _serie_base(datas, compradores=[100] * 15, comissao=[1100.0] * 15, cashback=[200.0] * 15),
        "Grupo 3": _serie_base(datas, compradores=[100] * 15, comissao=[900.0] * 15, cashback=[200.0] * 15),
    })
    resultados = posterior_todos_os_grupos(df, n_amostras=1000)
    variantes = {r.grupo_variante for r in resultados}
    assert variantes == {"Grupo 2", "Grupo 3"}
    assert all(r.grupo_baseline == "Grupo 1" for r in resultados)


def test_posterior_todos_os_grupos_ignora_parceiro_com_um_grupo_so():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro Y", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
    })
    assert posterior_todos_os_grupos(df) == []
