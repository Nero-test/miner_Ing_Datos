"""
Lectura y escritura de archivos CSV. Responsabilidad única: entrada/salida
tabular, sin lógica de negocio ni llamadas de red.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

# Nombres de columna candidatos, en orden de preferencia, para detectar
# automáticamente cuál identifica al repositorio en el CSV de entrada.
CANDIDATE_COLUMNS = ["full_name", "name", "repo", "repository", "url"]


def read_candidates(path: Path) -> pd.DataFrame:
    """Lee el CSV de repositorios candidatos (detecta gzip por firma de bytes)."""
    compression: Optional[str] = None
    with open(path, "rb") as f:
        if f.read(2) == b"\x1f\x8b":
            compression = "gzip"
    return pd.read_csv(path, compression=compression)


def detect_repo_column(df: pd.DataFrame) -> str:
    """Detecta la columna que identifica al repositorio."""
    for candidate in CANDIDATE_COLUMNS:
        if candidate in df.columns:
            return candidate
    return df.columns[0]


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)
