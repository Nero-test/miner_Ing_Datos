from pathlib import Path

import pandas as pd
import pytest

from miner.dataset_builder import DatasetBuilder
from miner.parquet_writer import write_parquet_tables


def _sample_tables():
    builder = DatasetBuilder()
    builder.add_workflow_file(
        owner="octocat",
        name="hello-world",
        file_name="daily-report.md",
        file_path=".github/workflows/daily-report.md",
        raw_content="---\non: push\npermissions:\n  contents: read\n---\nBody",
        lock_file_name="daily-report.lock.yml",
        lock_file_path=".github/workflows/daily-report.lock.yml",
        lock_raw_content="jobs: {}",
    )
    return builder.to_dataframes()


def test_write_parquet_tables_crea_los_4_archivos(tmp_path: Path):
    tables = _sample_tables()
    output_dir = tmp_path / "dataset"

    written = write_parquet_tables(tables, output_dir)

    assert set(written.keys()) == {"repositories", "workflow_files", "workflow_locks", "frontmatter_attributes"}
    for path in written.values():
        assert path.exists()
        assert path.suffix == ".parquet"


def test_directorio_de_salida_se_crea_si_no_existe(tmp_path: Path):
    tables = _sample_tables()
    output_dir = tmp_path / "no_existe_todavia" / "dataset"

    write_parquet_tables(tables, output_dir)

    assert output_dir.exists()


def test_datos_sobreviven_el_roundtrip(tmp_path: Path):
    tables = _sample_tables()
    written = write_parquet_tables(tables, tmp_path / "dataset")

    repos = pd.read_parquet(written["repositories"])
    files = pd.read_parquet(written["workflow_files"])
    locks = pd.read_parquet(written["workflow_locks"])
    attrs = pd.read_parquet(written["frontmatter_attributes"])

    assert repos.iloc[0]["full_name"] == "octocat/hello-world"
    assert files.iloc[0]["file_name"] == "daily-report.md"
    assert locks.iloc[0]["file_name"] == "daily-report.lock.yml"
    assert locks.iloc[0]["file_id"] == files.iloc[0]["file_id"]
    assert "permissions.contents" in set(attrs["key_path"])


def test_falta_tabla_requerida_lanza_error(tmp_path: Path):
    tables = _sample_tables()
    del tables["frontmatter_attributes"]

    with pytest.raises(ValueError, match="frontmatter_attributes"):
        write_parquet_tables(tables, tmp_path / "dataset")


def test_falta_tabla_workflow_locks_lanza_error(tmp_path: Path):
    tables = _sample_tables()
    del tables["workflow_locks"]

    with pytest.raises(ValueError, match="workflow_locks"):
        write_parquet_tables(tables, tmp_path / "dataset")


def test_tabla_vacia_se_escribe_igual_con_columnas_correctas(tmp_path: Path):
    empty_tables = DatasetBuilder().to_dataframes()
    written = write_parquet_tables(empty_tables, tmp_path / "dataset")

    repos = pd.read_parquet(written["repositories"])
    assert len(repos) == 0
    assert list(repos.columns) == ["repo_id", "owner", "name", "full_name"]
