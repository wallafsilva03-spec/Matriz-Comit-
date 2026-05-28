"""
Conexão e operações no banco Supabase (PostgreSQL via SQLAlchemy).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from app.utils import make_hash


class Database:
    def __init__(self, database_url: str):
        self._url = database_url
        self._engine = None
        self._session_factory = None

    def engine(self):
        if self._engine is None:
            self._engine = create_engine(
                self._url,
                pool_size=5,
                max_overflow=10,
                pool_recycle=1800,
                echo=False,
            )
        return self._engine

    @contextmanager
    def session(self):
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine())
        sess: Session = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception as exc:
            sess.rollback()
            logger.error(f"Erro na sessão: {exc}")
            raise
        finally:
            sess.close()

    def test(self) -> bool:
        try:
            with self.session() as s:
                s.execute(text("SELECT 1"))
            logger.info("Conexão PostgreSQL OK.")
            return True
        except Exception as exc:
            logger.error(f"Falha na conexão: {exc}")
            return False

    def init_schema(self) -> None:
        sql_path = Path("scripts/sql/schema.sql")
        with open(sql_path, encoding="utf-8") as f:
            ddl = f.read()
        with self.session() as s:
            s.execute(text(ddl))
        logger.info("Schema inicializado.")

    # ------------------------------------------------------------------
    # MATRIZES
    # ------------------------------------------------------------------

    def get_or_create_matriz(
        self,
        nome_matriz: str,
        tipo_quadro: str,
        data_referencia,
        arquivo_origem: str = "",
    ) -> int:
        chave = make_hash(nome_matriz, tipo_quadro, str(data_referencia))
        with self.session() as s:
            row = s.execute(
                text("SELECT id FROM matrizes WHERE chave_hash = :h"),
                {"h": chave},
            ).fetchone()
            if row:
                return row[0]

            result = s.execute(
                text("""
                    INSERT INTO matrizes
                        (nome_matriz, tipo_quadro, data_referencia, arquivo_origem, chave_hash)
                    VALUES (:nm, :tq, :dr, :ao, :h)
                    RETURNING id
                """),
                {
                    "nm": nome_matriz,
                    "tq": tipo_quadro,
                    "dr": data_referencia,
                    "ao": arquivo_origem,
                    "h":  chave,
                },
            )
            new_id = result.fetchone()[0]
            logger.debug(f"Nova matriz criada: {nome_matriz} / {tipo_quadro} / {data_referencia} (id={new_id})")
            return new_id

    # ------------------------------------------------------------------
    # INDICADORES
    # ------------------------------------------------------------------

    def upsert_indicador(self, matriz_id: int, row: dict) -> dict:
        """
        Insere ou atualiza um indicador.
        Se os valores mudaram, registra no histórico.
        Retorna {'acao': 'inserido'|'atualizado'|'duplicado', 'id': int}
        """
        chave = row["chave_hash"]

        with self.session() as s:
            existing = s.execute(
                text("""
                    SELECT id, meta, realizado, resultado, status, area, setor,
                           responsavel, observacao
                    FROM indicadores WHERE chave_hash = :h
                """),
                {"h": chave},
            ).fetchone()

            if existing:
                # Verifica se há mudanças relevantes
                campos = ["meta", "realizado", "resultado", "status", "area", "setor", "responsavel", "observacao"]
                mudancas = []
                ex_dict = dict(zip(campos, existing[1:]))
                for campo in campos:
                    val_novo = row.get(campo)
                    val_ant  = ex_dict.get(campo)
                    if str(val_novo) != str(val_ant):
                        mudancas.append((campo, val_ant, val_novo))

                if not mudancas:
                    return {"acao": "duplicado", "id": existing[0]}

                # Atualiza
                s.execute(
                    text("""
                        UPDATE indicadores SET
                            meta=:meta, realizado=:realizado, resultado=:resultado,
                            status=:status, area=:area, setor=:setor,
                            responsavel=:responsavel, observacao=:observacao,
                            atualizado_em=NOW()
                        WHERE id=:id
                    """),
                    {**{k: row.get(k) for k in campos}, "id": existing[0]},
                )

                # Histórico
                for campo, ant, novo in mudancas:
                    s.execute(
                        text("""
                            INSERT INTO historico_indicadores
                                (indicador_id, campo_alterado, valor_anterior, valor_novo)
                            VALUES (:iid, :campo, :ant, :novo)
                        """),
                        {"iid": existing[0], "campo": campo, "ant": str(ant), "novo": str(novo)},
                    )
                return {"acao": "atualizado", "id": existing[0]}

            # Insert
            result = s.execute(
                text("""
                    INSERT INTO indicadores
                        (matriz_id, categoria, indicador, meta, realizado, resultado,
                         status, area, setor, responsavel, observacao, data_referencia, chave_hash)
                    VALUES
                        (:mid, :cat, :ind, :meta, :real, :res,
                         :status, :area, :setor, :resp, :obs, :dr, :h)
                    RETURNING id
                """),
                {
                    "mid":    matriz_id,
                    "cat":    row.get("categoria"),
                    "ind":    row["indicador"],
                    "meta":   row.get("meta"),
                    "real":   row.get("realizado"),
                    "res":    row.get("resultado"),
                    "status": row.get("status"),
                    "area":   row.get("area"),
                    "setor":  row.get("setor"),
                    "resp":   row.get("responsavel"),
                    "obs":    row.get("observacao"),
                    "dr":     row["data_referencia"],
                    "h":      chave,
                },
            )
            new_id = result.fetchone()[0]
            return {"acao": "inserido", "id": new_id}

    def bulk_upsert(self, df: pd.DataFrame, arquivo_origem: str = "") -> dict:
        """Processa DataFrame completo e retorna resumo."""
        stats = {"inseridos": 0, "atualizados": 0, "duplicados": 0, "erros": 0}

        # Agrupa por matriz
        for (nome_matriz, tipo_quadro, data_ref), grupo in df.groupby(
            ["nome_matriz", "tipo_quadro", "data_referencia"]
        ):
            try:
                matriz_id = self.get_or_create_matriz(
                    nome_matriz, tipo_quadro, data_ref, arquivo_origem
                )
                for _, row in grupo.iterrows():
                    try:
                        r = self.upsert_indicador(matriz_id, row.to_dict())
                        stats[{"inserido": "inseridos", "atualizado": "atualizados",
                               "duplicado": "duplicados"}[r["acao"]]] += 1
                    except Exception as exc:
                        logger.error(f"Erro indicador '{row.get('indicador')}': {exc}")
                        stats["erros"] += 1
            except Exception as exc:
                logger.error(f"Erro matriz '{nome_matriz}': {exc}")
                stats["erros"] += len(grupo)

        logger.info(f"bulk_upsert → {stats}")
        return stats

    def registrar_arquivo(self, nome: str, status: str, **kwargs) -> None:
        try:
            with self.session() as s:
                s.execute(
                    text("""
                        INSERT INTO arquivos_processados
                            (nome_arquivo, status, total_abas, total_matrizes, total_indicadores, detalhes)
                        VALUES (:n, :s, :ta, :tm, :ti, :d)
                    """),
                    {
                        "n":  nome,
                        "s":  status,
                        "ta": kwargs.get("total_abas", 0),
                        "tm": kwargs.get("total_matrizes", 0),
                        "ti": kwargs.get("total_indicadores", 0),
                        "d":  kwargs.get("detalhes", ""),
                    },
                )
        except Exception as exc:
            logger.error(f"Erro ao registrar arquivo: {exc}")

    def log_sistema(self, nivel: str, mensagem: str, modulo: str = "sistema") -> None:
        try:
            with self.session() as s:
                s.execute(
                    text("INSERT INTO logs_sistema (nivel, mensagem, modulo) VALUES (:n,:m,:mod)"),
                    {"n": nivel, "m": mensagem, "mod": modulo},
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # QUERIES ANALÍTICAS
    # ------------------------------------------------------------------

    def query(self, sql: str, params: dict = None) -> pd.DataFrame:
        with self.session() as s:
            result = s.execute(text(sql), params or {})
            return pd.DataFrame(result.fetchall(), columns=result.keys())

    def get_matrizes(self) -> pd.DataFrame:
        return self.query("SELECT * FROM matrizes ORDER BY data_referencia DESC")

    def get_indicadores(
        self,
        nome_matriz: str = None,
        tipo_quadro: str = None,
        data_de: str = None,
        data_ate: str = None,
        status: str = None,
        area: str = None,
    ) -> pd.DataFrame:
        wheres, params = ["1=1"], {}
        if nome_matriz:
            wheres.append("m.nome_matriz = :nm"); params["nm"] = nome_matriz
        if tipo_quadro:
            wheres.append("m.tipo_quadro = :tq"); params["tq"] = tipo_quadro
        if data_de:
            wheres.append("i.data_referencia >= :dd"); params["dd"] = data_de
        if data_ate:
            wheres.append("i.data_referencia <= :da"); params["da"] = data_ate
        if status:
            wheres.append("i.status = :st"); params["st"] = status
        if area:
            wheres.append("i.area = :ar"); params["ar"] = area
        return self.query(
            f"""
            SELECT m.nome_matriz, m.tipo_quadro, i.*
            FROM indicadores i
            JOIN matrizes m ON m.id = i.matriz_id
            WHERE {' AND '.join(wheres)}
            ORDER BY i.data_referencia, i.categoria, i.indicador
            """,
            params,
        )

    def get_evolucao(self) -> pd.DataFrame:
        return self.query("SELECT * FROM vw_evolucao_temporal")

    def get_ranking(self) -> pd.DataFrame:
        return self.query("SELECT * FROM vw_ranking_performance ORDER BY pct_atingidos DESC")
