# Sistema ETL — Matriz Comitê → Supabase

## Arquitetura

```
data/input/*.xlsx
      │
      ▼
 XLSXReader          ← lê todas as abas, extrai matriz e data do nome
      │
 DataTransformer     ← normaliza colunas, serializa extras em dados_json
      │
 DataValidator       ← remove linhas inválidas, valida campos obrigatórios
      │
 DataLoader          ← orquestra, move arquivos, registra logs
      │
      ▼
PostgreSQL (Supabase)
  ├── registros            ← tabela principal (dado mais recente)
  ├── registros_historico  ← versões anteriores (histórico temporal)
  ├── arquivos_processados ← log de cada arquivo processado
  └── logs_etl             ← log geral de execução
      │
      ▼
Excel / Power BI  (via vw_comparativo_geral / vw_evolucao_temporal)
```

## Estrutura de Pastas

```
/
├── config/          configurações centralizadas (pydantic-settings)
├── database/        conexão e operações no banco
├── etl/             reader → transformer → validator → loader
├── utils/           logger centralizado (loguru)
├── scripts/
│   ├── sql/         schema.sql (DDL completo)
│   ├── generate_sample.py
│   └── export_to_excel.py
├── data/
│   ├── input/       ← coloque os XLSX aqui
│   ├── processed/   ← arquivos processados com sucesso
│   └── error/       ← arquivos com falha
├── logs/            arquivos de log diários
├── main.py
├── requirements.txt
└── .env
```

## Convenção de Nome de Aba

O nome de cada aba deve conter a **matriz** e a **data**:

| Exemplo de nome | Matriz extraída | Data extraída |
|---|---|---|
| `Matriz_Norte_2024-01` | Matriz Norte | 2024-01-01 |
| `Sul 2024-02-15` | Sul | 2024-02-15 |
| `Leste_03/2024` | Leste | 2024-03-01 |

Caso a data não seja encontrada no nome, usa a data de modificação do arquivo.

## Estratégia Anti-Duplicidade

- Chave única: **SHA-256(nome + matriz + data_referencia)**
- Se a chave já existe → registro ignorado (duplicado)
- Se `nome + matriz` existe com data diferente → versão anterior vai para `registros_historico`

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env
# Edite o .env com suas credenciais do Supabase
```

## Configuração do Supabase

1. Crie um projeto em https://supabase.com
2. Vá em **Settings → Database** e copie a **Connection String** (URI)
3. Vá em **Settings → API** e copie a **URL** e a **anon/service_role key**
4. Cole no `.env`

## Uso

```bash
# Processar arquivos existentes + monitorar continuamente
python main.py

# Processar e sair
python main.py --once

# Processar um arquivo específico
python main.py --file caminho/para/arquivo.xlsx

# Ver comparativo no terminal
python main.py --query

# Gerar XLSX de exemplo
python scripts/generate_sample.py

# Exportar dados para Excel
python scripts/export_to_excel.py
```

## Integração Power BI

Conecte diretamente ao PostgreSQL do Supabase:

- **Servidor:** `db.<project-id>.supabase.co`
- **Porta:** `5432`
- **Banco:** `postgres`
- **Usuário:** `postgres`
- Use as views `vw_comparativo_geral` e `vw_evolucao_temporal`

## Integração Excel

Use **Dados → Obter Dados → De Banco de Dados → Do PostgreSQL** com as mesmas credenciais acima, ou execute `scripts/export_to_excel.py` para gerar um `.xlsx` local.
