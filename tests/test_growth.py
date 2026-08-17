from pathlib import Path

import pandas as pd
import pytest

from engine.decision import Decisao
from engine.growth import growth_lens, projetar_impacto, sugerir_proximo_teste


def _dataset(parceiro: str, grupos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    partes = []
    for grupo, parcial in grupos.items():
        parcial = parcial.copy()
        parcial["grupo"] = grupo
        parcial["parceiro"] = parceiro
        partes.append(parcial)
    return pd.concat(partes, ignore_index=True)


def _serie_base(datas, compradores, comissao, cashback, vendas_totais) -> pd.DataFrame:
    return pd.DataFrame({
        "data": pd.to_datetime(datas),
        "compradores": compradores,
        "comissao": comissao,
        "cashback": cashback,
        "vendas_totais": vendas_totais,
    })


def _decisao(veredito, parceiro="Parceiro X", baseline="Grupo 1", variante="Grupo 2") -> Decisao:
    return Decisao(
        parceiro=parceiro,
        grupo_baseline=baseline,
        grupo_variante=variante,
        veredito=veredito,
        confianca="alta",
        media_diferenca=100.0,
        ic95_diferenca=(50.0, 150.0),
        t_p_valor=0.001,
        wilcoxon_p_valor=0.001,
        alfa=0.05,
        justificativa="teste",
    )


# --- projetar_impacto -------------------------------------------------------------

def test_projetar_impacto_variante_com_mais_margem_por_comprador_da_impacto_positivo():
    datas = pd.date_range("2024-01-01", periods=30)
    n = 30
    # baseline: 100 compradores/dia, margem/comprador = (1000-200)/100 = 8
    # variante: 100 compradores/dia, margem/comprador = (1400-200)/100 = 12 -> +4/comprador
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, [100] * n, [1000.0] * n, [200.0] * n, [5000.0] * n),
        "Grupo 2": _serie_base(datas, [100] * n, [1400.0] * n, [200.0] * n, [5000.0] * n),
    })
    projecao = projetar_impacto(df, "Parceiro X", "Grupo 1", "Grupo 2")
    assert projecao.diferenca_margem_por_comprador == pytest.approx(4.0)
    assert projecao.compradores_medios_dia_teste == pytest.approx(200.0)  # soma dos 2 grupos
    assert projecao.impacto_diario_estimado == pytest.approx(800.0)  # 4 * 200
    assert projecao.impacto_diario_ic95[0] <= projecao.impacto_diario_estimado <= projecao.impacto_diario_ic95[1]


def test_projetar_impacto_ignora_dias_com_zero_compradores():
    datas = pd.date_range("2024-01-01", periods=10)
    compradores = [0] + [100] * 9
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores, [1000.0] * 10, [200.0] * 10, [5000.0] * 10),
        "Grupo 2": _serie_base(datas, compradores, [1200.0] * 10, [200.0] * 10, [5000.0] * 10),
    })
    projecao = projetar_impacto(df, "Parceiro X", "Grupo 1", "Grupo 2")
    assert projecao.diferenca_margem_por_comprador == pytest.approx(2.0)


# --- sugerir_proximo_teste ---------------------------------------------------------

def test_sugerir_proximo_teste_com_um_unico_patamar_nao_inventa_numero():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, [100] * 10, [1000.0] * 10, [200.0] * 10, [10000.0] * 10),
    })
    sugestao = sugerir_proximo_teste(df, "Parceiro X")
    assert "2.0%" in sugestao  # 200/10000, único patamar existente
    assert "segundo patamar" in sugestao


def test_sugerir_proximo_teste_com_dois_patamares_usa_o_passo_do_historico():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, [100] * 10, [1000.0] * 10, [500.0] * 10, [10000.0] * 10),  # 5%
        "Grupo 2": _serie_base(datas, [100] * 10, [1000.0] * 10, [1000.0] * 10, [10000.0] * 10),  # 10%
    })
    sugestao = sugerir_proximo_teste(df, "Parceiro X")
    assert "10.0%" in sugestao  # maior patamar já testado
    assert "15.0%" in sugestao  # 10% + passo de 5pp


def test_sugerir_proximo_teste_sem_historico_do_parceiro():
    df = pd.DataFrame(columns=["data", "grupo", "parceiro", "compradores", "comissao", "cashback", "vendas_totais"])
    assert sugerir_proximo_teste(df, "Parceiro Inexistente") == (
        "histórico insuficiente para sugerir um próximo patamar de cashback."
    )


# --- growth_lens ---------------------------------------------------------------------

def test_growth_lens_calcula_projecao_quando_veredito_e_escalar():
    datas = pd.date_range("2024-01-01", periods=30)
    n = 30
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, [100] * n, [1000.0] * n, [200.0] * n, [5000.0] * n),
        "Grupo 2": _serie_base(datas, [100] * n, [1400.0] * n, [200.0] * n, [5000.0] * n),
    })
    lente = growth_lens(df, _decisao("escalar"))
    assert lente.projecao_impacto is not None
    assert lente.projecao_impacto.impacto_diario_estimado > 0
    assert lente.sugestao_proximo_teste  # não vazio


def test_growth_lens_nao_calcula_projecao_sem_vencedor():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, [100] * 10, [1000.0] * 10, [200.0] * 10, [5000.0] * 10),
        "Grupo 2": _serie_base(datas, [100] * 10, [1000.0] * 10, [200.0] * 10, [5000.0] * 10),
    })
    for veredito in ["manter_baseline", "sem_evidencia_suficiente"]:
        lente = growth_lens(df, _decisao(veredito))
        assert lente.projecao_impacto is None
        assert lente.sugestao_proximo_teste


@pytest.mark.parametrize("arquivo", [
    "dataset_01_parceiroA.csv",
    "dataset_02_parceiroB.csv",
    "dataset_03_parceiroC.csv",
])
def test_growth_lens_roda_sem_erro_nos_datasets_reais(arquivo):
    from engine.decision import decidir_todos
    from engine.parsing import carregar_csv
    from engine.stats_frequentist import comparar_todos_os_grupos

    df, _ = carregar_csv(Path(__file__).parent.parent / "data" / arquivo)
    for decisao in decidir_todos(comparar_todos_os_grupos(df)):
        lente = growth_lens(df, decisao)
        assert lente.sugestao_proximo_teste
        if decisao.veredito == "escalar":
            assert lente.projecao_impacto is not None
