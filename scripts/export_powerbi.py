"""
Gera um arquivo Excel estruturado e otimizado para Power BI.

Contém 4 abas:
  - fRegistros       → tabela fato principal (dados atuais)
  - fHistorico       → tabela fato histórica
  - dMatriz          → dimensão de matrizes
  - dCalendario      → dimensão de calendário (para eixo de tempo)

Execute:
  python scripts/export_powerbi.py

O arquivo gerado em data/powerbi_<data>.xlsx pode ser importado
diretamente no Power BI Desktop via "Obter Dados → Excel".
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ---------------------------------------------------------------------------
# Dados de amostra (substitua por leitura do Supabase se disponível)
# ---------------------------------------------------------------------------

REGISTROS_ATUAIS = [
    # nome, matriz, data_referencia, cargo, status, pontuacao
    ("Ana Silva",       "Matriz Norte", date(2025, 5, 27), "Gerente Sênior",  "Ativo",      98),
    ("Carlos Souza",    "Matriz Norte", date(2025, 5, 27), "Analista",        "Desligado",  None),
    ("Pedro Melo",      "Matriz Norte", date(2025, 5, 27), "Estagiário",      "Ativo",      60),
    ("João Costa",      "Matriz Sul",   date(2025, 5, 27), "Diretor",         "Ativo",      90),
    ("Paula Ramos",     "Matriz Sul",   date(2025, 5, 27), "Analista",        "Ativo",      85),
    ("Fernanda Lima",   "Matriz Leste", date(2025, 5, 27), "Coordenadora",    "Ativo",      92),
    ("Ricardo Alves",   "Matriz Leste", date(2025, 5, 27), "Analista",        "Licença",    70),
]

REGISTROS_HISTORICO = [
    # nome, matriz, data_referencia, cargo, status, pontuacao, arquivado_em
    ("Ana Silva",    "Matriz Norte", date(2024, 1, 1),  "Gerente",      "Ativo",  95, date(2025, 5, 27)),
    ("Ana Silva",    "Matriz Norte", date(2024, 2, 1),  "Gerente",      "Ativo",  96, date(2025, 5, 27)),
    ("Carlos Souza", "Matriz Norte", date(2024, 1, 1),  "Analista",     "Ativo",  88, date(2025, 5, 27)),
    ("Carlos Souza", "Matriz Norte", date(2024, 2, 1),  "Analista",     "Ativo",  84, date(2025, 5, 27)),
    ("João Costa",   "Matriz Sul",   date(2024, 1, 1),  "Diretor",      "Ativo",  88, date(2025, 5, 27)),
]


# ---------------------------------------------------------------------------
# Builders de DataFrame
# ---------------------------------------------------------------------------

def build_fRegistros() -> pd.DataFrame:
    rows = []
    for nome, matriz, data, cargo, status, pont in REGISTROS_ATUAIS:
        rows.append({
            "ID":              f"{nome[:3].upper()}{matriz[:3].upper()}{data.strftime('%Y%m%d')}",
            "Nome":            nome,
            "Matriz":          matriz,
            "Data_Referencia": data,
            "Cargo":           cargo,
            "Status":          status,
            "Pontuacao":       pont,
            "Ano":             data.year,
            "Mes":             data.month,
            "Mes_Ano":         data.strftime("%b/%Y"),
        })
    return pd.DataFrame(rows)


def build_fHistorico() -> pd.DataFrame:
    rows = []
    for nome, matriz, data, cargo, status, pont, arquivado in REGISTROS_HISTORICO:
        rows.append({
            "ID":              f"H{nome[:3].upper()}{matriz[:3].upper()}{data.strftime('%Y%m%d')}",
            "Nome":            nome,
            "Matriz":          matriz,
            "Data_Referencia": data,
            "Cargo":           cargo,
            "Status":          status,
            "Pontuacao":       pont,
            "Arquivado_Em":    arquivado,
            "Ano":             data.year,
            "Mes":             data.month,
            "Mes_Ano":         data.strftime("%b/%Y"),
        })
    return pd.DataFrame(rows)


def build_dMatriz() -> pd.DataFrame:
    matrizes = list({r[1] for r in REGISTROS_ATUAIS})
    rows = []
    for i, m in enumerate(sorted(matrizes), start=1):
        regiao = m.replace("Matriz ", "")
        rows.append({
            "MatrizID":    i,
            "Matriz":      m,
            "Regiao":      regiao,
            "Ativa":       "Sim",
        })
    return pd.DataFrame(rows)


def build_dCalendario(start: date, end: date) -> pd.DataFrame:
    rows = []
    current = start
    while current <= end:
        rows.append({
            "Data":        current,
            "Ano":         current.year,
            "Mes":         current.month,
            "Dia":         current.day,
            "Trimestre":   f"T{((current.month - 1) // 3) + 1}/{current.year}",
            "Mes_Ano":     current.strftime("%b/%Y"),
            "Semana":      current.isocalendar()[1],
            "Dia_Semana":  current.strftime("%A"),
        })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Estilização
# ---------------------------------------------------------------------------

HEADER_FILL   = PatternFill("solid", fgColor="1F3864")  # azul escuro
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
ALT_FILL      = PatternFill("solid", fgColor="DCE6F1")  # azul claro alternado
THIN_BORDER   = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)


def style_sheet(ws, df: pd.DataFrame):
    # Cabeçalho
    for col_idx, col_name in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.value = col_name
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER

    # Dados com linha alternada
    for row_idx in range(2, len(df) + 2):
        fill = ALT_FILL if row_idx % 2 == 0 else PatternFill()
        for col_idx in range(1, len(df.columns) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = fill
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center")

    # Auto-ajuste de largura
    for col_idx, col_name in enumerate(df.columns, start=1):
        max_len = max(len(str(col_name)), df.iloc[:, col_idx - 1].astype(str).str.len().max())
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 40)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    output = Path("data") / f"powerbi_matriz_comite.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)

    df_reg  = build_fRegistros()
    df_hist = build_fHistorico()
    df_mat  = build_dMatriz()
    df_cal  = build_dCalendario(date(2024, 1, 1), date(2025, 12, 31))

    with pd.ExcelWriter(output, engine="openpyxl", datetime_format="YYYY-MM-DD") as writer:
        df_reg.to_excel(writer,  sheet_name="fRegistros",  index=False)
        df_hist.to_excel(writer, sheet_name="fHistorico",  index=False)
        df_mat.to_excel(writer,  sheet_name="dMatriz",     index=False)
        df_cal.to_excel(writer,  sheet_name="dCalendario", index=False)

    # Aplica estilos
    wb = load_workbook(output)
    style_sheet(wb["fRegistros"],  df_reg)
    style_sheet(wb["fHistorico"],  df_hist)
    style_sheet(wb["dMatriz"],     df_mat)
    style_sheet(wb["dCalendario"], df_cal)

    # Aba de instruções
    ws_info = wb.create_sheet("⚙ Instruções Power BI", 0)
    instrucoes = [
        ["MODELO DE DADOS — Power BI", ""],
        ["", ""],
        ["PASSO 1 — Importar este arquivo", ""],
        ["", "Power BI Desktop → Página Inicial → Obter Dados → Excel → selecione este arquivo"],
        ["", "Marque as 4 tabelas: fRegistros, fHistorico, dMatriz, dCalendario"],
        ["", ""],
        ["PASSO 2 — Relacionamentos (Exibição de Modelo)", ""],
        ["", "fRegistros[Matriz]      → dMatriz[Matriz]      (Muitos:1)"],
        ["", "fRegistros[Data_Referencia] → dCalendario[Data]  (Muitos:1)"],
        ["", "fHistorico[Matriz]      → dMatriz[Matriz]      (Muitos:1)"],
        ["", "fHistorico[Data_Referencia] → dCalendario[Data]  (Muitos:1)"],
        ["", ""],
        ["PASSO 3 — Medidas DAX sugeridas", ""],
        ["", "Total Ativos = COUNTROWS(FILTER(fRegistros, fRegistros[Status] = \"Ativo\"))"],
        ["", "Media Pontuacao = AVERAGE(fRegistros[Pontuacao])"],
        ["", "Total Historico = COUNTROWS(fHistorico)"],
        ["", "Variacao Pontuacao = [Media Pontuacao] - CALCULATE([Media Pontuacao], PREVIOUSMONTH(dCalendario[Data]))"],
        ["", ""],
        ["PASSO 4 — Páginas do Relatório", ""],
        ["", "Pág 1 - Visão Geral:   Cartões (Total, Média, Ativos) + Tabela por Matriz"],
        ["", "Pág 2 - Evolução:      Gráfico de Linha (Pontuacao por Mes_Ano, linha por Nome)"],
        ["", "Pág 3 - Comparativo:   Gráfico de Barras Agrupadas (Matriz x Pontuacao)"],
        ["", ""],
        ["CONEXÃO DIRETA AO SUPABASE (opcional)", ""],
        ["", "Power BI → Obter Dados → PostgreSQL"],
        ["", "Servidor: db.<seu-projeto>.supabase.co"],
        ["", "Banco:    postgres  |  Porta: 5432"],
        ["", "Use as views: vw_comparativo_geral e vw_evolucao_temporal"],
    ]
    for row_idx, (col_a, col_b) in enumerate(instrucoes, start=1):
        ws_info.cell(row=row_idx, column=1).value = col_a
        ws_info.cell(row=row_idx, column=2).value = col_b
        if col_a and col_a != "":
            ws_info.cell(row=row_idx, column=1).font = Font(bold=True, color="1F3864")

    ws_info.column_dimensions["A"].width = 42
    ws_info.column_dimensions["B"].width = 80

    wb.save(output)
    print(f"\n✔ Arquivo gerado: {output}")
    print("  Abas: ⚙ Instruções | fRegistros | fHistorico | dMatriz | dCalendario")
    print("\nImporte no Power BI Desktop via:")
    print("  Página Inicial → Obter Dados → Excel → selecione o arquivo acima\n")


if __name__ == "__main__":
    main()
