"""
CLI de Miner: conecta lectura de CSV, consulta a GitHub y detección de GH-AW.

Uso:
    miner repositorios.csv --output repositorios_ghaw.csv

Soporta dos formas de consultar GitHub:
  --api rest     1 solicitud HTTP por repositorio (simple, más lenta a escala).
  --api graphql  varios repositorios por solicitud (batching), con
                 aislamiento de fallos: un repo problemático dentro de un
                 lote no le cuesta el resultado a los demás del mismo lote.

Ambos modos usan varios tokens en paralelo y guardan progreso incremental
(checkpoint) para poder reanudar si el proceso se interrumpe.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pandas as pd
import typer
from dotenv import load_dotenv

from miner.checkpoint import CheckpointWriter, default_checkpoint_path, load_checkpoint
from miner.csv_io import detect_repo_column, read_candidates, write_csv
from miner.detector import uses_gh_aw
from miner.github_client import GitHubClient
from miner.graphql_client import GitHubGraphQLClient
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


def _chunked(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ------------------------------------------------------------------
# Modo REST: 1 solicitud por repo
# ------------------------------------------------------------------
def _resolve_repo_rest(client: GitHubClient, raw_value: object) -> Tuple[Optional[str], Optional[bool]]:
    if pd.isna(raw_value):
        return None, None
    identifier = RepoIdentifier.from_raw(str(raw_value))
    if identifier is None:
        return None, None
    files = client.list_workflow_files(identifier.owner, identifier.name)
    if files is None:
        return identifier.full_name, None
    return identifier.full_name, uses_gh_aw(files)


def _run_rest(
    df: pd.DataFrame,
    repo_col: str,
    pending_indices: List[int],
    tokens: List[str],
    max_workers: int,
    writer: CheckpointWriter,
    report_every: int,
) -> int:
    unresolved = 0
    completed = 0
    with GitHubClient(tokens) as client:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_resolve_repo_rest, client, df.iloc[idx][repo_col]): idx
                for idx in pending_indices
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    repo_name, value = future.result()
                except Exception as exc:
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
    return unresolved


# ------------------------------------------------------------------
# Modo GraphQL: varios repos por solicitud, con aislamiento de fallos
# ------------------------------------------------------------------
def _process_graphql_batch(
    client: GitHubGraphQLClient, writer: CheckpointWriter, batch_items: List[Tuple[int, object]]
) -> int:
    """
    batch_items: lista de (idx_global, raw_value) del CSV original.
    Devuelve la cantidad de repos sin resolver dentro de este lote.
    """
    parsed: List[Tuple[int, str, str]] = []  # (idx_global, owner, name)
    unresolved = 0

    for idx_global, raw_value in batch_items:
        if pd.isna(raw_value):
            writer.write(idx_global, None, None)
            unresolved += 1
            continue
        identifier = RepoIdentifier.from_raw(str(raw_value))
        if identifier is None:
            writer.write(idx_global, None, None)
            unresolved += 1
            continue
        parsed.append((idx_global, identifier.owner, identifier.name))

    if not parsed:
        return unresolved

    # alias local (0..N-1) dentro del lote, mapeado de vuelta al idx global
    gql_batch = [(local_idx, owner, name) for local_idx, (_, owner, name) in enumerate(parsed)]
    files_by_alias = client.resolve_batch(gql_batch)

    for local_idx, (idx_global, owner, name) in enumerate(parsed):
        files = files_by_alias.get(local_idx)
        repo_name = f"{owner}/{name}"
        if files is None:
            writer.write(idx_global, repo_name, None)
            unresolved += 1
        else:
            writer.write(idx_global, repo_name, uses_gh_aw(files))

    return unresolved


def _run_graphql(
    df: pd.DataFrame,
    repo_col: str,
    pending_indices: List[int],
    tokens: List[str],
    max_workers: int,
    batch_size: int,
    writer: CheckpointWriter,
) -> int:
    unresolved = 0
    completed_batches = 0

    pending_items = [(idx, df.iloc[idx][repo_col]) for idx in pending_indices]
    batches = list(_chunked(pending_items, batch_size))
    total_batches = len(batches)
    report_every_batches = max(total_batches // 100, 1)

    with GitHubGraphQLClient(tokens) as client:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_graphql_batch, client, writer, batch): i for i, batch in enumerate(batches)}
            for future in as_completed(futures):
                try:
                    unresolved += future.result()
                except Exception as exc:
                    typer.secho(f"[WARN] error inesperado en un lote: {exc}", fg=typer.colors.YELLOW)

                completed_batches += 1
                if completed_batches % report_every_batches == 0 or completed_batches == total_batches:
                    repos_done = min(completed_batches * batch_size, len(pending_items))
                    typer.echo(
                        f"Progreso: {completed_batches}/{total_batches} lotes "
                        f"(~{repos_done}/{len(pending_items)} repos, "
                        f"{completed_batches / total_batches * 100:.1f}%) "
                        f"| sin resolver hasta ahora: {unresolved}"
                    )
    return unresolved


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
    api: str = typer.Option(
        "graphql",
        "--api",
        help="'graphql' (varios repos por solicitud, recomendado para muchos repos) "
        "o 'rest' (1 solicitud por repo, más simple).",
    ),
    batch_size: int = typer.Option(
        50,
        "--batch-size",
        min=1,
        max=200,
        help="Repositorios por solicitud GraphQL (solo aplica con --api graphql).",
    ),
    concurrency_per_token: int = typer.Option(
        4,
        "--concurrency-per-token",
        min=1,
        max=20,
        help="Solicitudes simultáneas por cada token cargado. Con modo REST cada "
        "solicitud es 1 repo; con GraphQL, cada solicitud es un lote completo.",
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
    if api not in ("rest", "graphql"):
        typer.secho("Error: --api debe ser 'rest' o 'graphql'.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

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
    typer.echo(f"API: {api} | tokens: {len(tokens)} | hilos totales: {max_workers}")
    if api == "graphql":
        typer.echo(f"Tamaño de lote GraphQL: {batch_size} repos por solicitud")

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

    if pending_indices:
        with CheckpointWriter(ckpt_path) as writer:
            report_every = max(len(pending_indices) // 100, 1)
            if api == "rest":
                _run_rest(df, repo_col, pending_indices, tokens, max_workers, writer, report_every)
            else:
                _run_graphql(df, repo_col, pending_indices, tokens, max_workers, batch_size, writer)

    # Reconstruir resultados finales a partir del checkpoint completo
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
