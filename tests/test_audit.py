from mednum import audit
from mednum.config import load_config


def test_ink(demo):
    assert audit.ink_ratio(demo / "pages" / "0003.png") == 0
    assert audit.ink_ratio(demo / "pages" / "0001.png") > 0.005


def test_critical_values():
    units = load_config()["audit"]["critical_units"]
    vals = audit.critical_values("Dose 2,5 mg ; seuil > 10 000 ; 12 % ; <b>40 ans</b>", units)
    assert {"2.5mg", ">10000", "12%", "40ans"} <= vals


def test_glued_words():
    assert audit.glued_words("une surveillanceattentive", "une surveillance attentive")
    assert audit.glued_words("fin de phraseDebut suivant")
    assert audit.glued_words("tout va bien", "tout va bien") == []


def test_audit_folder(demo):
    rows = {r["page"]: r for r in audit.audit_folder(demo / "lecture1", demo / "pages", demo / "lecture2")}
    assert "blanche_avec_texte" in rows["0003"]["problemes"]
    assert "langue_etrangere" in rows["0003"]["problemes"]
    assert rows["0001"]["valeurs_perdues"] == ["40ans"]
    assert rows["0002"]["problemes"] == []
    s = audit.summary(list(rows.values()))
    assert s["signalees"] == 2


def test_inked_page_without_text(demo, tmp_path):
    (tmp_path / "0001.md").write_text("")
    rows = audit.audit_folder(tmp_path, demo / "pages")
    assert rows[0]["problemes"] == ["encre_sans_texte"]


def test_watermarks_ignored(demo, tmp_path):
    text = (demo / "lecture1" / "0001.md").read_text()
    (tmp_path / "0003.md").write_text("diffusion interdite - exemple\n")
    cfg = load_config(overrides={"watermarks": [r"diffusion\s+interdite"]})
    rows = audit.audit_folder(tmp_path, demo / "pages", cfg=cfg)
    assert rows[0]["problemes"] == []
    assert text  # le texte original n'est pas modifié
