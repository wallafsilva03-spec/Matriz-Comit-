"""
Lê todas as abas de um arquivo XLSX.

Convenção do nome da aba:
  - Formato esperado: "MATRIZ_YYYY-MM" ou "MATRIZ YYYY-MM" ou "MATRIZ_DD/MM/YYYY"
  - Se não encontrar data, usa a data de modificação do arquivo como fallback.
"""
import re
from pathlib import Path
from datetime import datetime, date
from typing import Optional
import pandas as pd
from utils.logger import get_logger

log = get_logger("etl.reader")

# Padrões de data suportados no nome da aba
_DATE_PATTERNS = [
    (r"(\d{4}[-/]\d{2}[-/]\d{2})", "%Y-%m-%d"),
    (r"(\d{2}[-/]\d{2}[-/]\d{4})", "%d/%m/%Y"),
    (r"(\d{4}[-/]\d{2})",          "%Y-%m"),
    (r"(\d{2}[-/]\d{4})",          "%m/%Y"),
]


def _extract_date(sheet_name: str) -> Optional[date]:
    for pattern, fmt in _DATE_PATTERNS:
        match = re.search(pattern, sheet_name)
        if match:
            raw = match.group(1).replace("/", "-")
            fmt_norm = fmt.replace("/", "-")
            try:
                return datetime.strptime(raw, fmt_norm).date()
            except ValueError:
                continue
    return None


def _extract_matriz(sheet_name: str, extracted_date: Optional[date]) -> str:
    """Remove a porção de data do nome da aba para obter o nome da matriz."""
    name = sheet_name
    for pattern, _ in _DATE_PATTERNS:
        name = re.sub(pattern, "", name)
    # Remove separadores residuais
    name = re.sub(r"[-_\s]+$", "", name).strip()
    return name if name else sheet_name


class XLSXReader:
    def __init__(self, header_row: int = 0):
        self.header_row = header_row

    def read_file(self, file_path: str | Path) -> list[dict]:
        """
        Retorna lista de dicts, um por aba:
          {
            "sheet_name": str,
            "matriz": str,
            "data_referencia": date,
            "dataframe": pd.DataFrame,
          }
        """
        path = Path(file_path)
        log.info(f"Lendo arquivo: {path.name}")

        try:
            xl = pd.ExcelFile(path, engine="openpyxl")
        except Exception as exc:
            log.error(f"Não foi possível abrir {path.name}: {exc}")
            raise

        sheets = []
        file_mtime = date.fromtimestamp(path.stat().st_mtime)

        for sheet_name in xl.sheet_names:
            try:
                df = xl.parse(sheet_name, header=self.header_row)
                if df.empty:
                    log.warning(f"Aba '{sheet_name}' está vazia — ignorada.")
                    continue

                extracted_date = _extract_date(sheet_name) or file_mtime
                matriz = _extract_matriz(sheet_name, extracted_date)

                sheets.append(
                    {
                        "sheet_name": sheet_name,
                        "matriz": matriz,
                        "data_referencia": extracted_date,
                        "dataframe": df,
                    }
                )
                log.info(f"  ↳ Aba '{sheet_name}' → matriz='{matriz}' data={extracted_date} rows={len(df)}")

            except Exception as exc:
                log.error(f"Erro ao ler aba '{sheet_name}': {exc}")

        log.info(f"Total de abas lidas: {len(sheets)}")
        return sheets
