from miner.github_client import GitHubClient


def test_pool_requiere_al_menos_un_token():
    try:
        GitHubClient([])
        assert False, "debería haber lanzado ValueError"
    except ValueError:
        pass


def test_rotacion_round_robin_entre_tokens_con_cuota():
    client = GitHubClient(["tok1", "tok2", "tok3"])
    try:
        indices = [client._pool.next_slot().index for _ in range(6)]
        assert indices == [0, 1, 2, 0, 1, 2]
    finally:
        client.close()


def test_rotacion_salta_tokens_sin_cuota():
    client = GitHubClient(["tok1", "tok2", "tok3"])
    try:
        client._pool._slots[0].remaining = 0
        client._pool._slots[1].remaining = 0
        slot = client._pool.next_slot()
        assert slot.index == 2
    finally:
        client.close()


def test_token_count_refleja_cantidad_cargada():
    client = GitHubClient(["tok1", "tok2", "tok3", "tok4", "tok5"])
    try:
        assert client.token_count == 5
    finally:
        client.close()


class _FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


def test_get_file_content_devuelve_texto_plano(monkeypatch):
    raw_text = "---\non: push\n---\nBody"

    def fake_get(url, headers=None):
        assert headers == {"Accept": "application/vnd.github.raw"}
        return _FakeResponse(200, text=raw_text)

    client = GitHubClient(["tok1"])
    try:
        monkeypatch.setattr(client._pool._slots[0].client, "get", fake_get)
        content = client.get_file_content("octocat", "hello-world", ".github/workflows/a.md")
        assert content == raw_text
    finally:
        client.close()


def test_get_file_content_404_devuelve_none(monkeypatch):
    def fake_get(url, headers=None):
        return _FakeResponse(404)

    client = GitHubClient(["tok1"])
    try:
        monkeypatch.setattr(client._pool._slots[0].client, "get", fake_get)
        content = client.get_file_content("octocat", "hello-world", ".github/workflows/no-existe.md")
        assert content is None
    finally:
        client.close()
