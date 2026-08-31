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

from typing import Iterable, List, Set


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


def uses_gh_aw(filenames: Iterable[str]) -> bool:
    """
    Determina si el conjunto de nombres de archivo dado corresponde a un
    repositorio que usa GH-AW: es decir, si existe al menos un nombre base
    que tenga tanto un archivo .md como su .lock.yml/.lock.yaml correspondiente.
    """
    md_bases: Set[str] = set()
    lock_bases: Set[str] = set()

    for name in filenames:
        classified = _split_base_and_kind(name)
        if classified is None:
            continue
        base, kind = classified
        if kind == "md":
            md_bases.add(base)
        else:
            lock_bases.add(base)

    return bool(md_bases & lock_bases)


def matching_pairs(filenames: Iterable[str]) -> List[str]:
    """
    Devuelve los nombres base (en minúsculas) que tienen tanto .md como
    .lock.yml/.lock.yaml. Útil para depuración/logging, no solo un booleano.
    """
    md_bases: Set[str] = set()
    lock_bases: Set[str] = set()

    for name in filenames:
        classified = _split_base_and_kind(name)
        if classified is None:
            continue
        base, kind = classified
        if kind == "md":
            md_bases.add(base)
        else:
            lock_bases.add(base)

    return sorted(md_bases & lock_bases)
