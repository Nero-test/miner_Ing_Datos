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

## Ejecutar Miner a gran escala (cientos de miles de repositorios)

Miner procesa los repositorios en paralelo repartiendo la carga entre todos
los tokens configurados, y guarda progreso incremental para poder reanudar
si el proceso se corta.

```bash
miner repositorios_500k.csv --output repositorios_ghaw.csv --concurrency-per-token 6
```

- **`--concurrency-per-token`** (por defecto `4`): consultas simultáneas por
  cada token. Con 5 tokens y el valor por defecto se usan 20 hilos en total.
  El límite real no es la cantidad de hilos sino la cuota de la API
  (5.000 solicitudes/hora por token); subir mucho este número sin subir la
  cantidad de tokens no acelera el proceso más allá de ese techo, y valores
  demasiado altos pueden disparar el límite secundario de abuso de GitHub.
  Con 5 tokens, la cuota combinada es de 25.000 solicitudes/hora, por lo que
  revisar ~500.000 repositorios toma como mínimo unas 20 horas de cuota de
  API, sin importar cuántos hilos uses — los hilos evitan que el tiempo real
  sea mayor por la latencia de red, pero no pueden superar ese piso.
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
