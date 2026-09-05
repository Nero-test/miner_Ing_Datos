from miner.frontmatter_parser import flatten_frontmatter, parse_markdown


# ------------------------------------------------------------------
# parse_markdown
# ------------------------------------------------------------------
def test_separa_frontmatter_y_body_simple():
    content = """---
on: push
permissions:
  contents: read
---
# Daily report

Genera un resumen diario.
"""
    metadata, body = parse_markdown(content)
    assert metadata == {"on": "push", "permissions": {"contents": "read"}}
    assert body.strip() == "# Daily report\n\nGenera un resumen diario."


def test_sin_frontmatter_devuelve_metadata_vacia_y_body_completo():
    content = "# Solo markdown\n\nSin frontmatter aquí.\n"
    metadata, body = parse_markdown(content)
    assert metadata == {}
    assert body.rstrip("\n") == content.rstrip("\n")


def test_yaml_malformado_no_lanza_excepcion():
    content = """---
on: [push
permissions: {contents: read
---
# Body
"""
    metadata, body = parse_markdown(content)
    assert metadata == {}
    assert body == content  # se conserva el contenido completo, nada se pierde


def test_frontmatter_vacio():
    content = """---
---
# Solo título
"""
    metadata, body = parse_markdown(content)
    assert metadata == {}
    assert body.strip() == "# Solo título"


def test_clave_on_no_se_interpreta_como_booleano():
    # YAML 1.1 interpreta 'on:' como True -- este es el campo más común en
    # workflows de gh-aw/GitHub Actions, así que debe quedar como string "on".
    content = """---
on:
  schedule:
    - cron: "0 9 * * 1"
permissions:
  contents: read
---
body
"""
    metadata, _ = parse_markdown(content)
    assert "on" in metadata
    assert True not in metadata
    assert metadata["on"] == {"schedule": [{"cron": "0 9 * * 1"}]}


# ------------------------------------------------------------------
# flatten_frontmatter
# ------------------------------------------------------------------
def test_valores_escalares_de_primer_nivel():
    result = flatten_frontmatter({"on": "push", "timeout_minutes": 30, "draft": False})
    as_dict = {a.key_path: (a.value, a.value_type) for a in result}
    assert as_dict == {
        "on": ("push", "str"),
        "timeout_minutes": ("30", "int"),
        "draft": ("False", "bool"),
    }


def test_dict_anidado_usa_dot_notation():
    result = flatten_frontmatter({"permissions": {"contents": "read", "issues": "write"}})
    as_dict = {a.key_path: a.value for a in result}
    assert as_dict == {
        "permissions.contents": "read",
        "permissions.issues": "write",
    }


def test_lista_de_escalares_usa_notacion_de_indice():
    result = flatten_frontmatter({"on": {"schedule": ["0 9 * * 1", "0 9 * * 3"]}})
    as_dict = {a.key_path: a.value for a in result}
    assert as_dict == {
        "on.schedule[0]": "0 9 * * 1",
        "on.schedule[1]": "0 9 * * 3",
    }


def test_lista_de_dicts():
    result = flatten_frontmatter({"tools": [{"name": "search"}, {"name": "fetch"}]})
    as_dict = {a.key_path: a.value for a in result}
    assert as_dict == {
        "tools[0].name": "search",
        "tools[1].name": "fetch",
    }


def test_contenedores_vacios_se_registran_sin_perderse():
    result = flatten_frontmatter({"tools": {}, "labels": []})
    as_dict = {a.key_path: (a.value, a.value_type) for a in result}
    assert as_dict == {
        "tools": ("{}", "dict"),
        "labels": ("[]", "list"),
    }


def test_frontmatter_vacio_no_genera_filas():
    assert flatten_frontmatter({}) == []


def test_valor_none_se_representa_como_null():
    result = flatten_frontmatter({"description": None})
    assert result[0].key_path == "description"
    assert result[0].value == ""
    assert result[0].value_type == "null"
