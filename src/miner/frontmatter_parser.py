"""
Parseo de archivos .md de GitHub Agentic Workflows.

Responsabilidad única: dado el contenido crudo de un archivo .md, separar el
frontmatter YAML del body Markdown, y transformar el frontmatter (que puede
tener estructura anidada y variable entre workflows) en filas planas
clave-valor. No sabe nada de GitHub ni de CSV/Parquet -- eso vive en otros
módulos.
"""
from __future__ import annotations

from typing import Any, List, Tuple

import frontmatter
import yaml
from frontmatter.default_handlers import YAMLHandler

from miner.models import FrontmatterAttribute


class _GHAWSafeLoader(yaml.SafeLoader):
    """
    SafeLoader que solo interpreta true/false como booleanos (estilo YAML
    1.2), no on/off/yes/no ("el problema de Noruega": YAML 1.1 interpreta
    `no` como False). Esto importa mucho acá: `on:` es la clave más común
    en un workflow de GitHub Actions/gh-aw, y sin este ajuste se
    convertiría silenciosamente en la clave booleana `True`, corrompiendo
    el frontmatter -- y lo mismo aplicaría a cualquier valor "yes"/"no".
    """


_GHAWSafeLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if not (tag == "tag:yaml.org,2002:bool" and first_char in "oOyYnN")
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class _GHAWYAMLHandler(YAMLHandler):
    def load(self, fm: str, **kwargs: object) -> Any:
        kwargs.setdefault("Loader", _GHAWSafeLoader)
        return yaml.load(fm, **kwargs)  # type: ignore[arg-type]


_HANDLER = _GHAWYAMLHandler()


def parse_markdown(content: str) -> Tuple[dict, str]:
    """
    Separa un archivo .md en (frontmatter_dict, body_markdown).

    Si el archivo no tiene frontmatter válido (delimitado por `---`) o el
    YAML está mal formado, se devuelve un dict vacío y el contenido completo
    como body -- nunca se lanza una excepción por contenido inesperado, ya
    que a la escala de miles de repositorios siempre habrá archivos atípicos.

    Se usa frontmatter.parse() (no .loads()) porque .loads() intenta
    reconstruir un objeto Post pasando el metadata como **kwargs, lo que
    revienta con TypeError si alguna clave no quedó como string. Además se
    usa un handler de YAML personalizado (_GHAWYAMLHandler) para que `on:`
    y similares no se interpreten como booleanos.
    """
    try:
        metadata, body = frontmatter.parse(content, handler=_HANDLER)
    except Exception:
        return {}, content

    if not isinstance(metadata, dict):
        return {}, body
    return metadata, body


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    return "str"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def flatten_frontmatter(data: Any, prefix: str = "") -> List[FrontmatterAttribute]:
    """
    Aplana un valor YAML (dict/list anidado) en filas (key_path, value,
    value_type), usando dot-notation para claves de dict y `[i]` para
    posiciones de lista. Ejemplos:

        {"permissions": {"contents": "read"}}
            -> key_path="permissions.contents", value="read", value_type="str"

        {"on": {"schedule": ["0 9 * * 1", "0 9 * * 3"]}}
            -> key_path="on.schedule[0]", value="0 9 * * 1", value_type="str"
            -> key_path="on.schedule[1]", value="0 9 * * 3", value_type="str"

    Los contenedores vacíos ({} o []) se registran como una fila propia
    (con value_type "dict"/"list") en vez de desaparecer silenciosamente,
    para no perder la información de que la clave existía.
    """
    attributes: List[FrontmatterAttribute] = []

    if isinstance(data, dict):
        if not data:
            if prefix:
                attributes.append(FrontmatterAttribute(key_path=prefix, value="{}", value_type="dict"))
            return attributes
        for key, value in data.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            attributes.extend(flatten_frontmatter(value, child_prefix))
        return attributes

    if isinstance(data, list):
        if not data:
            if prefix:
                attributes.append(FrontmatterAttribute(key_path=prefix, value="[]", value_type="list"))
            return attributes
        for i, value in enumerate(data):
            attributes.extend(flatten_frontmatter(value, f"{prefix}[{i}]"))
        return attributes

    # Valor escalar (hoja): str, int, float, bool, None
    if prefix:
        attributes.append(FrontmatterAttribute(key_path=prefix, value=_stringify(data), value_type=_type_name(data)))
    return attributes
