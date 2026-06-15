"""Carga no Postgres: dicionários → dims e parquet curated → fato.

Idempotente: trunca as tabelas antes de inserir (recarga limpa).
"""
from __future__ import annotations

import logging

import polars as pl
from sqlalchemy import Engine, text

from .config import Settings, get_settings
from .dictionary import DIMENSIONS, load_dictionary
from .schema import FATO_COLUMNS, SCHEMA, create_schema, get_engine

log = logging.getLogger(__name__)


def _augment_with_observed(dim, df_dict: pl.DataFrame, curated: pl.DataFrame | None) -> pl.DataFrame:
    """Garante que a dimensão cubra todo código presente nos dados.

    Códigos observados no fato mas ausentes do dicionário semente são
    adicionados com descrição '(não mapeado)' — evita violar a FK e sinaliza
    o que falta reconciliar com o dicionário oficial.
    """
    if curated is None or dim.fato_column not in curated.columns:
        return df_dict
    observados = set(curated[dim.fato_column].drop_nulls().unique().to_list())
    conhecidos = set(df_dict["codigo"].to_list())
    faltando = sorted(observados - conhecidos, key=str)
    if faltando:
        log.warning(
            "dim %s: %d código(s) sem rótulo no dicionário -> %s (preencher com layout oficial)",
            dim.table, len(faltando), faltando,
        )
        extra = pl.DataFrame({
            "codigo": faltando,
            "descricao": [f"(não mapeado: {c})" for c in faltando],
        })
        df_dict = pl.concat([df_dict, extra], how="vertical")
    return df_dict


def load_dimensions(engine: Engine, settings: Settings, curated: pl.DataFrame | None = None) -> None:
    """Carrega cada dicionário na sua tabela dimensão (robusta a lacunas)."""
    for dim in DIMENSIONS:
        df = load_dictionary(dim.name, settings=settings)  # codigo, descricao
        df = _augment_with_observed(dim, df, curated)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {SCHEMA}.{dim.table} CASCADE;"))
        df.write_database(
            table_name=f"{SCHEMA}.{dim.table}",
            connection=settings.database_url,
            if_table_exists="append",
        )
        log.info("dim %s: %d linhas.", dim.table, df.height)


def load_fato(engine: Engine, settings: Settings, curated: pl.DataFrame | None = None) -> int:
    """Carrega o parquet curado na tabela fato. Retorna nº de linhas."""
    if curated is None:
        if not settings.curated_file.exists():
            raise FileNotFoundError(
                f"Curated não encontrado: {settings.curated_file}. Rode o notebook 03."
            )
        curated = pl.read_parquet(settings.curated_file)
    df = curated
    cols = [c for c in FATO_COLUMNS if c in df.columns]
    df = df.select(cols)

    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {SCHEMA}.fato_caged_mov RESTART IDENTITY CASCADE;"))
    df.write_database(
        table_name=f"{SCHEMA}.fato_caged_mov",
        connection=settings.database_url,
        if_table_exists="append",
    )
    log.info("fato_caged_mov: %d linhas carregadas.", df.height)
    return df.height


def run_load(settings: Settings | None = None, recreate: bool = False) -> int:
    """Pipeline de carga completo: schema → dims → fato.

    Lê o curated uma vez e usa em ambas as etapas, garantindo que as
    dimensões cubram todos os códigos presentes no fato (sem violar FK).
    """
    settings = settings or get_settings()
    if not settings.curated_file.exists():
        raise FileNotFoundError(
            f"Curated não encontrado: {settings.curated_file}. Rode o notebook 03."
        )
    curated = pl.read_parquet(settings.curated_file)
    engine = get_engine(settings)
    create_schema(engine, drop=recreate)
    load_dimensions(engine, settings, curated=curated)
    return load_fato(engine, settings, curated=curated)
