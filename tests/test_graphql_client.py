import re

from miner.graphql_client import GitHubGraphQLClient


class FakeResponse:
    """Respuesta HTTP falsa, con la misma interfaz mínima que usa el cliente."""

    def __init__(self, status_code: int, json_body: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.headers = headers or {}

    def json(self) -> dict:
        return self._json_body


def _make_fake_post(poison_repo: str):
    """
    Simula el servidor de GitHub: si el lote incluye `poison_repo`, la
    solicitud completa falla (500). Si no, responde 200 con datos válidos
    para cada alias presente en la query.
    """
    calls = {"n": 0}

    def fake_post(url, json):
        calls["n"] += 1
        query = json["query"]
        if poison_repo in query:
            return FakeResponse(500)

        aliases = re.findall(r'r(\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query)
        data = {"rateLimit": {"remaining": 4999, "resetAt": "2099-01-01T00:00:00Z", "cost": 1}}
        for alias_idx, _owner, _name in aliases:
            data[f"r{alias_idx}"] = {"object": {"entries": []}}
        return FakeResponse(200, {"data": data})

    return fake_post, calls


def _patch_all_slots(client: GitHubGraphQLClient, fake_post, monkeypatch) -> None:
    for slot in client._pool._slots:  # acceso interno, aceptable en tests de caja blanca
        monkeypatch.setattr(slot.client, "post", fake_post)


def test_lote_sano_se_resuelve_en_una_sola_llamada(monkeypatch):
    client = GitHubGraphQLClient(["tok1"], max_retries_per_batch=1, retry_backoff_seconds=0.0)
    try:
        fake_post, calls = _make_fake_post(poison_repo="nadie-usa-este-nombre")
        _patch_all_slots(client, fake_post, monkeypatch)

        batch = [(0, "octocat", "repo-a"), (1, "octocat", "repo-b")]
        results = client.resolve_batch(batch)

        assert results == {0: [], 1: []}
        assert calls["n"] == 1  # no debería necesitar reintentos ni dividir el lote
    finally:
        client.close()


def test_repo_problematico_no_arrastra_al_resto_del_lote(monkeypatch):
    """
    Este es el caso central: un lote de 4 repos donde uno (poison-repo) hace
    fallar la solicitud completa repetidamente. El cliente debe subdividir
    el lote y resolver los 3 repos sanos igual, dejando SOLO el problemático
    marcado como pendiente (None) -- nunca debe perderse el bloque entero.
    """
    client = GitHubGraphQLClient(["tok1"], max_retries_per_batch=1, retry_backoff_seconds=0.0)
    try:
        fake_post, _ = _make_fake_post(poison_repo="poison-repo")
        _patch_all_slots(client, fake_post, monkeypatch)

        batch = [
            (0, "octocat", "repo-a"),
            (1, "octocat", "poison-repo"),
            (2, "octocat", "repo-c"),
            (3, "octocat", "repo-d"),
        ]
        results = client.resolve_batch(batch)

        assert results[0] == []
        assert results[2] == []
        assert results[3] == []
        assert results[1] is None  # el problemático queda pendiente, no se pierde
    finally:
        client.close()


def test_lote_de_un_repo_problematico_termina_en_none_sin_colgarse(monkeypatch):
    client = GitHubGraphQLClient(["tok1"], max_retries_per_batch=1, retry_backoff_seconds=0.0)
    try:
        fake_post, _ = _make_fake_post(poison_repo="poison-repo")
        _patch_all_slots(client, fake_post, monkeypatch)

        results = client.resolve_batch([(0, "octocat", "poison-repo")])
        assert results == {0: None}
    finally:
        client.close()
