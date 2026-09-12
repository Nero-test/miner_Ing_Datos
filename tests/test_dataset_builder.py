import json

from miner.dataset_builder import DatasetBuilder, build_dataset_from_checkpoint

SAMPLE_MD = """---
on:
  schedule:
    - cron: "0 9 * * 1"
permissions:
  contents: read
---
# Daily report

Genera un resumen diario.
"""

SAMPLE_LOCK = "name: Daily report\non:\n  schedule:\n    - cron: \"0 9 * * 1\"\njobs: {}\n"


def _add_sample_file(builder: DatasetBuilder, **overrides) -> int:
    kwargs = dict(
        owner="octocat",
        name="hello-world",
        file_name="daily-report.md",
        file_path=".github/workflows/daily-report.md",
        raw_content=SAMPLE_MD,
        lock_file_name="daily-report.lock.yml",
        lock_file_path=".github/workflows/daily-report.lock.yml",
        lock_raw_content=SAMPLE_LOCK,
    )
    kwargs.update(overrides)
    return builder.add_workflow_file(**kwargs)


def test_add_workflow_file_crea_filas_relacionadas_correctamente():
    builder = DatasetBuilder()
    file_id = _add_sample_file(builder)

    assert builder.repo_count == 1
    assert builder.file_count == 1
    assert builder.repositories[0] == {
        "repo_id": 1,
        "owner": "octocat",
        "name": "hello-world",
        "full_name": "octocat/hello-world",
    }

    workflow_file = builder.workflow_files[0]
    assert workflow_file["file_id"] == file_id
    assert workflow_file["repo_id"] == 1
    assert workflow_file["file_name"] == "daily-report.md"
    assert "Genera un resumen diario" in workflow_file["body_markdown"]

    # el frontmatter crudo debe ser JSON válido y con la clave "on" preservada como string
    parsed_frontmatter = json.loads(workflow_file["raw_frontmatter"])
    assert parsed_frontmatter["on"] == {"schedule": [{"cron": "0 9 * * 1"}]}

    key_paths = {a["key_path"] for a in builder.frontmatter_attributes}
    assert "on.schedule[0].cron" in key_paths
    assert "permissions.contents" in key_paths
    assert all(a["file_id"] == file_id for a in builder.frontmatter_attributes)

    # relación 1:1 con workflow_locks
    assert len(builder.workflow_locks) == 1
    lock = builder.workflow_locks[0]
    assert lock["file_id"] == file_id
    assert lock["file_name"] == "daily-report.lock.yml"
    assert lock["raw_content"] == SAMPLE_LOCK


def test_mismo_repo_no_se_duplica_entre_archivos():
    builder = DatasetBuilder()
    _add_sample_file(
        builder, file_name="a.md", file_path=".github/workflows/a.md",
        raw_content="---\non: push\n---\nBody A",
        lock_file_name="a.lock.yml", lock_file_path=".github/workflows/a.lock.yml",
        lock_raw_content="jobs: {}",
    )
    _add_sample_file(
        builder, file_name="b.md", file_path=".github/workflows/b.md",
        raw_content="---\non: push\n---\nBody B",
        lock_file_name="b.lock.yml", lock_file_path=".github/workflows/b.lock.yml",
        lock_raw_content="jobs: {}",
    )

    assert builder.repo_count == 1  # mismo repo, no se duplica
    assert builder.file_count == 2
    assert len(builder.workflow_locks) == 2
    assert builder.workflow_files[0]["repo_id"] == builder.workflow_files[1]["repo_id"]


def test_to_dataframes_columnas_correctas_incluso_vacio():
    builder = DatasetBuilder()
    frames = builder.to_dataframes()

    assert set(frames.keys()) == {"repositories", "workflow_files", "workflow_locks", "frontmatter_attributes"}
    assert list(frames["repositories"].columns) == ["repo_id", "owner", "name", "full_name"]
    assert list(frames["workflow_files"].columns) == [
        "file_id", "repo_id", "file_name", "file_path",
        "raw_frontmatter", "body_markdown", "fetched_at",
    ]
    assert list(frames["workflow_locks"].columns) == [
        "lock_id", "file_id", "file_name", "file_path", "raw_content", "fetched_at",
    ]
    assert list(frames["frontmatter_attributes"].columns) == [
        "attribute_id", "file_id", "key_path", "value", "value_type",
    ]
    for frame in frames.values():
        assert len(frame) == 0


def test_frontmatter_con_valor_none_no_rompe_el_json():
    builder = DatasetBuilder()
    _add_sample_file(
        builder, file_name="a.md", file_path=".github/workflows/a.md",
        raw_content="---\ndescription:\n---\nBody",
    )
    raw = builder.workflow_files[0]["raw_frontmatter"]
    parsed = json.loads(raw)  # no debe lanzar excepción
    assert parsed["description"] is None


def test_build_dataset_from_checkpoint_usa_solo_registros_ok():
    records = {
        "octocat/repo:a.md": {
            "key": "octocat/repo:a.md",
            "status": "ok",
            "owner": "octocat",
            "name": "repo",
            "file_name": "a.md",
            "file_path": ".github/workflows/a.md",
            "raw_content": "---\non: push\n---\nBody A",
            "lock_file_name": "a.lock.yml",
            "lock_file_path": ".github/workflows/a.lock.yml",
            "lock_raw_content": "jobs: {}",
        },
        "octocat/repo:b.md": {
            "key": "octocat/repo:b.md",
            "status": "error",
            "owner": "octocat",
            "name": "repo",
        },
    }

    builder = build_dataset_from_checkpoint(records)
    assert builder.file_count == 1
    assert builder.workflow_files[0]["file_name"] == "a.md"
    assert len(builder.workflow_locks) == 1
    assert builder.workflow_locks[0]["file_name"] == "a.lock.yml"
    assert builder.workflow_locks[0]["file_id"] == builder.workflow_files[0]["file_id"]
