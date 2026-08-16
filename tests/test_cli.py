import csv
from pathlib import Path

import pytest

import cli

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATASETS_REAIS = sorted(DATA_DIR.glob("*.csv"))
FIXTURE_SINTETICA = Path(__file__).resolve().parent / "fixtures" / "dataset_04_sintetico.csv"


@pytest.mark.parametrize("caminho_dataset", DATASETS_REAIS, ids=lambda p: p.name)
def test_processar_dataset_gera_relatorio_grafico_e_tracking(tmp_path, caminho_dataset):
    diretorio_saida = tmp_path / "reports"
    caminho_tracking = tmp_path / "tracking" / "testes_ab.csv"

    ok = cli.processar_dataset(
        caminho_dataset,
        diretorio_saida=diretorio_saida,
        caminho_tracking=caminho_tracking,
        planilha_id=None,
        alfa=0.05,
    )

    assert ok is True
    relatorios = list(diretorio_saida.glob("relatorio_*.md"))
    graficos = list(diretorio_saida.glob("grafico_*.png"))
    assert len(relatorios) == 1
    assert len(graficos) == 1
    assert relatorios[0].read_text(encoding="utf-8").startswith("# Teste A/B —")

    assert caminho_tracking.exists()
    with caminho_tracking.open(encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) >= 1
    assert all(linha["veredito"] for linha in linhas)


def test_main_processa_os_3_datasets_fornecidos_sem_alteracao_de_codigo(tmp_path):
    diretorio_saida = tmp_path / "reports"
    caminho_tracking = tmp_path / "tracking" / "testes_ab.csv"

    codigo_saida = cli.main(
        [str(p) for p in DATASETS_REAIS]
        + ["--output-dir", str(diretorio_saida), "--tracking-csv", str(caminho_tracking)]
    )

    assert codigo_saida == 0
    assert len(list(diretorio_saida.glob("relatorio_*.md"))) == len(DATASETS_REAIS)
    with caminho_tracking.open(encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) >= len(DATASETS_REAIS)


def test_main_sem_argumentos_descobre_csvs_em_data_por_padrao(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    diretorio_saida = tmp_path / "reports"
    caminho_tracking = tmp_path / "tracking" / "testes_ab.csv"

    codigo_saida = cli.main(["--output-dir", str(diretorio_saida), "--tracking-csv", str(caminho_tracking)])

    assert codigo_saida == 0
    assert len(list(diretorio_saida.glob("relatorio_*.md"))) == len(DATASETS_REAIS)


def test_main_sem_datasets_encontrados_retorna_erro(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    codigo_saida = cli.main([])
    assert codigo_saida == 1


def test_dataset_ruim_e_pulado_sem_derrubar_o_processamento_dos_demais(tmp_path):
    fixture_malformada = Path(__file__).resolve().parent / "fixtures" / "dataset_malformado.csv"
    diretorio_saida = tmp_path / "reports"
    caminho_tracking = tmp_path / "tracking" / "testes_ab.csv"

    codigo_saida = cli.main(
        [str(fixture_malformada), str(DATASETS_REAIS[0])]
        + ["--output-dir", str(diretorio_saida), "--tracking-csv", str(caminho_tracking)]
    )

    assert codigo_saida == 1
    relatorios = list(diretorio_saida.glob("relatorio_*.md"))
    assert len(relatorios) == 1


def test_dataset_sintetico_nunca_visto_generaliza_sem_alteracao_de_codigo(tmp_path):
    """Prova de generalização (Fase 9.1): schema idêntico aos 3 datasets reais, mas parceiro,
    datas, número de grupos (4) e armadilha (cobertura de datas incompleta) inéditos — nenhum
    limiar do motor foi calibrado para este dataset."""
    diretorio_saida = tmp_path / "reports"
    caminho_tracking = tmp_path / "tracking" / "testes_ab.csv"

    ok = cli.processar_dataset(
        FIXTURE_SINTETICA,
        diretorio_saida=diretorio_saida,
        caminho_tracking=caminho_tracking,
        planilha_id=None,
        alfa=0.05,
    )

    assert ok is True
    relatorio = diretorio_saida / "relatorio_parceiro_delta.md"
    assert relatorio.exists()
    conteudo = relatorio.read_text(encoding="utf-8")
    assert "Grupo 2" in conteudo and "Grupo 3" in conteudo and "Grupo 4" in conteudo
    assert "cobertura_de_datas" in conteudo

    with caminho_tracking.open(encoding="utf-8") as arquivo:
        veredito_por_grupo = {linha["grupo_variante"]: linha["veredito"] for linha in csv.DictReader(arquivo)}
    assert veredito_por_grupo["Grupo 2"] == "escalar"
    assert veredito_por_grupo["Grupo 3"] == "sem_evidencia_suficiente"
    assert veredito_por_grupo["Grupo 4"] == "manter_baseline"
