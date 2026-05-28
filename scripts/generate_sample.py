"""
Gera um arquivo XLSX de exemplo para testar o sistema.
Execute: python scripts/generate_sample.py
"""
import pandas as pd
from pathlib import Path

OUTPUT = Path("data/input/exemplo_comite_2024-01.xlsx")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

abas = {
    "Matriz_Norte_2024-01": {
        "Nome": ["Ana Silva", "Carlos Souza", "Maria Lima"],
        "Cargo": ["Gerente", "Analista", "Coordenadora"],
        "Status": ["Ativo", "Ativo", "Licença"],
        "Pontuacao": [95, 88, 72],
    },
    "Matriz_Sul_2024-01": {
        "Nome": ["João Costa", "Paula Ramos"],
        "Cargo": ["Diretor", "Analista"],
        "Status": ["Ativo", "Ativo"],
        "Pontuacao": [90, 85],
    },
    "Matriz_Norte_2024-02": {
        # Ana Silva reaparece em fevereiro → deve gerar histórico
        "Nome": ["Ana Silva", "Carlos Souza", "Pedro Melo"],
        "Cargo": ["Gerente Sênior", "Analista", "Estagiário"],
        "Status": ["Ativo", "Desligado", "Ativo"],
        "Pontuacao": [98, None, 60],
    },
}

with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
    for sheet, data in abas.items():
        pd.DataFrame(data).to_excel(writer, sheet_name=sheet, index=False)

print(f"Arquivo gerado: {OUTPUT}")
