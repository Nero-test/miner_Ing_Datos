"""
Lógica pura para determinar si un repositorio usa GitHub Agentic Workflows (GH-AW).

Un repositorio usa GH-AW si, dentro de .github/workflows/, existe al menos un
par de archivos que comparten el mismo nombre base:
    <nombre>.md            (fuente en Markdown)
    <nombre>.lock.yml       (workflow compilado)
    <nombre>.lock.yaml      (variante de extensión también válida)

Esta lógica no depende de red ni de pandas: solo recibe una lista de nombres
de archivo, lo que la hace trivial de probar con pytest.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


def _split_base_and_kind(filename: str) -> tuple[str, str] | None:
    """
    Clasifica un nombre de archivo como fuente markdown ('md') o workflow
    compilado ('lock'), devolviendo (nombre_base_en_minusculas, tipo).
    Devuelve None si el archivo no es relevante para GH-AW.
    """
    lower = filename.lower()
    if lower.endswith(".lock.yml"):
        return lower[: -len(".lock.yml")], "lock"
    if lower.endswith(".lock.yaml"):
        return lower[: -len(".lock.yaml")], "lock"
    if lower.endswith(".md"):
        return lower[: -len(".md")], "md"
    return None


def _classify_bases(filenames: Iterable[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Recorre los nombres de archivo una sola vez y devuelve
    (md_by_base, lock_by_base): para cada nombre base normalizado (en
    minúsculas), el nombre de archivo ORIGINAL de su .md y de su
    .lock.yml/.lock.yaml. Si hay varios archivos con el mismo nombre base
    (ej. distinta capitalización), se conserva el primero en el orden en
    que aparece `filenames`.

    Es la pieza compartida por uses_gh_aw / matching_pairs /
    matching_file_pairs: la lógica de emparejar .md con .lock vive en un
    solo lugar.
    """
    md_by_base: Dict[str, str] = {}
    lock_by_base: Dict[str, str] = {}

    for name in filenames:
        classified = _split_base_and_kind(name)
        if classified is None:
            continue
        base, kind = classified
        if kind == "md":
            md_by_base.setdefault(base, name)
        else:
            lock_by_base.setdefault(base, name)

    return md_by_base, lock_by_base


def uses_gh_aw(filenames: Iterable[str]) -> bool:
    """
    Determina si el conjunto de nombres de archivo dado corresponde a un
    repositorio que usa GH-AW: es decir, si existe al menos un nombre base
    que tenga tanto un archivo .md como su .lock.yml/.lock.yaml correspondiente.
    """
    md_by_base, lock_by_base = _classify_bases(filenames)
    return bool(md_by_base.keys() & lock_by_base.keys())


def matching_pairs(filenames: Iterable[str]) -> List[str]:
    """
    Devuelve los nombres base (en minúsculas) que tienen tanto .md como
    .lock.yml/.lock.yaml. Útil para depuración/logging, no solo un booleano.
    """
    md_by_base, lock_by_base = _classify_bases(filenames)
    return sorted(md_by_base.keys() & lock_by_base.keys())


def matching_file_pairs(filenames: Iterable[str]) -> List[Tuple[str, str]]:
    """
    Como matching_pairs, pero devuelve pares (nombre_md, nombre_lock) con
    los nombres de archivo ORIGINALES (preservando mayúsculas/minúsculas),
    ordenados por nombre base para un resultado determinista. Necesario
    para saber exactamente qué archivo .md descargar de GitHub (las rutas
    son sensibles a mayúsculas).
    """
    md_by_base, lock_by_base = _classify_bases(filenames)
    return [(md_by_base[base], lock_by_base[base]) for base in sorted(md_by_base.keys() & lock_by_base.keys())]
