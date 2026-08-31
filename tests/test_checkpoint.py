from pathlib import Path

from miner.checkpoint import CheckpointWriter, default_checkpoint_path, load_checkpoint


def test_default_checkpoint_path_deriva_del_output():
    path = default_checkpoint_path(Path("salida.csv"))
    assert path.name == "salida.csv.checkpoint.jsonl"


def test_load_checkpoint_archivo_inexistente_devuelve_vacio(tmp_path: Path):
    ckpt = tmp_path / "no_existe.jsonl"
    assert load_checkpoint(ckpt) == {}


def test_write_y_load_roundtrip(tmp_path: Path):
    ckpt = tmp_path / "progreso.jsonl"
    with CheckpointWriter(ckpt) as writer:
        writer.write(0, "octocat/hello-world", True)
        writer.write(1, "octocat/otro-repo", False)
        writer.write(2, None, None)

    results = load_checkpoint(ckpt)
    assert results == {0: True, 1: False, 2: None}


def test_reanudacion_conserva_lo_ya_escrito(tmp_path: Path):
    ckpt = tmp_path / "progreso.jsonl"

    with CheckpointWriter(ckpt) as writer:
        writer.write(0, "octocat/hello-world", True)

    # Simula una segunda corrida que reabre el mismo archivo en modo append.
    with CheckpointWriter(ckpt) as writer:
        writer.write(1, "octocat/otro-repo", False)

    results = load_checkpoint(ckpt)
    assert results == {0: True, 1: False}


def test_linea_corrupta_se_ignora_sin_romper_la_carga(tmp_path: Path):
    ckpt = tmp_path / "progreso.jsonl"
    ckpt.write_text('{"idx": 0, "repo": "a/b", "uses_gh_aw": true}\nesto no es json\n')
    results = load_checkpoint(ckpt)
    assert results == {0: True}
