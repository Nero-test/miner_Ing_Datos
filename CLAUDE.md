# Miner — Contexto y decisiones de diseño

Este documento resume el proyecto y **por qué** se tomaron las decisiones
de diseño clave, para que cualquier sesión futura (humana o de Claude
Code) entienda el razonamiento sin tener que releer todo el historial.

## Qué es Miner

CLI en Python (Typer) que identifica repositorios de GitHub que usan
[GitHub Agentic Workflows (GH-AW)](https://github.github.com/gh-aw/) y
construye un dataset relacional en Parquet a partir del contenido de sus
workflows. Dos subcomandos:

- `miner mine`: dado un CSV de repos candidatos, genera un CSV con los que
  confirmadamente usan GH-AW (par `<nombre>.md` + `<nombre>.lock.yml` en
  `.github/workflows/`).
- `miner extract`: dado el CSV de `mine`, descarga cada `.md`, separa
  frontmatter/body, y genera 3 tablas Parquet (`repositories`,
  `workflow_files`, `frontmatter_attributes`).

Además: `eda/` contiene el análisis exploratorio del dataset generado
(dos notebooks Jupyter).

## Mapa de módulos (`src/miner/`)

| Módulo | Responsabilidad |
|---|---|
| `models.py` | Pydantic: `RepoIdentifier` (normaliza owner/repo/URL https/SSH), `GHAWResult`, `FrontmatterAttribute` |
| `csv_io.py` | Lectura/escritura de CSV, detección de columna y de compresión gzip |
| `token_pool.py` | Rotación round-robin de tokens de GitHub, compartida por REST y GraphQL |
| `github_client.py` | Consultas REST (`list_workflow_files`, `get_file_content`) |
| `graphql_client.py` | Consultas GraphQL en batch, con aislamiento de fallos por bisección |
| `checkpoint.py` | Progreso incremental reanudable de `mine` |
| `detector.py` | Lógica pura de detección de pares `.md`/`.lock` (sin red) |
| `frontmatter_parser.py` | Separación de frontmatter YAML / body Markdown |
| `extract_checkpoint.py` | Progreso incremental reanudable de `extract` (guarda el contenido crudo descargado, no solo un booleano) |
| `extraction.py` | Orquesta la descarga de `.md` desde GitHub, aislado por archivo |
| `dataset_builder.py` | Construye las 3 tablas relacionales en memoria a partir del contenido descargado |
| `parquet_writer.py` | Escribe las tablas a `.parquet` |
| `cli.py` | Capa delgada de Typer que orquesta todo lo anterior — no contiene lógica de negocio |

## Decisiones de diseño y por qué

### 1. Nunca confundir "no se pudo verificar" con "no cumple"

En `checkpoint.py` y `extract_checkpoint.py`, un resultado indeterminado
(rate limit no resuelto, repo renombrado/borrado, error de red) se
guarda como `None`/pendiente — **nunca** como `False`/"no usa GH-AW" ni
se descarta en silencio. Esto evita falsos negativos: si no sabemos,
decimos que no sabemos, y queda registrado para reintentar en la
siguiente corrida. Aplica también a `extraction.py` (una fila
`__listing__` sintética si no se puede listar `.github/workflows/`).

En `github_client.list_workflow_files`, un 404 al pedir
`/contents/.github/workflows` es ambiguo (carpeta ausente vs. repo
borrado/privado/sin permiso). Se desambigua con una segunda consulta a
`/repos/{owner}/{name}` (`_repo_exists`): solo se devuelve `[]`
("confirmado sin GH-AW") si el repo responde 200; si el repo también da
404 o queda indeterminado, se devuelve `None`. El camino GraphQL ya
distinguía este caso de forma nativa (`r{n}: null` → pendiente).

### 2. Aislamiento de fallos al grano más chico posible

- **GraphQL (`graphql_client.py`, `_retry_or_split`)**: si un lote de ~50
  repos falla persistentemente, se **bisecta recursivamente** en vez de
  descartarse completo, hasta aislar exactamente qué repo causa el
  problema. El resto del lote se resuelve igual en la misma corrida.
  Verificado con un test que simula un repo "venenoso" dentro de un lote
  sano (`test_graphql_client.py`).
- **Extracción de archivos (`extraction.py`)**: si un `.md` puntual falla
  al descargarse, se registra su error y se sigue con el resto del repo
  — un archivo problemático nunca frena la extracción completa.

Motivación: a escala (cientos de miles de repos), un solo elemento
problemático no puede tumbar el trabajo de todos los demás.

### 3. Todo es resumible (checkpoints JSONL append-only)

`checkpoint.py` y `extract_checkpoint.py` escriben cada resultado apenas
se conoce (no al final), en formato JSONL con `append`. Motivación: a
escala, un corte de proceso (Ctrl+C, corte de luz, rate limit de horas)
no puede significar perder todo el trabajo ya hecho. Diferencia entre
ambos: el de `mine` guarda solo el booleano; el de `extract` guarda el
**contenido crudo descargado**, para que un ajuste futuro al parser de
frontmatter no obligue a volver a pegarle a la API de GitHub.

### 4. REST vs GraphQL en `mine`

REST es 1 solicitud por repo — a 460k repos, el techo real es la cuota de
la API (5.000 req/hora/token), no la latencia. GraphQL agrupa ~50 repos
por solicitud (alias), reduciendo drásticamente el número de solicitudes
necesarias. GraphQL es el default; REST se mantiene como alternativa más
simple de razonar (`--api rest`). `extract` usa solo REST porque opera
sobre el subconjunto ya filtrado (mucho más chico), donde el batching no
es necesario.

### 5. Rotación de tokens (`token_pool.py`)

Extraído como módulo compartido (no duplicado entre REST y GraphQL)
porque ambos clientes necesitan la misma lógica: round-robin entre N
tokens, saltando los que se quedan sin cuota, esperando solo si todos
están agotados. `GITHUB_TOKENS` (varios, separados por coma) multiplica
la cuota disponible por la cantidad de tokens.

### 6. Esquema de 3 tablas para el dataset (`docs/er-diagram.md`)

`repositories` → `workflow_files` → `frontmatter_attributes` (1:N cada
relación). La decisión clave es que `frontmatter_attributes` es una
tabla **EAV** (entity-attribute-value, clave-valor aplanada con
dot-notation), no columnas fijas ni una tabla por campo. Motivación: el
frontmatter de gh-aw no tiene un esquema estable entre workflows
distintos (`on`, `permissions`, `tools`, `engine` varían, y algunos
campos se declaran de más de una forma — ver punto 8). Un esquema rígido
se habría roto con el primer workflow atípico; el EDA (Tarea 4) confirmó
en datos reales que esto era necesario (ej. `engine` a veces es un
string simple, a veces un objeto con subcampo `id`).

Se descartó una versión anterior de 4-5 tablas (con `workflow_triggers`,
`workflow_tools`, `workflow_permissions` como tablas separadas) que
apareció mezclada en el entorno de trabajo en algún punto — no era
consistente con este diseño aprobado y se reemplazó por completo (código
y documentación) antes de seguir.

### 7. El bug de `on:` en YAML (frontmatter_parser.py)

YAML 1.1 (el que implementa PyYAML) interpreta las claves `on`/`off`/
`yes`/`no` como booleanos, no como texto — conocido informalmente como
"Norway problem" (`no` → Noruega/falso). Esto es crítico acá porque `on:`
es el campo *más común* de un workflow (define los triggers). Se
resolvió con un `yaml.SafeLoader` personalizado (`_GHAWSafeLoader`) que
solo reconoce `true`/`false` como booleanos, pasado como handler a
`python-frontmatter`. Verificado contra los 1.409 archivos reales del
dataset: cero `key_path` corruptos con prefijo `True`/`False`.

Nota: `frontmatter.loads()` de la librería falla con `TypeError` si el
frontmatter tiene una clave no-string (como el booleano de `on:` mal
interpretado) porque intenta pasar el metadata como `**kwargs`. Por eso
se usa `frontmatter.parse()` (devuelve la tupla directamente) en vez de
`.loads()`.

### 8. `engine` se declara de dos formas — coalesce documentado

En datos reales, `engine` aparece como texto simple (`engine: claude`) o
como objeto anidado (`engine: {id: claude, ...}`). El EDA (Tarea 4)
verificó que ningún archivo usa ambas formas a la vez, así que se
combinan sin ambigüedad al analizar. Refuerza la decisión del punto 6
(EAV en vez de columnas fijas): con columnas fijas, esta variación de
forma habría requerido casos especiales constantes.

### 9. Migración de `huggingface-cli` a `hf`

La CLI de Hugging Face fue renombrada; `huggingface-cli` sigue
funcionando pero está deprecada. La documentación (`docs/
huggingface-publish.md`) usa `hf` como comando principal, con nota de
compatibilidad.

### 10. Problemas de entorno detectados en Windows (relevante si algo similar reaparece)

- `pip install <paquete>` sin `python -m` puede resolver a un `pip.exe`
  distinto al del venv activo (en particular con la distribución de
  Python de Microsoft Store) — instalando en el Python global en vez del
  entorno virtual. Se soluciona invocando siempre `python -m pip ...`.
- Un venv puede quedar sin `pip` instalado (bug conocido de esa
  distribución) — se repara con `python -m ensurepip --upgrade`.

## Estado actual

- **Tarea 2 (`mine`)** y **Tarea 3 (`extract`)**: completas, con tests
  (63 pasando) y `docs/` (ER diagram, diccionario de datos, guía de CLI,
  guías de Hugging Face).
- **Dataset publicado**: [EstebanCQ/gh-aw-workflows-dataset](https://huggingface.co/datasets/EstebanCQ/gh-aw-workflows-dataset)
  — 345 repositorios, 1.409 archivos de workflow, 58.573 atributos de
  frontmatter.
- **Tarea 4 (`eda/`)**: dos notebooks ejecutados de punta a punta contra
  los datos reales del dataset (no simulados). Hallazgos principales:
  distribución de archivos por repo muy asimétrica (53% de los repos
  tiene 1 solo archivo; `github/gh-aw` concentra 299), permisos
  mayoritariamente de solo lectura (99.8% en `permissions.contents`),
  triggers dominados por activación manual/programada más que reactiva a
  eventos, y un caso real de frontmatter mal formado en el repositorio de
  origen (documentado y tratado sin excluir la fila).

## Cosas a tener en cuenta si se retoma el proyecto

- El dataset es una instantánea (2026-09-05); no se actualiza solo.
- `docs/` y `eda/` asumen el esquema de 3 tablas — si se cambia el
  esquema, hay que actualizar ambos, no solo el código.
- Las dependencias de `eda/` (`jupyterlab`, `ipykernel`, `matplotlib`,
  `seaborn`) están en el grupo opcional `eda` de `pyproject.toml`, no en
  las dependencias principales de Miner.
