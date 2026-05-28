-- ============================================================
-- SCHEMA ETL - Matriz Comitê
-- ============================================================

-- Extensão para UUID (já habilitada no Supabase por padrão)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- TABELA PRINCIPAL DE REGISTROS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registros (
    id                BIGSERIAL PRIMARY KEY,
    chave_hash        VARCHAR(64)  NOT NULL UNIQUE,    -- SHA-256(nome|matriz|data)
    nome              TEXT         NOT NULL,
    nome_normalizado  TEXT         NOT NULL,            -- lowercase para buscas
    matriz            TEXT         NOT NULL,
    data_referencia   DATE         NOT NULL,
    dados_json        JSONB        DEFAULT '{}'::jsonb, -- colunas extras da planilha
    arquivo_origem    TEXT,
    criado_em         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_registros_nome_normalizado ON registros(nome_normalizado);
CREATE INDEX IF NOT EXISTS idx_registros_matriz           ON registros(matriz);
CREATE INDEX IF NOT EXISTS idx_registros_data             ON registros(data_referencia);
CREATE INDEX IF NOT EXISTS idx_registros_dados_json       ON registros USING gin(dados_json);

-- ------------------------------------------------------------
-- TABELA DE HISTÓRICO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registros_historico (
    id                BIGSERIAL PRIMARY KEY,
    registro_id       BIGINT       REFERENCES registros(id) ON DELETE SET NULL,
    nome              TEXT         NOT NULL,
    nome_normalizado  TEXT         NOT NULL,
    matriz            TEXT         NOT NULL,
    data_referencia   DATE         NOT NULL,
    dados_json        JSONB        DEFAULT '{}'::jsonb,
    arquivo_origem    TEXT,
    arquivado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_historico_nome   ON registros_historico(nome_normalizado);
CREATE INDEX IF NOT EXISTS idx_historico_matriz ON registros_historico(matriz);
CREATE INDEX IF NOT EXISTS idx_historico_data   ON registros_historico(data_referencia);

-- Evita duplicar a mesma versão histórica
CREATE UNIQUE INDEX IF NOT EXISTS idx_historico_unico
    ON registros_historico(nome_normalizado, matriz, data_referencia, arquivado_em);

-- ------------------------------------------------------------
-- LOG DE ARQUIVOS PROCESSADOS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS arquivos_processados (
    id               BIGSERIAL PRIMARY KEY,
    nome_arquivo     TEXT         NOT NULL,
    status           VARCHAR(20)  NOT NULL CHECK (status IN ('sucesso', 'erro', 'parcial')),
    total_abas       INT          DEFAULT 0,
    total_registros  INT          DEFAULT 0,
    detalhes         TEXT,
    processado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arquivos_status ON arquivos_processados(status);
CREATE INDEX IF NOT EXISTS idx_arquivos_data   ON arquivos_processados(processado_em);

-- ------------------------------------------------------------
-- LOG GERAL DO ETL
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs_etl (
    id         BIGSERIAL PRIMARY KEY,
    nivel      VARCHAR(10) NOT NULL CHECK (nivel IN ('INFO', 'WARNING', 'ERROR', 'DEBUG')),
    mensagem   TEXT        NOT NULL,
    modulo     TEXT        DEFAULT 'etl',
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_nivel ON logs_etl(nivel);
CREATE INDEX IF NOT EXISTS idx_logs_data  ON logs_etl(criado_em);

-- ------------------------------------------------------------
-- VIEW: COMPARATIVO GERAL (para Power BI / Excel)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vw_comparativo_geral AS
SELECT
    r.id,
    r.nome,
    r.matriz,
    r.data_referencia,
    r.dados_json,
    r.arquivo_origem,
    r.criado_em,
    COUNT(h.id)                         AS qtd_versoes_historico,
    MIN(h.data_referencia)              AS data_mais_antiga,
    MAX(h.data_referencia)              AS data_historico_mais_recente
FROM registros r
LEFT JOIN registros_historico h
    ON h.nome_normalizado = r.nome_normalizado
   AND h.matriz           = r.matriz
GROUP BY r.id, r.nome, r.matriz, r.data_referencia, r.dados_json, r.arquivo_origem, r.criado_em;

-- ------------------------------------------------------------
-- VIEW: EVOLUÇÃO TEMPORAL (para Power BI / Excel)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vw_evolucao_temporal AS
SELECT
    nome,
    nome_normalizado,
    matriz,
    data_referencia,
    dados_json,
    arquivo_origem,
    'historico'  AS origem,
    arquivado_em AS evento_em
FROM registros_historico
UNION ALL
SELECT
    nome,
    nome_normalizado,
    matriz,
    data_referencia,
    dados_json,
    arquivo_origem,
    'atual'      AS origem,
    criado_em    AS evento_em
FROM registros
ORDER BY nome_normalizado, matriz, data_referencia;

-- ------------------------------------------------------------
-- FUNÇÃO: trigger para atualizar atualizado_em automaticamente
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_registros_updated_at ON registros;
CREATE TRIGGER trg_registros_updated_at
    BEFORE UPDATE ON registros
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
