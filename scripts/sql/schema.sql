-- ============================================================
-- SCHEMA — Sistema Matriz Indicadores Comitê
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- MATRIZES
-- Cada aba processada gera um registro de matriz
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matrizes (
    id               BIGSERIAL    PRIMARY KEY,
    nome_matriz      TEXT         NOT NULL,
    tipo_quadro      TEXT         NOT NULL,
    data_referencia  DATE         NOT NULL,
    arquivo_origem   TEXT,
    chave_hash       VARCHAR(64)  NOT NULL UNIQUE, -- SHA-256(nome_matriz|tipo_quadro|data)
    criado_em        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_matrizes_nome  ON matrizes(nome_matriz);
CREATE INDEX IF NOT EXISTS idx_matrizes_tipo  ON matrizes(tipo_quadro);
CREATE INDEX IF NOT EXISTS idx_matrizes_data  ON matrizes(data_referencia);

-- ------------------------------------------------------------
-- INDICADORES
-- Um registro por linha de indicador em cada aba
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indicadores (
    id              BIGSERIAL    PRIMARY KEY,
    matriz_id       BIGINT       NOT NULL REFERENCES matrizes(id) ON DELETE CASCADE,
    categoria       TEXT,
    indicador       TEXT         NOT NULL,
    meta            NUMERIC,
    realizado       NUMERIC,
    resultado       TEXT,
    status          TEXT,
    area            TEXT,
    setor           TEXT,
    responsavel     TEXT,
    observacao      TEXT,
    data_referencia DATE         NOT NULL,
    chave_hash      VARCHAR(64)  NOT NULL UNIQUE, -- SHA-256(matriz_id|indicador|data)
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_indicadores_matriz    ON indicadores(matriz_id);
CREATE INDEX IF NOT EXISTS idx_indicadores_indicador ON indicadores(indicador);
CREATE INDEX IF NOT EXISTS idx_indicadores_data      ON indicadores(data_referencia);
CREATE INDEX IF NOT EXISTS idx_indicadores_status    ON indicadores(status);
CREATE INDEX IF NOT EXISTS idx_indicadores_area      ON indicadores(area);
CREATE INDEX IF NOT EXISTS idx_indicadores_setor     ON indicadores(setor);

-- ------------------------------------------------------------
-- HISTÓRICO DE INDICADORES
-- Toda alteração de valor gera um registro aqui
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico_indicadores (
    id              BIGSERIAL    PRIMARY KEY,
    indicador_id    BIGINT       NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    campo_alterado  TEXT         NOT NULL,
    valor_anterior  TEXT,
    valor_novo      TEXT,
    data_alteracao  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_historico_indicador_id ON historico_indicadores(indicador_id);
CREATE INDEX IF NOT EXISTS idx_historico_data         ON historico_indicadores(data_alteracao);

-- ------------------------------------------------------------
-- LOG DE ARQUIVOS PROCESSADOS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS arquivos_processados (
    id               BIGSERIAL    PRIMARY KEY,
    nome_arquivo     TEXT         NOT NULL,
    status           VARCHAR(20)  NOT NULL CHECK (status IN ('sucesso','erro','parcial')),
    total_abas       INT          DEFAULT 0,
    total_matrizes   INT          DEFAULT 0,
    total_indicadores INT         DEFAULT 0,
    detalhes         TEXT,
    processado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- LOGS DO SISTEMA
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs_sistema (
    id         BIGSERIAL    PRIMARY KEY,
    nivel      VARCHAR(10)  NOT NULL CHECK (nivel IN ('INFO','WARNING','ERROR','DEBUG')),
    mensagem   TEXT         NOT NULL,
    modulo     TEXT         DEFAULT 'sistema',
    criado_em  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_nivel ON logs_sistema(nivel);
CREATE INDEX IF NOT EXISTS idx_logs_data  ON logs_sistema(criado_em);

-- ------------------------------------------------------------
-- VIEW: COMPARATIVO GERAL
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vw_comparativo_geral AS
SELECT
    m.nome_matriz,
    m.tipo_quadro,
    m.data_referencia,
    i.categoria,
    i.indicador,
    i.meta,
    i.realizado,
    i.resultado,
    i.status,
    i.area,
    i.setor,
    i.responsavel,
    i.observacao
FROM indicadores i
JOIN matrizes m ON m.id = i.matriz_id
ORDER BY m.nome_matriz, m.data_referencia, i.categoria, i.indicador;

-- ------------------------------------------------------------
-- VIEW: EVOLUÇÃO TEMPORAL POR INDICADOR
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vw_evolucao_temporal AS
SELECT
    m.nome_matriz,
    m.tipo_quadro,
    i.indicador,
    i.categoria,
    i.area,
    i.setor,
    i.meta,
    i.realizado,
    i.status,
    i.data_referencia,
    LAG(i.realizado) OVER (
        PARTITION BY m.nome_matriz, i.indicador
        ORDER BY i.data_referencia
    ) AS realizado_anterior,
    i.realizado - LAG(i.realizado) OVER (
        PARTITION BY m.nome_matriz, i.indicador
        ORDER BY i.data_referencia
    ) AS variacao
FROM indicadores i
JOIN matrizes m ON m.id = i.matriz_id
ORDER BY m.nome_matriz, i.indicador, i.data_referencia;

-- ------------------------------------------------------------
-- VIEW: RANKING DE PERFORMANCE
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vw_ranking_performance AS
SELECT
    m.nome_matriz,
    m.data_referencia,
    COUNT(*)                                              AS total_indicadores,
    COUNT(*) FILTER (WHERE LOWER(i.status) IN ('ok','atingido','verde','bom'))   AS atingidos,
    COUNT(*) FILTER (WHERE LOWER(i.status) IN ('crítico','critico','vermelho','ruim')) AS criticos,
    ROUND(
        COUNT(*) FILTER (WHERE LOWER(i.status) IN ('ok','atingido','verde','bom'))::numeric
        / NULLIF(COUNT(*),0) * 100, 1
    )                                                     AS pct_atingidos
FROM indicadores i
JOIN matrizes m ON m.id = i.matriz_id
GROUP BY m.nome_matriz, m.data_referencia
ORDER BY pct_atingidos DESC;

-- ------------------------------------------------------------
-- TRIGGER: atualizado_em automático
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_indicadores_updated_at ON indicadores;
CREATE TRIGGER trg_indicadores_updated_at
    BEFORE UPDATE ON indicadores
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
