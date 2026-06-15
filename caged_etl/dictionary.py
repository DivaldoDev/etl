"""Dicionários de decodificação (código → descrição).

Os CSVs em `dictionaries/` foram extraídos do layout oficial do Novo CAGED.
Formato de cada arquivo: colunas `codigo,descricao` (UTF-8, vírgula).

Este módulo expõe:
- `load_dictionary(name)` → DataFrame polars (codigo, descricao);
- `decode_map(name)`      → dict {codigo: descricao};
- `DIMENSIONS`            → metadados que ligam cada dicionário à coluna do fato.
"""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from .config import Settings, get_settings


@dataclass(frozen=True)
class Dimension:
    """Liga um dicionário a uma coluna de código da tabela fato."""

    name: str          # nome lógico / arquivo (sem extensão)
    fato_column: str   # coluna de código correspondente no fato
    table: str         # nome da tabela dimensão no Postgres


# Ordem = ordem de criação/carga das dimensões.
DIMENSIONS: list[Dimension] = [
    Dimension("municipio", "municipio", "dim_municipio"),
    Dimension("sexo", "sexo", "dim_sexo"),
    Dimension("grau_instrucao", "grau_instrucao", "dim_grau_instrucao"),
    Dimension("cnae_secao", "cnae_secao", "dim_cnae_secao"),
    Dimension("tipo_movimentacao", "tipo_movimentacao", "dim_tipo_movimentacao"),
    Dimension("tam_estab", "tam_estab", "dim_tamanho_estab"),
    Dimension("raca_cor", "raca_cor", "dim_raca_cor"),
]

# nome lógico -> arquivo csv
_FILES = {
    "municipio": "municipio.csv",
    "sexo": "sexo.csv",
    "grau_instrucao": "graudeinstrucao.csv",
    "cnae_secao": "cnae20secao.csv",
    "tipo_movimentacao": "tipomovimentacao.csv",
    "tam_estab": "tamestab.csv",
    "raca_cor": "racacor.csv",
}


def load_dictionary(name: str, settings: Settings | None = None) -> pl.DataFrame:
    """Carrega um dicionário como DataFrame (codigo: str, descricao: str)."""
    settings = settings or get_settings()
    path = settings.dicts_dir / _FILES[name]
    return pl.read_csv(path, schema_overrides={"codigo": pl.Utf8, "descricao": pl.Utf8})


def decode_map(name: str, settings: Settings | None = None) -> dict[str, str]:
    """Retorna {codigo: descricao} para um dicionário."""
    df = load_dictionary(name, settings=settings)
    return dict(zip(df["codigo"].to_list(), df["descricao"].to_list()))


def all_dictionaries(settings: Settings | None = None) -> dict[str, pl.DataFrame]:
    """Carrega todos os dicionários (útil para inspeção em notebook)."""
    return {dim.name: load_dictionary(dim.name, settings=settings) for dim in DIMENSIONS}
