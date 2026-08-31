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

import threading
import time
from typing import List, Optional

import httpx

GITHUB_API_URL = "https://api.github.com"
MAX_RETRIES = 6
MIN_REMAINING_TO_USE = 2  # margen de seguridad antes de considerar "agotado"


class _TokenSlot:
    """Un token individual: su cliente httpx y el estado de rate limit conocido."""

    def __init__(self, token: str, index: int, timeout: float) -> None:
        self.index = index
        self.client = httpx.Client(
            base_url=GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
        )
        # Se asume cuota llena hasta que una respuesta real diga lo contrario.
        self.remaining = 5000
        self.reset_epoch = 0.0
        self.lock = threading.Lock()

    def update_from_headers(self, headers: httpx.Headers) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        with self.lock:
            if remaining is not None:
                self.remaining = int(remaining)
            if reset is not None:
                self.reset_epoch = float(reset)

    def close(self) -> None:
        self.client.close()


class GitHubClient:
    """
    Cliente con rotación de tokens (round-robin). Si todos los tokens están
    agotados, espera hasta que el que resetea más pronto vuelva a tener
    cuota, en vez de fallar. Es seguro de usar desde múltiples hilos.
    """

    def __init__(self, tokens: List[str], timeout: float = 15.0) -> None:
        if not tokens:
            raise ValueError("Se requiere al menos un token de GitHub")
        self._slots = [_TokenSlot(t, i, timeout) for i, t in enumerate(tokens)]
        self._counter = 0
        self._counter_lock = threading.Lock()

    @property
    def token_count(self) -> int:
        return len(self._slots)

    def close(self) -> None:
        for slot in self._slots:
            slot.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _next_slot(self) -> _TokenSlot:
        """Devuelve el próximo token con cuota disponible (round-robin)."""
        while True:
            with self._counter_lock:
                start = self._counter
                self._counter += 1

            n = len(self._slots)
            for offset in range(n):
                slot = self._slots[(start + offset) % n]
                with slot.lock:
                    if slot.remaining > MIN_REMAINING_TO_USE:
                        return slot

            # Todos los tokens sin cuota: esperar al que resetea antes.
            soonest = min((s.reset_epoch for s in self._slots), default=0.0)
            wait_seconds = max(soonest - time.time() + 2, 5)
            time.sleep(wait_seconds)

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
            slot = self._next_slot()
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
                # Si fue rate limit primario, update_from_headers ya dejó
                # remaining <= 0 y el próximo _next_slot() saltará este token.
                # Si el token todavía muestra cuota, probablemente sea un
                # límite secundario (abuse detection): esperar Retry-After.
                if slot.remaining > MIN_REMAINING_TO_USE:
                    retry_after = response.headers.get("Retry-After")
                    time.sleep(int(retry_after) + 2 if retry_after else 10)
                continue

            return None  # error real (401, 5xx, etc.), no confundir con "no usa"

        return None
