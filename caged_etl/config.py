"""Configuração central do ETL (carregada de variáveis de ambiente / .env).

Tudo que é "parâmetro do projeto" (municípios, janela temporal, caminhos,
conexão) vive aqui — para os notebooks e o futuro backend lerem da mesma fonte.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do pacote ETL (…/etl). Os dados e dicionários são relativos a ela.
ETL_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configurações do ETL, sobreponíveis por ambiente / arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=ETL_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Banco ---
    database_url: str = Field(
        default="postgresql+psycopg://caged:caged@localhost:5432/caged",
        alias="DATABASE_URL",
    )

    # --- FTP do Novo CAGED ---
    ftp_host: str = Field(default="ftp.mtps.gov.br", alias="CAGED_FTP_HOST")
    ftp_base: str = Field(default="/pdet/microdados/NOVO CAGED", alias="CAGED_FTP_BASE")

    # --- Escopo do projeto ---
    # Códigos IBGE de 6 dígitos: Maceió=270430, Arapiraca=270030.
    # Mantido como string (CSV) para evitar o parse JSON de listas do
    # pydantic-settings; exposto já parseado pela propriedade `municipios`.
    municipios_csv: str = Field(default="270430,270030", alias="CAGED_MUNICIPIOS")
    ano_inicio: int = Field(default=2021, alias="CAGED_ANO_INICIO")
    ano_fim: int = Field(default=2025, alias="CAGED_ANO_FIM")

    # --- Caminhos (camadas medallion) ---
    data_dir: Path = ETL_ROOT / "data"
    dicts_dir: Path = ETL_ROOT / "dictionaries"

    # --- Derivados ---
    @property
    def municipios(self) -> list[int]:
        """Códigos IBGE do escopo, parseados de 'CAGED_MUNICIPIOS'."""
        return [int(x.strip()) for x in self.municipios_csv.split(",") if x.strip()]

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def curated_dir(self) -> Path:
        return self.data_dir / "curated"

    @property
    def curated_file(self) -> Path:
        return self.curated_dir / "caged_mov_maceio_arapiraca.parquet"

    @property
    def municipios_nome(self) -> dict[int, str]:
        return {270430: "Maceió", 270030: "Arapiraca"}

    @property
    def competencias(self) -> list[str]:
        """Lista de competências 'AAAAMM' dentro da janela do projeto."""
        out: list[str] = []
        for ano in range(self.ano_inicio, self.ano_fim + 1):
            for mes in range(1, 13):
                out.append(f"{ano}{mes:02d}")
        return out

    def ensure_dirs(self) -> None:
        """Garante a existência das pastas de dados."""
        for d in (self.downloads_dir, self.raw_dir, self.curated_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Mapeamento de colunas do CAGEDMOV (cabeçalho oficial -> nome canônico)
# ---------------------------------------------------------------------------
# O cabeçalho da fonte vem com acentos e capitalização variável. Normalizamos
# (sem acento, minúsculo, sem espaços) e mapeamos para nomes canônicos estáveis.


def normalize_colname(name: str) -> str:
    """Remove acentos, espaços e baixa a caixa de um nome de coluna."""
    nfkd = unicodedata.normalize("NFKD", name)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.strip().lower().replace(" ", "").replace("_", "")


# normalizado -> canônico. Cobre as colunas usadas pelas análises do grupo
# (mais algumas úteis). Colunas não mapeadas são preservadas como vieram.
COLUMN_RENAME: dict[str, str] = {
    "competenciamov": "competenciamov",
    "regiao": "regiao",
    "uf": "uf",
    "municipio": "municipio",
    "secao": "cnae_secao",
    "subclasse": "cnae_subclasse",
    "saldomovimentacao": "saldo_movimentacao",
    "cbo2002ocupacao": "cbo2002",
    "categoria": "categoria",
    "graudeinstrucao": "grau_instrucao",
    "idade": "idade",
    "horascontratuais": "horas_contratuais",
    "racacor": "raca_cor",
    "sexo": "sexo",
    "tipoempregador": "tipo_empregador",
    "tipoestabelecimento": "tipo_estabelecimento",
    "tipomovimentacao": "tipo_movimentacao",
    "tipodedeficiencia": "tipo_deficiencia",
    "indtrabintermitente": "ind_trab_intermitente",
    "indtrabparcial": "ind_trab_parcial",
    "salario": "salario",
    "tamestabjan": "tam_estab",
    "indicadoraprendiz": "indicador_aprendiz",
    "origemdainformacao": "origem_informacao",
    "indicadordeforadoprazo": "indicador_fora_prazo",
    "unidadesalariocodigo": "unidade_salario_cod",
    "valorsalariofixo": "valor_salario_fixo",
}

# Colunas que seguem para a camada curated / Postgres (fato).
CURATED_COLUMNS: list[str] = [
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
]
