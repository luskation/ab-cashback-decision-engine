import numpy as np
import pandas as pd
import pytest

from engine.stats_frequentist import ParDadosInsuficientesError
from engine.stats_robustness import (
    bootstrap_em_bloco,
    bootstrap_todos_os_grupos,
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


def test_bootstrap_em_bloco_detecta_efeito_positivo_estavel():
    datas = pd.date_range("2024-01-01", periods=40)
    rng = np.random.default_rng(7)
    comissao_base = 1000 + rng.normal(0, 15, 40)
    comissao_var = comissao_base + 200  # variante gera bem mais margem, diferença estável
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 40, comissao=comissao_base, cashback=[300.0] * 40),
        "Grupo 2": _serie_base(datas, compradores=[100] * 40, comissao=comissao_var, cashback=[300.0] * 40),
    })
    resultado = bootstrap_em_bloco(df, "Parceiro X", "Grupo 2", n_reamostragens=500, seed=1)
    assert resultado.grupo_baseline == "Grupo 1"
    assert resultado.n_dias_pareados == 40
    assert resultado.media_diferenca == pytest.approx(200, abs=5)
    assert resultado.contem_zero is False
    assert resultado.ic95_diferenca[0] > 0


def test_bootstrap_em_bloco_reproduzivel_com_mesma_seed():
    datas = pd.date_range("2024-01-01", periods=30)
    rng = np.random.default_rng(3)
    comissao_base = 1000 + rng.normal(0, 40, 30)
    comissao_var = 1000 + rng.normal(0, 40, 30)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 30, comissao=comissao_base, cashback=[0.0] * 30),
        "Grupo 2": _serie_base(datas, compradores=[100] * 30, comissao=comissao_var, cashback=[0.0] * 30),
    })
    r1 = bootstrap_em_bloco(df, "Parceiro X", "Grupo 2", n_reamostragens=300, seed=9)
    r2 = bootstrap_em_bloco(df, "Parceiro X", "Grupo 2", n_reamostragens=300, seed=9)
    assert r1.ic95_diferenca == r2.ic95_diferenca


def test_bootstrap_em_bloco_levanta_erro_com_dados_insuficientes():
    datas_base = pd.date_range("2024-01-01", periods=10)
    datas_var = pd.date_range("2024-02-01", periods=1)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas_base, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
        "Grupo 2": _serie_base(datas_var, compradores=[100], comissao=[1000.0], cashback=[200.0]),
    })
    with pytest.raises(ParDadosInsuficientesError):
        bootstrap_em_bloco(df, "Parceiro X", "Grupo 2")


def test_bootstrap_em_bloco_baseline_igual_variante_levanta_erro():
    datas = pd.date_range("2024-01-01", periods=5)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 5, comissao=[1000.0] * 5, cashback=[200.0] * 5),
    })
    with pytest.raises(ValueError):
        bootstrap_em_bloco(df, "Parceiro X", "Grupo 1", grupo_baseline="Grupo 1")


def test_bootstrap_todos_os_grupos_cobre_teste_com_tres_variantes():
    datas = pd.date_range("2024-01-01", periods=15)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 15, comissao=[1000.0] * 15, cashback=[200.0] * 15),
        "Grupo 2": _serie_base(datas, compradores=[100] * 15, comissao=[1100.0] * 15, cashback=[200.0] * 15),
        "Grupo 3": _serie_base(datas, compradores=[100] * 15, comissao=[900.0] * 15, cashback=[200.0] * 15),
    })
    resultados = bootstrap_todos_os_grupos(df, n_reamostragens=200)
    variantes = {r.grupo_variante for r in resultados}
    assert variantes == {"Grupo 2", "Grupo 3"}
    assert all(r.grupo_baseline == "Grupo 1" for r in resultados)


def test_bootstrap_todos_os_grupos_ignora_parceiro_com_um_grupo_so():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro Y", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 10, comissao=[1000.0] * 10, cashback=[200.0] * 10),
    })
    assert bootstrap_todos_os_grupos(df) == []


def test_bootstrap_em_bloco_e_mais_conservador_que_bootstrap_ingenuo_com_autocorrelacao():
    """Série com autocorrelação forte (blocos de 10 dias com o mesmo choque) mas sem efeito
    real (média verdadeira do choque = 0). Um bootstrap ingênuo (reamostragem dia-a-dia,
    i.i.d.) trata os 100 dias como 100 observações independentes quando, na prática, são ~10
    blocos independentes — por isso tende a produzir um IC artificialmente estreito. O
    bootstrap em bloco, ao reamostrar blocos inteiros, preserva essa estrutura e produz um IC
    mais largo e mais honesto: contém o zero, e é mais largo que o do bootstrap ingênuo."""
    rng = np.random.default_rng(123)
    n_blocos, tamanho = 10, 10
    n = n_blocos * tamanho
    choques_por_bloco = rng.normal(0, 5, n_blocos)  # sem efeito médio real
    diffs = np.repeat(choques_por_bloco, tamanho)  # autocorrelação perfeita dentro do bloco

    datas = pd.date_range("2024-01-01", periods=n)
    comissao_base = 1000 + rng.normal(0, 0.01, n)  # ruído dia-a-dia desprezível
    comissao_var = comissao_base + diffs
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * n, comissao=comissao_base, cashback=[0.0] * n),
        "Grupo 2": _serie_base(datas, compradores=[100] * n, comissao=comissao_var, cashback=[0.0] * n),
    })

    resultado = bootstrap_em_bloco(
        df, "Parceiro X", "Grupo 2", tamanho_bloco=tamanho, n_reamostragens=1000, seed=1
    )
    assert resultado.contem_zero is True

    rng_ingenuo = np.random.default_rng(1)
    medias_ingenuas = np.array(
        [rng_ingenuo.choice(diffs, size=n, replace=True).mean() for _ in range(1000)]
    )
    ic_ingenuo = np.percentile(medias_ingenuas, [2.5, 97.5])
    largura_ingenua = ic_ingenuo[1] - ic_ingenuo[0]
    largura_bloco = resultado.ic95_diferenca[1] - resultado.ic95_diferenca[0]
    assert largura_bloco > largura_ingenua
