from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from supabase import create_client, Client
from utils.logger import get_logger

log = get_logger("database.connection")


class DatabaseConnection:
    _engine = None
    _session_factory = None
    _supabase: Client = None

    def __init__(self, database_url: str, supabase_url: str, supabase_key: str):
        self._database_url = database_url
        self._supabase_url = supabase_url
        self._supabase_key = supabase_key

    def get_engine(self):
        if self._engine is None:
            self._engine = create_engine(
                self._database_url,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,
                echo=False,
            )
            log.info("SQLAlchemy engine criado.")
        return self._engine

    def get_supabase(self) -> Client:
        if self._supabase is None:
            self._supabase = create_client(self._supabase_url, self._supabase_key)
            log.info("Cliente Supabase criado.")
        return self._supabase

    @contextmanager
    def session(self):
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.get_engine())
        sess: Session = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception as exc:
            sess.rollback()
            log.error(f"Erro na sessão do banco: {exc}")
            raise
        finally:
            sess.close()

    def test_connection(self) -> bool:
        try:
            with self.session() as sess:
                sess.execute(text("SELECT 1"))
            log.info("Conexão com PostgreSQL OK.")
            return True
        except Exception as exc:
            log.error(f"Falha na conexão: {exc}")
            return False
