"""
Ponto de entrada CLI do sistema.

Modos:
  python app/main.py --watch          → monitora pasta uploads/ continuamente
  python app/main.py --file foo.xlsx  → processa um arquivo
  python app/main.py --export         → exporta todas as matrizes para outputs/
  python app/main.py --init           → apenas inicializa schema no banco
  python app/main.py --status         → exibe KPIs no terminal

Dashboard Streamlit:
  streamlit run app/dashboard.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Garante que 'app' está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database
from app.excel_reader import XLSXReader
from app.parser import DataParser
from app.comparativo import Comparativo
from app.exportador import Exportador
from app.monitor import FolderMonitor
from app.utils import setup_logger
from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()


def build_db() -> Database:
    url = os.getenv("DATABASE_URL")
    if not url:
        logger.error("DATABASE_URL não definido no .env")
        sys.exit(1)
    db = Database(url)
    if not db.test():
        sys.exit(1)
    return db


def cmd_init(db: Database):
    db.init_schema()
    logger.info("Schema inicializado com sucesso.")


def cmd_file(file_path: str, db: Database):
    template = os.getenv("TEMPLATE_PATH", "templates/modelo.xlsx")
    reader = XLSXReader(template_path=template)
    parser = DataParser()

    sheets = reader.read_file(file_path)
    df = parser.parse_all(sheets)

    if df.empty:
        logger.warning("Nenhum dado extraído.")
        return

    stats = db.bulk_upsert(df, arquivo_origem=Path(file_path).name)
    db.registrar_arquivo(
        Path(file_path).name, "sucesso",
        total_abas=len(sheets),
        total_matrizes=df["nome_matriz"].nunique(),
        total_indicadores=stats["inseridos"],
        detalhes=str(stats),
    )

    table = Table(title=f"Resultado — {Path(file_path).name}")
    table.add_column("Ação"); table.add_column("Quantidade")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)


def cmd_watch(db: Database):
    template = os.getenv("TEMPLATE_PATH", "templates/modelo.xlsx")
    watch    = os.getenv("UPLOAD_FOLDER", "uploads")
    interval = int(os.getenv("WATCH_INTERVAL", "10"))
    monitor  = FolderMonitor(db, watch_folder=watch, template_path=template, interval=interval)
    monitor.start()


def cmd_export(db: Database):
    template = os.getenv("TEMPLATE_PATH", "templates/modelo.xlsx")
    output   = os.getenv("OUTPUT_FOLDER", "outputs")
    exp      = Exportador(template_path=template)
    paths    = exp.exportar_todos(db, output_folder=output)
    logger.info(f"{len(paths)} arquivo(s) exportado(s) para '{output}'.")


def cmd_status(db: Database):
    comp = Comparativo(db)
    kpis = comp.kpis_gerais()

    table = Table(title="KPIs Gerais")
    table.add_column("Indicador"); table.add_column("Valor")
    for k, v in kpis.items():
        table.add_row(k, str(v))
    console.print(table)

    ranking = comp.ranking_matrizes()
    if not ranking.empty:
        t2 = Table(title="Ranking de Matrizes")
        for col in ranking.columns:
            t2.add_column(str(col))
        for _, row in ranking.iterrows():
            t2.add_row(*[str(v) for v in row])
        console.print(t2)


def main():
    setup_logger(
        log_folder=os.getenv("LOG_FOLDER", "logs"),
        level=os.getenv("LOG_LEVEL", "INFO"),
    )

    parser = argparse.ArgumentParser(description="Matriz Indicadores Comitê — ETL CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--init",   action="store_true",  help="Inicializa schema no banco")
    group.add_argument("--file",   type=str,             help="Processa um arquivo XLSX")
    group.add_argument("--watch",  action="store_true",  help="Monitora pasta uploads/ continuamente")
    group.add_argument("--export", action="store_true",  help="Exporta todas as matrizes")
    group.add_argument("--status", action="store_true",  help="Exibe KPIs no terminal")
    args = parser.parse_args()

    db = build_db()

    if args.init:
        cmd_init(db)
    elif args.file:
        cmd_file(args.file, db)
    elif args.watch:
        cmd_watch(db)
    elif args.export:
        cmd_export(db)
    elif args.status:
        cmd_status(db)


if __name__ == "__main__":
    main()
