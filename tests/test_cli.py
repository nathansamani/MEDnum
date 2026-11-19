import json

import pytest

from mednum import tesseract
from mednum.cli import main


def test_demo_audit_bench_compare(tmp_path, capsys):
    out = tmp_path / "d"
    assert main(["demo", str(out)]) == 0
    assert main(["audit", str(out / "lecture1"), "--images", str(out / "pages"),
                 "--second", str(out / "lecture2"), "--json", str(tmp_path / "a.json")]) == 0
    rows = json.loads((tmp_path / "a.json").read_text())
    assert any("blanche_avec_texte" in r["problemes"] for r in rows)
    main(["ocr", "compare", str(out / "lecture1"), str(out / "lecture2"), "-o", str(tmp_path / "d.json")])
    assert json.loads((tmp_path / "d.json").read_text())
    main(["bench", str(out / "ref"), str(out / "lecture1")])
    assert "WER" in capsys.readouterr().out
    main(["textlayer", "analyze", str(out / "numerique.pdf")])
    assert '"couche_numerique": true' in capsys.readouterr().out
    main(["markers", "detect", str(out / "pages" / "0004.png"), "--kind", "carre"])
    assert '"lettre": "A"' in capsys.readouterr().out


def test_textlayer_correct_cli(tmp_path):
    (tmp_path / "t").mkdir(); (tmp_path / "l").mkdir()
    (tmp_path / "t" / "0001.md").write_text("une etude attentlve")
    (tmp_path / "l" / "0001.txt").write_text("une étude attentive")
    main(["textlayer", "correct", str(tmp_path / "t"), str(tmp_path / "l"), "-o", str(tmp_path / "p.json")])
    assert (tmp_path / "t" / "0001.md").read_text() == "une etude attentlve"
    main(["textlayer", "correct", str(tmp_path / "t"), str(tmp_path / "l"), "--ecrire", "-o", str(tmp_path / "p.json")])
    assert (tmp_path / "t" / "0001.md").read_text() == "une étude attentive"


@pytest.mark.skipif(not tesseract.available(), reason="tesseract absent")
def test_markers_place_with_tesseract(demo, tmp_path):
    main(["--lang", "eng", "markers", "place", str(demo / "lecture2"), "--images", str(demo / "pages"),
          "-o", str(tmp_path / "m")])
    assert "[A] La dose" in (tmp_path / "m" / "0001.md").read_text()
    assert "[B] Une surveillance" in (tmp_path / "m" / "0001.md").read_text()
