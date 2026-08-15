import numpy as np
import pandas as pd
import pytest

from engine.quality import (
    checar_bug_instrumentacao,
    checar_cobertura_de_datas,
    checar_colapso_de_volume_no_fim_da_serie,
    checar_desequilibrio_populacional,
    checar_mudanca_de_patamar,
    checar_pico_sincronizado,
)


def _dataset(parceiro: str, grupos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Monta um DataFrame no schema de engine.parsing a partir de {grupo: DataFrame-parcial}."""
    partes = []
    for grupo, parcial in grupos.items():
        parcial = parcial.copy()
        parcial["grupo"] = grupo
        parcial["parceiro"] = parceiro
        partes.append(parcial)
    return pd.concat(partes, ignore_index=True)


def _serie_base(datas, compradores, comissao=None, cashback=None, vendas_totais=None) -> pd.DataFrame:
    n = len(datas)
    return pd.DataFrame({
        "data": pd.to_datetime(datas),
        "compradores": compradores,
        "comissao": comissao if comissao is not None else [1000.0] * n,
        "cashback": cashback if cashback is not None else [200.0] * n,
        "vendas_totais": vendas_totais if vendas_totais is not None else [5000.0] * n,
    })


# --- desequilíbrio populacional -------------------------------------------------

def test_desequilibrio_populacional_detecta_grupos_desproporcionais():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[200] * 10),
        "Grupo 2": _serie_base(datas, compradores=[90] * 10),
    })
    issues = checar_desequilibrio_populacional(df, limiar_razao=1.5)
    assert len(issues) == 1
    assert issues[0].checagem == "desequilibrio_populacional"
    assert issues[0].parceiro == "Parceiro X"


def test_desequilibrio_populacional_nao_dispara_com_grupos_equilibrados():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 10),
        "Grupo 2": _serie_base(datas, compradores=[110] * 10),
    })
    assert checar_desequilibrio_populacional(df, limiar_razao=1.5) == []


# --- bug de instrumentação -------------------------------------------------------

def test_bug_instrumentacao_detecta_cashback_maior_que_vendas():
    datas = pd.date_range("2024-01-01", periods=5)
    vendas = [1000.0, 1000.0, 50.0, 1000.0, 1000.0]  # dia 3: cashback (200) > vendas (50)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 5, vendas_totais=vendas),
    })
    issues = checar_bug_instrumentacao(df)
    impossiveis = [i for i in issues if "impossível" in i.mensagem]
    assert len(impossiveis) == 1
    assert impossiveis[0].severidade == "critico"
    assert impossiveis[0].detalhes["datas"] == ["2024-01-03"]


def test_bug_instrumentacao_detecta_coluna_zerada():
    datas = pd.date_range("2024-01-01", periods=6)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 6, cashback=[0.0] * 6),
    })
    issues = checar_bug_instrumentacao(df)
    zeradas = [i for i in issues if "zero em todos os dias" in i.mensagem]
    assert len(zeradas) == 1
    assert zeradas[0].detalhes["coluna"] == "cashback"


def test_bug_instrumentacao_detecta_metrica_congelada():
    datas = pd.date_range("2024-01-01", periods=8)
    compradores = [100, 101, 99, 250, 250, 250, 250, 250]  # 5 dias repetindo 250
    vendas = [5000.0, 5100.0, 4900.0, 5200.0, 5300.0, 5150.0, 5050.0, 5250.0]  # varia, não congela
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=compradores, vendas_totais=vendas),
    })
    issues = checar_bug_instrumentacao(df, min_valores_repetidos=5)
    congeladas = [i for i in issues if "congelada" in i.mensagem]
    # comissao e cashback ficam constantes por padrão em _serie_base, então também
    # disparam — o que importa aqui é confirmar que 'compradores' foi detectado.
    colunas_congeladas = {i.detalhes["coluna"] for i in congeladas}
    assert "compradores" in colunas_congeladas
    compradores_issue = next(i for i in congeladas if i.detalhes["coluna"] == "compradores")
    assert compradores_issue.detalhes["sequencia"] == 5


def test_mudanca_de_patamar_detecta_quebra_de_nivel():
    datas = pd.date_range("2024-01-01", periods=20)
    rng = np.random.default_rng(42)
    primeira_metade = 1000 + rng.normal(0, 20, 10)
    segunda_metade = 3000 + rng.normal(0, 20, 10)
    vendas = np.concatenate([primeira_metade, segunda_metade])
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 20, vendas_totais=vendas.tolist()),
    })
    issues = checar_mudanca_de_patamar(df)
    assert len(issues) == 1
    assert issues[0].parceiro == "Parceiro X"
    assert issues[0].grupo == "Grupo 1"


def test_mudanca_de_patamar_nao_dispara_em_serie_estavel():
    datas = pd.date_range("2024-01-01", periods=20)
    rng = np.random.default_rng(42)
    vendas = 1000 + rng.normal(0, 20, 20)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 20, vendas_totais=vendas.tolist()),
    })
    assert checar_mudanca_de_patamar(df) == []


def test_pico_sincronizado_detecta_pico_em_todos_os_grupos_no_mesmo_dia():
    datas = pd.date_range("2024-01-01", periods=10)
    base = [100] * 10
    pico = base.copy()
    pico[5] = 500  # dia 2024-01-06 muito acima da média em ambos os grupos
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=pico),
        "Grupo 2": _serie_base(datas, compradores=[v + 10 if v == 500 else v for v in pico]),
    })
    issues = checar_pico_sincronizado(df, z_minimo=2.0)
    assert len(issues) == 1
    assert issues[0].detalhes["inicio"] == "2024-01-06"
    assert issues[0].detalhes["dias"] == 1


def test_pico_sincronizado_nao_dispara_se_so_um_grupo_tem_pico():
    datas = pd.date_range("2024-01-01", periods=10)
    pico_grupo1 = [100] * 10
    pico_grupo1[5] = 500
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=pico_grupo1),
        "Grupo 2": _serie_base(datas, compradores=[100] * 10),
    })
    assert checar_pico_sincronizado(df, z_minimo=2.0) == []


def test_cobertura_de_datas_detecta_periodo_diferente_entre_grupos():
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(pd.date_range("2024-01-01", periods=10), compradores=[100] * 10),
        "Grupo 2": _serie_base(pd.date_range("2024-01-01", periods=8), compradores=[100] * 8),
    })
    issues = checar_cobertura_de_datas(df)
    grupo2_issues = [i for i in issues if i.grupo == "Grupo 2" and "não coincide" in i.mensagem]
    assert len(grupo2_issues) == 1


def test_cobertura_de_datas_detecta_buraco_dentro_do_periodo():
    datas = list(pd.date_range("2024-01-01", periods=10))
    del datas[4]  # remove um dia no meio da série (buraco)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 9),
    })
    issues = checar_cobertura_de_datas(df)
    buracos = [i for i in issues if "faltando" in i.mensagem]
    assert len(buracos) == 1
    assert buracos[0].detalhes["dias_faltando"] == 1


def test_cobertura_de_datas_nao_dispara_quando_tudo_alinhado():
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, compradores=[100] * 10),
        "Grupo 2": _serie_base(datas, compradores=[100] * 10),
    })
    assert checar_cobertura_de_datas(df) == []


def test_colapso_de_volume_detecta_queda_isolada_a_um_grupo():
    datas = pd.date_range("2023-01-01", periods=40)
    grupo1 = [120] * 40  # estável o teste inteiro
    grupo2 = [118] * 35 + [45, 52, 38, 41, 36]  # colapsa nos últimos 5 dias
    df = _dataset("Parceiro Sintético", {
        "Grupo 1": _serie_base(datas, compradores=grupo1),
        "Grupo 2": _serie_base(datas, compradores=grupo2),
    })
    issues = checar_colapso_de_volume_no_fim_da_serie(df)
    assert len(issues) == 1
    assert issues[0].grupo == "Grupo 2"
    assert issues[0].severidade == "critico"
    assert issues[0].detalhes["dias_finais"] == 5


def test_colapso_de_volume_nao_dispara_quando_todos_os_grupos_caem_juntos():
    """Queda replicada em todos os grupos do mesmo teste é sazonalidade/evento
    externo, não bug isolado — não deve disparar esta checagem."""
    datas = pd.date_range("2023-01-01", periods=40)
    grupo1 = [120] * 35 + [40, 45, 38, 42, 36]
    grupo2 = [118] * 35 + [39, 44, 37, 41, 35]
    df = _dataset("Parceiro Sintético", {
        "Grupo 1": _serie_base(datas, compradores=grupo1),
        "Grupo 2": _serie_base(datas, compradores=grupo2),
    })
    assert checar_colapso_de_volume_no_fim_da_serie(df) == []


def test_colapso_de_volume_nao_dispara_com_historico_curto_demais():
    datas = pd.date_range("2023-01-01", periods=6)
    df = _dataset("Parceiro Sintético", {
        "Grupo 1": _serie_base(datas, compradores=[100, 100, 100, 20, 20, 20]),
    })
    assert checar_colapso_de_volume_no_fim_da_serie(df) == []


def test_colapso_de_volume_fixture_baseada_no_padrao_do_parceiro_c():
    from pathlib import Path

    from engine.parsing import carregar_csv

    df, _ = carregar_csv(Path(__file__).parent / "fixtures" / "dataset_colapso_volume.csv")
    issues = checar_colapso_de_volume_no_fim_da_serie(df)
    assert len(issues) == 1
    assert issues[0].grupo == "Grupo 2"


def test_colapso_de_volume_reproduz_o_achado_real_no_parceiro_c():
    from pathlib import Path

    from engine.parsing import carregar_csv

    dados = Path(__file__).parent.parent / "data"

    df_c, _ = carregar_csv(dados / "dataset_03_parceiroC.csv")
    issues_c = checar_colapso_de_volume_no_fim_da_serie(df_c)
    assert len(issues_c) == 1
    assert issues_c[0].grupo == "Grupo 2"
    assert issues_c[0].parceiro == "Parceiro C"

    for arquivo in ["dataset_01_parceiroA.csv", "dataset_02_parceiroB.csv"]:
        df, _ = carregar_csv(dados / arquivo)
        assert checar_colapso_de_volume_no_fim_da_serie(df) == []


@pytest.mark.parametrize("arquivo", [
    "dataset_01_parceiroA.csv",
    "dataset_02_parceiroB.csv",
    "dataset_03_parceiroC.csv",
])
def test_avaliar_qualidade_roda_sem_erro_nos_datasets_reais(arquivo):
    from pathlib import Path

    from engine.parsing import carregar_csv
    from engine.quality import avaliar_qualidade

    df, _ = carregar_csv(Path(__file__).parent.parent / "data" / arquivo)
    issues = avaliar_qualidade(df)
    assert isinstance(issues, list)
