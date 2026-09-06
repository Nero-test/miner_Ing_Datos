"""
Orquesta la extracción de contenido de GH-AW desde GitHub: para cada
repositorio, encuentra los archivos .md que tienen su .lock.yml/.lock.yaml
correspondiente (ver detector.matching_file_pairs), descarga su contenido, y
registra cada resultado en un checkpoint (ver extract_checkpoint.py) para
poder reanudar sin volver a descargar nada ya obtenido.

Responsabilidad única: obtener el contenido crudo de forma resiliente, sin
perder de vista los archivos que fallan. El parseo de frontmatter/body NO
ocurre acá -- eso vive en dataset_builder.py, para poder ajustar el parser
sin tener que volver a golpear la API de GitHub.
"""
from __future__ import annotations

from typing import Optional, Set

from miner.detector import matching_file_pairs
from miner.extract_checkpoint import ExtractCheckpointWriter
from miner.github_client import GitHubClient
from miner.models import RepoIdentifier

WORKFLOWS_DIR = ".github/workflows"


def checkpoint_key(owner: str, name: str, file_name: str) -> str:
    return f"{owner}/{name}:{file_name}"


def listing_checkpoint_key(owner: str, name: str) -> str:
    """Clave sintética para registrar que no se pudo listar .github/workflows/ del repo."""
    return f"{owner}/{name}:__listing__"


def extract_repo(
    client: GitHubClient,
    writer: ExtractCheckpointWriter,
    raw_value: str,
    already_done: Optional[Set[str]] = None,
) -> int:
    """
    Procesa un repositorio: lista .github/workflows/, encuentra los pares
    .md + .lock confirmados, y descarga el contenido de cada .md que no
    esté ya en `already_done` (claves de una corrida anterior con status
    "ok"). Cada resultado -- éxito o error -- se agrega al checkpoint.

    Un archivo individual que falla NO frena el resto del repo: se
    registra su error y se continúa con los demás (mismo principio de
    aislamiento de fallos que en el cliente GraphQL).

    Devuelve la cantidad de errores nuevos registrados en esta llamada
    (identificador inválido, listado fallido, o descarga fallida).
    """
    already_done = already_done or set()

    identifier = RepoIdentifier.from_raw(raw_value)
    if identifier is None:
        writer.write({"key": f"__invalid__:{raw_value}", "status": "error", "raw_value": raw_value})
        return 1

    filenames = client.list_workflow_files(identifier.owner, identifier.name)
    if filenames is None:
        # No se pudo determinar el listado (repo no encontrado, renombrado,
        # rate limit no resuelto, etc.) -- se registra para poder detectar
        # y reintentar el repo completo en otra corrida, en vez de omitirlo
        # en silencio.
        writer.write(
            {
                "key": listing_checkpoint_key(identifier.owner, identifier.name),
                "status": "error",
                "owner": identifier.owner,
                "name": identifier.name,
            }
        )
        return 1

    errors = 0
    for md_name, lock_name in matching_file_pairs(filenames):
        key = checkpoint_key(identifier.owner, identifier.name, md_name)
        if key in already_done:
            continue  # ya descargado con éxito en una corrida anterior

        path = f"{WORKFLOWS_DIR}/{md_name}"
        content = client.get_file_content(identifier.owner, identifier.name, path)

        if content is None:
            writer.write({"key": key, "status": "error", "owner": identifier.owner, "name": identifier.name})
            errors += 1
        else:
            writer.write(
                {
                    "key": key,
                    "status": "ok",
                    "owner": identifier.owner,
                    "name": identifier.name,
                    "file_name": md_name,
                    "file_path": path,
                    "lock_file_name": lock_name,
                    "raw_content": content,
                }
            )

    return errors
