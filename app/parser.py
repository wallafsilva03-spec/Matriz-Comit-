"""
Limpeza, padronização e validação dos dados extraídos pelo excel_reader.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from app.utils import safe_numeric, safe_str, parse_date, make_hash


# ---------------------------------------------------------------------------
# Mapeamento de status para categoria semáforo
# ---------------------------------------------------------------------------
_STATUS_MAP = {
    "ok":        "verde",
    "atingido":  "verde",
    "verde":     "verde",
    "bom":       "verde",
    "parcial":   "amarelo",
    "alerta":    "amarelo",
    "amarelo":   "amarelo",
    "atenção":   "amarelo",
    "atencao":   "amarelo",
    "crítico":   "vermelho",
    "critico":   "vermelho",
    "vermelho":  "vermelho",
    "ruim":      "vermelho",
    "não":       "vermelho",
    "nao":       "vermelho",
}


def _normalize_status(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).lower().strip()
    for trigger, semaforo in _STATUS_MAP.items():
        if trigger in key:
            return semaforo
    return str(raw).strip()


class DataParser:
    def parse_sheet(self, sheet_result: dict) -> pd.DataFrame:
        """
        Recebe o dict de uma aba retornado por XLSXReader.read_file()
        e devolve um DataFrame limpo e pronto para carga.
        """
        rows = sheet_result.get("rows", [])
        info = sheet_result.get("sheet_info", {})

        if not rows:
            return pd.DataFrame()

        records = []
        for row in rows:
            # Data: tenta info da aba, depois parse direto
            data_ref = info.get("data")
            if data_ref is None:
                data_ref = parse_date(str(info.get("data_str", "")))
            if data_ref is None:
                data_ref = datetime.now().date()

            nome_matriz  = safe_str(info.get("matriz")) or "SEM_MATRIZ"
            tipo_quadro  = safe_str(info.get("tipo_quadro")) or sheet_result.get("sheet_name")
            indicador    = safe_str(row.get("indicador"))
            if not indicador:
                continue

            meta      = safe_numeric(row.get("meta"))
            realizado = safe_numeric(row.get("realizado"))

            # Cálculo automático de resultado % se possível
            resultado_raw = row.get("resultado")
            resultado_num = safe_numeric(resultado_raw)
            if resultado_num is None and meta and realizado is not None and meta != 0:
                resultado_num = round((realizado / meta) * 100, 2)

            status_raw  = safe_str(row.get("status"))
            status_norm = _normalize_status(status_raw)

            # Inferência de status pelo % realizado se não informado
            if not status_norm and resultado_num is not None:
                if resultado_num >= 100:
                    status_norm = "verde"
                elif resultado_num >= 80:
                    status_norm = "amarelo"
                else:
                    status_norm = "vermelho"

            chave_indicador = make_hash(nome_matriz, tipo_quadro, indicador, str(data_ref))

            records.append({
                "nome_matriz":   nome_matriz,
                "tipo_quadro":   tipo_quadro,
                "data_referencia": data_ref,
                "categoria":     safe_str(row.get("categoria")),
                "indicador":     indicador,
                "meta":          meta,
                "realizado":     realizado,
                "resultado":     resultado_num,
                "status":        status_norm,
                "status_original": status_raw,
                "area":          safe_str(row.get("area")),
                "setor":         safe_str(row.get("setor")),
                "responsavel":   safe_str(row.get("responsavel")),
                "observacao":    safe_str(row.get("observacao")),
                "chave_hash":    chave_indicador,
            })

        df = pd.DataFrame(records)
        if df.empty:
            return df

        # Remove duplicatas pelo hash (mesma aba com linhas repetidas)
        df.drop_duplicates(subset=["chave_hash"], keep="first", inplace=True)
        df.reset_index(drop=True, inplace=True)

        logger.debug(f"Parser: {len(df)} registros válidos para '{info.get('matriz','?')}' {info.get('data_str','')}")
        return df

    def parse_all(self, sheet_results: list[dict]) -> pd.DataFrame:
        frames = []
        for sheet in sheet_results:
            df = self.parse_sheet(sheet)
            if not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
