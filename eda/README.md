# EDA — Análisis exploratorio de datos de GitHub Agentic Workflows

Análisis exploratorio del dataset generado por [Miner](../README.md) a
partir de repositorios de GitHub que usan
[GitHub Agentic Workflows (GH-AW)](https://github.github.com/gh-aw/).

**Dataset propio publicado en Hugging Face:**
[EstebanCQ/gh-aw-workflows-dataset](https://huggingface.co/datasets/EstebanCQ/gh-aw-workflows-dataset)

## Notebooks

| Notebook | Contenido |
|---|---|
| [`01_descripcion_y_calidad.ipynb`](01_descripcion_y_calidad.ipynb) | Carga de los datos, descripción de las 3 tablas y sus relaciones, revisión de calidad, y tratamiento de los problemas encontrados. |
| [`02_exploracion_y_hallazgos.ipynb`](02_exploracion_y_hallazgos.ipynb) | Distribución de archivos por repositorio, exploración del frontmatter y el body, preguntas exploratorias, y hallazgos/limitaciones. |

**Ejecutar en orden**: primero `01_descripcion_y_calidad.ipynb` (genera
las tablas preparadas en `data/processed/`), después
`02_exploracion_y_hallazgos.ipynb` (las consume desde archivo, no depende
de que el primero siga en memoria).

## 1. Obtener los datos

Coloca las 3 tablas del dataset en `eda/data/raw/`:

```
eda/data/raw/
├── repositories.parquet
├── workflow_files.parquet
└── frontmatter_attributes.parquet
```

Opciones para obtenerlas:

- **Generarlas vos mismo** con Miner: `miner extract repositorios_ghaw.csv --output-dir eda/data/raw` desde la raíz del proyecto (ver el [README principal](../README.md)).
- **Descargarlas del dataset publicado** en Hugging Face (enlace arriba),
  y copiar los 3 `.parquet` a `eda/data/raw/`.

`eda/data/processed/` se genera automáticamente al ejecutar el Notebook 1
— no hace falta crearlo a mano ni completarlo manualmente.

## 2. Instalar dependencias

Desde la **raíz del proyecto** (`miner/`), con el entorno virtual de Miner
ya creado y activado (ver el [README principal](../README.md) si aún no lo
tienes):

```bash
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

python -m pip install jupyterlab ipykernel pandas pyarrow matplotlib seaborn
```

Estas dependencias también quedaron registradas como grupo opcional `eda`
en `pyproject.toml`, así que alternativamente:

```bash
python -m pip install -e ".[eda]"
```

## 3. Registrar el kernel del entorno virtual

Para que JupyterLab ejecute los notebooks con el Python (y las
dependencias) del entorno virtual de Miner, y no con otro Python del
sistema:

```bash
python -m ipykernel install --user --name miner --display-name "Python (miner)"
```

## 4. Iniciar JupyterLab

Desde la carpeta `eda/` (para que las rutas relativas `data/raw/` y
`data/processed/` de los notebooks funcionen correctamente):

```bash
cd eda
jupyter lab
```

Se abre JupyterLab en el navegador. Al abrir cada notebook, verifica en
la esquina superior derecha que el kernel seleccionado sea
**"Python (miner)"** (el registrado en el paso 3) — si aparece otro
kernel, cámbialo desde el menú *Kernel → Change Kernel*.

## 5. Ejecutar los notebooks

1. Abre `01_descripcion_y_calidad.ipynb` y ejecútalo de principio a fin
   (*Run → Run All Cells*). Al terminar, deja las 3 tablas preparadas en
   `data/processed/`.
2. Abre `02_exploracion_y_hallazgos.ipynb` y ejecútalo de principio a fin.
   Carga los datos desde `data/processed/`, así que puede ejecutarse en
   una sesión nueva sin depender del primer notebook.

Ambos notebooks conservan sus salidas de ejecución (tablas, gráficos,
interpretaciones) tal como quedaron guardadas, para poder revisarlas
directamente desde GitHub sin tener que volver a ejecutarlos.
