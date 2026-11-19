import numpy as np
from PIL import Image

from mednum import markers
from mednum.config import load_config
from mednum.synthetic import add_margin_letter, add_square_marker, text_page

CFG = load_config()["markers"]


def test_color_mask():
    arr = np.array([[[230, 110, 100], [40, 170, 90], [0, 0, 0]]])
    m = markers.color_mask(arr, CFG["square"]["labels"]["A"])
    assert m.tolist() == [[True, False, False]]


def test_count_holes():
    o = np.zeros((9, 9), bool)
    o[1:8, 1:8] = True
    o[3:6, 3:6] = False
    assert markers.count_holes(o) == 1
    o[1:8, 4] = True
    assert markers.count_holes(o, min_size=1) == 2


def test_letters(demo):
    found = markers.detect_letters(demo / "pages" / "0001.png", CFG["letter"])
    assert [(f["lettre"], f["couleur"]) for f in found] == [("A", "noir"), ("B", "rouge")]


def test_letter_touching_text_rejected():
    img, boxes = text_page(x=120)          # texte tout près de la marge
    add_margin_letter(img, "A", boxes[1][1], x=100)
    assert markers.detect_letters(img_to_array(img), CFG["letter"]) == []


def test_letter_mapping_configurable():
    img, boxes = text_page()
    add_margin_letter(img, "C", boxes[2][1])
    cfg = load_config(overrides={"markers": {"letter": {"holes_to_letter": {"0": "C", "1": "A", "2": "B"}}}})
    found = markers.detect_letters(img_to_array(img), cfg["markers"]["letter"])
    assert [f["lettre"] for f in found] == ["C"]


def test_squares_and_frames(demo):
    res = markers.detect_squares(demo / "pages" / "0004.png", CFG["square"])
    sq = res["carres"]
    assert [s["lettre"] for s in sq] == ["A", "B"]
    assert all(s["forme_ok"] for s in sq)
    assert all(s["cadre"][1] - s["cadre"][0] > 0.05 for s in sq)


def test_frame_continuation_without_square():
    img, _ = text_page()
    a = np.asarray(img).copy()
    x = int(a.shape[1] * 0.12)
    a[200:600, x:x + 3] = (40, 170, 90)
    res = markers.detect_squares(a, CFG["square"])
    assert res["carres"] == []
    assert res["cadres"] and res["cadres"][0]["lettre"] == "B"


def test_square_wrong_shape_flagged():
    img, boxes = text_page()
    add_square_marker(img, "B", boxes[1][1], (230, 110, 100))   # lettre B dans la couleur de A
    sq = markers.detect_squares(img_to_array(img), CFG["square"])["carres"]
    assert sq and sq[0]["lettre"] == "A" and sq[0]["forme_ok"] is False


def test_insert_marker():
    md = "# Titre\n- La dose initiale est de 5 mg.\nAutre ligne de texte."
    out, ok = markers.insert_marker(md, "La dose initiale est", "A")
    assert ok and out.splitlines()[1] == "- [A] La dose initiale est de 5 mg."
    out2, ok2 = markers.insert_marker(out, "La dose initiale est", "A")
    assert ok2 and out2 == out
    _, miss = markers.insert_marker(md, "phrase absente du texte", "B")
    assert not miss


def test_place_with_simulated_lines():
    lines = [{"words": [{"text": t, "x": 200 + 60 * i, "y": 100, "w": 50, "h": 20} for i, t in enumerate("La dose initiale est".split())],
              "x0": 200, "x1": 440, "y0": 100, "y1": 120}]
    md, n = markers.place("Titre\nLa dose initiale est de 5 mg.", [{"lettre": "B", "x": 80, "y": 110}], lines)
    assert n == 1 and "[B] La dose" in md


def img_to_array(img: Image.Image):
    return np.asarray(img)
