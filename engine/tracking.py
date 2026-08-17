from __future__ import annotations

import csv
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from engine.decision import Decisao
from engine.growth import GrowthLens

logger = logging.getLogger(__name__)

CAMPOS_TRACKING = [
    "timestamp_utc",
    "parceiro",
    "grupo_baseline",
    "grupo_variante",
    "veredito",
    "confianca",
    "media_diferenca",
    "ic95_inferior",
    "ic95_superior",
    "t_p_valor",
    "wilcoxon_p_valor",
    "impacto_diario_estimado",
    "impacto_diario_ic95_inferior",
    "impacto_diario_ic95_superior",
    "sugestao_proximo_teste",
]


@dataclass
class LinhaTracking:
    timestamp_utc: str
    parceiro: str
    grupo_baseline: str
    grupo_variante: str
    veredito: str
    confianca: str
    media_diferenca: float
    ic95_inferior: float
    ic95_superior: float
    t_p_valor: float
    wilcoxon_p_valor: float
    impacto_diario_estimado: float | None
    impacto_diario_ic95_inferior: float | None
    impacto_diario_ic95_superior: float | None
    sugestao_proximo_teste: str


def montar_linha(decisao: Decisao, lente: GrowthLens, agora: datetime | None = None) -> LinhaTracking:
    agora = agora or datetime.now(timezone.utc)
    projecao = lente.projecao_impacto
    return LinhaTracking(
        timestamp_utc=agora.isoformat(),
        parceiro=decisao.parceiro,
        grupo_baseline=decisao.grupo_baseline,
        grupo_variante=decisao.grupo_variante,
        veredito=decisao.veredito,
        confianca=decisao.confianca,
        media_diferenca=decisao.media_diferenca,
        ic95_inferior=decisao.ic95_diferenca[0],
        ic95_superior=decisao.ic95_diferenca[1],
        t_p_valor=decisao.t_p_valor,
        wilcoxon_p_valor=decisao.wilcoxon_p_valor,
        impacto_diario_estimado=projecao.impacto_diario_estimado if projecao else None,
        impacto_diario_ic95_inferior=min(projecao.impacto_diario_ic95) if projecao else None,
        impacto_diario_ic95_superior=max(projecao.impacto_diario_ic95) if projecao else None,
        sugestao_proximo_teste=lente.sugestao_proximo_teste,
    )


def registrar_csv(linhas: list[LinhaTracking], caminho: Path) -> Path:
    """Grava/acrescenta linhas no CSV local de tracking. Sempre roda — é o "mínimo
    aceito" pelo enunciado, nunca depende do Google Sheets estar disponível."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    arquivo_ja_existe = caminho.exists()
    with caminho.open("a", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS_TRACKING)
        if not arquivo_ja_existe:
            escritor.writeheader()
        for linha in linhas:
            escritor.writerow(asdict(linha))
    return caminho


def registrar_google_sheets(
    linhas: list[LinhaTracking],
    planilha_id: str,
    aba: str = "testes_ab",
    caminho_credenciais: Path = Path("credentials.json"),
) -> bool:
    """Escreve as linhas também no Google Sheets — best-effort. Qualquer falha (biblioteca
    ausente, credencial ausente, rede, permissão) é logada e engolida aqui, nunca propaga:
    travar o pipeline por causa do Sheets seria pior do que simplesmente não ter Sheets, e
    o CSV local já foi gravado antes desta chamada."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.warning("gspread/google-auth não instalados — pulando escrita no Google Sheets.")
        return False

    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciais = Credentials.from_service_account_file(str(caminho_credenciais), scopes=escopos)
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_key(planilha_id)
        try:
            aba_planilha = planilha.worksheet(aba)
        except gspread.WorksheetNotFound:
            aba_planilha = planilha.add_worksheet(title=aba, rows=1, cols=len(CAMPOS_TRACKING))
            aba_planilha.append_row(CAMPOS_TRACKING)
        for linha in linhas:
            valores = (getattr(linha, campo) for campo in CAMPOS_TRACKING)
            aba_planilha.append_row(["" if valor is None else str(valor) for valor in valores])
        return True
    except Exception:  # best-effort por design (2.8) — qualquer falha aqui não pode travar o pipeline.
        logger.exception("falha ao escrever no Google Sheets — tracking local em CSV já foi gravado.")
        return False


def registrar(
    decisoes: list[Decisao],
    lentes: list[GrowthLens],
    caminho_csv: Path = Path("tracking/testes_ab.csv"),
    planilha_id: str | None = None,
) -> list[LinhaTracking]:
    linhas = [montar_linha(decisao, lente) for decisao, lente in zip(decisoes, lentes)]
    registrar_csv(linhas, caminho_csv)
    if planilha_id:
        registrar_google_sheets(linhas, planilha_id)
    return linhas
