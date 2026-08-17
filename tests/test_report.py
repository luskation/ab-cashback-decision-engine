from pathlib import Path

import pandas as pd
import pytest

from engine.decision import Decisao
from engine.growth import GrowthLens, ProjecaoImpacto
from engine.quality import QualityIssue
from engine.report import (
    _slug,
    gerar_grafico_margem_diaria,
    gerar_relatorio_completo,
    gerar_relatorio_markdown,
)
from engine.stats_bayesian import PosteriorBayesiano
from engine.stats_frequentist import ComparacaoPareada


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


def test_slug_remove_acento_e_espaco():
    assert _slug("Parceiro Ação C") == "parceiro_acao_c"


def test_gerar_grafico_margem_diaria_cria_png(tmp_path):
    datas = pd.date_range("2024-01-01", periods=10)
    df = _dataset("Parceiro X", {
        "Grupo 1": _serie_base(datas, [100] * 10, [1000.0] * 10, [200.0] * 10, [5000.0] * 10),
        "Grupo 2": _serie_base(datas, [100] * 10, [1200.0] * 10, [200.0] * 10, [5000.0] * 10),
    })
    caminho = gerar_grafico_margem_diaria(df, "Parceiro X", tmp_path / "grafico.png")
    assert caminho.exists()
    assert caminho.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def _decisao(veredito, grupo_variante="Grupo 2") -> Decisao:
    return Decisao(
        parceiro="Parceiro X",
        grupo_baseline="Grupo 1",
        grupo_variante=grupo_variante,
        veredito=veredito,
        confianca="alta",
        media_diferenca=200.0,
        ic95_diferenca=(100.0, 300.0),
        t_p_valor=0.001,
        wilcoxon_p_valor=0.001,
        alfa=0.05,
        justificativa="teste",
    )


def _comparacao(grupo_variante="Grupo 2") -> ComparacaoPareada:
    return ComparacaoPareada(
        parceiro="Parceiro X",
        grupo_baseline="Grupo 1",
        grupo_variante=grupo_variante,
        coluna="margem",
        n_dias_pareados=30,
        media_baseline=1000.0,
        media_variante=1200.0,
        media_diferenca=200.0,
        desvio_padrao_diferenca=50.0,
        ic95_diferenca=(100.0, 300.0),
        t_estatistica=5.0,
        t_p_valor=0.001,
        wilcoxon_estatistica=10.0,
        wilcoxon_p_valor=0.001,
    )


def _growth_lens_com_projecao() -> GrowthLens:
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


def test_gerar_relatorio_markdown_contem_secoes_esperadas(tmp_path):
    resultados = [(_comparacao(), _decisao("escalar"), _growth_lens_com_projecao())]
    caminho = gerar_relatorio_markdown(
        "Parceiro X", resultados, [], tmp_path / "grafico_parceiro_x.png", tmp_path / "relatorio.md"
    )
    conteudo = caminho.read_text(encoding="utf-8")
    assert "# Teste A/B — Parceiro X" in conteudo
    assert "## Resumo executivo" in conteudo
    assert "escalar Grupo 2" in conteudo
    assert "![Margem diária por grupo](grafico_parceiro_x.png)" in conteudo
    assert "## Racional" in conteudo
    assert "## Ressalvas" in conteudo
    assert "Nenhum problema de qualidade de dados identificado" in conteudo
    assert "## Apêndice técnico" in conteudo
    assert "p=0.0010" in conteudo
    assert "R$ 400,00" in conteudo  # padrão pt-BR: vírgula decimal
    assert "R$ 400.00" not in conteudo  # nunca no padrão US


def _posterior_bayesiano(grupo_variante="Grupo 2") -> PosteriorBayesiano:
    return PosteriorBayesiano(
        parceiro="Parceiro X",
        grupo_baseline="Grupo 1",
        grupo_variante=grupo_variante,
        coluna="margem",
        n_dias_pareados=53,
        media_diferenca=-781.71,
        ic95_diferenca=(-1119.59, -443.05),
        probabilidade_variante_melhor=0.0,
        perda_esperada_escalar=781.71,
        perda_esperada_manter=0.0,
    )


def test_gerar_relatorio_markdown_traduz_saida_bayesiana_em_linguagem_de_negocio(tmp_path):
    resultados = [(_comparacao(), _decisao("manter_baseline"), _growth_lens_com_projecao())]
    posteriores = {"Grupo 2": _posterior_bayesiano()}
    caminho = gerar_relatorio_markdown(
        "Parceiro X", resultados, [], tmp_path / "grafico.png", tmp_path / "relatorio.md",
        posteriores=posteriores,
    )
    conteudo = caminho.read_text(encoding="utf-8")

    # corpo principal: linguagem de negócio, nunca jargão técnico (mitigação obrigatória, 2.12)
    secao_principal = conteudo.split("## Apêndice técnico")[0]
    assert "chance de Grupo 1 ser melhor" in secao_principal
    assert "perda esperada seria de R$ 781,71/dia" in secao_principal
    for jargao in ("posterior", "prior", "expected loss", "Student-t"):
        assert jargao not in secao_principal

    # apêndice técnico: aqui sim, jargão é esperado
    assert "camada bayesiana" in conteudo
    assert "prior de Jeffreys" in conteudo
    assert "P(μ>0)=0.0000" in conteudo


def test_gerar_relatorio_markdown_sem_posteriores_nao_menciona_camada_bayesiana(tmp_path):
    resultados = [(_comparacao(), _decisao("escalar"), _growth_lens_com_projecao())]
    caminho = gerar_relatorio_markdown(
        "Parceiro X", resultados, [], tmp_path / "grafico.png", tmp_path / "relatorio.md"
    )
    conteudo = caminho.read_text(encoding="utf-8")
    assert "camada bayesiana" not in conteudo
    assert "chance de" not in conteudo


def test_gerar_relatorio_markdown_lista_ressalvas_quando_ha_issues(tmp_path):
    issue = QualityIssue(
        checagem="bug_instrumentacao",
        severidade="critico",
        parceiro="Parceiro X",
        grupo="Grupo 1",
        mensagem="cashback maior que vendas totais.",
    )
    resultados = [(_comparacao(), _decisao("manter_baseline"), _growth_lens_com_projecao())]
    caminho = gerar_relatorio_markdown(
        "Parceiro X", resultados, [issue], tmp_path / "grafico.png", tmp_path / "relatorio.md"
    )
    conteudo = caminho.read_text(encoding="utf-8")
    assert "bug_instrumentacao" in conteudo
    assert "cashback maior que vendas totais" in conteudo


@pytest.mark.parametrize("arquivo", [
    "dataset_01_parceiroA.csv",
    "dataset_02_parceiroB.csv",
    "dataset_03_parceiroC.csv",
])
def test_gerar_relatorio_completo_roda_sem_erro_nos_datasets_reais(arquivo, tmp_path):
    from engine.parsing import carregar_csv

    df, _ = carregar_csv(Path(__file__).parent.parent / "data" / arquivo)
    caminho = gerar_relatorio_completo(df, diretorio_saida=tmp_path)
    assert caminho.exists()
    conteudo = caminho.read_text(encoding="utf-8")
    assert "# Teste A/B —" in conteudo
    assert "## Resumo executivo" in conteudo

    grafico = next(tmp_path.glob("grafico_*.png"))
    assert grafico.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_gerar_relatorio_completo_recusa_dataframe_com_mais_de_um_parceiro(tmp_path):
    datas = pd.date_range("2024-01-01", periods=5)
    df1 = _dataset("Parceiro X", {"Grupo 1": _serie_base(datas, [100] * 5, [1000.0] * 5, [200.0] * 5, [5000.0] * 5)})
    df2 = _dataset("Parceiro Y", {"Grupo 1": _serie_base(datas, [100] * 5, [1000.0] * 5, [200.0] * 5, [5000.0] * 5)})
    df = pd.concat([df1, df2], ignore_index=True)
    with pytest.raises(ValueError):
        gerar_relatorio_completo(df, diretorio_saida=tmp_path)
