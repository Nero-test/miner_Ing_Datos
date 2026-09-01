"""
Cliente GraphQL para consultar varios repositorios en una sola solicitud
(batching), con rotación de tokens.

Garantía central de este módulo: un lote NUNCA se descarta como bloque
completo por culpa de un solo repositorio problemático. Si un lote falla de
forma persistente (red, HTTP, o error de GraphQL a nivel de query completa),
se subdivide recursivamente por la mitad hasta aislar exactamente qué
repositorio(s) causan el problema. El resto de repositorios del lote
original sí quedan resueltos en la misma corrida. Solo el repositorio
verdaderamente problemático (tras aislarse a un lote de tamaño 1 y agotar
sus propios reintentos) queda marcado como pendiente (None) para la
siguiente corrida, vía checkpoint -- nunca se "pierde" ni se ignora en
silencio.
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Tuple

import httpx

from miner.token_pool import TokenPool

GRAPHQL_URL = "https://api.github.com/graphql"

# (idx_local_en_el_lote, owner, name)
BatchItem = Tuple[int, str, str]


def _build_client(token: str, timeout: float) -> httpx.Client:
    return httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        },
        timeout=timeout,
    )


def _build_query(batch: List[BatchItem]) -> str:
    """Arma una query con un alias por repo (r0, r1, ...) pidiendo su árbol
    de .github/workflows en el branch por defecto (HEAD)."""
    parts = ["query {", "  rateLimit { remaining resetAt cost }"]
    for alias_idx, owner, name in batch:
        parts.append(
            f"""
  r{alias_idx}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
    object(expression: "HEAD:.github/workflows") {{
      ... on Tree {{ entries {{ name type }} }}
    }}
  }}"""
        )
    parts.append("}")
    return "\n".join(parts)


class GitHubGraphQLClient:
    """Cliente GraphQL con batching, rotación de tokens y aislamiento de fallos."""

    def __init__(
        self,
        tokens: List[str],
        timeout: float = 30.0,
        max_retries_per_batch: int = 4,
        retry_backoff_seconds: float = 2.0,
    ) -> None:
        self._pool = TokenPool(tokens, lambda t: _build_client(t, timeout))
        self._max_retries_per_batch = max_retries_per_batch
        self._retry_backoff_seconds = retry_backoff_seconds

    @property
    def token_count(self) -> int:
        return self._pool.token_count

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> "GitHubGraphQLClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def resolve_batch(self, batch: List[BatchItem]) -> Dict[int, Optional[List[str]]]:
        """
        Punto de entrada público. Recibe una lista de (idx, owner, name) y
        devuelve {idx: lista_de_archivos | None}.

          lista  -> repo accesible; son los nombres de archivo en
                    .github/workflows (puede ser vacía si no existe la carpeta).
          None   -> no se pudo determinar (pendiente de reintento en otra
                    corrida). Nunca implica "no usa GH-AW".
        """
        return self._resolve(batch, retries_left=self._max_retries_per_batch)

    def _resolve(self, batch: List[BatchItem], retries_left: int) -> Dict[int, Optional[List[str]]]:
        if not batch:
            return {}

        query = _build_query(batch)
        slot = self._pool.next_slot()

        try:
            response = slot.client.post(GRAPHQL_URL, json={"query": query})
        except httpx.HTTPError:
            return self._retry_or_split(batch, retries_left)

        # Rate limit primario: no cuenta como fallo del lote, se reintenta
        # el mismo lote completo sin consumir presupuesto de reintentos.
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset_epoch = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset_epoch - int(time.time()) + 2, 5)
            time.sleep(wait)
            return self._resolve(batch, retries_left)

        # Rate limit secundario (abuse detection): idem, no es culpa del lote.
        if response.status_code == 403 and "Retry-After" in response.headers:
            wait = int(response.headers["Retry-After"]) + 2
            time.sleep(wait)
            return self._resolve(batch, retries_left)

        if response.status_code != 200:
            return self._retry_or_split(batch, retries_left)

        try:
            payload = response.json()
        except ValueError:
            return self._retry_or_split(batch, retries_left)

        data = payload.get("data")
        if data is None:
            # Fallo a nivel de la query completa (ej. error de sintaxis o
            # timeout del servidor sin datos parciales): aislar, no asumir.
            return self._retry_or_split(batch, retries_left)

        slot.update_from_rate_limit_field(data.get("rateLimit"))

        results: Dict[int, Optional[List[str]]] = {}
        for alias_idx, owner, name in batch:
            repo_data = data.get(f"r{alias_idx}")
            if repo_data is None:
                # Repo no encontrado / renombrado / sin acceso -> no se puede
                # confirmar contenido, queda pendiente (NO se asume "no usa").
                results[alias_idx] = None
                continue
            obj = repo_data.get("object")
            if obj is None:
                results[alias_idx] = []  # confirmado: sin carpeta .github/workflows
                continue
            entries = obj.get("entries", [])
            results[alias_idx] = [e.get("name", "") for e in entries if e.get("type") == "blob"]

        return results

    def _retry_or_split(
        self, batch: List[BatchItem], retries_left: int
    ) -> Dict[int, Optional[List[str]]]:
        """
        Maneja un fallo a nivel del LOTE COMPLETO (no de un repo individual):

          1. Si quedan reintentos, reintenta el mismo lote entero -- la
             falla puede ser transitoria (timeout puntual, error 5xx) y
             afectar a todos los repos por igual, sin que ninguno sea
             realmente el culpable.
          2. Si se agotaron los reintentos y el lote tiene más de un repo,
             se divide a la mitad y cada mitad se resuelve de forma
             independiente (con su propio presupuesto de reintentos). Así,
             un único repo problemático no le cuesta el resultado a los
             demás del lote original.
          3. Si ya es un lote de un solo repo y sigue fallando tras agotar
             sus reintentos, se marca como pendiente (None) y se sigue.
             Nunca se descarta en silencio: queda registrado para
             reintentarse en la siguiente corrida vía checkpoint.
        """
        if retries_left > 0:
            time.sleep(self._retry_backoff_seconds)
            return self._resolve(batch, retries_left - 1)

        if len(batch) == 1:
            idx = batch[0][0]
            return {idx: None}

        mid = len(batch) // 2
        left, right = batch[:mid], batch[mid:]
        results: Dict[int, Optional[List[str]]] = {}
        results.update(self._resolve(left, self._max_retries_per_batch))
        results.update(self._resolve(right, self._max_retries_per_batch))
        return results
