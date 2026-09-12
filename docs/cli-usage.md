# Uso de la CLI: extracción del dataset (`miner extract`)

Este documento cubre específicamente el comando `extract`, que construye el
dataset relacional en Parquet a partir de los repositorios ya identificados
como usuarios de GH-AW. Para la instalación general de Miner y el comando
`mine` (Tarea 2), ver el [`README.md`](../README.md) en la raíz del
proyecto.

## Qué hace

1. Lee un CSV con repositorios ya identificados como usuarios de GH-AW (la
   salida del comando `mine`).
2. Para cada repositorio, vuelve a listar `.github/workflows/` y encuentra
   los pares de archivos `<nombre>.md` + `<nombre>.lock.yml` (o
   `.lock.yaml`) — ver `detector.matching_file_pairs`.
3. Descarga el contenido de AMBOS archivos de cada par (`.md` y `.lock`),
   registrando cada resultado en un checkpoint incremental para poder
   reanudar sin volver a descargar nada ya obtenido. Un par solo se marca
   resuelto si los dos archivos se descargaron con éxito.
4. Separa el frontmatter YAML del body Markdown de cada `.md` (ver
   `src/miner/frontmatter_parser.py`); el `.lock` se conserva tal cual, como
   texto plano.
5. Genera **4 tablas relacionadas** (`repositories`, `workflow_files`,
   `workflow_locks`, `frontmatter_attributes`) y las escribe como archivos
   `.parquet` en la carpeta de salida.

Ver [`er-diagram.md`](./er-diagram.md) para el esquema completo y
[`data-dictionary.md`](./data-dictionary.md) para el detalle de cada
columna.

## Entrada requerida

Un archivo CSV con al menos una columna que identifique el repositorio
(`owner/repo`, URL de GitHub, o URL SSH) — típicamente, la salida generada
por `miner mine`. Miner detecta automáticamente la columna (`full_name`,
`name`, `repo`, `repository`, o `url`); si tu columna se llama distinto,
indícala con `--column`.

## Salida generada

Una carpeta (por defecto `dataset/`) con 4 archivos `.parquet`, uno por
tabla, más el checkpoint de extracción:

```
dataset/
├── repositories.parquet
├── workflow_files.parquet
├── workflow_locks.parquet
├── frontmatter_attributes.parquet
└── extract.checkpoint.jsonl
```

## Ejemplo completo de ejecución

Suponiendo que ya ejecutaste `mine` y tienes `repositorios_ghaw.csv` con 2
repositorios:

```bash
miner extract repositorios_ghaw.csv --output-dir dataset
```

Salida real en la terminal (2 repos, 2 archivos `.md` encontrados, 5 tokens
configurados en `.env`):

```
Leyendo repositorios_ghaw.csv...
Columna de repositorio detectada: 'full_name' (2 filas)
Tokens de GitHub cargados: 5 | hilos totales: 20
Progreso: 1/2 repos (50.0%) | errores hasta ahora: 0
Progreso: 2/2 repos (100.0%) | errores hasta ahora: 0
Construyendo tablas del dataset a partir del checkpoint...
Repositorios con archivos extraídos: 2 | archivos .md: 2

Dataset generado:
  repositories: dataset/repositories.parquet
  workflow_files: dataset/workflow_files.parquet
  workflow_locks: dataset/workflow_locks.parquet
  frontmatter_attributes: dataset/frontmatter_attributes.parquet
```

Para inspeccionar el resultado en Python:

```python
import pandas as pd

files = pd.read_parquet("dataset/workflow_files.parquet")
locks = pd.read_parquet("dataset/workflow_locks.parquet")
attrs = pd.read_parquet("dataset/frontmatter_attributes.parquet")

print(files[["file_name", "file_path"]])

# ¿Qué motor de IA (engine) declara cada workflow?
engine = attrs[attrs["key_path"] == "engine"][["file_id", "value"]]
print(files.merge(engine, on="file_id")[["file_name", "value"]])

# .md fuente junto con su .lock compilado (relación 1:1 por file_id)
print(files.merge(locks, on="file_id", suffixes=("_md", "_lock"))[["file_name_md", "file_name_lock"]])
```

## Opciones disponibles

| Opción | Por defecto | Descripción |
|---|---|---|
| `--output-dir`, `-d` | `dataset` | Carpeta donde se escriben las tablas `.parquet` y el checkpoint. |
| `--column`, `-c` | autodetectada | Columna del CSV que identifica al repositorio. |
| `--concurrency-per-token` | `4` | Repositorios procesados simultáneamente por cada token de `GITHUB_TOKENS`/`GITHUB_TOKEN` configurado en `.env`. |
| `--checkpoint` | `<output-dir>/extract.checkpoint.jsonl` | Ruta explícita del checkpoint incremental, si no quieres la ubicación por defecto. |
| `--fresh` | (desactivado) | Ignora cualquier checkpoint previo y vuelve a descargar todo desde cero. |

## Notas y limitaciones

- `extract` usa la API REST (1 solicitud para listar el directorio + 2
  solicitudes por par `.md`/`.lock` encontrado: una por cada archivo). Al
  operar sobre el subconjunto ya filtrado de repositorios que usan GH-AW
  (típicamente mucho más chico que el CSV de candidatos original de
  `mine`), esto es suficiente sin necesitar batching GraphQL.
- **Es reanudable**: si el `.md` o el `.lock` de un par no se pudo
  descargar (error transitorio, rate limit, archivo borrado/renombrado
  desde el escaneo de `mine`), se registra error para ese par en el
  checkpoint y se sigue con el resto — un par problemático nunca frena la
  extracción completa, y nunca se guarda un `.md` sin su `.lock`
  correspondiente. Si el proceso se interrumpe (`Ctrl+C`, corte de luz) o
  algunos pares quedan pendientes, vuelve a correr **exactamente el mismo
  comando**: los pares ya descargados con éxito no se vuelven a pedir a la
  red.
- `--fresh` fuerza a ignorar el checkpoint existente (útil si cambiaste el
  CSV de entrada pero reusaste el mismo `--output-dir`).
- Requiere el mismo archivo `.env` con `GITHUB_TOKENS`/`GITHUB_TOKEN` que
  usa el comando `mine`.
