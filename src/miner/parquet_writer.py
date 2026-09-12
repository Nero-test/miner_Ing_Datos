"""
Escritura de las tablas del dataset a archivos Apache Parquet.

Responsabilidad única: dado un dict de DataFrames (ver
dataset_builder.DatasetBuilder.to_dataframes), escribirlos a disco como
.parquet. No sabe nada de GitHub, checkpoints, ni de la CLI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

REQUIRED_TABLES = ("repositories", "workflow_files", "workflow_locks", "frontmatter_attributes")


def write_parquet_tables(tables: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, Path]:
    """
    Escribe cada tabla como <output_dir>/<nombre_tabla>.parquet.

    Lanza ValueError si falta alguna de las tablas requeridas por el
    esquema (repositories, workflow_files, workflow_locks,
    frontmatter_attributes), para detectar temprano un DatasetBuilder mal
    construido en vez de generar en silencio un dataset incompleto que
    solo se nota al publicarlo.

    Devuelve {nombre_tabla: ruta_escrita} para las tablas efectivamente
    escritas (incluye cualquier tabla extra que venga en `tables` además
    de las requeridas).
    """
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise ValueError(f"Faltan tablas requeridas para el dataset: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)

    written: Dict[str, Path] = {}
    for table_name, df in tables.items():
        path = output_dir / f"{table_name}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        written[table_name] = path
    return written
