import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.decision import Decisao
from engine.growth import GrowthLens, ProjecaoImpacto
from engine.tracking import (
    CAMPOS_TRACKING,
    montar_linha,
    registrar,
    registrar_csv,
    registrar_google_sheets,
)


def _decisao(veredito="escalar") -> Decisao:
    return Decisao(
        parceiro="Parceiro X",
        grupo_baseline="Grupo 1",
        grupo_variante="Grupo 2",
        veredito=veredito,
        confianca="alta",
        media_diferenca=200.0,
        ic95_diferenca=(100.0, 300.0),
        t_p_valor=0.001,
        wilcoxon_p_valor=0.002,
        alfa=0.05,
        justificativa="teste",
    )


def _lente_com_projecao() -> GrowthLens:
    return GrowthLens(
        parceiro="Parceiro X",
        veredito="escalar",
        projecao_impacto=ProjecaoImpacto(
            parceiro="Parceiro X",
            grupo_baseline="Grupo 1",
            grupo_variante="Grupo 2",
            margem_por_comprador_baseline=8.0,
            margem_por_comprador_variante=12.0,
            diferenca_margem_por_comprador=4.0,
            compradores_medios_dia_teste=200.0,
            impacto_diario_estimado=800.0,
            impacto_diario_ic95=(400.0, 1200.0),
        ),
        sugestao_proximo_teste="considere testar acima de 9%.",
    )


def _lente_sem_projecao() -> GrowthLens:
    return GrowthLens(
        parceiro="Parceiro X",
        veredito="manter_baseline",
        projecao_impacto=None,
        sugestao_proximo_teste="considere testar acima de 9%.",
    )


def test_montar_linha_mapeia_decisao_e_projecao():
    agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    linha = montar_linha(_decisao(), _lente_com_projecao(), agora=agora)
    assert linha.parceiro == "Parceiro X"
    assert linha.grupo_baseline == "Grupo 1"
    assert linha.grupo_variante == "Grupo 2"
    assert linha.veredito == "escalar"
    assert linha.media_diferenca == 200.0
    assert linha.ic95_inferior == 100.0
    assert linha.ic95_superior == 300.0
    assert linha.impacto_diario_estimado == 800.0
    assert linha.impacto_diario_ic95_inferior == 400.0
    assert linha.impacto_diario_ic95_superior == 1200.0
    assert linha.timestamp_utc == "2026-01-01T00:00:00+00:00"


def test_montar_linha_sem_projecao_deixa_campos_de_impacto_none():
    linha = montar_linha(_decisao("manter_baseline"), _lente_sem_projecao())
    assert linha.impacto_diario_estimado is None
    assert linha.impacto_diario_ic95_inferior is None
    assert linha.impacto_diario_ic95_superior is None


def test_registrar_csv_cria_arquivo_com_header_e_linha(tmp_path):
    caminho = tmp_path / "tracking" / "testes_ab.csv"
    linha = montar_linha(_decisao(), _lente_com_projecao())
    registrar_csv([linha], caminho)

    with caminho.open(encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) == 1
    assert linhas[0]["parceiro"] == "Parceiro X"
    assert list(linhas[0].keys()) == CAMPOS_TRACKING


def test_registrar_csv_acrescenta_sem_duplicar_header(tmp_path):
    caminho = tmp_path / "testes_ab.csv"
    linha1 = montar_linha(_decisao(), _lente_com_projecao())
    linha2 = montar_linha(_decisao("manter_baseline"), _lente_sem_projecao())
    registrar_csv([linha1], caminho)
    registrar_csv([linha2], caminho)

    conteudo = caminho.read_text(encoding="utf-8")
    assert conteudo.count(",".join(CAMPOS_TRACKING)) == 1
    with caminho.open(encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) == 2


def test_registrar_google_sheets_sem_credenciais_retorna_false_sem_lancar_excecao(tmp_path):
    linha = montar_linha(_decisao(), _lente_com_projecao())
    resultado = registrar_google_sheets(
        [linha], planilha_id="id-qualquer", caminho_credenciais=tmp_path / "nao_existe.json"
    )
    assert resultado is False


def test_registrar_sem_planilha_id_so_grava_csv(tmp_path):
    caminho_csv = tmp_path / "testes_ab.csv"
    linhas = registrar([_decisao()], [_lente_com_projecao()], caminho_csv=caminho_csv, planilha_id=None)
    assert len(linhas) == 1
    assert caminho_csv.exists()


@pytest.mark.parametrize("arquivo", [
    "dataset_01_parceiroA.csv",
    "dataset_02_parceiroB.csv",
    "dataset_03_parceiroC.csv",
])
def test_registrar_roda_sem_erro_nos_datasets_reais(arquivo, tmp_path):
    from engine.parsing import carregar_csv
    from engine.stats_frequentist import comparar_todos_os_grupos
    from engine.decision import decidir_todos
    from engine.growth import growth_lens

    df, _ = carregar_csv(Path(__file__).parent.parent / "data" / arquivo)
    comparacoes = comparar_todos_os_grupos(df)
    decisoes = decidir_todos(comparacoes)
    lentes = [growth_lens(df, decisao) for decisao in decisoes]

    caminho_csv = tmp_path / "testes_ab.csv"
    linhas = registrar(decisoes, lentes, caminho_csv=caminho_csv, planilha_id=None)
    assert len(linhas) == len(decisoes)
    assert caminho_csv.exists()
