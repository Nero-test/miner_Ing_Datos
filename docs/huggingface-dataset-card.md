---
license: <completar-licencia, ej. mit>
task_categories:
  - other
tags:
  - github
  - github-actions
  - agentic-workflows
  - llm-agents
pretty_name: <Nombre legible del dataset>
size_categories:
  - n<1K
---

# <Nombre del dataset>

Dataset relacional con repositorios de GitHub que usan
[GitHub Agentic Workflows (GH-AW)](https://github.github.com/gh-aw/), y el
contenido estructurado (frontmatter YAML + body Markdown) de sus archivos de
workflow.

Generado con [Miner](https://github.com/<tu-usuario>/miner), una CLI en
Python que identifica repositorios que usan GH-AW y extrae sus workflows
`.md` en un formato analítico.

- **Repositorios incluidos:** `<completar>`
- **Archivos de workflow incluidos:** `<completar>`
- **Fecha de generación:** `<completar, ej. 2026-09-05>`

## Estructura del dataset

El dataset está compuesto por 3 tablas Parquet relacionadas:

| Tabla | Filas ≈ | Descripción |
|---|---|---|
| `repositories.parquet` | 1 por repo | Repositorios de GitHub que usan GH-AW. |
| `workflow_files.parquet` | 1 por archivo `.md` | Frontmatter completo (como JSON) + body Markdown de cada workflow. |
| `frontmatter_attributes.parquet` | N por archivo | Atributos del frontmatter aplanados como pares clave-valor (ej. `permissions.contents`, `on.schedule[0].cron`) — el frontmatter de GH-AW varía entre workflows, así que no se fuerzan columnas fijas. |

Esquema entidad-relación completo y diccionario de datos (tipos, PKs, FKs)
disponibles en el repositorio de Miner: `docs/er-diagram.md` y
`docs/data-dictionary.md`.

## Cómo cargar el dataset

```python
from datasets import load_dataset

files = load_dataset("tu-usuario/nombre-del-dataset", data_files="workflow_files.parquet")
attrs = load_dataset("tu-usuario/nombre-del-dataset", data_files="frontmatter_attributes.parquet")
```

O directamente con pandas:

```python
import pandas as pd
from huggingface_hub import hf_hub_download

path = hf_hub_download("tu-usuario/nombre-del-dataset", "workflow_files.parquet", repo_type="dataset")
files = pd.read_parquet(path)
```

## Cómo se generó

1. Se identificaron repositorios candidatos y se filtraron los que usan
   GH-AW (al menos un par `<nombre>.md` + `<nombre>.lock.yml` en
   `.github/workflows/`).
2. Para cada repositorio identificado, se descargó cada archivo `.md` de
   workflow y se separó su frontmatter YAML del body Markdown.
3. El frontmatter se aplanó en pares clave-valor (tabla
   `frontmatter_attributes`) y se conservó completo como JSON en
   `workflow_files.raw_frontmatter`, para no perder ningún campo.

## Limitaciones

- Solo incluye repositorios **públicos** accesibles con un token de GitHub
  estándar al momento de la generación.
- Es una instantánea (snapshot): los workflows pueden cambiar o eliminarse
  después de la fecha de generación indicada arriba.
- `has_lock` es siempre `true` en este dataset: solo se incluyen archivos
  `.md` que tienen su `.lock.yml`/`.lock.yaml` compilado confirmado (la
  definición de "usa GH-AW" de este proyecto).

## Licencia

`<completar>` — ten en cuenta que el *contenido* de cada workflow (el body
Markdown y el frontmatter) es propiedad de sus respectivos repositorios de
origen y puede tener su propia licencia; este dataset agrega y estructura
metadatos públicos, no releva la licencia del código fuente original.
