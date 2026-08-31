"""
Modelos de datos de Miner, usando Pydantic para representación y validación.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator

# Patrones para reconocer distintas formas en que puede venir un repositorio
# en el CSV de entrada: URL https, URL SSH, o "owner/repo" ya limpio.
_SSH_PATTERN = re.compile(r"^git@github\.com:([^/]+)/([^/]+?)(\.git)?$")
_HTTPS_PATTERN = re.compile(r"github\.com/([^/]+)/([^/]+)")


class RepoIdentifier(BaseModel):
    """Identificador validado de un repositorio de GitHub: owner + name."""

    owner: str
    name: str

    @field_validator("owner", "name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("owner/name no puede estar vacío")
        return value

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @classmethod
    def from_raw(cls, raw_value: str) -> Optional["RepoIdentifier"]:
        """
        Intenta construir un RepoIdentifier a partir de un valor de celda del
        CSV de entrada. Soporta:
          - "owner/repo"
          - "https://github.com/owner/repo(.git)?(/...)?(?query)?(#fragment)?"
          - "git@github.com:owner/repo.git"
        Devuelve None si no se pudo determinar con confianza, en vez de
        adivinar un valor incorrecto.
        """
        if not isinstance(raw_value, str):
            return None

        cleaned = raw_value.strip()
        if not cleaned:
            return None

        # quitar query string / fragment y barra final
        cleaned = cleaned.split("?")[0].split("#")[0].rstrip("/")

        ssh_match = _SSH_PATTERN.match(cleaned)
        if ssh_match:
            owner, name = ssh_match.group(1), ssh_match.group(2)
            return cls(owner=owner, name=name)

        https_match = _HTTPS_PATTERN.search(cleaned)
        if https_match:
            owner = https_match.group(1)
            name = https_match.group(2)
            if name.endswith(".git"):
                name = name[: -len(".git")]
            return cls(owner=owner, name=name)

        parts = [p for p in cleaned.split("/") if p]
        if len(parts) == 2:
            owner, name = parts
            if name.endswith(".git"):
                name = name[: -len(".git")]
            try:
                return cls(owner=owner, name=name)
            except ValueError:
                return None

        return None


class GHAWResult(BaseModel):
    """Resultado de evaluar un repositorio."""

    repo: str
    # True  -> confirmado que usa GH-AW
    # False -> confirmado que NO usa GH-AW
    # None  -> no se pudo determinar (repo no encontrado, error, rate limit persistente)
    uses_gh_aw: Optional[bool] = None
