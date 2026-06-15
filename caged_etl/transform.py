"""Camada CURATED: raw → recorte + limpeza + tipagem + decode.

Aplica, nesta ordem, o pré-processamento definido no projeto:
1. filtro de escopo (municípios Maceió/Arapiraca + anos 2021–2025);
2. tipagem (salário vírgula→ponto→float, idade/saldo inteiros);
3. remoção de nulos críticos (salário, sexo, grau de instrução);
4. remoção do código 99 (ignorado) em grau de instrução;
5. remoção de outliers de salário (≤ 0 e acima de um teto plausível);
6. coluna derivada `movimento` (Admissão/Desligamento);
7. decode (colunas `*_desc` legíveis via dicionários).

Grava um único parquet curado em `data/curated/`.
"""
from __future__ import annotations

import logging

import polars as pl

from .config import CURATED_COLUMNS, Settings, get_settings
from .dictionary import DIMENSIONS, load_dictionary

log = logging.getLogger(__name__)

# Acima deste valor o salário mensal é tratado como erro de digitação.
# (Refinável via análise IQR no notebook 03.)
SALARIO_TETO = 1_000_000.0
CRITICOS = ["salario", "sexo", "grau_instrucao"]


def _scan_raw(settings: Settings) -> pl.LazyFrame:
    arquivos = sorted(settings.raw_dir.glob("caged_mov_*.parquet"))
    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum parquet raw em {settings.raw_dir}. Rode o notebook 01 antes."
        )
    return pl.scan_parquet(arquivos)


def _decode(lf: pl.LazyFrame, settings: Settings) -> pl.LazyFrame:
    """Adiciona colunas `<dim>_desc` por join com cada dicionário."""
    for dim in DIMENSIONS:
        if dim.fato_column not in lf.collect_schema().names():
            continue
        dic = (
            load_dictionary(dim.name, settings=settings)
            .rename({"codigo": dim.fato_column, "descricao": f"{dim.fato_column}_desc"})
            .lazy()
        )
        lf = lf.join(dic, on=dim.fato_column, how="left")
    return lf


def build_curated(
    settings: Settings | None = None,
    overwrite: bool = True,
) -> pl.DataFrame:
    """Constrói a camada curada e grava o parquet. Retorna o DataFrame."""
    settings = settings or get_settings()
    settings.ensure_dirs()

    if settings.curated_file.exists() and not overwrite:
        log.info("curated já existe: %s", settings.curated_file.name)
        return pl.read_parquet(settings.curated_file)

    municipios = [str(m) for m in settings.municipios]
    lf = _scan_raw(settings)

    presentes = [c for c in CURATED_COLUMNS if c in lf.collect_schema().names()]
    lf = lf.select(presentes)

    # 1. escopo: municípios + janela temporal
    lf = lf.filter(pl.col("municipio").is_in(municipios))
    lf = lf.filter(
        pl.col("competenciamov").str.slice(0, 4).cast(pl.Int32)
        .is_between(settings.ano_inicio, settings.ano_fim)
    )

    # 2. tipagem e tratamento de centavos
    # Parse inteligente: se contiver ',', remove '.' (separador de milhar) e troca ',' por '.'
    # Se não contiver ',', o '.' já é o separador decimal (ex: 2643.4299)
    sal_expr = (
        pl.when(pl.col("salario").str.contains(","))
        .then(pl.col("salario").str.replace_all(r"\.", "").str.replace(",", "."))
        .otherwise(pl.col("salario"))
        .cast(pl.Float64, strict=False)
    )

    lf = lf.with_columns(
        sal_expr.alias("salario"),
        pl.col("idade").cast(pl.Int32, strict=False),
        pl.col("saldo_movimentacao").cast(pl.Int32, strict=False),
    )

    # Corrige salários informados em centavos (sem separador decimal adequado).
    # Valores acima de 50.000 são corrigidos dividindo por 100.
    lf = lf.with_columns(
        pl.when(pl.col("salario") > 50000.0)
        .then(pl.col("salario") / 100.0)
        .otherwise(pl.col("salario"))
        .alias("salario")
    )

    # 3. nulos críticos
    for col in CRITICOS:
        if col in presentes:
            lf = lf.filter(pl.col(col).is_not_null() & (pl.col(col).cast(pl.Utf8) != ""))

    # 4. código 99 (ignorado) em grau de instrução
    lf = lf.filter(pl.col("grau_instrucao") != "99")

    # 5. outliers de salário
    lf = lf.filter((pl.col("salario") > 0) & (pl.col("salario") <= SALARIO_TETO))

    # 6. derivada: movimento (saldomovimentação: +1 admissão / -1 desligamento)
    lf = lf.with_columns(
        pl.when(pl.col("saldo_movimentacao") > 0)
        .then(pl.lit("Admissão"))
        .when(pl.col("saldo_movimentacao") < 0)
        .then(pl.lit("Desligamento"))
        .otherwise(pl.lit("Indefinido"))
        .alias("movimento")
    )

    # 7. decode
    lf = _decode(lf, settings)

    df = lf.collect()
    df.write_parquet(settings.curated_file)
    log.info("curated gravado: %s (%d linhas)", settings.curated_file.name, df.height)
    return df
