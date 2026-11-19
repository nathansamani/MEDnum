import json

import pytest

from mednum.config import DEFAULTS, image_for, load_config


def test_defaults_are_generic():
    cfg = load_config()
    assert cfg["watermarks"] == []
    assert cfg["tesseract_lang"] == "fra"


def test_file_and_overrides(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"audit": {"blank_ink": 0.01}, "watermarks": ["^diffusion"]}))
    cfg = load_config(path, {"tesseract_lang": "eng"})
    assert cfg["audit"]["blank_ink"] == 0.01
    assert cfg["audit"]["min_words_inked"] == DEFAULTS["audit"]["min_words_inked"]
    assert cfg["watermarks"] == ["^diffusion"] and cfg["tesseract_lang"] == "eng"


def test_unknown_key_rejected(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"audit": {"blank_ikn": 0.01}}))
    with pytest.raises(KeyError):
        load_config(path)


def test_marker_labels_replaced_not_merged():
    cfg = load_config(overrides={"markers": {"square": {"labels": {"X": {"min": [0, 0, 200]}}}}})
    assert list(cfg["markers"]["square"]["labels"]) == ["X"]


def test_image_for(tmp_path):
    (tmp_path / "p-0007.png").write_bytes(b"")
    (tmp_path / "0008.jpg").write_bytes(b"")
    assert image_for(tmp_path, "0007", "p-{page}.png").name == "p-0007.png"
    assert image_for(tmp_path, "0008").name == "0008.jpg"
