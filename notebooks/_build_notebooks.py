"""Gera os notebooks 00–04 do ETL (executar uma vez: `python _build_notebooks.py`).

Mantido no repo para permitir regenerar os notebooks de forma versionável.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

KERNEL = {
    "display_name": "CAGED ETL",
    "language": "python",
    "name": "caged-etl",
}

BOOTSTRAP = (
    "import sys, pathlib\n"
    "# garante que o pacote caged_etl (em ../) seja importável a partir do notebook\n"
    "sys.path.insert(0, str(pathlib.Path.cwd().parent))\n"
    "from caged_etl import setup_logging, get_settings\n"
    "setup_logging()\n"
    "settings = get_settings()\n"
    "print('Municípios:', settings.municipios, '| Anos:', settings.ano_inicio, '-', settings.ano_fim)"
)


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": text}


def write_nb(name, cells):
    nb = {
        "cells": cells,
        "metadata": {"kernelspec": KERNEL, "language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (HERE / name).write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print("gerado:", name)


# --------------------------------------------------------------------------- 00
write_nb("00_setup_e_ftp_explore.ipynb", [
    md("# 00 — Setup & Exploração do FTP\n"
       "\n"
       "**Objetivo:** validar acesso ao FTP do Novo CAGED, baixar **1 mês piloto**, "
       "confirmar delimitador/encoding e o **código de município** (6 dígitos) "
       "antes de processar a janela completa.\n"
       "\n"
       "> Pré-requisito: `docker compose up -d db` na raiz e `cp .env.example .env` aqui."),
    code(BOOTSTRAP),
    md("## 1. Conexão e listagem de uma competência"),
    code("from caged_etl import ftp_client\n"
         "\n"
         "PILOTO = '202401'  # mês piloto\n"
         "arquivos = ftp_client.list_remote_files(PILOTO)\n"
         "arquivos"),
    md("## 2. Download do CAGEDMOV piloto"),
    code("zip_path = ftp_client.download_mov(PILOTO)\n"
         "zip_path"),
    md("## 3. Extração do .7z"),
    code("from caged_etl import extract\n"
         "txts = extract.extract_file(zip_path)\n"
         "txts"),
    md("## 4. Encoding, delimitador e cabeçalho"),
    code("import polars as pl\n"
         "from caged_etl.raw import detect_encoding\n"
         "\n"
         "txt = txts[0]\n"
         "enc = detect_encoding(txt)\n"
         "print('encoding detectado:', enc)\n"
         "\n"
         "preview = pl.read_csv(txt, separator=';', encoding=enc, infer_schema_length=0, n_rows=5)\n"
         "print('colunas originais:', preview.columns)\n"
         "preview"),
    md("## 5. Validação do código de município (6 dígitos)\n"
       "Confirma que `270430` (Maceió) e `270030` (Arapiraca) existem na coluna `município`."),
    code("from caged_etl.config import normalize_colname\n"
         "col_mun = next(c for c in preview.columns if normalize_colname(c) == 'municipio')\n"
         "amostra = pl.read_csv(txt, separator=';', encoding=enc, infer_schema_length=0,\n"
         "                      columns=[col_mun])\n"
         "vc = amostra[col_mun].value_counts().sort('count', descending=True)\n"
         "print('exemplos de códigos de município:')\n"
         "print(vc.head(10))\n"
         "alvo = {str(m) for m in settings.municipios}\n"
         "encontrados = set(amostra[col_mun].unique().to_list()) & alvo\n"
         "print('municípios-alvo encontrados:', encontrados)\n"
         "assert encontrados == alvo, 'Conferir formato do código de município no layout!'"),
    md("## ✅ Conclusões\n"
       "- FTP acessível, arquivo `CAGEDMOV` baixado e extraído.\n"
       "- Delimitador `;` e encoding confirmados.\n"
       "- Códigos de município de 6 dígitos validados → seguir para o `01`."),
])

# --------------------------------------------------------------------------- 01
write_nb("01_extract_e_raw.ipynb", [
    md("# 01 — Download + Camada RAW\n"
       "\n"
       "**Objetivo:** baixar todos os `CAGEDMOV` de 2021–2025, extrair os `.txt` e "
       "gravar a **camada raw** (parquet fiel à fonte, sem filtro). Idempotente."),
    code(BOOTSTRAP),
    md("## 1. Download de toda a janela (2021–2025)\n"
       "Pode demorar — cada mês tem dezenas de MB. Já baixados são pulados."),
    code("from caged_etl import ftp_client\n"
         "baixados = ftp_client.download_range()\n"
         "print(f'{len(baixados)} arquivos disponíveis em downloads/')"),
    md("## 2. Extração de todos os .7z"),
    code("from caged_etl import extract\n"
         "txts = extract.extract_all()\n"
         "print(f'{len(txts)} arquivos .txt extraídos')"),
    md("## 3. Construção da camada RAW (parquet por competência)"),
    code("from caged_etl import raw\n"
         "parquets = raw.build_raw_layer()\n"
         "print(f'{len(parquets)} parquets raw gravados em {settings.raw_dir}')"),
    md("## 4. Sanidade: linhas por competência"),
    code("import polars as pl\n"
         "lf = pl.scan_parquet(sorted(settings.raw_dir.glob('caged_mov_*.parquet')))\n"
         "por_comp = (lf.group_by('competenciamov').len()\n"
         "              .sort('competenciamov').collect())\n"
         "print('total de linhas (Brasil, sem filtro):', por_comp['len'].sum())\n"
         "por_comp"),
])

# --------------------------------------------------------------------------- 02
write_nb("02_dicionario_e_colunas.ipynb", [
    md("# 02 — Dicionário de Dados & Identificação de Colunas\n"
       "\n"
       "**Objetivo:** mapear cada coluna do CAGEDMOV ao seu significado e produzir o "
       "**dicionário de dados do projeto**.\n"
       "\n"
       "> ⚠️ Os CSVs em `../dictionaries/` são **sementes** baseadas no layout do "
       "Novo CAGED. **Reconcilie-os com o layout oficial** (planilha do MTE) antes de "
       "considerar a decodificação final."),
    code(BOOTSTRAP),
    md("## 1. Colunas presentes na camada raw"),
    code("import polars as pl\n"
         "um = sorted(settings.raw_dir.glob('caged_mov_*.parquet'))[0]\n"
         "df = pl.read_parquet(um)\n"
         "print('nº de colunas:', len(df.columns))\n"
         "df.columns"),
    md("## 2. Domínio de valores das colunas categóricas\n"
       "Valores distintos observados (ajuda a validar os dicionários)."),
    code("from caged_etl.dictionary import DIMENSIONS\n"
         "for dim in DIMENSIONS:\n"
         "    if dim.fato_column in df.columns:\n"
         "        vals = sorted(df[dim.fato_column].unique().to_list(), key=lambda x: (x is None, x))\n"
         "        print(f'{dim.fato_column:20s} -> {vals[:15]}')"),
    md("## 3. Dicionários carregados (código → descrição)"),
    code("from caged_etl.dictionary import all_dictionaries\n"
         "dics = all_dictionaries()\n"
         "for nome, tab in dics.items():\n"
         "    print(f'### {nome} ({tab.height} códigos)')\n"
         "    print(tab)\n"),
    md("## 4. Dicionário de dados do projeto (coluna → tipo → domínio)"),
    code("from caged_etl.config import CURATED_COLUMNS\n"
         "linhas = []\n"
         "for col in CURATED_COLUMNS:\n"
         "    if col in df.columns:\n"
         "        n_distintos = df[col].n_unique()\n"
         "        linhas.append({'coluna': col, 'tipo_origem': str(df[col].dtype),\n"
         "                       'valores_distintos': n_distintos})\n"
         "dicionario_projeto = pl.DataFrame(linhas)\n"
         "dicionario_projeto"),
])

# --------------------------------------------------------------------------- 03
write_nb("03_limpeza_e_curated.ipynb", [
    md("# 03 — Limpeza & Camada CURATED\n"
       "\n"
       "**Objetivo:** aplicar o pré-processamento (escopo, nulos, código 99, "
       "outliers de salário, tipagem, decode) e gravar a **camada curated**.\n"
       "\n"
       "Regras implementadas em `caged_etl/transform.py`."),
    code(BOOTSTRAP),
    md("## 1. Diagnóstico ANTES (no recorte Maceió + Arapiraca)"),
    code("import polars as pl\n"
         "municipios = [str(m) for m in settings.municipios]\n"
         "lf = (pl.scan_parquet(sorted(settings.raw_dir.glob('caged_mov_*.parquet')))\n"
         "        .filter(pl.col('municipio').is_in(municipios)))\n"
         "escopo = lf.collect()\n"
         "print('linhas no recorte (bruto):', escopo.height)\n"
         "print('nulos/vazios por coluna crítica:')\n"
         "for c in ['salario', 'sexo', 'grau_instrucao']:\n"
         "    n = escopo.filter(pl.col(c).is_null() | (pl.col(c) == '')).height\n"
         "    print(f'  {c:16s}: {n}')\n"
         "print('grau de instrução == 99 (ignorado):',\n"
         "      escopo.filter(pl.col('grau_instrucao') == '99').height)"),
    md("## 2. Distribuição de salário (antes da limpeza de outliers)"),
    code("import matplotlib.pyplot as plt\n"
         "sal = (escopo.select(pl.col('salario').str.replace_all(r'\\\\.', '')\n"
         "                      .str.replace(',', '.').cast(pl.Float64, strict=False))\n"
         "              .drop_nulls()['salario'])\n"
         "print(sal.describe())\n"
         "fig, ax = plt.subplots(1, 2, figsize=(11, 3))\n"
         "ax[0].hist(sal.filter(sal <= sal.quantile(0.99)), bins=50)\n"
         "ax[0].set_title('Salário (<= p99)')\n"
         "ax[1].boxplot(sal.filter(sal <= sal.quantile(0.99)).to_list(), vert=False)\n"
         "ax[1].set_title('Boxplot (<= p99)')\n"
         "plt.tight_layout(); plt.show()"),
    md("## 3. Construção da camada CURATED"),
    code("from caged_etl import transform\n"
         "curated = transform.build_curated(overwrite=True)\n"
         "print('linhas curadas:', curated.height)\n"
         "curated.head()"),
    md("## 4. Diagnóstico DEPOIS"),
    code("print('linhas por município:')\n"
         "print(curated.group_by('municipio_desc').len())\n"
         "print('\\nnulos críticos restantes (esperado 0):')\n"
         "for c in ['salario', 'sexo', 'grau_instrucao']:\n"
         "    print(f'  {c:16s}: {curated.filter(pl.col(c).is_null()).height}')\n"
         "print('\\ngrau 99 restante (esperado 0):',\n"
         "      curated.filter(pl.col('grau_instrucao') == '99').height)\n"
         "print('salário mín/máx:', curated['salario'].min(), curated['salario'].max())"),
    md("## ✅ Decisões de limpeza documentadas\n"
       "- **Escopo**: somente Maceió/Arapiraca, 2021–2025.\n"
       "- **Nulos críticos** (`salario`, `sexo`, `grau_instrucao`): linhas removidas.\n"
       "- **Código 99** em grau de instrução: removido (não distorcer médias).\n"
       "- **Outliers de salário**: `<= 0` e `> R$ 1.000.000` removidos (teto refinável por IQR).\n"
       "- **Tipagem**: salário `float` (vírgula→ponto), idade/saldo inteiros.\n"
       "- **Decode**: colunas `*_desc` adicionadas para leitura."),
])

# --------------------------------------------------------------------------- 04
write_nb("04_carga_postgres.ipynb", [
    md("# 04 — Carga no Postgres\n"
       "\n"
       "**Objetivo:** criar o schema `caged` (dims + fato), carregar dicionários e "
       "a camada curada, e rodar **queries de sanidade**.\n"
       "\n"
       "> Pré-requisito: `docker compose up -d db` ativo."),
    code(BOOTSTRAP),
    md("## 1. Criar schema + carregar dims e fato (recarga limpa)"),
    code("from caged_etl import load\n"
         "n = load.run_load(recreate=True)\n"
         "print('linhas carregadas no fato:', n)"),
    md("## 2. Sanidade — contagem por município (deve ser só 270430 e 270030)"),
    code("import polars as pl\n"
         "from caged_etl.schema import get_engine, SCHEMA\n"
         "eng = get_engine()\n"
         "q = f'''SELECT f.municipio, m.descricao AS municipio_nome, count(*) AS n\n"
         "        FROM {SCHEMA}.fato_caged_mov f\n"
         "        JOIN {SCHEMA}.dim_municipio m ON m.codigo = f.municipio\n"
         "        GROUP BY 1,2 ORDER BY n DESC'''\n"
         "pl.read_database(q, connection=eng)"),
    md("## 3. Sanidade — saldo de emprego mensal por município\n"
       "(admissões − desligamentos = soma de `saldo_movimentacao`)"),
    code("q = f'''SELECT f.competenciamov, m.descricao AS municipio,\n"
         "               SUM(f.saldo_movimentacao) AS saldo\n"
         "        FROM {SCHEMA}.fato_caged_mov f\n"
         "        JOIN {SCHEMA}.dim_municipio m ON m.codigo = f.municipio\n"
         "        GROUP BY 1,2 ORDER BY 1,2'''\n"
         "saldo = pl.read_database(q, connection=eng)\n"
         "print(saldo.head(24))\n"
         "saldo"),
    md("## 4. Sanidade — decode via JOIN (salário médio por sexo)"),
    code("q = f'''SELECT m.descricao AS municipio, s.descricao AS sexo,\n"
         "               ROUND(AVG(f.salario),2) AS salario_medio, count(*) AS n\n"
         "        FROM {SCHEMA}.fato_caged_mov f\n"
         "        JOIN {SCHEMA}.dim_municipio m ON m.codigo = f.municipio\n"
         "        JOIN {SCHEMA}.dim_sexo s ON s.codigo = f.sexo\n"
         "        GROUP BY 1,2 ORDER BY 1,2'''\n"
         "pl.read_database(q, connection=eng)"),
    md("## ✅ ETL concluído\n"
       "Dados curados disponíveis no Postgres (`schema caged`) para o backend/frontend."),
])

print('OK — notebooks gerados.')
