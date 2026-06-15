"""Cliente FTP para o Novo CAGED.

Baixa apenas os arquivos `CAGEDMOV<AAAAMM>.7z` das competências do projeto.
Idempotente: pula arquivos já baixados. Usa apenas a stdlib (`ftplib`).

Estrutura no servidor:
    /pdet/microdados/NOVO CAGED/<AAAA>/<AAAAMM>/CAGEDMOV<AAAAMM>.7z
"""
from __future__ import annotations

import logging
from ftplib import FTP, error_perm
from pathlib import Path

from tqdm.auto import tqdm

from .config import Settings, get_settings

log = logging.getLogger(__name__)

CONNECT_TIMEOUT = 60


def _connect(settings: Settings) -> FTP:
    ftp = FTP(settings.ftp_host, timeout=CONNECT_TIMEOUT)
    ftp.login()  # anônimo
    ftp.set_pasv(True)
    return ftp


def _competencia_dir(settings: Settings, competencia: str) -> str:
    """Caminho remoto da pasta de uma competência 'AAAAMM'."""
    ano = competencia[:4]
    return f"{settings.ftp_base}/{ano}/{competencia}"


def list_remote_files(competencia: str, settings: Settings | None = None) -> list[str]:
    """Lista os arquivos da pasta de uma competência (ou [] se não existir)."""
    settings = settings or get_settings()
    with _connect(settings) as ftp:
        try:
            ftp.cwd(_competencia_dir(settings, competencia))
        except error_perm:
            log.warning("Competência %s ainda não disponível no FTP.", competencia)
            return []
        return ftp.nlst()


def download_mov(
    competencia: str,
    settings: Settings | None = None,
    overwrite: bool = False,
    desc_prefix: str = "",
) -> Path | None:
    """Baixa o CAGEDMOV de uma competência. Retorna o caminho local ou None.

    Mostra uma barra de progresso (MB baixados / total) durante a transferência.
    Idempotente: se o arquivo já existe e `overwrite=False`, não rebaixa.

    `desc_prefix` é um rótulo opcional (ex.: "[3/60] ") exibido na barra.
    """
    settings = settings or get_settings()
    settings.ensure_dirs()

    with _connect(settings) as ftp:
        try:
            ftp.cwd(_competencia_dir(settings, competencia))
        except error_perm:
            log.warning("%sCompetência %s indisponível — pulando.", desc_prefix, competencia)
            return None

        nomes = ftp.nlst()
        alvo = next(
            (n for n in nomes if n.upper().startswith("CAGEDMOV") and n.lower().endswith(".7z")),
            None,
        )
        if alvo is None:
            log.warning("%sCAGEDMOV não encontrado em %s (arquivos: %s)", desc_prefix, competencia, nomes)
            return None

        destino = settings.downloads_dir / alvo
        if destino.exists() and not overwrite:
            log.info("%s✓ já existe, pulando: %s", desc_prefix, destino.name)
            return destino

        # tamanho total para a barra de progresso (SIZE pode não ser suportado)
        total = None
        try:
            ftp.voidcmd("TYPE I")  # modo binário p/ SIZE confiável
            total = ftp.size(alvo)
        except Exception:  # noqa: BLE001
            pass

        tmp = destino.with_suffix(destino.suffix + ".part")
        bar = tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"{desc_prefix}{alvo}",
            leave=True,
        )
        try:
            with open(tmp, "wb") as fh:
                def _write(chunk: bytes) -> None:
                    fh.write(chunk)
                    bar.update(len(chunk))

                ftp.retrbinary(f"RETR {alvo}", _write, blocksize=1 << 20)
        finally:
            bar.close()

        tmp.replace(destino)  # rename atômico só após sucesso
        log.info("%s✓ ok: %s (%.1f MB)", desc_prefix, destino.name, destino.stat().st_size / 1e6)
        return destino


def download_range(
    competencias: list[str] | None = None,
    settings: Settings | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Baixa o CAGEDMOV de várias competências (default: janela do projeto)."""
    settings = settings or get_settings()
    competencias = competencias or settings.competencias
    total = len(competencias)
    log.info("Iniciando download de %d competência(s): %s … %s",
             total, competencias[0], competencias[-1])
    baixados: list[Path] = []
    for i, comp in enumerate(competencias, start=1):
        prefix = f"[{i:>2}/{total}] "
        p = download_mov(comp, settings=settings, overwrite=overwrite, desc_prefix=prefix)
        if p is not None:
            baixados.append(p)
    log.info("Download concluído: %d/%d arquivo(s) disponível(is) em %s",
             len(baixados), total, settings.downloads_dir)
    return baixados
