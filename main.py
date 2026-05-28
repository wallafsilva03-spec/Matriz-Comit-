"""
Ponto de entrada do sistema ETL.

Modos de uso:
  python main.py                  → processa arquivos existentes + inicia watch
  python main.py --once           → processa apenas os arquivos presentes e sai
  python main.py --file foo.xlsx  → processa um único arquivo
  python main.py --query          → exibe comparativo no terminal
"""
import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from config import settings
from database.connection import DatabaseConnection
from database.operations import DatabaseOperations
from etl.loader import DataLoader
from utils.logger import get_logger
from rich.console import Console
from rich.table import Table

log = get_logger("main", log_folder=str(settings.log_folder), level=settings.log_level)
console = Console()


def build_dependencies():
    settings.ensure_folders()
    conn = DatabaseConnection(
        database_url=settings.database_url,
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_key,
    )
    if not conn.test_connection():
        log.error("Não foi possível conectar ao banco. Verifique o .env.")
        sys.exit(1)

    db_ops = DatabaseOperations(conn)
    db_ops.init_schema()

    loader = DataLoader(
        db_ops=db_ops,
        processed_folder=settings.processed_folder,
        error_folder=settings.error_folder,
    )
    return conn, db_ops, loader


def process_existing(loader: DataLoader) -> list[dict]:
    xlsx_files = list(Path(settings.input_folder).glob("*.xlsx")) + \
                 list(Path(settings.input_folder).glob("*.XLSX"))
    if not xlsx_files:
        log.info("Nenhum arquivo XLSX encontrado na pasta input.")
        return []
    results = []
    for f in xlsx_files:
        try:
            result = loader.process_file(f)
            results.append(result)
        except Exception as exc:
            log.error(f"Erro inesperado ao processar {f.name}: {exc}")
    return results


def watch_folder(loader: DataLoader):
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class XLSXHandler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory and event.src_path.lower().endswith(".xlsx"):
                log.info(f"Novo arquivo detectado: {event.src_path}")
                time.sleep(1)  # Aguarda escrita completa
                loader.process_file(event.src_path)

    observer = Observer()
    observer.schedule(XLSXHandler(), str(settings.input_folder), recursive=False)
    observer.start()
    log.info(f"Monitorando pasta '{settings.input_folder}' (Ctrl+C para parar)...")
    try:
        while True:
            time.sleep(settings.watch_interval)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def print_query(db_ops: DatabaseOperations):
    df = db_ops.get_comparativo()
    if df.empty:
        console.print("[yellow]Nenhum registro encontrado.[/yellow]")
        return
    table = Table(title="Comparativo Geral")
    for col in df.columns:
        table.add_column(str(col), overflow="fold")
    for _, row in df.iterrows():
        table.add_row(*[str(v) for v in row])
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="ETL Matriz Comitê → Supabase")
    parser.add_argument("--once",  action="store_true", help="Processa e sai sem monitorar")
    parser.add_argument("--file",  type=str,            help="Processa um arquivo específico")
    parser.add_argument("--query", action="store_true", help="Exibe comparativo no terminal")
    args = parser.parse_args()

    conn, db_ops, loader = build_dependencies()

    if args.query:
        print_query(db_ops)
        return

    if args.file:
        loader.process_file(args.file)
        return

    process_existing(loader)

    if not args.once:
        watch_folder(loader)


if __name__ == "__main__":
    main()
