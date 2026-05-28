"""
Lê arquivos XLSX preservando estilos e estrutura de células mescladas.
Detecta automaticamente o padrão de abas do modelo Matriz Indicadores Comitê.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.worksheet.worksheet import Worksheet
from loguru import logger

from app.utils import parse_sheet_name


# ---------------------------------------------------------------------------
# Colunas esperadas no modelo (variações aceitas por coluna)
# ---------------------------------------------------------------------------
_COL_ALIASES: dict[str, list[str]] = {
    "categoria":    ["categoria", "category", "cat"],
    "indicador":    ["indicador", "indicator", "nome", "descricao", "descrição"],
    "meta":         ["meta", "target", "objetivo"],
    "realizado":    ["realizado", "resultado", "result", "real", "valor"],
    "status":       ["status", "situação", "situacao", "semaforo", "semáforo"],
    "area":         ["area", "área", "departamento"],
    "setor":        ["setor", "sector", "unidade"],
    "responsavel":  ["responsavel", "responsável", "resp", "gestor"],
    "observacao":   ["observacao", "observação", "obs", "comentario", "comentário", "nota"],
}


def _expand_merged_cells(ws: Worksheet) -> dict[tuple[int, int], Any]:
    """
    Cria mapa {(row, col): valor} desdobrando células mescladas.
    Cada célula mesclada recebe o valor da célula-mestra do bloco.
    """
    cell_values: dict[tuple[int, int], Any] = {}

    # Coleta valores das células normais
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell, MergedCell):
                cell_values[(cell.row, cell.column)] = cell.value

    # Propaga valor da célula-mestra para todas as células do bloco mesclado
    for merged_range in ws.merged_cells.ranges:
        master = ws.cell(merged_range.min_row, merged_range.min_col)
        master_value = master.value
        for row in range(merged_range.min_row, merged_range.max_row + 1):
            for col in range(merged_range.min_col, merged_range.max_col + 1):
                cell_values[(row, col)] = master_value

    return cell_values


def _detect_header_row(ws: Worksheet, cell_map: dict) -> Optional[int]:
    """
    Detecta a linha de cabeçalho procurando por 'indicador' ou termos similares
    nas primeiras 20 linhas.
    """
    trigger_words = {"indicador", "indicator", "categoria", "meta", "realizado", "status"}
    for row_idx in range(1, min(21, ws.max_row + 1)):
        row_values = {
            str(cell_map.get((row_idx, c), "") or "").lower().strip()
            for c in range(1, ws.max_column + 1)
        }
        if row_values & trigger_words:
            return row_idx
    return None


def _map_columns(header_row: int, ws: Worksheet, cell_map: dict) -> dict[str, int]:
    """
    Mapeia nome canônico → índice de coluna usando aliases definidos.
    """
    col_map: dict[str, int] = {}
    for col_idx in range(1, ws.max_column + 1):
        raw = str(cell_map.get((header_row, col_idx), "") or "").lower().strip()
        if not raw:
            continue
        for canonical, aliases in _COL_ALIASES.items():
            if any(raw.startswith(a) or a in raw for a in aliases):
                if canonical not in col_map:
                    col_map[canonical] = col_idx
    return col_map


def _extract_rows(
    ws: Worksheet,
    cell_map: dict,
    header_row: int,
    col_map: dict[str, int],
    matriz_info: dict,
) -> list[dict]:
    """Extrai linhas de dados abaixo do cabeçalho."""
    rows = []
    current_categoria = None

    for row_idx in range(header_row + 1, ws.max_row + 1):
        # Tenta capturar categoria da coluna correspondente (ou propagada)
        if "categoria" in col_map:
            cat_val = cell_map.get((row_idx, col_map["categoria"]))
            if cat_val and str(cat_val).strip():
                current_categoria = str(cat_val).strip()

        indicador_col = col_map.get("indicador")
        indicador_val = cell_map.get((row_idx, indicador_col)) if indicador_col else None

        if not indicador_val or not str(indicador_val).strip():
            continue

        def get(field: str):
            col = col_map.get(field)
            return cell_map.get((row_idx, col)) if col else None

        rows.append({
            **matriz_info,
            "categoria":   current_categoria,
            "indicador":   str(indicador_val).strip(),
            "meta":        get("meta"),
            "realizado":   get("realizado"),
            "resultado":   get("realizado"),   # alias
            "status":      get("status"),
            "area":        get("area"),
            "setor":       get("setor"),
            "responsavel": get("responsavel"),
            "observacao":  get("observacao"),
            "_row_idx":    row_idx,
        })

    return rows


class XLSXReader:
    def __init__(self, template_path: Optional[str] = None):
        self.template_path = Path(template_path) if template_path else None

    def read_file(self, file_path: str | Path) -> list[dict]:
        """
        Lê todas as abas do arquivo e retorna lista de dicts por aba processada.
        Cada dict contém: sheet_info, rows (lista de indicadores extraídos).
        """
        path = Path(file_path)
        logger.info(f"Abrindo: {path.name}")

        try:
            wb = openpyxl.load_workbook(path, data_only=True)
        except Exception as exc:
            logger.error(f"Erro ao abrir {path.name}: {exc}")
            raise

        results = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheet_info = parse_sheet_name(sheet_name)

            # Ignora abas sem matriz/data (ex: "Quadro Geral Op." sem contexto)
            if not sheet_info.get("matriz") and not sheet_info.get("data"):
                logger.debug(f"  ↳ Aba '{sheet_name}' sem matriz/data — incluída sem filtro.")

            logger.info(f"  ↳ Aba: '{sheet_name}' → {sheet_info}")

            try:
                cell_map = _expand_merged_cells(ws)
                header_row = _detect_header_row(ws, cell_map)

                if header_row is None:
                    logger.warning(f"    Cabeçalho não encontrado em '{sheet_name}' — ignorada.")
                    continue

                col_map = _map_columns(header_row, ws, cell_map)
                if not col_map.get("indicador"):
                    logger.warning(f"    Coluna 'indicador' não mapeada em '{sheet_name}' — ignorada.")
                    continue

                rows = _extract_rows(ws, cell_map, header_row, col_map, sheet_info)
                logger.info(f"    {len(rows)} indicadores extraídos.")

                results.append({
                    "sheet_name":  sheet_name,
                    "sheet_info":  sheet_info,
                    "col_map":     col_map,
                    "header_row":  header_row,
                    "rows":        rows,
                    "worksheet":   ws,   # mantido para exportação de estilos
                })

            except Exception as exc:
                logger.error(f"    Erro ao processar aba '{sheet_name}': {exc}")

        wb.close()
        logger.info(f"Total: {len(results)} abas processadas em {path.name}")
        return results

    def get_workbook(self, file_path: str | Path) -> openpyxl.Workbook:
        """Retorna workbook completo com estilos (para uso no exportador)."""
        return openpyxl.load_workbook(str(file_path))
