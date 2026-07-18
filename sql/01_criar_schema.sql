
CREATE TABLE IF NOT EXISTS dim_material (
    codigo_item     INTEGER PRIMARY KEY,
    codigo_classe   INTEGER,
    nome_classe     TEXT,
    codigo_grupo    INTEGER,
    nome_grupo      TEXT,
    codigo_pdm      INTEGER,
    nome_pdm        TEXT,
    descricao_item  TEXT
);

CREATE TABLE IF NOT EXISTS dim_fornecedor (
    ni_fornecedor   TEXT PRIMARY KEY,
    nome_fornecedor TEXT
);

CREATE TABLE IF NOT EXISTS dim_uasg (
    codigo_uasg      TEXT PRIMARY KEY,
    nome_uasg        TEXT,
    codigo_municipio INTEGER,
    municipio        TEXT,
    estado           TEXT,
    codigo_orgao     INTEGER,
    nome_orgao       TEXT,
    poder            TEXT,
    esfera           TEXT
);

CREATE TABLE IF NOT EXISTS fato_precos_praticados (
    id_compra_item              TEXT,
    codigo_item_catalogo        INTEGER,
    ni_fornecedor                TEXT,
    codigo_uasg                  TEXT,
    quantidade                   REAL,
    preco_unitario               REAL,
    data_compra                  TEXT,
    data_resultado               TEXT,
    marca                        TEXT,
    sigla_unidade_medida         TEXT,
    nome_unidade_medida          TEXT,
    criterio_julgamento          TEXT,
    modalidade                   INTEGER,
    objeto_compra                TEXT,
    codigo_classe                INTEGER,
    nome_classe                  TEXT,
    data_hora_atualizacao_item   TEXT,
    FOREIGN KEY (codigo_item_catalogo) REFERENCES dim_material (codigo_item),
    FOREIGN KEY (ni_fornecedor) REFERENCES dim_fornecedor (ni_fornecedor),
    FOREIGN KEY (codigo_uasg) REFERENCES dim_uasg (codigo_uasg)
);
