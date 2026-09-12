from pathlib import Path

from miner.extract_checkpoint import ExtractCheckpointWriter, load_extract_checkpoint
from miner.extraction import checkpoint_key, extract_repo, listing_checkpoint_key


class _FakeClient:
    """Stand-in de GitHubClient: mismo contrato (list_workflow_files / get_file_content)."""

    def __init__(self, filenames=None, contents=None, listing_fails=False):
        self._filenames = filenames or []
        self._contents = contents or {}
        self._listing_fails = listing_fails
        self.fetched_paths = []  # para verificar qué se descargó realmente

    def list_workflow_files(self, owner, name):
        if self._listing_fails:
            return None
        return self._filenames

    def get_file_content(self, owner, name, path):
        self.fetched_paths.append(path)
        return self._contents.get(path)


def test_extract_repo_descarga_el_par_md_y_lock(tmp_path: Path):
    client = _FakeClient(
        filenames=["a.md", "a.lock.yml", "b.md", "other.txt"],
        contents={
            ".github/workflows/a.md": "---\non: push\n---\nBody A",
            ".github/workflows/a.lock.yml": "jobs: {}",
        },
    )
    ckpt = tmp_path / "extract.jsonl"

    with ExtractCheckpointWriter(ckpt) as writer:
        errors = extract_repo(client, writer, "octocat/repo")

    assert errors == 0
    records = load_extract_checkpoint(ckpt)
    key = checkpoint_key("octocat", "repo", "a.md")
    assert key in records
    record = records[key]
    assert record["status"] == "ok"
    assert record["raw_content"] == "---\non: push\n---\nBody A"
    assert record["lock_file_name"] == "a.lock.yml"
    assert record["lock_file_path"] == ".github/workflows/a.lock.yml"
    assert record["lock_raw_content"] == "jobs: {}"
    assert checkpoint_key("octocat", "repo", "b.md") not in records  # b.md no tiene lock, se ignora
    assert client.fetched_paths == [".github/workflows/a.md", ".github/workflows/a.lock.yml"]


def test_extract_repo_omite_archivos_ya_descargados(tmp_path: Path):
    client = _FakeClient(filenames=["a.md", "a.lock.yml"])
    ckpt = tmp_path / "extract.jsonl"
    already = {checkpoint_key("octocat", "repo", "a.md")}

    with ExtractCheckpointWriter(ckpt) as writer:
        errors = extract_repo(client, writer, "octocat/repo", already_done=already)

    assert errors == 0
    assert client.fetched_paths == []  # no debió llamar a get_file_content


def test_extract_repo_registra_error_cuando_no_puede_listar(tmp_path: Path):
    client = _FakeClient(listing_fails=True)
    ckpt = tmp_path / "extract.jsonl"

    with ExtractCheckpointWriter(ckpt) as writer:
        errors = extract_repo(client, writer, "octocat/repo")

    assert errors == 1
    records = load_extract_checkpoint(ckpt)
    key = listing_checkpoint_key("octocat", "repo")
    assert records[key]["status"] == "error"


def test_extract_repo_identificador_invalido_registra_error(tmp_path: Path):
    client = _FakeClient()
    ckpt = tmp_path / "extract.jsonl"

    with ExtractCheckpointWriter(ckpt) as writer:
        errors = extract_repo(client, writer, "esto-no-es-un-repo-valido")

    assert errors == 1


def test_archivo_individual_fallido_no_frena_los_demas_del_repo(tmp_path: Path):
    client = _FakeClient(
        filenames=["a.md", "a.lock.yml", "b.md", "b.lock.yml"],
        contents={
            ".github/workflows/a.md": "---\non: push\n---\nBody A",
            ".github/workflows/a.lock.yml": "jobs: {}",
        },
        # b.md no está en `contents` -> get_file_content devuelve None para ese archivo
    )
    ckpt = tmp_path / "extract.jsonl"

    with ExtractCheckpointWriter(ckpt) as writer:
        errors = extract_repo(client, writer, "octocat/repo")

    assert errors == 1  # solo b.md falla
    records = load_extract_checkpoint(ckpt)
    assert records[checkpoint_key("octocat", "repo", "a.md")]["status"] == "ok"
    assert records[checkpoint_key("octocat", "repo", "b.md")]["status"] == "error"


def test_lock_fallido_marca_el_par_completo_como_error(tmp_path: Path):
    """Si el .md se descarga pero su .lock falla, el PAR se registra como
    error (no un workflow_files sin su workflow_locks correspondiente)."""
    client = _FakeClient(
        filenames=["a.md", "a.lock.yml"],
        contents={".github/workflows/a.md": "---\non: push\n---\nBody A"},
        # a.lock.yml no está en `contents` -> get_file_content devuelve None
    )
    ckpt = tmp_path / "extract.jsonl"

    with ExtractCheckpointWriter(ckpt) as writer:
        errors = extract_repo(client, writer, "octocat/repo")

    assert errors == 1
    records = load_extract_checkpoint(ckpt)
    assert records[checkpoint_key("octocat", "repo", "a.md")]["status"] == "error"
    # se pidió el .md y, como se obtuvo, también se intentó el .lock
    assert client.fetched_paths == [".github/workflows/a.md", ".github/workflows/a.lock.yml"]
