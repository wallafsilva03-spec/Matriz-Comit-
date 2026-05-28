"""Utilitários compartilhados entre módulos."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Logger configurado centralmente
# ---------------------------------------------------------------------------

def setup_logger(log_folder: str = "logs", level: str = "INFO") -> None:
    Path(log_folder).mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        colorize=True,
    )
    logger.add(
        Path(log_folder) / "sistema_{time:YYYY-MM-DD}.log",
        level=level,
        rotation="1 day",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
    )
    logger.add(
        Path(log_folder) / "erros_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation="1 day",
        retention="60 days",
        compression="zip",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Hashing para chaves únicas
# ---------------------------------------------------------------------------

def make_hash(*parts: str) -> str:
    raw = "|".join(str(p).strip().lower() for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Parsing de datas no formato DD.MM (ex: 27.05 ou 27.5)
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    (r"(\d{4})[-/\.](\d{2})[-/\.](\d{2})", "ymd"),   # 2024-05-27
    (r"(\d{2})[-/\.](\d{2})[-/\.](\d{4})", "dmy"),   # 27-05-2024
    (r"(\d{4})[-/\.](\d{1,2})",             "ym"),    # 2024-05
    (r"(\d{1,2})[-/\.](\d{1,2})",           "dm"),    # 27.05 ou 27.5
]


def parse_date(raw: str, reference_year: Optional[int] = None) -> Optional[date]:
    raw = str(raw).strip()
    year = reference_year or datetime.now().year

    for pattern, fmt in _DATE_PATTERNS:
        m = re.search(pattern, raw)
        if not m:
            continue
        try:
            if fmt == "ymd":
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if fmt == "dmy":
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if fmt == "ym":
                return date(int(m.group(1)), int(m.group(2)), 1)
            if fmt == "dm":
                return date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Parsing do nome de aba
# Padrões aceitos:
#   "Quadro Geral - COP 27.05"
#   "Quadro Detalhado - CEMMA 13.05"
#   "Quadro Geral Op."   (sem matriz/data)
# ---------------------------------------------------------------------------

_ABA_PATTERN = re.compile(
    r"^(?P<tipo>Quadro\s+\S+(?:\s+\S+)?)"   # "Quadro Geral" / "Quadro Detalhado"
    r"\s*-\s*"                               # separador " - "
    r"(?P<matriz>[A-Z][A-Z0-9]+)"            # código da matriz: COP, CEMMA, etc.
    r"\s+"
    r"(?P<data>\d{1,2}\.\d{1,2}(?:\.\d{4})?)",  # data: 27.05 ou 27.05.2024
    re.IGNORECASE,
)


def parse_sheet_name(name: str) -> dict:
    """
    Retorna dict com chaves: tipo_quadro, matriz, data_str, data (date|None).
    Se não conseguir extrair matriz/data, retorna apenas tipo_quadro.
    """
    result = {"tipo_quadro": None, "matriz": None, "data_str": None, "data": None}
    m = _ABA_PATTERN.match(name.strip())
    if m:
        result["tipo_quadro"] = m.group("tipo").strip().title()
        result["matriz"]      = m.group("matriz").strip().upper()
        result["data_str"]    = m.group("data").strip()
        result["data"]        = parse_date(result["data_str"])
    else:
        # Aba sem matriz/data (ex: "Quadro Geral Op.")
        result["tipo_quadro"] = name.strip()
    return result


# ---------------------------------------------------------------------------
# Helpers de valor
# ---------------------------------------------------------------------------

def safe_numeric(value) -> Optional[float]:
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", ".").replace("%", "").strip()
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def safe_str(value, max_len: int = 500) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s[:max_len] if s else None
