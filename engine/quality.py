from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class QualityIssue:
    checagem: str
    severidade: str 
    parceiro: str
    grupo: str | None
    mensagem: str
    detalhes: dict = field(default_factory=dict)

    def __str__(self) -> str:
        alvo = self.parceiro + (f" / {self.grupo}" if self.grupo else "")
        return f"[{self.severidade.upper()}] {self.checagem} ({alvo}): {self.mensagem}"


def _serie_diaria(df_grupo: pd.DataFrame, coluna: str) -> pd.Series:
    return df_grupo.sort_values("data").set_index("data")[coluna]


def _maior_sequencia_repetida(valores: np.ndarray) -> int:
    if len(valores) == 0:
        return 0
    maior = atual = 1
    for i in range(1, len(valores)):
        if valores[i] == valores[i - 1]:
            atual += 1
            maior = max(maior, atual)
        else:
            atual = 1
    return maior


def _agrupar_datas_consecutivas(datas) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    datas = sorted(datas)
    if not datas:
        return []
    grupos = []
    inicio = anterior = datas[0]
    for data in datas[1:]:
        if (data - anterior).days > 1:
            grupos.append((inicio, anterior))
            inicio = data
        anterior = data
    grupos.append((inicio, anterior))
    return grupos


def checar_desequilibrio_populacional(df: pd.DataFrame, limiar_razao: float = 1.5) -> list[QualityIssue]:
    """Compara o volume médio diário de compradores entre os grupos do mesmo teste."""
    issues = []
    for parceiro, df_p in df.groupby("parceiro"):
        medias = df_p.groupby("grupo")["compradores"].mean()
        if len(medias) < 2:
            continue
        maior, menor = medias.max(), medias.min()
        if menor <= 0:
            continue
        razao = maior / menor
        if razao >= limiar_razao:
            grupo_maior, grupo_menor = medias.idxmax(), medias.idxmin()
            issues.append(QualityIssue(
                checagem="desequilibrio_populacional",
                severidade="aviso",
                parceiro=parceiro,
                grupo=None,
                mensagem=(
                    f"{grupo_maior} tem {razao:.1f}x mais compradores/dia em média que {grupo_menor} "
                    f"({medias[grupo_maior]:.0f} vs {medias[grupo_menor]:.0f}) — confirme se o split "
                    "de amostra entre os grupos é o esperado pelo desenho do teste."
                ),
                detalhes={"medias_por_grupo": medias.to_dict(), "razao": float(razao)},
            ))
    return issues


def checar_bug_instrumentacao(df: pd.DataFrame, min_valores_repetidos: int = 5) -> list[QualityIssue]:
    """Sinaliza valores logicamente impossíveis ou métricas congeladas/zeradas."""
    issues = []

    impossivel = df[df["cashback"] > df["vendas_totais"]]
    for (parceiro, grupo), grupo_df in impossivel.groupby(["parceiro", "grupo"]):
        issues.append(QualityIssue(
            checagem="bug_instrumentacao",
            severidade="critico",
            parceiro=parceiro,
            grupo=grupo,
            mensagem=(
                f"{len(grupo_df)} dia(s) com cashback maior que vendas totais — logicamente impossível, "
                "indica erro de instrumentação/captura de dados."
            ),
            detalhes={"datas": grupo_df["data"].dt.strftime("%Y-%m-%d").tolist()},
        ))

    for (parceiro, grupo), grupo_df in df.groupby(["parceiro", "grupo"]):
        for coluna in ["compradores", "comissao", "cashback", "vendas_totais"]:
            serie = _serie_diaria(grupo_df, coluna)
            if (serie == 0).all():
                issues.append(QualityIssue(
                    checagem="bug_instrumentacao",
                    severidade="critico",
                    parceiro=parceiro,
                    grupo=grupo,
                    mensagem=f"coluna '{coluna}' é zero em todos os dias — métrica provavelmente não é capturada.",
                    detalhes={"coluna": coluna},
                ))
                continue
            maior_run = _maior_sequencia_repetida(serie.values)
            if maior_run >= min_valores_repetidos:
                issues.append(QualityIssue(
                    checagem="bug_instrumentacao",
                    severidade="aviso",
                    parceiro=parceiro,
                    grupo=grupo,
                    mensagem=(
                        f"coluna '{coluna}' repete o mesmo valor por {maior_run} dias seguidos — "
                        "possível métrica congelada (pipeline não atualizando)."
                    ),
                    detalhes={"coluna": coluna, "sequencia": int(maior_run)},
                ))
    return issues


def checar_mudanca_de_patamar(
    df: pd.DataFrame,
    coluna: str = "vendas_totais",
    limiar_diferenca_relativa: float = 0.4,
    z_minimo: float = 2.0,
) -> list[QualityIssue]:
    """Detecta quebra de nível no meio da série (primeira metade vs segunda metade)."""
    issues = []
    for (parceiro, grupo), grupo_df in df.groupby(["parceiro", "grupo"]):
        serie = _serie_diaria(grupo_df, coluna).values
        if len(serie) < 10:
            continue
        meio = len(serie) // 2
        primeira, segunda = serie[:meio], serie[meio:]
        media1, media2 = primeira.mean(), segunda.mean()
        std_conjunto = np.sqrt((primeira.var(ddof=1) + segunda.var(ddof=1)) / 2) or 1e-9
        z = abs(media2 - media1) / std_conjunto
        diferenca_relativa = abs(media2 - media1) / (abs(media1) or 1e-9)
        if z >= z_minimo and diferenca_relativa >= limiar_diferenca_relativa:
            issues.append(QualityIssue(
                checagem="mudanca_de_patamar",
                severidade="aviso",
                parceiro=parceiro,
                grupo=grupo,
                mensagem=(
                    f"'{coluna}' muda de patamar no meio da série: média de {media1:.0f} na primeira "
                    f"metade para {media2:.0f} na segunda ({diferenca_relativa:.0%} de diferença) — "
                    "verifique se houve mudança de configuração/comissão durante o teste."
                ),
                detalhes={
                    "media_primeira_metade": float(media1),
                    "media_segunda_metade": float(media2),
                    "z": float(z),
                },
            ))
    return issues


def checar_pico_sincronizado(
    df: pd.DataFrame, coluna: str = "compradores", z_minimo: float = 2.0
) -> list[QualityIssue]:
    """Detecta dias em que TODOS os grupos do mesmo teste têm pico simultâneo — sinal de evento externo."""
    issues = []
    for parceiro, df_p in df.groupby("parceiro"):
        grupos = df_p["grupo"].unique()
        if len(grupos) < 2:
            continue
        zscores = {}
        for grupo, grupo_df in df_p.groupby("grupo"):
            serie = _serie_diaria(grupo_df, coluna)
            std = serie.std(ddof=1) or 1e-9
            zscores[grupo] = (serie - serie.mean()) / std
        tabela = pd.DataFrame(zscores).dropna()
        pico_em_todos = (tabela >= z_minimo).all(axis=1)
        datas_pico = list(tabela.index[pico_em_todos])
        if not datas_pico:
            continue
        for inicio, fim in _agrupar_datas_consecutivas(datas_pico):
            dias = (fim - inicio).days + 1
            issues.append(QualityIssue(
                checagem="pico_sincronizado",
                severidade="info",
                parceiro=parceiro,
                grupo=None,
                mensagem=(
                    f"pico simultâneo em todos os {len(grupos)} grupos entre {inicio.date()} e {fim.date()} "
                    f"({dias} dia(s)) — provável evento externo (sazonalidade, campanha), não efeito do teste."
                ),
                detalhes={"inicio": str(inicio.date()), "fim": str(fim.date()), "dias": dias},
            ))
    return issues


def checar_cobertura_de_datas(df: pd.DataFrame) -> list[QualityIssue]:
    """Verifica se os grupos do mesmo teste cobrem o mesmo período, sem buracos internos."""
    issues = []
    for parceiro, df_p in df.groupby("parceiro"):
        faixas = df_p.groupby("grupo")["data"].agg(["min", "max", "count"])
        inicio_geral, fim_geral = faixas["min"].min(), faixas["max"].max()
        for grupo, linha in faixas.iterrows():
            if linha["min"] != inicio_geral or linha["max"] != fim_geral:
                issues.append(QualityIssue(
                    checagem="cobertura_de_datas",
                    severidade="aviso",
                    parceiro=parceiro,
                    grupo=grupo,
                    mensagem=(
                        f"período de {grupo} ({linha['min'].date()} a {linha['max'].date()}) não coincide "
                        "com o de outros grupos do mesmo teste — período comparável pode ser menor."
                    ),
                    detalhes={"inicio": str(linha["min"].date()), "fim": str(linha["max"].date())},
                ))
            dias_esperados = (linha["max"] - linha["min"]).days + 1
            if linha["count"] < dias_esperados:
                buracos = dias_esperados - linha["count"]
                issues.append(QualityIssue(
                    checagem="cobertura_de_datas",
                    severidade="aviso",
                    parceiro=parceiro,
                    grupo=grupo,
                    mensagem=f"{grupo} tem {int(buracos)} dia(s) faltando dentro do próprio período (buraco na série).",
                    detalhes={"dias_faltando": int(buracos)},
                ))
    return issues


def checar_colapso_de_volume_no_fim_da_serie(
    df: pd.DataFrame,
    coluna: str = "compradores",
    fracao_final: float = 0.1,
    minimo_dias_finais: int = 5,
    z_maximo: float = -2.0,
) -> list[QualityIssue]:
    issues = []
    for parceiro, df_p in df.groupby("parceiro"):
        grupos = list(df_p.groupby("grupo"))
        colapsos = {}
        for grupo, grupo_df in grupos:
            serie = _serie_diaria(grupo_df, coluna)
            n = len(serie)
            k = max(minimo_dias_finais, round(n * fracao_final))
            if n < k + minimo_dias_finais:
                continue  # histórico insuficiente antes do fim para comparar com confiança
            resto, finais = serie.iloc[:-k], serie.iloc[-k:]
            std_resto = resto.std(ddof=1) or 1e-9
            z = (finais.mean() - resto.mean()) / std_resto
            if z <= z_maximo:
                colapsos[grupo] = {
                    "z": z,
                    "media_resto": resto.mean(),
                    "media_final": finais.mean(),
                    "k": k,
                    "inicio": finais.index.min(),
                    "fim": finais.index.max(),
                }
        if not colapsos:
            continue
        todos_os_grupos_colapsaram = len(colapsos) == len(grupos) and len(grupos) > 1
        if todos_os_grupos_colapsaram:
            continue
        for grupo, info in colapsos.items():
            issues.append(QualityIssue(
                checagem="colapso_de_volume_fim_serie",
                severidade="critico",
                parceiro=parceiro,
                grupo=grupo,
                mensagem=(
                    f"'{coluna}' de {grupo} despenca nos últimos {info['k']} dias da série: média cai de "
                    f"{info['media_resto']:.0f} para {info['media_final']:.0f} (z={info['z']:.1f}), e a "
                    "queda não aparece nos demais grupos do mesmo teste no mesmo período — investigar "
                    "antes de confiar no resultado (possível bug de instrumentação isolado ao grupo)."
                ),
                detalhes={
                    "z": float(info["z"]),
                    "media_resto": float(info["media_resto"]),
                    "media_final": float(info["media_final"]),
                    "dias_finais": info["k"],
                    "inicio": str(info["inicio"].date()),
                    "fim": str(info["fim"].date()),
                },
            ))
    return issues


def checar_repasse_total_de_cashback(
    df: pd.DataFrame,
    limiar_proximidade_relativa: float = 0.02,
    limiar_fracao_dias: float = 0.9,
) -> list[QualityIssue]:
    """Detecta grupos onde o cashback pago é praticamente igual à comissão recebida
    (repasse de ~100% da comissão) na maior parte dos dias. Nesses casos a margem
    (comissão - cashback) é ~zero por construção, não por um efeito do teste — muda como
    o resultado estatístico da comparação de margem deve ser lido."""
    issues = []
    for (parceiro, grupo), grupo_df in df.groupby(["parceiro", "grupo"]):
        comissao_segura = grupo_df["comissao"].where(grupo_df["comissao"] > 0)
        proximidade_relativa = (grupo_df["cashback"] - comissao_segura).abs() / comissao_segura
        fracao_repasse_total = (proximidade_relativa <= limiar_proximidade_relativa).mean()
        if fracao_repasse_total >= limiar_fracao_dias:
            issues.append(QualityIssue(
                checagem="repasse_total_de_cashback",
                severidade="aviso",
                parceiro=parceiro,
                grupo=grupo,
                mensagem=(
                    f"{grupo} repassa ~100% da comissão como cashback em {fracao_repasse_total:.0%} "
                    "dos dias — a margem (comissão - cashback) desse grupo é próxima de zero por "
                    "desenho, não por efeito do teste; interprete a comparação de margem com essa "
                    "ressalva."
                ),
                detalhes={"fracao_dias_repasse_total": float(fracao_repasse_total)},
            ))
    return issues


CHECAGENS_PADRAO = [
    checar_desequilibrio_populacional,
    checar_bug_instrumentacao,
    checar_mudanca_de_patamar,
    checar_pico_sincronizado,
    checar_cobertura_de_datas,
    checar_colapso_de_volume_no_fim_da_serie,
    checar_repasse_total_de_cashback,
]


def avaliar_qualidade(df: pd.DataFrame, checagens=None) -> list[QualityIssue]:
    """Roda as checagens de qualidade padrão sobre o dataset carregado."""
    checagens = checagens if checagens is not None else CHECAGENS_PADRAO
    issues: list[QualityIssue] = []
    for checagem in checagens:
        issues.extend(checagem(df))
    return issues
