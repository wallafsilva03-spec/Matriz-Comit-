"""
Dashboard Streamlit — Sistema Matriz Indicadores Comitê

Execute:
    streamlit run app/dashboard.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from app.database import Database
from app.comparativo import Comparativo
from app.exportador import Exportador
from app.excel_reader import XLSXReader
from app.parser import DataParser
from app.utils import setup_logger

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Matriz Indicadores Comitê",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS = """
<style>
    .metric-card {
        background: #1F3864; color: white;
        border-radius: 10px; padding: 20px;
        text-align: center; margin: 5px;
    }
    .metric-card h2 { font-size: 2.2rem; margin: 0; }
    .metric-card p  { margin: 0; font-size: 0.9rem; opacity: 0.85; }
    .verde    { background: #28a745; }
    .amarelo  { background: #ffc107; color: #333; }
    .vermelho { background: #dc3545; }
    [data-testid="stSidebar"] { background: #0d2137; color: white; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Conexão com banco (cache)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db() -> Database:
    url = os.getenv("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL não configurado no .env")
        st.stop()
    db = Database(url)
    if not db.test():
        st.error("Não foi possível conectar ao banco de dados.")
        st.stop()
    return db


@st.cache_resource
def get_comparativo() -> Comparativo:
    return Comparativo(get_db())


# ---------------------------------------------------------------------------
# Sidebar — filtros e upload
# ---------------------------------------------------------------------------
def sidebar(db: Database) -> dict:
    st.sidebar.image("https://img.icons8.com/color/96/combo-chart.png", width=60)
    st.sidebar.title("Matriz Comitê")
    st.sidebar.markdown("---")

    df_matrizes = db.get_matrizes()

    matrizes_disp = ["Todas"] + sorted(df_matrizes["nome_matriz"].dropna().unique().tolist()) \
        if not df_matrizes.empty else ["Todas"]
    tipos_disp = ["Todos"] + sorted(df_matrizes["tipo_quadro"].dropna().unique().tolist()) \
        if not df_matrizes.empty else ["Todos"]

    filtros = {
        "matriz":     st.sidebar.selectbox("Matriz", matrizes_disp),
        "tipo":       st.sidebar.selectbox("Tipo de Quadro", tipos_disp),
        "status":     st.sidebar.selectbox("Status", ["Todos", "verde", "amarelo", "vermelho"]),
        "data_de":    str(st.sidebar.date_input("Data início", value=None) or ""),
        "data_ate":   str(st.sidebar.date_input("Data fim",   value=None) or ""),
    }

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Upload de Planilha")
    uploaded = st.sidebar.file_uploader("Enviar XLSX", type=["xlsx"])
    if uploaded:
        _process_upload(uploaded, db)

    return filtros


def _process_upload(uploaded_file, db: Database):
    with st.spinner(f"Processando {uploaded_file.name}..."):
        Path("uploads").mkdir(exist_ok=True)
        dest = Path("uploads") / uploaded_file.name
        dest.write_bytes(uploaded_file.getvalue())

        reader = XLSXReader(template_path="templates/modelo.xlsx")
        parser = DataParser()
        sheets = reader.read_file(dest)
        df = parser.parse_all(sheets)

        if df.empty:
            st.sidebar.error("Nenhum dado extraído.")
            return

        stats = db.bulk_upsert(df, arquivo_origem=uploaded_file.name)
        db.registrar_arquivo(
            uploaded_file.name, "sucesso",
            total_abas=len(sheets),
            total_matrizes=df["nome_matriz"].nunique(),
            total_indicadores=stats["inseridos"],
            detalhes=str(stats),
        )
        st.sidebar.success(f"✔ {stats['inseridos']} indicadores inseridos!")
        st.cache_data.clear()


# ---------------------------------------------------------------------------
# Helpers de gráficos
# ---------------------------------------------------------------------------

def _gauge(valor: float, title: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=valor,
        title={"text": title, "font": {"size": 14}},
        number={"suffix": "%"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar":  {"color": "#1F3864"},
            "steps": [
                {"range": [0, 60],  "color": "#FF4B4B"},
                {"range": [60, 80], "color": "#FFC300"},
                {"range": [80, 100],"color": "#28a745"},
            ],
            "threshold": {"line": {"color": "white", "width": 4}, "value": 80},
        },
    ))
    fig.update_layout(height=220, margin=dict(t=30, b=0, l=20, r=20))
    return fig


def _metric_card(label: str, value, css_class: str = "") -> str:
    return f"""
    <div class="metric-card {css_class}">
        <h2>{value}</h2>
        <p>{label}</p>
    </div>"""


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

def pagina_visao_geral(db: Database, comp: Comparativo, filtros: dict):
    st.title("📊 Visão Geral — Indicadores Comitê")

    kpis = comp.kpis_gerais()
    if not kpis:
        st.info("Nenhum dado disponível. Faça upload de uma planilha.")
        return

    # Cards KPI
    cols = st.columns(6)
    cards = [
        ("Total Indicadores", kpis["total_indicadores"],  ""),
        ("Matrizes",          kpis["total_matrizes"],     ""),
        ("Atingidos",         kpis["atingidos"],          "verde"),
        ("Alerta",            kpis["alerta"],             "amarelo"),
        ("Críticos",          kpis["criticos"],           "vermelho"),
        ("% Atingido",        f"{kpis['pct_atingidos']}%",""),
    ]
    for col, (label, val, css) in zip(cols, cards):
        col.markdown(_metric_card(label, val, css), unsafe_allow_html=True)

    st.markdown("---")
    col1, col2 = st.columns([1, 2])

    with col1:
        st.plotly_chart(_gauge(kpis["pct_atingidos"], "Performance Geral"), use_container_width=True)

    with col2:
        # Distribuição de status
        status_data = pd.DataFrame({
            "Status":       ["Atingidos", "Alerta", "Críticos"],
            "Quantidade":   [kpis["atingidos"], kpis["alerta"], kpis["criticos"]],
        })
        fig = px.pie(
            status_data, names="Status", values="Quantidade",
            color="Status",
            color_discrete_map={"Atingidos": "#28a745", "Alerta": "#FFC300", "Críticos": "#dc3545"},
            title="Distribuição de Status",
        )
        fig.update_layout(height=220, margin=dict(t=40, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Ranking
    st.subheader("🏆 Ranking de Matrizes")
    df_rank = comp.ranking_matrizes()
    if not df_rank.empty:
        fig = px.bar(
            df_rank,
            x="nome_matriz", y="pct_atingidos",
            color="pct_atingidos",
            color_continuous_scale=["#dc3545", "#FFC300", "#28a745"],
            range_color=[0, 100],
            labels={"nome_matriz": "Matriz", "pct_atingidos": "% Atingido"},
            title="Performance por Matriz",
            text="pct_atingidos",
        )
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        fig.update_layout(height=350, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    # Indicadores críticos
    st.subheader("🚨 Indicadores Críticos")
    nm = None if filtros["matriz"] == "Todas" else filtros["matriz"]
    df_crit = comp.indicadores_criticos(nome_matriz=nm)
    if not df_crit.empty:
        st.dataframe(df_crit, use_container_width=True, height=300)
    else:
        st.success("Nenhum indicador crítico encontrado.")


def pagina_evolucao(db: Database, comp: Comparativo, filtros: dict):
    st.title("📈 Evolução Temporal")

    nm = None if filtros["matriz"] == "Todas" else filtros["matriz"]
    df = comp.tendencia_periodo(nome_matriz=nm)

    if df.empty:
        st.info("Sem dados para exibir.")
        return

    fig = px.line(
        df,
        x="data_referencia", y="pct_atingidos",
        color="nome_matriz",
        markers=True,
        labels={"data_referencia": "Data", "pct_atingidos": "% Atingido", "nome_matriz": "Matriz"},
        title="Evolução do % de Indicadores Atingidos por Matriz",
    )
    fig.add_hline(y=80, line_dash="dash", line_color="green",
                  annotation_text="Meta 80%", annotation_position="right")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Evolução por Indicador")

    col1, col2 = st.columns(2)
    with col1:
        indicador_busca = st.text_input("Buscar indicador", placeholder="Ex: Produção")
    with col2:
        matriz_sel = st.selectbox("Filtrar matriz", ["Todas"] + (
            sorted(df["nome_matriz"].unique().tolist()) if not df.empty else []))

    if indicador_busca:
        nm2 = None if matriz_sel == "Todas" else matriz_sel
        df_ev = comp.evolucao_indicador(indicador_busca, nome_matriz=nm2)
        if not df_ev.empty:
            fig2 = px.line(
                df_ev, x="data_referencia", y="realizado",
                color="nome_matriz", markers=True,
                title=f"Evolução: {indicador_busca}",
            )
            st.plotly_chart(fig2, use_container_width=True)
            st.dataframe(df_ev, use_container_width=True)
        else:
            st.info("Nenhum dado encontrado.")


def pagina_comparativo(db: Database, comp: Comparativo, filtros: dict):
    st.title("⚖️ Comparativo entre Matrizes")

    df_matrizes = db.get_matrizes()
    if df_matrizes.empty:
        st.info("Sem dados.")
        return

    datas_disp = sorted(df_matrizes["data_referencia"].astype(str).unique().tolist(), reverse=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        data_sel = st.selectbox("Data de referência", datas_disp)
    with col2:
        indicador_filtro = st.text_input("Filtrar indicador (opcional)")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        gerar = st.button("Gerar Comparativo")

    if gerar or data_sel:
        df_comp = comp.comparar_matrizes(data_sel, indicador=indicador_filtro or None)
        if not df_comp.empty:
            st.dataframe(df_comp, use_container_width=True, height=400)

            # Heatmap de performance
            df_ind = db.get_indicadores(data_de=data_sel, data_ate=data_sel)
            if not df_ind.empty:
                status_num = {"verde": 1, "amarelo": 0.5, "vermelho": 0}
                df_ind["status_num"] = df_ind["status"].map(status_num)
                pivot = df_ind.pivot_table(
                    index="indicador", columns="nome_matriz",
                    values="status_num", aggfunc="first"
                )
                if not pivot.empty and len(pivot) <= 50:
                    fig = px.imshow(
                        pivot,
                        color_continuous_scale=["#dc3545", "#FFC300", "#28a745"],
                        range_color=[0, 1],
                        title=f"Heatmap de Status — {data_sel}",
                        aspect="auto",
                    )
                    fig.update_layout(height=max(300, len(pivot) * 20))
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado para o período selecionado.")

    st.markdown("---")
    st.subheader("Comparar entre duas datas")
    col1, col2, col3 = st.columns(3)
    with col1:
        d_base = st.selectbox("Data base", datas_disp, key="dbase")
    with col2:
        d_comp = st.selectbox("Data comparação", datas_disp, key="dcomp")
    with col3:
        nm_comp = st.selectbox("Matriz", ["Todas"] + sorted(
            df_matrizes["nome_matriz"].dropna().unique().tolist()), key="nmcomp")

    if st.button("Comparar Datas"):
        nm_val = None if nm_comp == "Todas" else nm_comp
        df_delta = comp.comparar_datas(d_base, d_comp, nome_matriz=nm_val)
        if not df_delta.empty:
            st.dataframe(df_delta, use_container_width=True)
            fig = px.bar(
                df_delta.sort_values("variacao"),
                x="indicador", y="variacao",
                color="tendencia",
                color_discrete_map={
                    "↑ Crescimento": "#28a745",
                    "↓ Queda":       "#dc3545",
                    "→ Estável":     "#6c757d",
                },
                title=f"Variação: {d_base} → {d_comp}",
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para comparar.")


def pagina_indicadores(db: Database, filtros: dict):
    st.title("📋 Indicadores")

    nm = None if filtros["matriz"] == "Todas" else filtros["matriz"]
    tq = None if filtros["tipo"] == "Todos" else filtros["tipo"]
    st = None if filtros["status"] == "Todos" else filtros["status"]
    dd = filtros["data_de"] or None
    da = filtros["data_ate"] or None

    df = db.get_indicadores(
        nome_matriz=nm, tipo_quadro=tq, status=st, data_de=dd, data_ate=da
    )

    if df.empty:
        import streamlit as _st
        _st.info("Nenhum dado encontrado com os filtros aplicados.")
        return

    import streamlit as _st
    col1, col2, col3 = _st.columns(3)
    col1.metric("Total", len(df))
    col2.metric("Atingidos", (df["status"] == "verde").sum())
    col3.metric("Críticos", (df["status"] == "vermelho").sum())

    _st.markdown("---")
    _st.dataframe(
        df[["nome_matriz", "tipo_quadro", "data_referencia", "categoria",
            "indicador", "meta", "realizado", "resultado", "status",
            "area", "setor", "responsavel", "observacao"]],
        use_container_width=True,
        height=500,
    )

    # Download CSV
    csv = df.to_csv(index=False).encode("utf-8")
    _st.download_button("⬇ Baixar CSV", csv, "indicadores.csv", "text/csv")


def pagina_exportar(db: Database):
    st.title("📤 Exportar Matrizes")

    df_matrizes = db.get_matrizes()
    if df_matrizes.empty:
        st.info("Nenhuma matriz no banco.")
        return

    st.dataframe(df_matrizes, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        nm_exp = st.selectbox("Matriz", df_matrizes["nome_matriz"].unique())
    with col2:
        datas = df_matrizes[df_matrizes["nome_matriz"] == nm_exp]["data_referencia"].astype(str)
        data_exp = st.selectbox("Data", datas)

    if st.button("Exportar Excel"):
        exportador = Exportador(template_path="templates/modelo.xlsx")
        df = db.get_indicadores(nome_matriz=nm_exp, data_de=data_exp, data_ate=data_exp)
        m_row = df_matrizes[
            (df_matrizes["nome_matriz"] == nm_exp) &
            (df_matrizes["data_referencia"].astype(str) == data_exp)
        ].iloc[0]

        import tempfile, os
        from datetime import date as dt
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            path = exportador.gerar_matriz(
                df=df,
                nome_matriz=nm_exp,
                tipo_quadro=m_row["tipo_quadro"],
                data_referencia=m_row["data_referencia"],
                output_path=tmp.name,
            )
            with open(path, "rb") as f:
                st.download_button(
                    "⬇ Baixar XLSX",
                    f.read(),
                    file_name=f"matriz_{nm_exp}_{data_exp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------

def main():
    setup_logger()
    db   = get_db()
    comp = get_comparativo()
    filtros = sidebar(db)

    pages = {
        "Visão Geral":    lambda: pagina_visao_geral(db, comp, filtros),
        "Evolução":       lambda: pagina_evolucao(db, comp, filtros),
        "Comparativo":    lambda: pagina_comparativo(db, comp, filtros),
        "Indicadores":    lambda: pagina_indicadores(db, filtros),
        "Exportar":       lambda: pagina_exportar(db),
    }

    st.sidebar.markdown("---")
    page = st.sidebar.radio("Navegação", list(pages.keys()))
    pages[page]()


if __name__ == "__main__":
    main()
