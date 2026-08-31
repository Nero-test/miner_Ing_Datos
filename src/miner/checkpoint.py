"""
Checkpoint incremental de resultados, pensado para corridas de horas sobre
cientos de miles de repositorios.

En vez de mantener todo en memoria y escribir el CSV final recién al
terminar (perdiendo todo el progreso si el proceso se corta), cada resultado
se agrega (append) a un archivo JSONL apenas se resuelve. Si Miner se
interrumpe y se vuelve a ejecutar, retoma desde donde quedó.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Optional


def default_checkpoint_path(output_csv: Path) -> Path:
    """Deriva un nombre de checkpoint a partir del CSV de salida."""
    return output_csv.with_suffix(output_csv.suffix + ".checkpoint.jsonl")


def load_checkpoint(path: Path) -> Dict[int, Optional[bool]]:
    """
    Carga el checkpoint existente, si lo hay.
    Devuelve {idx: True/False/None}. Las entradas None se tratan como
    pendientes y se reintentan en la siguiente corrida.
    """
    results: Dict[int, Optional[bool]] = {}
    if not path.exists():
        return results

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                results[int(record["idx"])] = record.get("uses_gh_aw")
            except (json.JSONDecodeError, KeyError, ValueError):
                continue  # línea corrupta (ej. corte a mitad de escritura): se ignora
    return results


class CheckpointWriter:
    """Escritor thread-safe que agrega resultados al archivo de checkpoint."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        # Abrir en modo append: si el archivo ya existía (reanudación),
        # se conservan los resultados previos.
        self._file = path.open("a", encoding="utf-8")

    def write(self, idx: int, repo: Optional[str], uses_gh_aw: Optional[bool]) -> None:
        record = {"idx": idx, "repo": repo, "uses_gh_aw": uses_gh_aw}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()

    def __enter__(self) -> "CheckpointWriter":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
