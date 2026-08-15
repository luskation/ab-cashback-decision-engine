import math
from pathlib import Path

import pytest

from engine.parsing import SchemaError, carregar_csv, parse_inteiro, parse_moeda_brl

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("R$ 10.273", 10273.0),
        ("R$ 1.234,56", 1234.56),
        ("R$ 50", 50.0),
        ("-R$ 50", -50.0),
        ("R$ -50", -50.0),
        ("R$ 123.456.789", 123456789.0),
        ("100.00", 100.0),
        (1234.5, 1234.5),
    ],
)
def test_parse_moeda_brl_formatos_validos(bruto, esperado):
    assert parse_moeda_brl(bruto) == esperado


@pytest.mark.parametrize("bruto", ["", "   ", None, "abc", "R$ "])
def test_parse_moeda_brl_formatos_invalidos_retornam_nan(bruto):
    assert math.isnan(parse_moeda_brl(bruto))


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("196", 196.0),
        (" 115 ", 115.0),
        ("1.234", 1234.0),
        (82, 82.0),
    ],
)
def test_parse_inteiro_formatos_validos(bruto, esperado):
    assert parse_inteiro(bruto) == esperado


@pytest.mark.parametrize("bruto", ["", "abc", None])
def test_parse_inteiro_formatos_invalidos_retornam_nan(bruto):
    assert math.isnan(parse_inteiro(bruto))


def test_carregar_csv_descarta_linhas_ruins_e_conta_motivos():
    df, report = carregar_csv(FIXTURES / "dataset_malformado.csv")

    assert report.linhas_lidas == 8
    assert report.linhas_validas == 3
    assert report.linhas_descartadas == 5
    assert report.motivos_descarte == {
        "valor ausente ou malformado": 3,
        "valor numérico negativo": 1,
        "linha duplicada (mesma data/grupo/parceiro)": 1,
    }
    assert len(df) == 3
    assert set(df.columns) == {"data", "grupo", "parceiro", "compradores", "comissao", "cashback", "vendas_totais"}

    linha_decimal = df[df["compradores"] == 110].iloc[0]
    assert linha_decimal["comissao"] == 1150.50


def test_carregar_csv_schema_invalido_levanta_erro(tmp_path):
    caminho = tmp_path / "sem_cashback.csv"
    caminho.write_text(
        "Data,Grupos de usuários,Parceiro,compradores,comissão,vendas totais\n"
        "2024-01-01,Grupo 1,Parceiro X,100,R$ 100,R$ 1.000\n",
        encoding="utf-8",
    )
    with pytest.raises(SchemaError):
        carregar_csv(caminho)


@pytest.mark.parametrize(
    "arquivo, parceiro_esperado, grupos_esperados",
    [
        ("dataset_01_parceiroA.csv", "Parceiro A", {"Grupo 1", "Grupo 2", "Grupo 3"}),
        ("dataset_02_parceiroB.csv", "Parceiro B", {"Grupo 1", "Grupo 2", "Grupo 3"}),
        ("dataset_03_parceiroC.csv", "Parceiro C", {"Grupo 1", "Grupo 2"}),
    ],
)
def test_carregar_csv_datasets_reais_nao_perdem_linhas(arquivo, parceiro_esperado, grupos_esperados):
    df, report = carregar_csv(DATA / arquivo)

    assert report.linhas_validas == report.linhas_lidas
    assert report.linhas_descartadas == 0
    assert set(df["parceiro"].unique()) == {parceiro_esperado}
    assert set(df["grupo"].unique()) == grupos_esperados
