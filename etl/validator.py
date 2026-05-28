"""
Valida o DataFrame transformado antes de enviar ao banco.

Retorna (df_valido, df_invalido, lista_de_erros).
"""
from datetime import date
import pandas as pd
from utils.logger import get_logger

log = get_logger("etl.validator")

REQUIRED_COLUMNS = {"nome", "matriz", "data_referencia"}


class DataValidator:
    def validate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
        erros: list[str] = []

        # Colunas obrigatórias
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            msg = f"Colunas obrigatórias ausentes: {missing}"
            log.error(msg)
            erros.append(msg)
            return pd.DataFrame(), df, erros

        mask_valid = pd.Series([True] * len(df), index=df.index)

        # Nome não pode ser vazio
        nome_vazio = df["nome"].isna() | (df["nome"].str.strip() == "")
        if nome_vazio.any():
            erros.append(f"{nome_vazio.sum()} registros com 'nome' vazio ignorados.")
            mask_valid &= ~nome_vazio

        # Matriz não pode ser vazia
        matriz_vazia = df["matriz"].isna() | (df["matriz"].astype(str).str.strip() == "")
        if matriz_vazia.any():
            erros.append(f"{matriz_vazia.sum()} registros com 'matriz' vazio ignorados.")
            mask_valid &= ~matriz_vazia

        # data_referencia deve ser date
        def is_valid_date(v):
            if isinstance(v, date):
                return True
            try:
                pd.to_datetime(v)
                return True
            except Exception:
                return False

        data_invalida = ~df["data_referencia"].apply(is_valid_date)
        if data_invalida.any():
            erros.append(f"{data_invalida.sum()} registros com 'data_referencia' inválida ignorados.")
            mask_valid &= ~data_invalida

        df_valido = df[mask_valid].reset_index(drop=True)
        df_invalido = df[~mask_valid].reset_index(drop=True)

        log.info(f"Validação: {len(df_valido)} válidos / {len(df_invalido)} inválidos.")
        for e in erros:
            log.warning(e)

        return df_valido, df_invalido, erros
