import json

from PIL import Image

from mednum import review
from mednum.ocr import compare_dirs


def fake_words():
    text = "Une surveillance attentive reste utile chez tous les patients."
    return [{"text": t, "x": 200 + 80 * i, "y": 340, "w": 70, "h": 24} for i, t in enumerate(text.split())]


def test_locate_by_context():
    item = {"lecture1": "attentlve", "lecture2": "attentive",
            "contexte": "Une surveillance attentlve reste utile chez"}
    bbox, score = review.locate(item, fake_words())
    assert bbox == [360, 340, 70, 24] and score > 0.8


def test_locate_all_and_sheets(demo, tmp_path):
    items = compare_dirs(demo / "lecture1", demo / "lecture2")
    review.locate_all(items, demo / "pages", lambda image: fake_words())
    assert all(i["bbox"] for i in items if i["page"] == "0001")
    index = review.make_sheets(items, demo / "pages", tmp_path / "planches", {"rows_per_sheet": 2},
                               decisions={str(items[0]["id"]): "2"})
    assert sum(len(x["ids"]) for x in index) == len(items) - 1
    sheet = Image.open(tmp_path / "planches" / index[0]["planche"])
    assert sheet.width == 1500
    assert json.loads((tmp_path / "planches" / "index.json").read_text()) == index


def test_apply_decisions(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    (tmp_path / "a" / "0001.md").write_text("La dose de 4o mg reste attentlve chez tous.")
    (tmp_path / "b" / "0001.md").write_text("La dose de 40 mg reste attentive chez tous les patients.")
    items = compare_dirs(tmp_path / "a", tmp_path / "b")
    by = {i["lecture1"] or i["lecture2"]: str(i["id"]) for i in items}
    decisions = {by["4o"]: "2", by["attentlve"]: "attentive", by["les patients"]: "2"}
    log = review.apply_decisions(items, decisions, tmp_path / "a", write=True)
    assert {l["statut"] for l in log} == {"remplace", "insere"}
    assert (tmp_path / "a" / "0001.md").read_text() == "La dose de 40 mg reste attentive chez tous les patients."
    # le fichier a changé : un second passage est refusé
    log2 = review.apply_decisions(items, {by["4o"]: "2"}, tmp_path / "a")
    assert log2[0]["statut"].startswith("refuse")


def test_decision_keep_first(tmp_path):
    (tmp_path / "0001.md").write_text("mot")
    items = [{"id": 0, "page": "0001", "lecture1": "mot", "lecture2": "mat", "pos1": [0, 3]}]
    assert review.apply_decisions(items, {"0": "1"}, tmp_path) == []
    assert review.apply_decisions(items, {"0": "?"}, tmp_path) == []
