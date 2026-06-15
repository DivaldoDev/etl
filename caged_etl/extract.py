"""Descompactação dos `.7z` do CAGED → `.txt` (py7zr).

Idempotente: pula extração se o `.txt` correspondente já existe.
"""
from __future__ import annotations

import logging
from pathlib import Path

import py7zr

from .config import Settings, get_settings

log = logging.getLogger(__name__)


def extract_file(archive: Path, settings: Settings | None = None) -> list[Path]:
    """Extrai um `.7z` para a pasta de downloads. Retorna os `.txt` resultantes."""
    settings = settings or get_settings()
    dest = settings.downloads_dir

    with py7zr.SevenZipFile(archive, mode="r") as z:
        nomes = z.getnames()
        ja_extraidos = [dest / n for n in nomes]
        if all(p.exists() for p in ja_extraidos):
            log.info("já extraído, pulando: %s", archive.name)
        else:
            log.info("extraindo %s …", archive.name)
            z.extractall(path=dest)

    return [dest / n for n in nomes if n.lower().endswith(".txt")]


def extract_all(settings: Settings | None = None) -> list[Path]:
    """Extrai todos os `CAGEDMOV*.7z` da pasta de downloads."""
    settings = settings or get_settings()
    txts: list[Path] = []
    for archive in sorted(settings.downloads_dir.glob("CAGEDMOV*.7z")):
        txts.extend(extract_file(archive, settings=settings))
    return txts
