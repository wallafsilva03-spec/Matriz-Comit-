"""
Orquestra a leitura, transformação, validação e carga de um arquivo XLSX.
"""
import shutil
from pathlib import Path
from datetime import datetime
import pandas as pd
from .reader import XLSXReader
from .transformer import DataTransformer
from .validator import DataValidator
from database.operations import DatabaseOperations
from utils.logger import get_logger

log = get_logger("etl.loader")


class DataLoader:
    def __init__(
        self,
        db_ops: DatabaseOperations,
        processed_folder: str | Path = "data/processed",
        error_folder: str | Path = "data/error",
    ):
        self.db_ops = db_ops
        self.processed_folder = Path(processed_folder)
        self.error_folder = Path(error_folder)
        self.reader = XLSXReader()
        self.transformer = DataTransformer()
        self.validator = DataValidator()

    def process_file(self, file_path: str | Path) -> dict:
        path = Path(file_path)
        log.info(f"=== Iniciando processamento: {path.name} ===")
        self.db_ops.log_etl("INFO", f"Iniciando: {path.name}")

        total_inseridos = 0
        total_duplicados = 0
        total_erros = 0
        abas_processadas = 0
        status = "sucesso"

        try:
            sheets = self.reader.read_file(path)
            if not sheets:
                raise ValueError("Nenhuma aba com dados encontrada.")

            for sheet in sheets:
                try:
                    df_transformed = self.transformer.transform(
                        sheet["dataframe"],
                        sheet["matriz"],
                        sheet["data_referencia"],
                    )
                    df_valid, df_invalid, validation_errors = self.validator.validate(df_transformed)

                    if validation_errors:
                        for err in validation_errors:
                            self.db_ops.log_etl("WARNING", err, modulo="validator")

                    if df_valid.empty:
                        log.warning(f"Aba '{sheet['sheet_name']}' sem registros válidos.")
                        continue

                    result = self.db_ops.upsert_registros(df_valid, path.name)
                    total_inseridos += result["inseridos"]
                    total_duplicados += result["duplicados"]
                    total_erros += result["erros"]
                    abas_processadas += 1

                except Exception as exc:
                    log.error(f"Erro ao processar aba '{sheet['sheet_name']}': {exc}")
                    total_erros += 1
                    status = "parcial"

            # Move para pasta de processados
            dest = self.processed_folder / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{path.name}"
            shutil.move(str(path), str(dest))
            log.info(f"Arquivo movido para: {dest}")

        except Exception as exc:
            log.error(f"Falha crítica ao processar {path.name}: {exc}")
            status = "erro"
            shutil.move(str(path), str(self.error_folder / path.name))
            self.db_ops.log_etl("ERROR", f"Falha crítica: {path.name} → {exc}")

        finally:
            self.db_ops.registrar_arquivo(
                nome_arquivo=path.name,
                status=status,
                total_abas=abas_processadas,
                total_registros=total_inseridos,
                detalhes=f"duplicados={total_duplicados} erros={total_erros}",
            )

        summary = {
            "arquivo": path.name,
            "status": status,
            "abas": abas_processadas,
            "inseridos": total_inseridos,
            "duplicados": total_duplicados,
            "erros": total_erros,
        }
        log.info(f"=== Resumo: {summary} ===")
        self.db_ops.log_etl("INFO", f"Concluído: {summary}")
        return summary
