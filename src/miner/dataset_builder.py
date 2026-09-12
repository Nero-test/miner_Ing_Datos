"""
Construye las tablas relacionadas del dataset (repositorios, archivos .md
de workflow, archivos .lock compilados, atributos de frontmatter) en
memoria, a partir de contenido ya descargado. Sigue el esquema
entidad-relación acordado:

  repositories (1) ----< (N) workflow_files (1) ----< (N) frontmatter_attributes
                                    |
                                    +----1:1---- workflow_locks

- `raw_frontmatter` y `body_markdown` viven como columnas de workflow_files
  porque son 1:1 con el archivo .md (no vale la pena normalizarlos aparte).
  Por la misma razón, `workflow_locks` guarda el YAML compilado del .lock
  como texto plano en una columna (`raw_content`), no aplanado: es
  contenido generado/compilado, no un frontmatter con estructura variable.
- `frontmatter_attributes` es una tabla EAV (clave-valor aplanada) porque el
  frontmatter de gh-aw no tiene un esquema fijo entre workflows distintos.

Pensado para usarse de forma secuencial (single-threaded) DESPUÉS de
recolectar el contenido de los archivos en paralelo (ver extraction.py), así
la asignación de llaves subrogadas no necesita locks entre hilos.
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from miner.frontmatter_parser import flatten_frontmatter, parse_markdown

REPOSITORIES_COLUMNS = ["repo_id", "owner", "name", "full_name"]
WORKFLOW_FILES_COLUMNS = [
    "file_id",
    "repo_id",
    "file_name",
    "file_path",
    "raw_frontmatter",
    "body_markdown",
    "fetched_at",
]
WORKFLOW_LOCKS_COLUMNS = ["lock_id", "file_id", "file_name", "file_path", "raw_content", "fetched_at"]
FRONTMATTER_ATTRIBUTES_COLUMNS = ["attribute_id", "file_id", "key_path", "value", "value_type"]


class DatasetBuilder:
    """Acumula filas para las 4 tablas del esquema y las expone como DataFrames."""

    def __init__(self) -> None:
        self._repo_ids = itertools.count(1)
        self._file_ids = itertools.count(1)
        self._lock_ids = itertools.count(1)
        self._attribute_ids = itertools.count(1)
        self._repo_id_by_full_name: Dict[str, int] = {}

        self.repositories: List[Dict[str, Any]] = []
        self.workflow_files: List[Dict[str, Any]] = []
        self.workflow_locks: List[Dict[str, Any]] = []
        self.frontmatter_attributes: List[Dict[str, Any]] = []

    @property
    def repo_count(self) -> int:
        return len(self.repositories)

    @property
    def file_count(self) -> int:
        return len(self.workflow_files)

    def _get_or_create_repo_id(self, owner: str, name: str) -> int:
        full_name = f"{owner}/{name}"
        if full_name in self._repo_id_by_full_name:
            return self._repo_id_by_full_name[full_name]
        repo_id = next(self._repo_ids)
        self._repo_id_by_full_name[full_name] = repo_id
        self.repositories.append({"repo_id": repo_id, "owner": owner, "name": name, "full_name": full_name})
        return repo_id

    def add_workflow_file(
        self,
        owner: str,
        name: str,
        file_name: str,
        file_path: str,
        raw_content: str,
        lock_file_name: str,
        lock_file_path: str,
        lock_raw_content: str,
        fetched_at: Optional[str] = None,
    ) -> int:
        """
        Registra un par .md + .lock ya descargado: separa frontmatter y
        body del .md, y agrega las filas correspondientes a las 4 tablas
        (el .lock se agrega tal cual, como una fila 1:1 de
        workflow_locks). Devuelve el file_id asignado (útil para
        trazabilidad en logs de la CLI).
        """
        repo_id = self._get_or_create_repo_id(owner, name)
        file_id = next(self._file_ids)
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()

        metadata, body = parse_markdown(raw_content)

        self.workflow_files.append(
            {
                "file_id": file_id,
                "repo_id": repo_id,
                "file_name": file_name,
                "file_path": file_path,
                "raw_frontmatter": json.dumps(metadata, ensure_ascii=False, default=str),
                "body_markdown": body,
                "fetched_at": fetched_at,
            }
        )

        for attribute in flatten_frontmatter(metadata):
            self.frontmatter_attributes.append(
                {
                    "attribute_id": next(self._attribute_ids),
                    "file_id": file_id,
                    "key_path": attribute.key_path,
                    "value": attribute.value,
                    "value_type": attribute.value_type,
                }
            )

        self.workflow_locks.append(
            {
                "lock_id": next(self._lock_ids),
                "file_id": file_id,
                "file_name": lock_file_name,
                "file_path": lock_file_path,
                "raw_content": lock_raw_content,
                "fetched_at": fetched_at,
            }
        )

        return file_id

    def to_dataframes(self) -> Dict[str, pd.DataFrame]:
        """Devuelve las 4 tablas como DataFrames, con columnas fijas aunque estén vacías."""
        return {
            "repositories": pd.DataFrame(self.repositories, columns=REPOSITORIES_COLUMNS),
            "workflow_files": pd.DataFrame(self.workflow_files, columns=WORKFLOW_FILES_COLUMNS),
            "workflow_locks": pd.DataFrame(self.workflow_locks, columns=WORKFLOW_LOCKS_COLUMNS),
            "frontmatter_attributes": pd.DataFrame(
                self.frontmatter_attributes, columns=FRONTMATTER_ATTRIBUTES_COLUMNS
            ),
        }


# La escritura a .parquet vive en parquet_writer.write_parquet_tables (que además
# valida que estén las 4 tablas del esquema). Este módulo solo arma las tablas.


def build_dataset_from_checkpoint(checkpoint_records: Dict[str, dict]) -> DatasetBuilder:
    """
    Construye un DatasetBuilder a partir de los registros con status "ok" de
    un checkpoint de extracción ya cargado (ver
    extract_checkpoint.load_extract_checkpoint). Los registros con error se
    ignoran acá -- quedan para reintentarse en otra corrida de extracción,
    no deben aparecer en el dataset como si fueran "sin frontmatter".

    Como extraction.py solo escribe status "ok" cuando se pudo descargar
    tanto el .md como su .lock (ver extract_repo), cada registro "ok" aporta
    exactamente una fila a workflow_files y una a workflow_locks -- se
    mantiene la relación 1:1 entre ambas tablas.
    """
    builder = DatasetBuilder()
    for record in checkpoint_records.values():
        if record.get("status") != "ok":
            continue
        builder.add_workflow_file(
            owner=record["owner"],
            name=record["name"],
            file_name=record["file_name"],
            file_path=record["file_path"],
            raw_content=record["raw_content"],
            lock_file_name=record["lock_file_name"],
            lock_file_path=record["lock_file_path"],
            lock_raw_content=record["lock_raw_content"],
            fetched_at=record.get("fetched_at"),
        )
    return builder
