"""
KPIs, comparações, rankings e análise de tendências.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from loguru import logger


class Comparativo:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # KPIs gerais
    # ------------------------------------------------------------------

    def kpis_gerais(self) -> dict:
        df = self.db.get_indicadores()
        if df.empty:
            return {}

        total = len(df)
        verdes    = (df["status"] == "verde").sum()
        amarelos  = (df["status"] == "amarelo").sum()
        vermelhos = (df["status"] == "vermelho").sum()
        sem_status = df["status"].isna().sum()

        return {
            "total_indicadores": int(total),
            "total_matrizes":    df["nome_matriz"].nunique(),
            "atingidos":         int(verdes),
            "alerta":            int(amarelos),
            "criticos":          int(vermelhos),
            "sem_status":        int(sem_status),
            "pct_atingidos":     round(verdes / total * 100, 1) if total else 0,
            "ultima_atualizacao": str(df["data_referencia"].max()) if "data_referencia" in df.columns else "-",
        }

    # ------------------------------------------------------------------
    # Comparação entre duas datas
    # ------------------------------------------------------------------

    def comparar_datas(
        self,
        data_base: str,
        data_comp: str,
        nome_matriz: Optional[str] = None,
    ) -> pd.DataFrame:
        df_base = self.db.get_indicadores(nome_matriz=nome_matriz, data_de=data_base, data_ate=data_base)
        df_comp = self.db.get_indicadores(nome_matriz=nome_matriz, data_de=data_comp, data_ate=data_comp)

        if df_base.empty or df_comp.empty:
            return pd.DataFrame()

        merged = df_base[["nome_matriz", "indicador", "realizado", "status"]].merge(
            df_comp[["nome_matriz", "indicador", "realizado", "status"]],
            on=["nome_matriz", "indicador"],
            suffixes=("_base", "_comp"),
        )
        merged["variacao"] = pd.to_numeric(merged["realizado_comp"], errors="coerce") - \
                              pd.to_numeric(merged["realizado_base"], errors="coerce")
        merged["tendencia"] = merged["variacao"].apply(
            lambda v: "↑ Crescimento" if v and v > 0 else ("↓ Queda" if v and v < 0 else "→ Estável")
        )
        return merged

    # ------------------------------------------------------------------
    # Comparação entre matrizes (mesma data)
    # ------------------------------------------------------------------

    def comparar_matrizes(self, data_referencia: str, indicador: Optional[str] = None) -> pd.DataFrame:
        df = self.db.get_indicadores(data_de=data_referencia, data_ate=data_referencia)
        if df.empty:
            return pd.DataFrame()
        if indicador:
            df = df[df["indicador"].str.contains(indicador, case=False, na=False)]

        pivot = df.pivot_table(
            index="indicador",
            columns="nome_matriz",
            values="realizado",
            aggfunc="first",
        ).reset_index()
        return pivot

    # ------------------------------------------------------------------
    # Evolução histórica por indicador
    # ------------------------------------------------------------------

    def evolucao_indicador(self, indicador: str, nome_matriz: Optional[str] = None) -> pd.DataFrame:
        df = self.db.get_indicadores(nome_matriz=nome_matriz)
        if df.empty:
            return pd.DataFrame()
        mask = df["indicador"].str.contains(indicador, case=False, na=False)
        result = df[mask].sort_values("data_referencia")
        return result[["nome_matriz", "indicador", "data_referencia", "meta", "realizado", "status"]]

    # ------------------------------------------------------------------
    # Ranking de matrizes
    # ------------------------------------------------------------------

    def ranking_matrizes(self) -> pd.DataFrame:
        return self.db.get_ranking()

    # ------------------------------------------------------------------
    # Indicadores críticos
    # ------------------------------------------------------------------

    def indicadores_criticos(self, nome_matriz: Optional[str] = None) -> pd.DataFrame:
        df = self.db.get_indicadores(nome_matriz=nome_matriz, status="vermelho")
        if df.empty:
            return pd.DataFrame()
        return df[["nome_matriz", "data_referencia", "categoria", "indicador",
                   "meta", "realizado", "responsavel", "observacao"]].sort_values(
            ["nome_matriz", "indicador"]
        )

    # ------------------------------------------------------------------
    # Heatmap de status por área x setor
    # ------------------------------------------------------------------

    def heatmap_area_setor(self, nome_matriz: Optional[str] = None) -> pd.DataFrame:
        df = self.db.get_indicadores(nome_matriz=nome_matriz)
        if df.empty or "area" not in df.columns:
            return pd.DataFrame()

        status_num = {"verde": 1, "amarelo": 0.5, "vermelho": 0}
        df["status_num"] = df["status"].map(status_num)

        pivot = df.pivot_table(
            index="area",
            columns="setor",
            values="status_num",
            aggfunc="mean",
        ).round(2)
        return pivot

    # ------------------------------------------------------------------
    # Tendência geral por período
    # ------------------------------------------------------------------

    def tendencia_periodo(self, nome_matriz: Optional[str] = None) -> pd.DataFrame:
        df = self.db.get_indicadores(nome_matriz=nome_matriz)
        if df.empty:
            return pd.DataFrame()

        df["data_referencia"] = pd.to_datetime(df["data_referencia"])
        df["realizado"] = pd.to_numeric(df["realizado"], errors="coerce")

        agg = (
            df.groupby(["nome_matriz", "data_referencia"])
            .agg(
                media_realizado=("realizado", "mean"),
                total_indicadores=("indicador", "count"),
                atingidos=("status", lambda x: (x == "verde").sum()),
            )
            .reset_index()
        )
        agg["pct_atingidos"] = (agg["atingidos"] / agg["total_indicadores"] * 100).round(1)
        return agg.sort_values(["nome_matriz", "data_referencia"])
