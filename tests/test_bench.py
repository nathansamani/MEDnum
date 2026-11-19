from mednum import bench


def test_perfect_and_errors():
    ref = "La dose est de 5 mg.\n[A] Ligne classee importante ici."
    crit = [{"texte": "5 mg", "type": "valeur"},
            {"texte": "A", "type": "marqueur", "contexte": "Ligne classee importante"}]
    r = bench.score_page(ref, crit, ref)
    assert r["wer"] == 0 and r["critiques"] == [1, 1] and r["marqueurs"] == [1, 1]
    r = bench.score_page(ref, crit, "La dose est de 6 mg.\nLigne classee importante ici.")
    assert r["wer"] > 0 and r["critiques"] == [0, 1] and r["marqueurs"] == [0, 1]


def test_markdown_ignored():
    assert bench.score_page("Titre\nmot un", [], "# **Titre**\n- mot un")["wer"] == 0


def test_table_marker():
    ref = "| Ligne importante | A |\n|---|---|"
    crit = [{"texte": "A", "type": "marqueur", "contexte": "Ligne importante"}]
    assert bench.score_page(ref, crit, "| Ligne importante | A |")["marqueurs_tableau"] == [1, 1]


def test_empty_reference():
    assert bench.score_page("", [], "")["wer"] == 0
    assert bench.score_page("", [], "texte invente")["wer"] == 1


def test_score_dirs(demo):
    res = bench.score_dirs(demo / "ref", demo / "ref")
    assert res["total"]["wer"] == 0 and res["total"]["pages"] == 4
    res = bench.score_dirs(demo / "ref", demo / "lecture1")
    assert res["total"]["wer"] > 0
    assert res["total"]["critiques"] == [2, 3]
    assert "WER" in bench.format_total("x", res["total"])
