"""
Padroniza e enriquece os dados lidos de cada aba antes da carga.

Responsabilidades:
  - Identificar coluna 'nome' (heurística por nome de coluna)
  - Remover linhas completamente vazias
  - Normalizar strings
  - Serializar colunas extras em dados_json
"""
import json
from datetime import date
from typing import Optional
import pandas as pd
from utils.logger import get_logger

log = get_logger("etl.transformer")

# Possíveis nomes para a coluna principal de identificação
_NOME_CANDIDATES = ["nome", "name", "colaborador", "funcionario", "participante", "membro"]


def _find_nome_column(df: pd.DataFrame) -> Optional[str]:
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for candidate in _NOME_CANDIDATES:
        if candidate in cols_lower:
            return cols_lower[candidate]
    # Fallback: primeira coluna de texto
    for col in df.columns:
        if df[col].dtype == object:
            return col
    return None


class DataTransformer:
    def transform(
        self,
        df: pd.DataFrame,
        matriz: str,
        data_referencia: date,
    ) -> pd.DataFrame:
        df = df.copy()

        # Remove linhas completamente vazias
        df.dropna(how="all", inplace=True)
        df.reset_index(drop=True, inplace=True)

        nome_col = _find_nome_column(df)
        if nome_col is None:
            log.warning("Coluna 'nome' não identificada — usando índice como nome.")
            df["nome"] = df.index.astype(str)
            nome_col = "nome"

        # Renomeia para padronizar
        if nome_col != "nome":
            df.rename(columns={nome_col: "nome"}, inplace=True)

        # Remove registros sem nome
        df = df[df["nome"].notna() & (df["nome"].astype(str).str.strip() != "")]

        # Normaliza strings
        df["nome"] = df["nome"].astype(str).str.strip()

        # Campos obrigatórios
        df["matriz"] = matriz
        df["data_referencia"] = data_referencia

        # Serializa colunas extras em dados_json
        extra_cols = [c for c in df.columns if c not in ("nome", "matriz", "data_referencia")]
        df["dados_json"] = df[extra_cols].apply(
            lambda row: json.dumps(
                {k: (str(v) if not pd.isna(v) else None) for k, v in row.items()},
                ensure_ascii=False,
            ),
            axis=1,
        )

        result = df[["nome", "matriz", "data_referencia", "dados_json"]].copy()
        log.debug(f"Transformação concluída: {len(result)} registros válidos.")
        return result
