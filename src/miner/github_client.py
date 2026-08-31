"""
Cliente para consultar la API REST de GitHub usando httpx.

Responsabilidad única: dado un owner/name, obtener la lista de nombres de
archivo dentro de .github/workflows/. No sabe nada de CSV ni de la lógica
de detección de GH-AW (eso vive en detector.py).
"""
from __future__ import annotations

import time
from typing import List, Optional

import httpx

GITHUB_API_URL = "https://api.github.com"
MAX_RETRIES = 6


class GitHubClient:
    def __init__(self, token: str, timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            base_url=GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def list_workflow_files(self, owner: str, name: str) -> Optional[List[str]]:
        """
        Devuelve la lista de nombres de archivo dentro de .github/workflows/.

        Retorna:
          []    si el repositorio existe y es accesible pero no tiene esa carpeta
                (o está vacía) -> confirmado que NO usa GH-AW.
          list  con los nombres de archivo si la carpeta existe.
          None  si no se pudo determinar (repo no encontrado/privado/renombrado,
                error de red persistente, o rate limit que no se resolvió tras
                varios reintentos). None NUNCA debe interpretarse como "no usa
                GH-AW": debe tratarse como pendiente de reintento.
        """
        url = f"/repos/{owner}/{name}/contents/.github/workflows"

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.get(url)
            except httpx.HTTPError:
                time.sleep(min(2 ** attempt, 30))
                continue

            if response.status_code == 200:
                try:
                    items = response.json()
                except ValueError:
                    return None
                if not isinstance(items, list):
                    return []
                return [item.get("name", "") for item in items if item.get("type") == "file"]

            if response.status_code == 404:
                return []  # repo accesible, sin carpeta .github/workflows -> confirmado

            if response.status_code in (403, 429):
                if response.headers.get("X-RateLimit-Remaining") == "0":
                    reset_epoch = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                    wait_seconds = max(reset_epoch - int(time.time()) + 2, 5)
                    time.sleep(wait_seconds)
                    continue
                retry_after = response.headers.get("Retry-After")
                time.sleep(int(retry_after) + 2 if retry_after else 30)
                continue

            # Otros códigos (401, 5xx, etc.): error real, no lo confundimos con "no usa"
            return None

        return None
