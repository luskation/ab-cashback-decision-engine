from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

CANONICAL_COLUMNS = {
    "data": "data",
    "grupos de usuarios": "grupo",
    "parceiro": "parceiro",
    "compradores": "compradores",
    "comissao": "comissao",
    "cashback": "cashback",
    "vendas totais": "vendas_totais",
}

REQUIRED_CANONICAL = set(CANONICAL_COLUMNS.values())
COLUNAS_MOEDA = ["comissao", "cashback", "vendas_totais"]

_CURRENCY_RE = re.compile(r"[^\d,.\-]")
_DIGITS_RE = re.compile(r"[^\d\-]")


class SchemaError(ValueError):
    """CSV não tem as colunas mínimas esperadas, mesmo após normalização de nomes."""


@dataclass
class ParseReport:
    """Resumo do que aconteceu durante o parsing de um arquivo — nunca fica implícito."""

    source: str
    linhas_lidas: int = 0
    linhas_validas: int = 0
    linhas_descartadas: int = 0
    motivos_descarte: dict[str, int] = field(default_factory=dict)

    def registrar_descarte(self, motivo: str, n: int) -> None:
        if n <= 0:
            return
        self.motivos_descarte[motivo] = self.motivos_descarte.get(motivo, 0) + n
        self.linhas_descartadas += n

    def __str__(self) -> str:
        linhas = [f"{self.source}: {self.linhas_validas}/{self.linhas_lidas} linhas válidas"]
        for motivo, n in self.motivos_descarte.items():
            linhas.append(f"  - descartadas por {motivo}: {n}")
        return "\n".join(linhas)


def _normalizar_nome_coluna(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


def _mapear_colunas(colunas_originais: list[str]) -> dict[str, str]:
    mapa = {}
    for original in colunas_originais:
        chave = _normalizar_nome_coluna(original)
        if chave in CANONICAL_COLUMNS:
            mapa[original] = CANONICAL_COLUMNS[chave]
    return mapa


def parse_moeda_brl(valor) -> float:
    """Converte string de moeda pt-BR ('R$ 10.273', 'R$ 1.234,56', '-R$ 50') em float.

    Retorna NaN para valores vazios ou não conversíveis — nunca lança exceção,
    porque uma linha ruim não pode derrubar o parsing do arquivo inteiro.
    """
    if valor is None:
        return np.nan
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto:
        return np.nan

    negativo = texto.strip().startswith("-")
    texto = _CURRENCY_RE.sub("", texto)
    if not texto:
        return np.nan

    if "," in texto:
        # pt-BR: '.' é separador de milhar, ',' é decimal.
        texto = texto.replace(".", "").replace(",", ".")
    else:
        # Sem vírgula, '.' é ambíguo: pode ser milhar ('10.273') ou decimal
        # ('10.5'). Heurística: só é decimal quando sobra 1 ou 2 dígitos após
        # o último ponto — 3 dígitos exatos é o padrão de milhar pt-BR.
        partes = texto.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
            texto = texto.replace(".", "")

    try:
        numero = float(texto)
    except ValueError:
        return np.nan

    return -numero if negativo and numero > 0 else numero


def parse_inteiro(valor) -> float:
    """Converte contagem (ex: 'compradores') para float, tolerando ruído textual."""
    if valor is None:
        return np.nan
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = _DIGITS_RE.sub("", str(valor).strip())
    if not texto or texto == "-":
        return np.nan

    try:
        return float(texto)
    except ValueError:
        return np.nan


def carregar_csv(caminho: str | Path) -> tuple[pd.DataFrame, ParseReport]:
    """Lê um CSV de teste A/B de cashback de forma defensiva.

    Retorna o DataFrame já limpo e tipado, mais um ParseReport com o que foi
    descartado e por quê. Não assume quantidade de grupos nem nome de parceiro.
    """
    caminho = Path(caminho)
    report = ParseReport(source=caminho.name)

    try:
        bruto = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError as exc:
        raise SchemaError(f"{caminho.name}: arquivo vazio ou sem cabeçalho") from exc
    except pd.errors.ParserError as exc:
        raise SchemaError(f"{caminho.name}: CSV malformado (ex: número de campos inconsistente entre linhas): {exc}") from exc

    report.linhas_lidas = len(bruto)

    mapa_colunas = _mapear_colunas(list(bruto.columns))
    faltando = REQUIRED_CANONICAL - set(mapa_colunas.values())
    if faltando:
        raise SchemaError(
            f"{caminho.name}: colunas obrigatórias ausentes após normalização: {sorted(faltando)}"
        )

    df = bruto.rename(columns=mapa_colunas)[sorted(REQUIRED_CANONICAL)].copy()

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["compradores"] = df["compradores"].map(parse_inteiro)
    for coluna in COLUNAS_MOEDA:
        df[coluna] = df[coluna].map(parse_moeda_brl)

    colunas_obrigatorias = ["data", "grupo", "parceiro", "compradores", *COLUNAS_MOEDA]
    invalido = df[colunas_obrigatorias].isna().any(axis=1) | (df["grupo"].str.strip() == "") | (
        df["parceiro"].str.strip() == ""
    )
    report.registrar_descarte("valor ausente ou malformado", int(invalido.sum()))
    df = df[~invalido]

    negativo = (df[["compradores", *COLUNAS_MOEDA]] < 0).any(axis=1)
    report.registrar_descarte("valor numérico negativo", int(negativo.sum()))
    df = df[~negativo]

    df["grupo"] = df["grupo"].str.strip()
    df["parceiro"] = df["parceiro"].str.strip()

    duplicado = df.duplicated(subset=["data", "grupo", "parceiro"], keep="first")
    report.registrar_descarte("linha duplicada (mesma data/grupo/parceiro)", int(duplicado.sum()))
    df = df[~duplicado]

    df = df.sort_values(["parceiro", "grupo", "data"]).reset_index(drop=True)
    report.linhas_validas = len(df)
    return df, report
