"""
Pool de tokens de GitHub con rotación round-robin, compartido por los
clientes REST y GraphQL. Cada token tiene su propia cuota de rate limit;
el pool salta automáticamente los tokens agotados y espera solo cuando
todos lo están.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

import httpx

MIN_REMAINING_TO_USE = 2  # margen de seguridad antes de considerar "agotado"


class TokenSlot:
    """Un token individual: su cliente httpx y el estado de rate limit conocido."""

    def __init__(self, token: str, index: int, build_client: Callable[[str], httpx.Client]) -> None:
        self.index = index
        self.token = token
        self.client = build_client(token)
        # Se asume cuota llena hasta que una respuesta real diga lo contrario.
        self.remaining = 5000
        self.reset_epoch = 0.0
        self.lock = threading.Lock()

    def update_from_headers(self, headers: httpx.Headers) -> None:
        """Actualiza el estado a partir de encabezados REST (X-RateLimit-*)."""
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        with self.lock:
            if remaining is not None:
                self.remaining = int(remaining)
            if reset is not None:
                self.reset_epoch = float(reset)

    def update_from_rate_limit_field(self, rate_limit: Optional[dict]) -> None:
        """Actualiza el estado a partir del campo `rateLimit` de una respuesta GraphQL."""
        if not rate_limit:
            return
        with self.lock:
            remaining = rate_limit.get("remaining")
            if remaining is not None:
                self.remaining = int(remaining)
            # GraphQL da resetAt en ISO-8601; se usa un margen simple en vez
            # de parsear la fecha exacta, suficiente para no golpear el límite.
            self.reset_epoch = time.time() + 60

    def close(self) -> None:
        self.client.close()


class TokenPool:
    """Reparte trabajo entre varios tokens en round-robin, saltando los agotados."""

    def __init__(self, tokens: List[str], build_client: Callable[[str], httpx.Client]) -> None:
        if not tokens:
            raise ValueError("Se requiere al menos un token de GitHub")
        self._slots = [TokenSlot(t, i, build_client) for i, t in enumerate(tokens)]
        self._counter = 0
        self._counter_lock = threading.Lock()

    @property
    def token_count(self) -> int:
        return len(self._slots)

    def close(self) -> None:
        for slot in self._slots:
            slot.close()

    def __enter__(self) -> "TokenPool":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def next_slot(self) -> TokenSlot:
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

            soonest = min((s.reset_epoch for s in self._slots), default=0.0)
            wait_seconds = max(soonest - time.time() + 2, 5)
            time.sleep(wait_seconds)
