# ETL — Novo CAGED (Maceió × Arapiraca)

Pipeline **medallion** que baixa os microdados do Novo CAGED, converte para
Parquet, filtra/limpa/decodifica e carrega num Postgres.

```
FTP  →  data/downloads/*.7z  →  *.txt  →  data/raw/*.parquet  →  data/curated/*.parquet  →  Postgres (schema caged)
```

A lógica vive no pacote **`caged_etl/`** (reutilizável/testável). Os **notebooks**
apenas orquestram e exploram, chamando funções do pacote.

## Setup

```bash
# Postgres precisa estar no ar (na raiz do repo):  docker compose up -d db
cp .env.example .env
uv sync --extra notebook
uv run python -m ipykernel install --user --name caged-etl --display-name "CAGED ETL"
uv run jupyter lab
```

## Notebooks (rodar na ordem)

| # | Notebook | O que faz |
|---|----------|-----------|
| 00 | `00_setup_e_ftp_explore` | Testa FTP, baixa 1 mês piloto, detecta encoding/delimitador, valida código de município |
| 01 | `01_extract_e_raw` | Baixa 2021–2025, extrai `.7z`, grava camada **raw** em parquet |
| 02 | `02_dicionario_e_colunas` | Mapeia colunas via dicionário oficial; gera o dicionário de dados do projeto |
| 03 | `03_limpeza_e_curated` | Filtra municípios, trata nulos/código 99/outliers, decodifica → **curated** |
| 04 | `04_carga_postgres` | Cria schema, carrega dims + fato, queries de sanidade |

## Pacote `caged_etl/`

| Módulo | Responsabilidade |
|--------|------------------|
| `config.py` | Settings (pydantic): municípios, anos, paths, FTP, `DATABASE_URL` |
| `ftp_client.py` | Listar/baixar `CAGEDMOV*.7z` do FTP (idempotente) |
| `extract.py` | `.7z` → `.txt` (py7zr) |
| `raw.py` | `.txt(;)` → parquet **raw** (polars, fiel à fonte) |
| `dictionary.py` | Carrega dicionários (`dictionaries/*.csv`) → mapas de decode |
| `transform.py` | Filtra/limpa/decodifica → parquet **curated** |
| `schema.py` | DDL do schema `caged` (dims + fato) |
| `load.py` | Carrega curated + dicionários no Postgres |

## Notas sobre os dados
- `salário` usa **vírgula decimal** → convertido para `float`.
- `graudeinstrução` código **99** = "ignorado" → removido (não distorcer médias).
- `município` = código IBGE de **6 dígitos**.
- Camada **raw** é fiel à fonte (sem filtro); o recorte ocorre na **curated**.
