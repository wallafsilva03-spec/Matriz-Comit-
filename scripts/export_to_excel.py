"""
Exporta os dados do Supabase de volta para Excel (para integração com Power BI).
Execute: python scripts/export_to_excel.py
"""
from dotenv import load_dotenv
load_dotenv()

from config import settings
from database.connection import DatabaseConnection
from database.operations import DatabaseOperations
import pandas as pd
from pathlib import Path
from datetime import datetime

conn = DatabaseConnection(
    database_url=settings.database_url,
    supabase_url=settings.supabase_url,
    supabase_key=settings.supabase_key,
)
db_ops = DatabaseOperations(conn)

output = Path("data") / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

with pd.ExcelWriter(output, engine="openpyxl") as writer:
    db_ops.get_comparativo().to_excel(writer, sheet_name="Comparativo_Geral", index=False)
    db_ops.get_evolucao_temporal().to_excel(writer, sheet_name="Evolucao_Temporal", index=False)

print(f"Exportado: {output}")
