"""caged_etl — pipeline ETL do Novo CAGED (Maceió × Arapiraca).

Camadas (medallion):
    FTP → downloads(.7z) → .txt → raw(parquet) → curated(parquet) → Postgres

Uso típico (orquestrado pelos notebooks):
    from caged_etl import ftp_client, extract, raw, transform, load
    ftp_client.download_range()
    extract.extract_all()
    raw.build_raw_layer()
    transform.build_curated()
    load.run_load(recreate=True)
"""
from __future__ import annotations

import logging

from .config import Settings, get_settings

__all__ = ["get_settings", "Settings", "setup_logging"]


def setup_logging(level: int = logging.INFO) -> None:
    """Configura logging amigável para uso em notebooks."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
