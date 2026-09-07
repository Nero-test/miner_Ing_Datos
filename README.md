# Miner

Miner es una aplicación de línea de comandos (CLI) en Python que automatiza la
identificación de repositorios de GitHub que utilizan **GitHub Agentic
Workflows (GH-AW)**, y la construcción de un dataset relacional a partir del
contenido de sus workflows.

## Problema que resuelve

Dado un archivo CSV con una lista de repositorios candidatos, revisar
manualmente uno por uno si cada repositorio usa GH-AW —y luego extraer y
estructurar el contenido de sus workflows— es lento y propenso a errores.
Miner automatiza todo el proceso en dos etapas (dos subcomandos):

**`miner mine`** — identificación:
1. Lee el CSV de repositorios candidatos.
2. Para cada repositorio, consulta vía la API de GitHub el contenido de la
   carpeta `.github/workflows/`.
3. Determina si existe al menos un par de archivos con el mismo nombre base:
   un archivo fuente `.md` y su workflow compilado `.lock.yml` (o
   `.lock.yaml`). Por ejemplo: `daily-report.md` + `daily-report.lock.yml`.
4. Genera un nuevo CSV que contiene **únicamente** los repositorios que
   cumplen ese criterio.

**`miner extract`** — construcción del dataset:
5. Descarga el contenido de cada archivo `.md` de workflow encontrado
   (reanudable: si se interrumpe, la siguiente corrida solo descarga lo
   pendiente).
6. Separa su frontmatter YAML del body Markdown, y aplana el frontmatter
   (que varía de un workflow a otro: `on`, `permissions`, `tools`, `engine`,
   etc.) en pares clave-valor, en vez de forzar columnas fijas que se
   romperían con el primer workflow distinto.
7. Genera un dataset relacional de **3 tablas** en formato Parquet
   (`repositories`, `workflow_files`, `frontmatter_attributes`), listo para
   análisis o publicación en Hugging Face Datasets.

## Estructura del proyecto

```
miner/
├── pyproject.toml        # dependencias y entry point de la CLI
├── .env.example          # variables de entorno necesarias (sin credenciales)
├── .gitignore
├── docs/                       # diagrama ER, diccionario de datos, guías de uso
│   ├── er-diagram.md
│   ├── data-dictionary.md
│   ├── cli-usage.md
│   ├── huggingface-publish.md
│   └── huggingface-dataset-card.md
├── src/
│   └── miner/
│       ├── cli.py                 # interfaz de línea de comandos (Typer): mine + extract
│       ├── models.py              # modelos y validación de datos (Pydantic)
│       ├── csv_io.py              # lectura/escritura de CSV (pandas)
│       ├── token_pool.py          # rotación de tokens compartida (REST + GraphQL)
│       ├── github_client.py       # consultas REST a la API de GitHub (httpx)
│       ├── graphql_client.py      # consultas GraphQL en batch, con aislamiento de fallos
│       ├── checkpoint.py          # progreso incremental reanudable (comando 'mine')
│       ├── detector.py            # lógica de detección de GH-AW
│       ├── frontmatter_parser.py  # separación de frontmatter YAML / body Markdown
│       ├── extract_checkpoint.py  # progreso incremental reanudable (comando 'extract')
│       ├── extraction.py          # descarga de .md desde GitHub (aislada por archivo)
│       ├── dataset_builder.py     # construcción de las 3 tablas relacionales en memoria
│       └── parquet_writer.py      # escritura de las tablas a archivos .parquet
└── tests/
    └── test_*.py              # pruebas de cada módulo de arriba
```

## Preparar el entorno Python

Se recomienda `uv`, pero también funciona `venv` estándar.

### Opción A: usando `uv`

```bash
uv venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

uv pip install -e ".[dev]"
```

### Opción B: usando `venv`

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

Esto instala Miner en modo editable junto con sus dependencias
(`typer`, `pydantic`, `pandas`, `httpx`, `python-dotenv`, `python-frontmatter`,
`pyyaml`, `pyarrow`) y las de desarrollo (`pytest`).

## Configurar el token de GitHub

Miner soporta usar **uno o varios tokens de GitHub**. Cada token tiene su
propia cuota de rate limit (5.000 solicitudes por hora autenticado), así que
usar 5 tokens multiplica por 5 la cantidad de repositorios que se pueden
consultar por hora sin tener que esperar. Miner rota automáticamente entre
los tokens disponibles y salta los que se van agotando.

1. Genera Personal Access Tokens en GitHub con permisos de lectura sobre
   repositorios públicos (Settings → Developer settings → Personal access
   tokens). Puedes usar hasta 5 tokens de cuentas distintas.
2. Copia el archivo de ejemplo:

   ```bash
   cp .env.example .env
   ```

3. Edita `.env` y completa tus tokens separados por coma:

   ```
   GITHUB_TOKENS=tok1,tok2,tok3,tok4,tok5
   ```

   Si solo tienes un token, también puedes usar la variable `GITHUB_TOKEN`
   en su lugar (se mantiene por compatibilidad):

   ```
   GITHUB_TOKEN=tu_token_aqui
   ```

   **Importante:** el archivo `.env` nunca debe subirse al repositorio (ya
   está excluido en `.gitignore`). Solo `.env.example` se versiona, y no
   contiene credenciales reales.

## Ejecutar Miner

Miner tiene dos subcomandos: `mine` (identificar repos que usan GH-AW —
Tarea 2) y `extract` (construir el dataset relacional a partir de esos
repos — Tarea 3, ver la sección "Construir el dataset de workflows" más
abajo). Esta sección cubre `mine`.

Una vez instalado el entorno y configurado `.env`:

```bash
miner mine repositorios.csv --output repositorios_ghaw.csv
```

- **Entrada** (`repositorios.csv`): un CSV con una columna que identifique el
  repositorio. Miner detecta automáticamente una columna llamada
  `full_name`, `name`, `repo`, `repository` o `url`; si tu columna se llama
  distinto, indícala con `--column`:

  ```bash
  miner mine repositorios.csv --output repositorios_ghaw.csv --column mi_columna
  ```

  Los valores de esa columna pueden venir como `owner/repo`,
  `https://github.com/owner/repo`, o `git@github.com:owner/repo.git`.

- **Salida** (`repositorios_ghaw.csv`): un CSV con las mismas columnas del
  archivo de entrada, filtrado para incluir **solo** los repositorios
  identificados como usuarios de GH-AW.

Durante la ejecución, Miner muestra una barra de progreso y, al finalizar,
un resumen con la cantidad de repositorios confirmados con GH-AW y la
cantidad de repositorios que no pudieron resolverse (por ejemplo, por no
encontrarse o por errores de red) — estos últimos **no** se cuentan como
"no usa GH-AW", ya que no fue posible confirmarlo.

## REST vs GraphQL

Miner soporta dos formas de consultar GitHub, elegibles con `--api`:

- **`graphql`** (por defecto): agrupa varios repositorios en una sola
  solicitud HTTP (`--batch-size`, por defecto 50). Es muchísimo más eficiente
  en cuota de API: revisar 500.000 repos con lotes de 50 son ~10.000
  solicitudes en vez de 500.000, muy por debajo del límite de puntos de
  GraphQL (5.000/hora por token). Recomendado para volúmenes grandes.
- **`rest`**: 1 solicitud por repositorio. Más simple de razonar, pero el
  límite real termina siendo la cantidad de solicitudes (5.000/hora por
  token), no la cantidad de repos por solicitud.

```bash
miner mine repositorios_500k.csv --output repositorios_ghaw.csv --api graphql --batch-size 50
```

### Aislamiento de fallos en modo GraphQL

Un lote GraphQL agrupa muchos repositorios en una sola solicitud, así que
hay que evitar que **un solo repositorio problemático arruine el resultado
de todos los demás del mismo lote** (por ejemplo, un timeout puntual del
servidor, o un repo cuyo contenido dispara un error al resolverlo).

Miner nunca descarta un lote completo por esto. Si un lote falla de forma
persistente:

1. Primero reintenta el lote completo (la falla puede ser transitoria y
   no ser culpa de ningún repo en particular).
2. Si sigue fallando, **lo divide a la mitad** y resuelve cada mitad por
   separado, cada una con su propio presupuesto de reintentos.
3. Repite la división recursivamente hasta aislar exactamente cuál repo (o
   repos) es el problemático. El resto de los repos del lote original **sí
   quedan resueltos correctamente en la misma corrida**.
4. Solo el repo verdaderamente problemático queda marcado como pendiente
   (no se pierde ni se ignora): el checkpoint lo retiene para reintentarlo
   en la siguiente corrida.

Esto está cubierto por pruebas automatizadas (`tests/test_graphql_client.py`)
que simulan un repo que hace fallar la solicitud y verifican que los demás
repos del lote se resuelven igual.

## Ejecutar Miner a gran escala (cientos de miles de repositorios)

Miner procesa los repositorios en paralelo repartiendo la carga entre todos
los tokens configurados, y guarda progreso incremental para poder reanudar
si el proceso se corta.

```bash
miner mine repositorios_500k.csv --output repositorios_ghaw.csv --concurrency-per-token 6
```

- **`--concurrency-per-token`** (por defecto `4`): solicitudes simultáneas por
  cada token. Con 5 tokens y el valor por defecto se usan 20 hilos en total.
  En modo `graphql`, cada solicitud cubre `--batch-size` repos a la vez, así
  que el techo real de tiempo es mucho más bajo que en modo `rest` (donde
  cada solicitud es 1 repo y 5 tokens dan ~25.000 repos/hora como máximo
  teórico). Con GraphQL y lotes de 50, revisar ~500.000 repos puede tomar
  del orden de minutos a poco más de una hora, en vez de las ~20 horas que
  tomaría en modo `rest`.
- **Checkpoint automático**: junto al CSV de salida, Miner crea un archivo
  `<output>.checkpoint.jsonl` con el resultado de cada fila apenas se
  resuelve. Si interrumpes la ejecución (`Ctrl+C`, corte de luz, cierre de
  la terminal) y vuelves a correr **exactamente el mismo comando**, Miner
  detecta el checkpoint y solo vuelve a consultar las filas pendientes o
  con error — no repite trabajo ya confirmado.
- **`--fresh`**: ignora cualquier checkpoint existente y vuelve a consultar
  todo desde cero (útil si cambiaste de CSV de entrada pero reusaste el
  mismo nombre de salida).
- **`--checkpoint ruta.jsonl`**: para elegir explícitamente dónde guardar el
  progreso, en vez de derivarlo automáticamente del nombre de `--output`.

## Construir el dataset de workflows (`extract`)

Además de identificar *qué* repositorios usan GH-AW, Miner descarga sus
archivos `.md` de workflow, separa el frontmatter YAML del body Markdown, y
genera un **dataset relacional en formato Parquet**.

```bash
miner extract repositorios_ghaw.csv --output-dir dataset
```

- **Entrada**: el CSV de salida de `miner mine` (repos ya confirmados con
  GH-AW). Igual que en `mine`, la columna de repositorio se autodetecta o
  se indica con `--column`.
- **Salida** (`--output-dir`, por defecto `dataset/`): 3 archivos Parquet
  relacionados entre sí:

  | Tabla | Grano | Contenido |
  |---|---|---|
  | `repositories.parquet` | 1 fila por repo | `repo_id` (PK), `owner`, `name`, `full_name` |
  | `workflow_files.parquet` | 1 fila por archivo `.md` | `file_id` (PK), `repo_id` (FK), nombre/ruta del archivo, `has_lock`, el frontmatter completo como JSON (`raw_frontmatter`), y el body en Markdown (`body_markdown`) |
  | `frontmatter_attributes.parquet` | 1 fila por atributo del frontmatter | `attribute_id` (PK), `file_id` (FK), `key_path` (ej. `permissions.contents`, `on.schedule[0]`), `value`, `value_type` |

  El frontmatter se aplana como pares clave-valor (`frontmatter_attributes`)
  en vez de columnas fijas, porque varía bastante entre workflows distintos
  (`on`, `permissions`, `tools`, `engine`, etc., algunos anidados) — un
  esquema de columnas rígidas se rompería con el primer workflow atípico.

- **Reanudable**: igual que `mine`, cada archivo `.md` descargado se
  registra en un checkpoint (`<output-dir>/extract.checkpoint.jsonl` por
  defecto, o `--checkpoint ruta.jsonl`) apenas se resuelve. Si el proceso se
  corta, vuelve a correr el mismo comando y solo se reintenta lo pendiente.
  `--fresh` fuerza a ignorar el checkpoint y descargar todo de nuevo.
- **Aislamiento de fallos por archivo**: si un `.md` puntual falla al
  descargarse, se registra su error y se sigue con el resto del repositorio
  y con los demás repositorios — un archivo problemático nunca frena la
  extracción completa.
- **`--concurrency-per-token`** (por defecto `4`): repositorios procesados
  simultáneamente por cada token cargado en `GITHUB_TOKENS`.

La documentación completa está en `docs/`: diagrama entidad-relación
([`er-diagram.md`](docs/er-diagram.md)), diccionario de datos columna por
columna ([`data-dictionary.md`](docs/data-dictionary.md)), guía de la CLI
([`cli-usage.md`](docs/cli-usage.md)) y guías de publicación en Hugging
Face ([`huggingface-publish.md`](docs/huggingface-publish.md),
[`huggingface-dataset-card.md`](docs/huggingface-dataset-card.md)).

## Ejecutar las pruebas

```bash
pytest
```

Las pruebas cubren, como mínimo, la lógica de detección de GH-AW:

| Archivos                          | Resultado esperado |
|------------------------------------|---------------------|
| `report.md` + `report.lock.yml`    | usa GH-AW           |
| `report.md` solamente              | no usa GH-AW        |
| `report.lock.yml` solamente        | no usa GH-AW        |
| `report.md` + `other.lock.yml`     | no usa GH-AW        |

## Notas

- La API de GitHub aplica límites de tasa (rate limit): 5.000 solicitudes por
  hora por token autenticado. Miner detecta el límite de cada token y espera
  automáticamente antes de reintentar, o rota a otro token si hay más de uno
  configurado en `GITHUB_TOKENS`.
- Para volúmenes muy grandes de repositorios (decenas o cientos de miles),
  usar 5 tokens (`GITHUB_TOKENS`) reduce el tiempo total aproximadamente a
  una quinta parte frente a usar un solo token.
