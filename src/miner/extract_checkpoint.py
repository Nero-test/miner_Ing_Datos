"""
Checkpoint para el proceso de extracción de contenido (Tarea 3): guarda,
por cada archivo .md ya descargado, su contenido crudo, para poder reanudar
sin volver a descargarlo. El parseo de frontmatter/body se hace al momento
de construir el dataset final (no aquí), así que un futuro ajuste al
parser no requiere volver a descargar nada.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict


def default_extract_checkpoint_path(output_dir: Path) -> Path:
    return output_dir / "extract.checkpoint.jsonl"


def load_extract_checkpoint(path: Path) -> Dict[str, Dict[str, Any]]:
    """Carga el checkpoint existente: {key: record}. Ver ExtractCheckpointWriter.write."""
    records: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return records

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records[record["key"]] = record
            except (json.JSONDecodeError, KeyError):
                continue  # línea corrupta (ej. corte a mitad de escritura): se ignora
    return records


class ExtractCheckpointWriter:
    """Escritor thread-safe que agrega registros de extracción al checkpoint."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = path.open("a", encoding="utf-8")

    def write(self, record: Dict[str, Any]) -> None:
        """
        record debe incluir al menos {"key": str, "status": "ok"|"error", ...}.
        Solo los registros con status == "ok" se consideran resueltos; el
        resto se reintenta en la siguiente corrida.
        """
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()

    def __enter__(self) -> "ExtractCheckpointWriter":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
