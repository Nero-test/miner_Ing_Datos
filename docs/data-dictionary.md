# Diccionario de datos

Este documento describe cada tabla del dataset generado por `miner extract`,
sus columnas, tipos de dato, significado y claves. Ver
[`er-diagram.md`](er-diagram.md) para el diagrama completo y la
justificación del diseño.

## Nota técnica: el campo `on` y el "Norway problem" de YAML

El campo más importante de un workflow gh-aw se llama `on` (define los
triggers). YAML 1.1 —el estándar que implementa PyYAML por defecto—
interpreta la clave `on` (sin comillas) como el **booleano `True`**, no
como la cadena `"on"` (el mismo problema conocido informalmente como "the
Norway problem", porque `no` se interpreta como Noruega/falso). Esto no es
solo un detalle de implementación: si no se corrige, la clave `on` se
pierde silenciosamente en cada archivo procesado.

Miner corrige esto con un `yaml.SafeLoader` personalizado que solo
reconoce `true`/`false` como booleanos (no `on`/`off`/`yes`/`no`), pasado
como handler a `python-frontmatter` (ver `src/miner/frontmatter_parser.py`,
función `parse_markdown`). El fix aplica tanto a claves como a valores, en
cualquier nivel de anidamiento.

## Tabla: `repositories`

Un registro por repositorio de GitHub del que se extrajo al menos un
archivo de workflow.

| Columna | Tipo | Descripción | Clave |
|---|---|---|---|
| `repo_id` | int | Identificador surrogado, asignado por Miner al procesar el dataset (no es estable entre corridas distintas). | PK |
| `owner` | string | Organización o usuario dueño del repositorio. | |
| `name` | string | Nombre del repositorio (sin el owner). | |
| `full_name` | string | Nombre completo `owner/name`. Único por repositorio. | |

## Tabla: `workflow_files`

Un registro por archivo `.md` de GH-AW encontrado (que tiene su
`.lock.yml`/`.lock.yaml` correspondiente — ver `detector.matching_file_pairs`
— y que se descargó con éxito junto con él), con su frontmatter y body ya
separados.

| Columna | Tipo | Descripción | Clave |
|---|---|---|---|
| `file_id` | int | Identificador surrogado del archivo. | PK |
| `repo_id` | int | Repositorio al que pertenece este archivo. | FK → `repositories.repo_id` |
| `file_name` | string | Nombre del archivo `.md` (ej. `daily-report.md`), preservando mayúsculas/minúsculas originales. | |
| `file_path` | string | Ruta completa dentro del repo (`.github/workflows/<file_name>`). | |
| `raw_frontmatter` | string (JSON) | El frontmatter **completo** del archivo, serializado como JSON, para no perder ningún campo aunque no esté descompuesto en `frontmatter_attributes` (por ejemplo, valores `null` o tipos no triviales). | |
| `body_markdown` | string | El body Markdown del archivo (las instrucciones en lenguaje natural para el agente de IA), sin el frontmatter. | |
| `fetched_at` | string (ISO 8601, UTC) | Marca de tiempo de cuándo Miner descargó este archivo (y su `.lock` correspondiente). | |

## Tabla: `workflow_locks`

Un registro por archivo `.lock.yml`/`.lock.yaml` — el workflow de GitHub
Actions **compilado** a partir del `.md` correspondiente. Relación 1:1 con
`workflow_files`: todo archivo `.md` del dataset tiene exactamente un
`.lock` (ver ["Por qué `workflow_locks` es una tabla aparte"](er-diagram.md)
en el diagrama ER).

| Columna | Tipo | Descripción | Clave |
|---|---|---|---|
| `lock_id` | int | Identificador surrogado del `.lock`. | PK |
| `file_id` | int | Archivo `.md` del que este `.lock` es la versión compilada. | FK → `workflow_files.file_id` (1:1) |
| `file_name` | string | Nombre del archivo `.lock.yml`/`.lock.yaml`, preservando mayúsculas/minúsculas originales. | |
| `file_path` | string | Ruta completa dentro del repo (`.github/workflows/<file_name>`). | |
| `raw_content` | string | El YAML compilado completo, como texto plano (no aplanado — es contenido generado, no un frontmatter con esquema variable). | |
| `fetched_at` | string (ISO 8601, UTC) | Marca de tiempo de cuándo Miner descargó este archivo. | |

## Tabla: `frontmatter_attributes`

Un registro por cada atributo hoja del frontmatter YAML, aplanado (ver
["Por qué `frontmatter_attributes` es una tabla clave-valor"](er-diagram.md)
en el diagrama ER para el detalle de la notación).

| Columna | Tipo | Descripción | Clave |
|---|---|---|---|
| `attribute_id` | int | Identificador surrogado. | PK |
| `file_id` | int | Archivo de workflow al que pertenece este atributo. | FK → `workflow_files.file_id` |
| `key_path` | string | Ruta aplanada de la clave dentro del YAML (ej. `permissions.contents`, `on.schedule[0].cron`, `tools`). | |
| `value` | string | Valor del atributo, convertido a texto. Contenedores vacíos (`{}`/`[]`) se registran como `"{}"`/`"[]"` en vez de omitirse. | |
| `value_type` | string | Tipo original del valor antes de convertirlo a texto: `str`, `int`, `float`, `bool`, `null`, `dict` o `list` (estos dos últimos solo aparecen cuando el contenedor estaba vacío). | |

### Ejemplos de consulta

Como `frontmatter_attributes` es una tabla larga (long format), consultar
un campo específico de todos los workflows es un filtro por `key_path`:

```python
import pandas as pd

files = pd.read_parquet("dataset/workflow_files.parquet")
attrs = pd.read_parquet("dataset/frontmatter_attributes.parquet")

# ¿Qué workflows declaran permiso de escritura sobre "contents"?
contents_write = attrs[(attrs["key_path"] == "permissions.contents") & (attrs["value"] == "write")]
files[files["file_id"].isin(contents_write["file_id"])][["file_name", "file_path"]]
```

Como `workflow_locks` es 1:1 con `workflow_files`, cruzarlas es un join
directo por `file_id`:

```python
locks = pd.read_parquet("dataset/workflow_locks.parquet")

# .md fuente junto con su .lock compilado
files.merge(locks, on="file_id", suffixes=("_md", "_lock"))[
    ["file_name_md", "file_name_lock", "body_markdown", "raw_content"]
]
```

## Formato de archivo

Todas las tablas se escriben como archivos `.parquet` independientes
(`repositories.parquet`, `workflow_files.parquet`, `workflow_locks.parquet`,
`frontmatter_attributes.parquet`), usando PyArrow como motor. Se pueden leer
con `pandas.read_parquet(...)` o cualquier herramienta compatible con
Apache Parquet (DuckDB, Polars, Spark, etc.).
