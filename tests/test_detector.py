from miner.detector import matching_pairs, uses_gh_aw


def test_md_con_su_lock_yml_usa_gh_aw():
    # report.md + report.lock.yml -> utiliza GH-AW
    assert uses_gh_aw(["report.md", "report.lock.yml"]) is True


def test_solo_md_no_usa_gh_aw():
    # report.md solamente -> no utiliza GH-AW
    assert uses_gh_aw(["report.md"]) is False


def test_solo_lock_no_usa_gh_aw():
    # report.lock.yml solamente -> no utiliza GH-AW
    assert uses_gh_aw(["report.lock.yml"]) is False


def test_nombres_base_distintos_no_usa_gh_aw():
    # report.md + other.lock.yml -> no utiliza GH-AW (nombres base distintos)
    assert uses_gh_aw(["report.md", "other.lock.yml"]) is False


def test_variante_lock_yaml_tambien_cuenta():
    assert uses_gh_aw(["report.md", "report.lock.yaml"]) is True


def test_comparacion_insensible_a_mayusculas():
    assert uses_gh_aw(["Report.MD", "report.lock.yml"]) is True


def test_lista_vacia_no_usa_gh_aw():
    assert uses_gh_aw([]) is False


def test_archivos_irrelevantes_se_ignoran():
    assert uses_gh_aw(["README.md", "ci.yml", "report.md", "report.lock.yml"]) is True


def test_multiples_pares_reporta_todos():
    files = ["a.md", "a.lock.yml", "b.md", "b.lock.yaml", "c.md"]
    assert uses_gh_aw(files) is True
    assert matching_pairs(files) == ["a", "b"]
