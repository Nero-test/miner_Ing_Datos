# Tarea 5 — Evolución de archivos GH-AW entre versiones (GHAW-H)

Estudia cómo cambian los archivos Markdown de GitHub Agentic Workflows
(GH-AW) entre sus versiones: longitud del body, tamaño del frontmatter y
tiempo transcurrido entre versiones consecutivas, agregados por archivo y
por mes y visualizados con boxplots.

A diferencia del EDA de la Tarea 4 (que trabaja sobre un único snapshot por
archivo, el dataset propio de Miner en [`../`](../)), esta tarea usa un
dataset externo con **historial de versiones**: no se genera con Miner.

## Dataset: GHAW-H

- **Fuente**: [huggingface.co/datasets/pavtch/GHAW-H](https://huggingface.co/datasets/pavtch/GHAW-H)
- **Versión utilizada**: v0.1.2 (cita más abajo), commit de Hugging Face
  `9ccc840bd7e96fd90db3a16548d5482c2833c47d` (consultado 2026-09-14).
- **Licencia**: CC-BY-4.0.

```bibtex
@dataset{valenzuela_toledo_ghaw_h_2026,
  author    = {Valenzuela-Toledo, Pablo and Kehrer, Timo and Panichella, Sebastiano},
  title     = {{GHAW-H}: A Dataset of GitHub Agentic Workflow Histories},
  year      = {2026},
  publisher = {Zenodo},
  version   = {v0.1.2},
  doi       = {10.5281/zenodo.22084012},
  url       = {https://doi.org/10.5281/zenodo.22084012}
}
```

De las 5 tablas publicadas (`repository`, `source_markdown_file_history`,
`source_markdown_file_version`, `source_markdown_file_snapshot`,
`lock_file_snapshot`), esta tarea usa las primeras 4 — no se necesita
`lock_file_snapshot` (el `.lock.yml` compilado), ya que el análisis trabaja
sobre el Markdown fuente (frontmatter + body). El diccionario completo de
columnas está en
[`docs/table_dictionary.md`](https://huggingface.co/datasets/pavtch/GHAW-H/blob/main/docs/table_dictionary.md)
del propio dataset.

## 1. Obtener los datos

Descarga las 4 tablas parquet necesarias y colócalas en `data/raw/`,
pineadas al commit exacto usado en este análisis para reproducibilidad:

```bash
mkdir -p data/raw
REV=9ccc840bd7e96fd90db3a16548d5482c2833c47d
BASE="https://huggingface.co/datasets/pavtch/GHAW-H/resolve/$REV/data"
for f in repository.parquet source_markdown_file_history.parquet \
         source_markdown_file_snapshot.parquet source_markdown_file_version.parquet; do
  curl -sL "$BASE/$f" -o "data/raw/$f"
done
```

En PowerShell:

```powershell
New-Item -ItemType Directory -Force data\raw | Out-Null
$rev = "9ccc840bd7e96fd90db3a16548d5482c2833c47d"
$base = "https://huggingface.co/datasets/pavtch/GHAW-H/resolve/$rev/data"
foreach ($f in "repository.parquet","source_markdown_file_history.parquet",
               "source_markdown_file_snapshot.parquet","source_markdown_file_version.parquet") {
  Invoke-WebRequest "$base/$f" -OutFile "data\raw\$f"
}
```

Al terminar, `data/raw/` debe quedar así (~16 MB en total):

```
data/raw/
├── repository.parquet
├── source_markdown_file_history.parquet
├── source_markdown_file_snapshot.parquet
└── source_markdown_file_version.parquet
```

`data/raw/` y `data/processed/` no se versionan en git (regla `*.parquet`
del [`.gitignore`](../../.gitignore) del proyecto), igual que en la Tarea 4.

## 2. Instalar dependencias

Esta tarea reutiliza el mismo entorno virtual y el extra `eda` de la Tarea 4
(pandas, pyarrow, matplotlib, seaborn, jupyterlab, ipykernel) más `pyyaml`
—ya declarado como dependencia **core** del proyecto en
[`pyproject.toml`](../../pyproject.toml)—, así que no se necesita instalar
nada nuevo. Si todavía no tienes el entorno:

```bash
# desde la raíz del proyecto
uv venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
uv pip install -e ".[eda]"
python -m ipykernel install --user --name miner --display-name "Python (miner)"
```

Ver el [README principal](../../README.md) y [`eda/README.md`](../README.md)
para más detalle sobre esta preparación.

## 3. Ejecutar los notebooks

Desde esta carpeta (`eda/tarea_5/`), con el kernel **"Python (miner)"**:

```bash
cd eda/tarea_5
jupyter lab
```

Ejecutar **en orden**, de principio a fin (*Run → Run All Cells*):

1. **[`01_preparacion_y_agregaciones.ipynb`](01_preparacion_y_agregaciones.ipynb)**
   — carga y relaciona las 4 tablas, reconstruye las secuencias de
   versiones, calcula las medidas de cambio y genera las 4 tablas agregadas
   en `data/processed/`.
2. **[`02_boxplots_y_evolucion.ipynb`](02_boxplots_y_evolucion.ipynb)** —
   carga las tablas de `data/processed/` (y puntualmente `data/raw/` para
   extractos de contenido en la Sección 5), construye los boxplots,
   interpreta los resultados e inspecciona casos concretos. No depende de
   ninguna variable en memoria del primer notebook: puede ejecutarse en una
   sesión nueva siempre que `data/processed/` ya exista.

Ambos notebooks conservan sus salidas de ejecución (tablas, gráficos,
interpretaciones) para poder revisarlos directamente desde GitHub.

## 4. Archivos generados

El Notebook 1 guarda 4 tablas en `data/processed/`, que son la entrada del
Notebook 2:

| Archivo | Grano | Contenido |
|---|---|---|
| `version_measures.parquet` | Una versión | Identificadores, `repo_full_name`, `path`, `rank`, `committed_at`, longitud del body, tamaño y categoría del frontmatter |
| `transitions.parquet` | Una transición (versión con predecesor válido) | Identificadores de ambas versiones comparadas, sus medidas, y los deltas (cambio de longitud, magnitud, cambio de frontmatter, días entre versiones) |
| `file_summary.parquet` | Una historia de archivo | Cantidad de versiones, primera/última fecha, longitud inicial/final, cambio neto, mediana del tiempo entre versiones |
| `file_month_summary.parquet` | Una historia con transiciones en un mes dado | Cantidad de transiciones y mediana de la magnitud del cambio de longitud ese mes |
