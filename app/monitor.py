"""
Monitoramento automático da pasta uploads/.
Detecta novos arquivos XLSX e dispara o pipeline ETL completo.
"""
from __future__ import annotations

import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from loguru import logger

from app.excel_reader import XLSXReader
from app.parser import DataParser
from app.database import Database
from app.exportador import Exportador


class XLSXHandler(FileSystemEventHandler):
    def __init__(self, db: Database, template_path: str = "templates/modelo.xlsx"):
        self.db         = db
        self.reader     = XLSXReader(template_path=template_path)
        self.parser     = DataParser()
        self.exportador = Exportador(template_path=template_path)
        self._processing: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".xlsx":
            return
        if str(path) in self._processing:
            return

        self._processing.add(str(path))
        logger.info(f"Novo arquivo detectado: {path.name}")
        time.sleep(1)  # aguarda escrita completa

        try:
            self._process(path)
        finally:
            self._processing.discard(str(path))

    def _process(self, path: Path) -> None:
        try:
            sheet_results = self.reader.read_file(path)
            df = self.parser.parse_all(sheet_results)

            if df.empty:
                logger.warning(f"Nenhum dado extraído de {path.name}")
                self.db.registrar_arquivo(path.name, "erro", detalhes="Sem dados")
                return

            stats = self.db.bulk_upsert(df, arquivo_origem=path.name)
            self.db.registrar_arquivo(
                path.name,
                "sucesso",
                total_abas=len(sheet_results),
                total_matrizes=df["nome_matriz"].nunique(),
                total_indicadores=stats["inseridos"] + stats["atualizados"],
                detalhes=str(stats),
            )
            logger.info(f"✔ {path.name} processado: {stats}")

        except Exception as exc:
            logger.error(f"Falha ao processar {path.name}: {exc}")
            self.db.registrar_arquivo(path.name, "erro", detalhes=str(exc))


class FolderMonitor:
    def __init__(
        self,
        db: Database,
        watch_folder: str = "uploads",
        template_path: str = "templates/modelo.xlsx",
        interval: int = 10,
    ):
        self.db           = db
        self.watch_folder = Path(watch_folder)
        self.template_path = template_path
        self.interval     = interval

    def start(self) -> None:
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        handler  = XLSXHandler(self.db, self.template_path)
        observer = Observer()
        observer.schedule(handler, str(self.watch_folder), recursive=False)
        observer.start()
        logger.info(f"Monitorando '{self.watch_folder}' (Ctrl+C para parar)...")

        # Processa arquivos já existentes na pasta
        for xlsx in self.watch_folder.glob("*.xlsx"):
            logger.info(f"Processando arquivo existente: {xlsx.name}")
            handler._process(xlsx)

        try:
            while True:
                time.sleep(self.interval)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
        logger.info("Monitor encerrado.")
