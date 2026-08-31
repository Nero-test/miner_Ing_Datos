"""
CLI de Miner: conecta lectura de CSV, consulta a GitHub y detección de GH-AW.

Uso:
    miner repositorios.csv --output repositorios_ghaw.csv

Pensado para escalar a corridas grandes (cientos de miles de repositorios):
usa varios tokens en paralelo y guarda progreso incremental para poder
reanudar si el proceso se interrumpe.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

import pandas as pd
import typer
from dotenv import load_dotenv

from miner.checkpoint import CheckpointWriter, default_checkpoint_path, load_checkpoint
from miner.csv_io import detect_repo_column, read_candidates, write_csv
from miner.detector import uses_gh_aw
from miner.github_client import GitHubClient
from miner.models import RepoIdentifier

app = typer.Typer(
    add_completion=False,
    help="Miner: identifica repositorios de GitHub que usan GitHub Agentic Workflows (GH-AW).",
)


def _load_tokens() -> List[str]:
    """
    Carga uno o varios tokens de GitHub desde variables de entorno.

    Formatos soportados (en orden de prioridad):
      GITHUB_TOKENS="tok1,tok2,tok3,tok4,tok5"   (varios tokens, separados por coma)
      GITHUB_TOKEN=tok1                           (un solo token, compatibilidad)
    """
    combined = os.getenv("GITHUB_TOKENS")
    if combined:
        tokens = [t.strip() for t in combined.split(",") if t.strip()]
        if tokens:
            return tokens

    single = os.getenv("GITHUB_TOKEN")
    if single:
        return [single]

    return []


def _resolve_repo(client: GitHubClient, raw_value: object) -> tuple[Optional[str], Optional[bool]]:
    """Resuelve si un valor de celda corresponde a un repo que usa GH-AW."""
    if pd.isna(raw_value):
        return None, None

    identifier = RepoIdentifier.from_raw(str(raw_value))
    if identifier is None:
        return None, None

    files = client.list_workflow_files(identifier.owner, identifier.name)
    if files is None:
        return identifier.full_name, None

    return identifier.full_name, uses_gh_aw(files)


@app.command()
def main(
    input_csv: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="CSV de entrada con los repositorios candidatos.",
    ),
    output: Path = typer.Option(
        Path("repositorios_ghaw.csv"),
        "--output",
        "-o",
        help="CSV de salida con los repositorios que usan GH-AW.",
    ),
    column: Optional[str] = typer.Option(
        None,
        "--column",
        "-c",
        help="Nombre de la columna que identifica al repositorio (se autodetecta si se omite).",
    ),
    concurrency_per_token: int = typer.Option(
        4,
        "--concurrency-per-token",
        min=1,
        max=20,
        help="Consultas simultáneas por cada token cargado. Con 5 tokens y el valor "
        "por defecto (4) se usan 20 hilos en total. Súbelo con cuidado: valores muy "
        "altos pueden disparar el límite secundario de abuso de GitHub.",
    ),
    checkpoint_path: Optional[Path] = typer.Option(
        None,
        "--checkpoint",
        help="Archivo de progreso incremental (JSONL). Por defecto se deriva del "
        "nombre de --output. Si ya existe, Miner reanuda desde ahí en vez de "
        "empezar de cero.",
    ),
    fresh: bool = typer.Option(
        False,
        "--fresh",
        help="Ignora cualquier checkpoint previo y vuelve a consultar todo desde cero.",
    ),
) -> None:
    """Procesa INPUT_CSV, consulta GitHub y genera OUTPUT con los repos que usan GH-AW."""
    load_dotenv()
    tokens = _load_tokens()
    if not tokens:
        typer.secho(
            "Error: no se encontró ningún token de GitHub. Crea un archivo .env a "
            "partir de .env.example y completa GITHUB_TOKENS (uno o varios, "
            "separados por coma) o GITHUB_TOKEN.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Leyendo {input_csv}...")
    df = read_candidates(input_csv)
    repo_col = column or detect_repo_column(df)
    total = len(df)
    typer.echo(f"Columna de repositorio detectada: '{repo_col}' ({total} filas)")

    max_workers = max(len(tokens) * concurrency_per_token, 1)
    typer.echo(f"Tokens de GitHub cargados: {len(tokens)} | hilos totales: {max_workers}")

    ckpt_path = checkpoint_path or default_checkpoint_path(output)
    if fresh and ckpt_path.exists():
        ckpt_path.unlink()

    done = load_checkpoint(ckpt_path)
    # Solo se consideran resueltas las filas con True/False confirmado;
    # las que quedaron en None (pendiente/error) se vuelven a intentar.
    pending_indices = [i for i in range(total) if done.get(i) not in (True, False)]
    already_resolved = total - len(pending_indices)
    if already_resolved:
        typer.echo(
            f"Checkpoint encontrado en {ckpt_path}: {already_resolved} filas ya "
            f"resueltas, {len(pending_indices)} pendientes por consultar."
        )

    unresolved = 0
    completed = 0
    # Con cientos de miles de filas, imprimir en cada iteración inunda la
    # terminal: se reporta progreso aproximadamente 100 veces en total.
    report_every = max(len(pending_indices) // 100, 1)

    if pending_indices:
        with GitHubClient(tokens) as client, CheckpointWriter(ckpt_path) as writer:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_resolve_repo, client, df.iloc[idx][repo_col]): idx
                    for idx in pending_indices
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        repo_name, value = future.result()
                    except Exception as exc:  # un repo problemático no debe tumbar la corrida
                        typer.secho(f"[WARN] error inesperado en fila {idx}: {exc}", fg=typer.colors.YELLOW)
                        repo_name, value = None, None

                    writer.write(idx, repo_name, value)
                    if value is None:
                        unresolved += 1

                    completed += 1
                    if completed % report_every == 0 or completed == len(pending_indices):
                        typer.echo(
                            f"Progreso: {completed}/{len(pending_indices)} pendientes "
                            f"resueltas ({completed / len(pending_indices) * 100:.1f}%) "
                            f"| sin resolver hasta ahora: {unresolved}"
                        )

    # Reconstruir resultados finales a partir del checkpoint completo
    # (incluye tanto lo ya resuelto antes como lo resuelto en esta corrida).
    final_results = load_checkpoint(ckpt_path)
    df["uses_gh_aw"] = [final_results.get(i) for i in range(total)]
    df_filtered = df[df["uses_gh_aw"] == True]  # noqa: E712 -- comparación explícita para excluir None

    write_csv(df_filtered, output)

    n_sin_resolver = sum(1 for v in final_results.values() if v is None)
    typer.echo("")
    typer.secho(f"Repositorios que usan GH-AW: {len(df_filtered)}", fg=typer.colors.GREEN)
    if n_sin_resolver:
        typer.secho(
            f"Repositorios sin resolver (no encontrados / error): {n_sin_resolver}. "
            f"Estos NO se cuentan como 'no usa GH-AW'. Vuelve a ejecutar el mismo "
            f"comando (usará {ckpt_path.name} para reintentar solo estos).",
            fg=typer.colors.YELLOW,
        )
    typer.echo(f"Archivo generado: {output}")


if __name__ == "__main__":
    app()
