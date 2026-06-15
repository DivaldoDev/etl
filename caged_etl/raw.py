"""Camada RAW: `.txt` (delimitado por `;`) → Parquet fiel à fonte.

Decisões da camada raw:
- Lê **todas** as colunas como texto (`infer_schema_length=0`) para não perder
  precisão nem reinterpretar códigos/decimais — a tipagem acontece na curated.
- Renomeia colunas para nomes canônicos (sem acento/snake), mas **não filtra**
  linhas: a raw espelha o arquivo original.
- Grava 1 parquet por competência em `data/raw/`.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import polars as pl

from .config import COLUMN_RENAME, Settings, get_settings, normalize_colname

log = logging.getLogger(__name__)

_COMPETENCIA_RE = re.compile(r"(\d{6})")


def detect_encoding(txt_path: Path, sample_bytes: int = 1 << 20) -> str:
    """Detecta encoding utilizável pelo polars ('utf8' ou 'utf8-lossy').

    Tenta decodificar uma amostra como UTF-8; se falhar, usa 'utf8-lossy'
    (tolerante a bytes inválidos). Os dados do Novo CAGED são, em regra, UTF-8.
    """
    with open(txt_path, "rb") as fh:
        sample = fh.read(sample_bytes)
    try:
        sample.decode("utf-8")
        return "utf8"
    except UnicodeDecodeError:
        log.warning("%s não é UTF-8 puro → usando utf8-lossy.", txt_path.name)
        return "utf8-lossy"


def _competencia_from_name(path: Path) -> str:
    m = _COMPETENCIA_RE.search(path.stem)
    return m.group(1) if m else "000000"


def _rename_map(columns: list[str]) -> dict[str, str]:
    """Mapa de renome: cabeçalho original -> canônico (preserva não mapeados)."""
    out: dict[str, str] = {}
    for col in columns:
        canon = COLUMN_RENAME.get(normalize_colname(col))
        if canon and canon != col:
            out[col] = canon
    return out


def txt_to_raw_parquet(
    txt_path: Path,
    settings: Settings | None = None,
    overwrite: bool = False,
) -> Path:
    """Converte um `.txt` do CAGEDMOV para parquet raw. Retorna o caminho."""
    settings = settings or get_settings()
    settings.ensure_dirs()

    competencia = _competencia_from_name(txt_path)
    destino = settings.raw_dir / f"caged_mov_{competencia}.parquet"
    if destino.exists() and not overwrite:
        log.info("raw já existe, pulando: %s", destino.name)
        return destino

    encoding = detect_encoding(txt_path)
    df = pl.read_csv(
        txt_path,
        separator=";",
        encoding=encoding,
        infer_schema_length=0,  # tudo como Utf8 (fiel)
        truncate_ragged_lines=True,
        ignore_errors=True,
    )
    df = df.rename(_rename_map(df.columns))
    if "competenciamov" not in df.columns:
        df = df.with_columns(pl.lit(competencia).alias("competenciamov"))

    df.write_parquet(destino)
    log.info("raw gravado: %s (%d linhas)", destino.name, df.height)
    return destino


def build_raw_layer(
    settings: Settings | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Converte todos os `.txt` da pasta de downloads para a camada raw."""
    settings = settings or get_settings()
    out: list[Path] = []
    for txt in sorted(settings.downloads_dir.glob("*.txt")):
        out.append(txt_to_raw_parquet(txt, settings=settings, overwrite=overwrite))
    return out
