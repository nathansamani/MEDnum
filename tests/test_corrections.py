from collections import Counter

from mednum import corrections as c


def test_apply_word_keeps_case_and_hyphen_prefix():
    assert c.apply_word("Attentlve et attentlve", "attentlve", "attentive") == ("Attentive et attentive", 2)
    assert c.apply_word("une sur-veillance", "veillance", "surveillance")[0] == "une surveillance"
    assert c.apply_word("ATTENTLVE", "attentlve", "attentive")[0] == "ATTENTIVE"
    assert c.apply_word("attentlves", "attentlve", "attentive")[1] == 0   # mot entier seulement


def test_zero_as_o():
    assert c.fix_zero_as_o("plus de 4o ans, 1o5 cas, o,5 mg, 1,o g")[0] == "plus de 40 ans, 105 cas, 0,5 mg, 1,0 g"
    assert c.fix_zero_as_o("un mot normal")[1] == 0
    assert c.fix_zero_as_o("classe T2No et No", ["T", "N", "M"])[0] == "classe T2N0 et N0"
    assert c.fix_zero_as_o("classe T2No")[0] == "classe T2No"      # sans codes : rien


def test_hyphen_candidates():
    text = "une surveil- lance et une surveil-\nlance mais un mot-clé"
    vocab = Counter({"surveillance": 3})
    found = c.hyphen_join_candidates(text, vocab)
    assert [f["correct"] for f in found] == ["surveillance", "surveillance"]
    assert c.hyphen_join_candidates("des exem- ples", Counter()) == []


def test_apply_file(tmp_path):
    (tmp_path / "0001.md").write_text("---\n{\"page\": 1}\n---\nune surveillance attentlve de 4o ans\n")
    corr = [{"page": "0001", "lu": "attentlve", "correct": "attentive"},
            {"page": "0001", "lu": "absent", "correct": "x"}]
    log = c.apply_file(corr, tmp_path, write=False, zero_pages=["0001"])
    assert [l["remplacements"] for l in log] == [1, 0, 1]
    assert "attentlve" in (tmp_path / "0001.md").read_text()
    c.apply_file(corr, tmp_path, write=True, zero_pages=["0001"])
    assert (tmp_path / "0001.md").read_text() == "---\n{\"page\": 1}\n---\nune surveillance attentive de 40 ans\n"
