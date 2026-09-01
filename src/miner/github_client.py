"""
Cliente para consultar la API REST de GitHub usando httpx.

Soporta rotar entre uno o varios tokens: cada token tiene su propia cuota de
rate limit (5.000 req/hora autenticado), así que usar N tokens multiplica por
N la cantidad de repositorios que se pueden consultar por hora sin esperar.

Responsabilidad única: dado un owner/name, obtener la lista de nombres de
archivo dentro de .github/workflows. No sabe nada de CSV ni de la lógica de
detección de GH-AW (eso vive en detector.py).
"""
from __future__ import annotations

import time
from typing import List, Optional

import httpx

from miner.token_pool import TokenPool

GITHUB_API_URL = "https://api.github.com"
MAX_RETRIES = 6


def _build_client(token: str, timeout: float) -> httpx.Client:
    return httpx.Client(
        base_url=GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=timeout,
    )


class GitHubClient:
    """
    Cliente REST con rotación de tokens (round-robin). Es seguro de usar
    desde múltiples hilos.
    """

    def __init__(self, tokens: List[str], timeout: float = 15.0) -> None:
        self._pool = TokenPool(tokens, lambda t: _build_client(t, timeout))

    @property
    def token_count(self) -> int:
        return self._pool.token_count

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def list_workflow_files(self, owner: str, name: str) -> Optional[List[str]]:
        """
        Devuelve la lista de nombres de archivo dentro de .github/workflows/.

        Retorna:
          []    repositorio accesible pero sin esa carpeta -> confirmado que
                NO usa GH-AW.
          list  con los nombres de archivo si la carpeta existe.
          None  no se pudo determinar (repo no encontrado/privado/renombrado,
                error de red persistente, o rate limit que no se resolvió).
                None NUNCA debe interpretarse como "no usa GH-AW": debe
                tratarse como pendiente de reintento.
        """
        url = f"/repos/{owner}/{name}/contents/.github/workflows"

        for attempt in range(MAX_RETRIES):
            slot = self._pool.next_slot()
            try:
                response = slot.client.get(url)
            except httpx.HTTPError:
                time.sleep(min(2 ** attempt, 30))
                continue

            slot.update_from_headers(response.headers)

            if response.status_code == 200:
                try:
                    items = response.json()
                except ValueError:
                    return None
                if not isinstance(items, list):
                    return []
                return [item.get("name", "") for item in items if item.get("type") == "file"]

            if response.status_code == 404:
                return []

            if response.status_code in (403, 429):
                if slot.remaining > 2:
                    retry_after = response.headers.get("Retry-After")
                    time.sleep(int(retry_after) + 2 if retry_after else 10)
                continue

            return None  # error real (401, 5xx, etc.), no confundir con "no usa"

        return None
