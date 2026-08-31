"""
CLI de Miner: conecta lectura de CSV, consulta a GitHub y detección de GH-AW.

Uso:
    miner repositorios.csv --output repositorios_ghaw.csv
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd
import typer
from dotenv import load_dotenv

from miner.csv_io import detect_repo_column, read_candidates, write_csv
from miner.detector import uses_gh_aw
from miner.github_client import GitHubClient
from miner.models import RepoIdentifier

app = typer.Typer(
    add_completion=False,
    help="Miner: identifica repositorios de GitHub que usan GitHub Agentic Workflows (GH-AW).",
)


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
) -> None:
    """Procesa INPUT_CSV, consulta GitHub y genera OUTPUT con los repos que usan GH-AW."""
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        typer.secho(
            "Error: no se encontró GITHUB_TOKEN. Crea un archivo .env a partir "
            "de .env.example y completa tu token.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Leyendo {input_csv}...")
    df = read_candidates(input_csv)
    repo_col = column or detect_repo_column(df)
    typer.echo(f"Columna de repositorio detectada: '{repo_col}' ({len(df)} filas)")

    uses_flags: list[Optional[bool]] = []
    unresolved = 0

    with GitHubClient(token) as client:
        with typer.progressbar(range(len(df)), label="Consultando GitHub") as progress:
            for idx in progress:
                raw_value = df.iloc[idx][repo_col]
                if pd.isna(raw_value):
                    uses_flags.append(None)
                    continue

                identifier = RepoIdentifier.from_raw(str(raw_value))
                if identifier is None:
                    uses_flags.append(None)
                    continue

                files = client.list_workflow_files(identifier.owner, identifier.name)
                if files is None:
                    uses_flags.append(None)
                    unresolved += 1
                else:
                    uses_flags.append(uses_gh_aw(files))

    df["uses_gh_aw"] = uses_flags
    df_filtered = df[df["uses_gh_aw"] == True]  # noqa: E712 -- comparación explícita para excluir None

    write_csv(df_filtered, output)

    typer.echo("")
    typer.secho(f"Repositorios que usan GH-AW: {len(df_filtered)}", fg=typer.colors.GREEN)
    if unresolved:
        typer.secho(
            f"Repositorios sin resolver (no encontrados / error): {unresolved}. "
            "Estos NO se cuentan como 'no usa GH-AW'; vuelve a ejecutar Miner sobre "
            "ellos si necesitas confirmarlos.",
            fg=typer.colors.YELLOW,
        )
    typer.echo(f"Archivo generado: {output}")


if __name__ == "__main__":
    app()
