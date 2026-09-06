from miner.detector import matching_file_pairs


def test_matching_file_pairs_preserva_casing_original():
    filenames = ["Daily-Report.md", "daily-report.lock.yml", "README.md"]
    pairs = matching_file_pairs(filenames)
    assert pairs == [("Daily-Report.md", "daily-report.lock.yml")]


def test_matching_file_pairs_multiples_pares():
    filenames = ["a.md", "a.lock.yml", "b.md", "b.lock.yaml", "c.md"]
    pairs = matching_file_pairs(filenames)
    assert set(pairs) == {("a.md", "a.lock.yml"), ("b.md", "b.lock.yaml")}


def test_matching_file_pairs_sin_pares():
    assert matching_file_pairs(["a.md", "b.lock.yml"]) == []


def test_matching_file_pairs_lista_vacia():
    assert matching_file_pairs([]) == []


def test_matching_file_pairs_orden_deterministico_por_nombre_base():
    filenames = ["z.md", "z.lock.yml", "a.md", "a.lock.yml"]
    pairs = matching_file_pairs(filenames)
    assert [md for md, _ in pairs] == ["a.md", "z.md"]
