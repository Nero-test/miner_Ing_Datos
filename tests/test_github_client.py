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
