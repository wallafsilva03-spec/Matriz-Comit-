import hashlib
from datetime import datetime
from typing import Optional
import pandas as pd
from sqlalchemy import text
from .connection import DatabaseConnection
from utils.logger import get_logger

log = get_logger("database.operations")


def _make_hash(nome: str, matriz: str, data_referencia: str) -> str:
    raw = f"{str(nome).strip().lower()}|{str(matriz).strip().lower()}|{str(data_referencia).strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


class DatabaseOperations:
    def __init__(self, conn: DatabaseConnection):
        self.conn = conn

    # ------------------------------------------------------------------
    # Inicialização do schema
    # ------------------------------------------------------------------
    def init_schema(self) -> None:
        sql_path = "scripts/sql/schema.sql"
        try:
            with open(sql_path, "r", encoding="utf-8") as f:
                ddl = f.read()
            with self.conn.session() as sess:
                sess.execute(text(ddl))
            log.info("Schema criado/verificado com sucesso.")
        except Exception as exc:
            log.error(f"Erro ao inicializar schema: {exc}")
            raise

    # ------------------------------------------------------------------
    # Inserção de registros principais
    # ------------------------------------------------------------------
    def upsert_registros(self, df: pd.DataFrame, arquivo_origem: str) -> dict:
        inseridos = 0
        duplicados = 0
        erros = 0

        for _, row in df.iterrows():
            try:
                chave = _make_hash(row["nome"], row["matriz"], str(row["data_referencia"]))
                with self.conn.session() as sess:
                    existe = sess.execute(
                        text("SELECT id FROM registros WHERE chave_hash = :h"),
                        {"h": chave},
                    ).fetchone()

                    if existe:
                        duplicados += 1
                        continue

                    # Verifica histórico: mesmo nome+matriz, data diferente
                    registro_anterior = sess.execute(
                        text(
                            """
                            SELECT id, data_referencia FROM registros
                            WHERE nome_normalizado = :n AND matriz = :m
                            ORDER BY data_referencia DESC
                            LIMIT 1
                            """
                        ),
                        {"n": str(row["nome"]).strip().lower(), "m": str(row["matriz"]).strip()},
                    ).fetchone()

                    if registro_anterior:
                        # Arquiva o anterior no histórico
                        self._arquivar_historico(sess, registro_anterior[0])

                    sess.execute(
                        text(
                            """
                            INSERT INTO registros
                                (chave_hash, nome, nome_normalizado, matriz, data_referencia,
                                 dados_json, arquivo_origem, criado_em, atualizado_em)
                            VALUES
                                (:hash, :nome, :nome_n, :matriz, :data,
                                 :dados::jsonb, :arquivo, NOW(), NOW())
                            """
                        ),
                        {
                            "hash": chave,
                            "nome": str(row["nome"]).strip(),
                            "nome_n": str(row["nome"]).strip().lower(),
                            "matriz": str(row["matriz"]).strip(),
                            "data": row["data_referencia"],
                            "dados": row.get("dados_json", "{}"),
                            "arquivo": arquivo_origem,
                        },
                    )
                    inseridos += 1

            except Exception as exc:
                log.error(f"Erro ao inserir registro {row.get('nome')}: {exc}")
                erros += 1

        log.info(f"upsert_registros → inseridos={inseridos} duplicados={duplicados} erros={erros}")
        return {"inseridos": inseridos, "duplicados": duplicados, "erros": erros}

    def _arquivar_historico(self, sess, registro_id: int) -> None:
        sess.execute(
            text(
                """
                INSERT INTO registros_historico
                    (registro_id, nome, nome_normalizado, matriz, data_referencia,
                     dados_json, arquivo_origem, arquivado_em)
                SELECT id, nome, nome_normalizado, matriz, data_referencia,
                       dados_json, arquivo_origem, NOW()
                FROM registros
                WHERE id = :id
                ON CONFLICT DO NOTHING
                """
            ),
            {"id": registro_id},
        )

    # ------------------------------------------------------------------
    # Log de arquivos processados
    # ------------------------------------------------------------------
    def registrar_arquivo(
        self,
        nome_arquivo: str,
        status: str,
        total_abas: int = 0,
        total_registros: int = 0,
        detalhes: Optional[str] = None,
    ) -> None:
        try:
            with self.conn.session() as sess:
                sess.execute(
                    text(
                        """
                        INSERT INTO arquivos_processados
                            (nome_arquivo, status, total_abas, total_registros, detalhes, processado_em)
                        VALUES (:nome, :status, :abas, :regs, :det, NOW())
                        """
                    ),
                    {
                        "nome": nome_arquivo,
                        "status": status,
                        "abas": total_abas,
                        "regs": total_registros,
                        "det": detalhes,
                    },
                )
        except Exception as exc:
            log.error(f"Erro ao registrar arquivo: {exc}")

    # ------------------------------------------------------------------
    # Log de execução ETL
    # ------------------------------------------------------------------
    def log_etl(self, nivel: str, mensagem: str, modulo: str = "etl") -> None:
        try:
            with self.conn.session() as sess:
                sess.execute(
                    text(
                        """
                        INSERT INTO logs_etl (nivel, mensagem, modulo, criado_em)
                        VALUES (:nivel, :msg, :mod, NOW())
                        """
                    ),
                    {"nivel": nivel, "msg": mensagem, "mod": modulo},
                )
        except Exception:
            pass  # Log não pode bloquear o fluxo principal

    # ------------------------------------------------------------------
    # Consultas analíticas (usadas pelo Power BI / Excel)
    # ------------------------------------------------------------------
    def get_comparativo(self) -> pd.DataFrame:
        sql = """
            SELECT
                r.nome,
                r.matriz,
                r.data_referencia,
                r.dados_json,
                COUNT(h.id) AS qtd_versoes_historico
            FROM registros r
            LEFT JOIN registros_historico h ON h.nome_normalizado = r.nome_normalizado
                AND h.matriz = r.matriz
            GROUP BY r.nome, r.matriz, r.data_referencia, r.dados_json
            ORDER BY r.matriz, r.nome, r.data_referencia
        """
        with self.conn.session() as sess:
            result = sess.execute(text(sql))
            return pd.DataFrame(result.fetchall(), columns=result.keys())

    def get_evolucao_temporal(self, nome: Optional[str] = None, matriz: Optional[str] = None) -> pd.DataFrame:
        where_clauses = []
        params = {}
        if nome:
            where_clauses.append("nome_normalizado = :nome")
            params["nome"] = nome.strip().lower()
        if matriz:
            where_clauses.append("matriz = :matriz")
            params["matriz"] = matriz.strip()

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        sql = f"""
            SELECT nome, matriz, data_referencia, dados_json, 'historico' AS origem
            FROM registros_historico
            {where_sql}
            UNION ALL
            SELECT nome, matriz, data_referencia, dados_json, 'atual' AS origem
            FROM registros
            {where_sql}
            ORDER BY nome, matriz, data_referencia
        """
        with self.conn.session() as sess:
            result = sess.execute(text(sql), params)
            return pd.DataFrame(result.fetchall(), columns=result.keys())
