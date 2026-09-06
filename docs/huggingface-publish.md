# Publicar el dataset en Hugging Face Datasets

Este documento explica cómo subir las tablas `.parquet` generadas por
`miner extract` a [Hugging Face Datasets](https://huggingface.co/datasets).

> Miner no publica el dataset automáticamente (requiere una cuenta y
> credenciales de Hugging Face que son personales). Esta guía deja el
> proceso listo para ejecutar en unos pocos comandos.

## 1. Requisitos previos

- Una cuenta en [huggingface.co](https://huggingface.co/join).
- Un token de acceso con permiso de escritura: **Settings → Access Tokens →
  New token** (tipo `Write`).
- La CLI `hf` de Hugging Face instalada. Reemplaza a la antigua
  `huggingface-cli` (que sigue funcionando pero muestra un aviso de
  obsolescencia):

  ```bash
  pip install -U huggingface_hub
  ```

## 2. Iniciar sesión

```bash
hf auth login
```

Pega el token cuando lo pida. También puedes exportarlo como variable de
entorno (`HF_TOKEN=hf_...`) para usarlo sin login interactivo.

## 3. Crear el repositorio del dataset

```bash
hf repo create tu-usuario/nombre-del-dataset --repo-type dataset
```

Reemplaza `nombre-del-dataset` por algo descriptivo, por ejemplo
`gh-aw-workflows-dataset`. Esto crea
`https://huggingface.co/datasets/tu-usuario/nombre-del-dataset`.

## 4. Preparar la carpeta a subir

Copia la dataset card (`docs/huggingface-dataset-card.md`, provista en este
repositorio) como `README.md` dentro de la carpeta del dataset generado por
`extract`, junto a las tablas `.parquet`:

```bash
cp docs/huggingface-dataset-card.md dataset/README.md
```

La carpeta debería quedar así:

```
dataset/
├── README.md                    (la dataset card, con front-matter YAML)
├── repositories.parquet
├── workflow_files.parquet
└── frontmatter_attributes.parquet
```

Antes de subir, edita `dataset/README.md` y completa los datos marcados
entre `<...>` (nombre del dataset, cantidad de repos/archivos, fecha de
generación, licencia). No es necesario subir `extract.checkpoint.jsonl`
(es un archivo de progreso interno de Miner, no parte del dataset).

## 5. Subir los archivos

Con la CLI, para carpetas chicas o medianas (un solo commit):

```bash
hf upload tu-usuario/nombre-del-dataset ./dataset . --repo-type dataset
```

Para datasets grandes (varios GB o muchos archivos), usa el subidor
resumible, que tolera cortes de conexión:

```bash
hf upload-large-folder tu-usuario/nombre-del-dataset ./dataset --repo-type dataset
```

O con Python, si prefieres integrarlo al final del pipeline de Miner:

```python
from huggingface_hub import HfApi

api = HfApi()
api.upload_folder(
    folder_path="dataset",
    repo_id="tu-usuario/nombre-del-dataset",
    repo_type="dataset",
)
```

## 6. Verificar la publicación

Visita `https://huggingface.co/datasets/tu-usuario/nombre-del-dataset` y
confirma que:

- Las 3 tablas `.parquet` (`repositories`, `workflow_files`,
  `frontmatter_attributes`) aparecen en la pestaña **Files**.
- La pestaña **Dataset Viewer** puede previsualizar `workflow_files.parquet`
  automáticamente (Hugging Face detecta el formato Parquet sin
  configuración adicional).
- El `README.md` se renderiza como la descripción del dataset en la página
  principal.

## Actualizaciones posteriores

Para publicar una nueva corrida de `extract` (dataset actualizado), repite
el paso 5 — `upload`/`upload_folder` sobrescribe los archivos existentes en
el repositorio del dataset, manteniendo el historial de versiones de Git
por debajo.
