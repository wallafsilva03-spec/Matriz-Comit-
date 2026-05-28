# Sistema Matriz Indicadores Comitê

ETL profissional + Dashboard para consolidar, historiar e comparar indicadores de matrizes XLSX no Supabase.

---

## Arquitetura

```
uploads/*.xlsx
      │
      ▼
excel_reader   ← abre XLSX, expande células mescladas, detecta cabeçalho
      │
parser         ← limpa, normaliza status (semáforo), calcula % resultado
      │
database       ← insere/atualiza matrizes e indicadores, registra histórico
      │
PostgreSQL (Supabase)
  ├── matrizes
  ├── indicadores
  ├── historico_indicadores
  ├── arquivos_processados
  └── logs_sistema
      │
      ├── comparativo    → KPIs, rankings, tendências, heatmaps
      └── exportador     → gera XLSX preservando layout do template
            │
            ▼
      dashboard.py (Streamlit + Plotly)
```

---

## Estrutura do Projeto

```
/
├── app/
│   ├── main.py          CLI — processa arquivos, watch, export, status
│   ├── dashboard.py     Streamlit — dashboard visual completo
│   ├── excel_reader.py  Lê XLSX, expande mesclados, detecta header
│   ├── parser.py        Limpa, normaliza, calcula resultado %
│   ├── database.py      Conexão Supabase, upsert, histórico, queries
│   ├── comparativo.py   KPIs, comparações, rankings, tendências
│   ├── exportador.py    Gera XLSX mantendo layout do template
│   ├── monitor.py       Watchdog — processa uploads automáticos
│   └── utils.py         Logger, hash, parse de data/aba
├── templates/
│   └── modelo.xlsx      ← coloque aqui o modelo original da planilha
├── uploads/             ← coloque novos XLSX aqui para processamento automático
├── outputs/             ← planilhas exportadas pelo sistema
├── logs/
├── scripts/sql/
│   └── schema.sql       DDL completo do banco
├── requirements.txt
└── .env
```

---

## Convenção de Nome de Aba

| Nome da aba | tipo_quadro | matriz | data |
|---|---|---|---|
| `Quadro Geral - COP 27.05` | Quadro Geral | COP | 2025-05-27 |
| `Quadro Detalhado - CEMMA 13.05` | Quadro Detalhado | CEMMA | 2025-05-13 |
| `Quadro Geral Op.` | Quadro Geral Op. | — | — |

---

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env
# Edite o .env com suas credenciais do Supabase
```

---

## Configuração do Supabase

1. Acesse seu projeto em https://supabase.com
2. Copie a **Connection String (URI)** em Settings → Database
3. Copie a **URL** e **anon key** em Settings → API
4. Cole no `.env`

---

## Inicializar o Banco

```bash
python app/main.py --init
```

---

## Uso CLI

```bash
# Processar um arquivo específico
python app/main.py --file uploads/minha_planilha.xlsx

# Monitorar pasta automaticamente (detecta novos XLSX)
python app/main.py --watch

# Exportar todas as matrizes do banco para Excel
python app/main.py --export

# Ver KPIs e ranking no terminal
python app/main.py --status
```

---

## Dashboard

```bash
streamlit run app/dashboard.py
```

Acesse: http://localhost:8501

### Páginas disponíveis

| Página | Conteúdo |
|---|---|
| Visão Geral | KPIs, gauge de performance, ranking, críticos |
| Evolução | Linha temporal por matriz e por indicador |
| Comparativo | Heatmap de status, comparação entre datas e matrizes |
| Indicadores | Tabela filtrada completa + download CSV |
| Exportar | Gera XLSX preservando layout do template |

---

## Banco de Dados

### Tabelas

| Tabela | Descrição |
|---|---|
| `matrizes` | Uma linha por aba (matriz + tipo + data) |
| `indicadores` | Um indicador por linha, com chave única |
| `historico_indicadores` | Toda alteração de valor é registrada aqui |
| `arquivos_processados` | Log de cada arquivo processado |
| `logs_sistema` | Log geral de operações |

### Views

| View | Descrição |
|---|---|
| `vw_comparativo_geral` | Join completo indicadores × matrizes |
| `vw_evolucao_temporal` | Com variação e LAG por período |
| `vw_ranking_performance` | % atingido por matriz/data |

---

## Histórico Inteligente

- Chave única: **SHA-256(nome_matriz + tipo_quadro + indicador + data)**
- Se o indicador já existe com **mesmos valores** → ignorado (sem duplicata)
- Se os **valores mudaram** → atualiza o registro e grava em `historico_indicadores`
- Se é **nova data** → novo registro (histórico completo preservado)

---

## Template de Exportação

Coloque o arquivo `Cópia de Modelo Matriz Indicadores Comitê.xlsx` em `templates/modelo.xlsx`.

O sistema usará ele como base visual para todas as exportações, preservando:
- Células mescladas
- Cores e fontes
- Bordas
- Largura de colunas
- Alinhamentos

---

## Integração Power BI

Conecte diretamente ao PostgreSQL do Supabase:

```
Servidor: db.<project-id>.supabase.co
Porta:    5432
Banco:    postgres
Usuário:  postgres
```

Use as views `vw_comparativo_geral` e `vw_evolucao_temporal` como fonte.
