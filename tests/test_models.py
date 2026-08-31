import pytest

from miner.models import GHAWResult, RepoIdentifier


def test_formato_owner_repo():
    identifier = RepoIdentifier.from_raw("octocat/hello-world")
    assert identifier is not None
    assert identifier.full_name == "octocat/hello-world"


def test_formato_https():
    identifier = RepoIdentifier.from_raw("https://github.com/octocat/hello-world")
    assert identifier.full_name == "octocat/hello-world"


def test_formato_https_con_git_y_segmentos_extra():
    identifier = RepoIdentifier.from_raw("https://github.com/octocat/hello-world.git/tree/main")
    assert identifier.full_name == "octocat/hello-world"


def test_formato_ssh():
    identifier = RepoIdentifier.from_raw("git@github.com:octocat/hello-world.git")
    assert identifier.full_name == "octocat/hello-world"


def test_valor_invalido_devuelve_none():
    assert RepoIdentifier.from_raw("no-es-un-repo-valido") is None


def test_valor_no_string_devuelve_none():
    assert RepoIdentifier.from_raw(None) is None  # type: ignore[arg-type]


def test_owner_o_name_vacio_es_invalido():
    with pytest.raises(ValueError):
        RepoIdentifier(owner="", name="hello-world")


def test_ghaw_result_permite_none_para_pendientes():
    result = GHAWResult(repo="octocat/hello-world", uses_gh_aw=None)
    assert result.uses_gh_aw is None
