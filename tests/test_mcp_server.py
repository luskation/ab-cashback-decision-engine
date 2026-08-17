import csv
from pathlib import Path

import pytest

from mcp_server import server

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATASETS_REAIS = sorted(DATA_DIR.glob("*.csv"))
FIXTURE_MALFORMADA = Path(__file__).resolve().parent / "fixtures" / "dataset_malformado.csv"


def test_listar_datasets_encontra_os_3_datasets_reais(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    nomes = {Path(p).name for p in server.listar_datasets()}
    assert nomes == {p.name for p in DATASETS_REAIS}


@pytest.mark.parametrize("caminho_dataset", DATASETS_REAIS, ids=lambda p: p.name)
def test_analisar_teste_ab_processa_cada_dataset_real_e_devolve_resumo_estruturado(tmp_path, caminho_dataset):
    diretorio_saida = tmp_path / "reports"
    caminho_tracking = tmp_path / "tracking" / "testes_ab.csv"

    resultado = server.analisar_teste_ab(
        str(caminho_dataset),
        diretorio_saida=str(diretorio_saida),
        caminho_tracking=str(caminho_tracking),
    )

    assert resultado["ok"] is True
    assert resultado["decisoes"], "esperado ao menos uma decisão por dataset"
    for decisao in resultado["decisoes"]:
        assert decisao["veredito"] in {"escalar", "manter_baseline", "sem_evidencia_suficiente"}
        assert decisao["confianca"] in {"alta", "baixa"}
        assert decisao["sugestao_proximo_teste"]

    relatorio = Path(resultado["relatorio"])
    assert relatorio.exists()
    assert relatorio.read_text(encoding="utf-8").startswith("# Teste A/B —")

    assert caminho_tracking.exists()
    with caminho_tracking.open(encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) == len(resultado["decisoes"])


def test_analisar_todos_os_testes_ab_processa_os_3_datasets_sem_alteracao_de_codigo(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    diretorio_saida = tmp_path / "reports"
    caminho_tracking = tmp_path / "tracking" / "testes_ab.csv"

    resumo = server.analisar_todos_os_testes_ab(
        diretorio_saida=str(diretorio_saida),
        caminho_tracking=str(caminho_tracking),
    )

    assert resumo["total"] == len(DATASETS_REAIS)
    assert resumo["sucesso"] == len(DATASETS_REAIS)
    assert len(list(diretorio_saida.glob("relatorio_*.md"))) == len(DATASETS_REAIS)


def test_analisar_teste_ab_com_schema_invalido_devolve_erro_estruturado_sem_lancar(tmp_path):
    resultado = server.analisar_teste_ab(
        str(FIXTURE_MALFORMADA),
        diretorio_saida=str(tmp_path / "reports"),
        caminho_tracking=str(tmp_path / "tracking" / "testes_ab.csv"),
    )
    assert resultado["ok"] is False
    assert resultado["erro"]


def test_analisar_teste_ab_com_arquivo_inexistente_devolve_erro_estruturado_sem_lancar(tmp_path):
    resultado = server.analisar_teste_ab(
        str(tmp_path / "nao_existe.csv"),
        diretorio_saida=str(tmp_path / "reports"),
        caminho_tracking=str(tmp_path / "tracking" / "testes_ab.csv"),
    )
    assert resultado["ok"] is False
    assert resultado["erro"]
