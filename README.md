# Miner

Miner es una aplicación de línea de comandos (CLI) en Python que automatiza la
identificación de repositorios de GitHub que utilizan **GitHub Agentic
Workflows (GH-AW)**.

## Problema que resuelve

Dado un archivo CSV con una lista de repositorios candidatos, revisar
manualmente uno por uno si cada repositorio usa GH-AW es lento y propenso a
errores. Miner automatiza todo el proceso:

1. Lee el CSV de repositorios candidatos.
2. Para cada repositorio, consulta vía la API de GitHub el contenido de la
   carpeta `.github/workflows/`.
3. Determina si existe al menos un par de archivos con el mismo nombre base:
   un archivo fuente `.md` y su workflow compilado `.lock.yml` (o
   `.lock.yaml`). Por ejemplo: `daily-report.md` + `daily-report.lock.yml`.
4. Genera un nuevo CSV que contiene **únicamente** los repositorios que
   cumplen ese criterio.

## Estructura del proyecto

```
miner/
├── pyproject.toml        # dependencias y entry point de la CLI
├── .env.example          # variables de entorno necesarias (sin credenciales)
├── .gitignore
├── src/
│   └── miner/
│       ├── cli.py             # interfaz de línea de comandos (Typer)
│       ├── models.py          # modelos y validación de datos (Pydantic)
│       ├── csv_io.py          # lectura/escritura de CSV (pandas)
│       ├── github_client.py   # consultas a la API de GitHub (httpx)
│       └── detector.py        # lógica de detección de GH-AW
└── tests/
    ├── test_detector.py       # pruebas de la lógica de detección
    └── test_models.py         # pruebas de validación de identificadores
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
(`typer`, `pydantic`, `pandas`, `httpx`, `python-dotenv`) y las de desarrollo
(`pytest`).

## Configurar el token de GitHub

1. Genera un Personal Access Token en GitHub con permisos de lectura sobre
   repositorios públicos (Settings → Developer settings → Personal access
   tokens).
2. Copia el archivo de ejemplo:

   ```bash
   cp .env.example .env
   ```

3. Edita `.env` y completa tu token:

   ```
   GITHUB_TOKEN=tu_token_aqui
   ```

   **Importante:** el archivo `.env` nunca debe subirse al repositorio (ya
   está excluido en `.gitignore`). Solo `.env.example` se versiona, y no
   contiene credenciales reales.

## Ejecutar Miner

Una vez instalado el entorno y configurado `.env`:

```bash
miner repositorios.csv --output repositorios_ghaw.csv
```

- **Entrada** (`repositorios.csv`): un CSV con una columna que identifique el
  repositorio. Miner detecta automáticamente una columna llamada
  `full_name`, `name`, `repo`, `repository` o `url`; si tu columna se llama
  distinto, indícala con `--column`:

  ```bash
  miner repositorios.csv --output repositorios_ghaw.csv --column mi_columna
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

- La API de GitHub aplica límites de tasa (rate limit). Con un token
  autenticado el límite es de 5.000 solicitudes por hora; Miner detecta el
  límite y espera automáticamente antes de reintentar.
- Para volúmenes muy grandes de repositorios (decenas o cientos de miles),
  considera dividir el CSV de entrada en lotes o usar múltiples tokens.
