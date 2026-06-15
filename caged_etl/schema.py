"""DDL do schema `caged` no Postgres (modelo estrela: dims + 1 fato).

As dimensões são lookups vindos dos dicionários; o fato guarda as
movimentações curadas com chaves de código (FK) para as dimensões.
"""
from __future__ import annotations

import logging

from sqlalchemy import Engine, create_engine, text

from .config import Settings, get_settings

log = logging.getLogger(__name__)

SCHEMA = "caged"

# Colunas do fato carregadas no Postgres (subconjunto canônico da curated).
FATO_COLUMNS: list[str] = [
    "competenciamov",
    "municipio",
    "cnae_secao",
    "salario",
    "sexo",
    "grau_instrucao",
    "idade",
    "tipo_movimentacao",
    "tam_estab",
    "raca_cor",
    "ind_trab_intermitente",
    "ind_trab_parcial",
    "indicador_aprendiz",
    "saldo_movimentacao",
    "movimento",
]

_DIM_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.{table} (
    codigo    TEXT PRIMARY KEY,
    descricao TEXT NOT NULL
);
"""

_FATO_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.fato_caged_mov (
    id                     BIGSERIAL PRIMARY KEY,
    competenciamov         TEXT NOT NULL,
    municipio              TEXT REFERENCES {schema}.dim_municipio(codigo),
    cnae_secao             TEXT REFERENCES {schema}.dim_cnae_secao(codigo),
    salario                NUMERIC(12,2),
    sexo                   TEXT REFERENCES {schema}.dim_sexo(codigo),
    grau_instrucao         TEXT REFERENCES {schema}.dim_grau_instrucao(codigo),
    idade                  INTEGER,
    tipo_movimentacao      TEXT REFERENCES {schema}.dim_tipo_movimentacao(codigo),
    tam_estab              TEXT REFERENCES {schema}.dim_tamanho_estab(codigo),
    raca_cor               TEXT REFERENCES {schema}.dim_raca_cor(codigo),
    ind_trab_intermitente  TEXT,
    ind_trab_parcial       TEXT,
    indicador_aprendiz     TEXT,
    saldo_movimentacao     INTEGER,
    movimento              TEXT
);
"""

# Dimensões e seus nomes de tabela (alinhado com dictionary.DIMENSIONS).
_DIM_TABLES = [
    "dim_municipio",
    "dim_sexo",
    "dim_grau_instrucao",
    "dim_cnae_secao",
    "dim_tipo_movimentacao",
    "dim_tamanho_estab",
    "dim_raca_cor",
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_fato_competencia ON {schema}.fato_caged_mov(competenciamov);",
    "CREATE INDEX IF NOT EXISTS ix_fato_municipio   ON {schema}.fato_caged_mov(municipio);",
    "CREATE INDEX IF NOT EXISTS ix_fato_secao       ON {schema}.fato_caged_mov(cnae_secao);",
]


def get_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    return create_engine(settings.database_url)


def create_schema(engine: Engine | None = None, drop: bool = False) -> None:
    """Cria o schema `caged` com dims, fato e índices. `drop=True` recria do zero."""
    engine = engine or get_engine()
    with engine.begin() as conn:
        if drop:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE;"))
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};"))
        for table in _DIM_TABLES:
            conn.execute(text(_DIM_DDL.format(schema=SCHEMA, table=table)))
        conn.execute(text(_FATO_DDL.format(schema=SCHEMA)))
        for stmt in _INDEXES:
            conn.execute(text(stmt.format(schema=SCHEMA)))
    log.info("schema '%s' criado/atualizado (drop=%s).", SCHEMA, drop)
