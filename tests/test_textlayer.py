from mednum import textlayer


def test_digital_vs_scanned(demo):
    digital = textlayer.analyze_pdf(demo / "numerique.pdf")
    scanned = textlayer.analyze_pdf(demo / "scanne.pdf")
    assert digital["verdict"]["couche_numerique"] is True
    assert digital["detail"][0]["polices_embarquees"] >= 1
    assert scanned["verdict"]["couche_numerique"] is False
    assert scanned["verdict"]["pages_image"] == [1, 2]


def test_extract_only_digital(demo, tmp_path):
    assert textlayer.extract_layer(demo / "numerique.pdf", tmp_path / "a") == [1, 2]
    assert "dose initiale" in (tmp_path / "a" / "0001.txt").read_text()
    assert textlayer.extract_layer(demo / "scanne.pdf", tmp_path / "b") == []


def _apply(body, layer, **kw):
    return textlayer.apply_proposals(body, textlayer.proposals(body, layer, **kw))


def test_word_corrected():
    assert _apply("une surveillance attentlve reste", "une surveillance attentive reste") == \
        "une surveillance attentive reste"


def test_guards():
    # jamais de nombre
    assert _apply("dose de 4O mg", "dose de 40 mg") == "dose de 4O mg"
    # pas de mot de deux lettres
    assert _apply("il va au lit", "il va ou lit") == "il va au lit"
    # pas de troncature (mot coupé en fin de ligne dans la couche)
    assert _apply("une surveillance totale", "une surveil totale") == "une surveillance totale"


def test_accents_only_added():
    assert _apply("une etude recente", "une étude récente") == "une étude récente"
    assert _apply("une étude récente", "une etude recente") == "une étude récente"
    assert _apply("Etude", "étude") == "Étude"


def test_accents_only_mode():
    out = _apply("une etude attentlve", "une étude attentive", accents_only=True)
    assert out == "une étude attentlve"


def test_layer_hyphen_rejoined():
    assert _apply("une surveillance attentlve", "une surveil-\nlance attentive") == "une surveillance attentive"
