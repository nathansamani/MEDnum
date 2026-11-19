import sys
import types

from mednum import ocr


def test_read_pages_with_fake_reader(tmp_path):
    images = []
    for name in ("0001", "0002"):
        p = tmp_path / f"{name}.png"
        p.write_bytes(b"")
        images.append(p)
    calls = []

    def reader(image):
        calls.append(image)
        return f"texte de {image[-8:-4]}"

    out = tmp_path / "out"
    ocr.read_pages(reader, images, out, log=None)
    assert (out / "0001.md").read_text() == "texte de 0001"
    ocr.read_pages(reader, images, out, log=None)  # reprise : rien de relu
    assert len(calls) == 2


def test_mlx_reader_simulated(monkeypatch):
    calls = {}
    fake = types.ModuleType("mlx_vlm")

    class Model:
        config = {"fictif": True}

    def load(model_id):
        calls["load"] = model_id
        return Model(), "processeur"

    def generate(model, processor, prompt, image, max_tokens, temperature, verbose):
        calls["gen"] = (prompt, image, max_tokens, temperature)
        return types.SimpleNamespace(text="# Titre\nTexte lu")

    fake.load, fake.generate = load, generate
    utils = types.ModuleType("mlx_vlm.prompt_utils")
    utils.apply_chat_template = lambda processor, config, prompt, num_images: f"<img>{prompt}"
    monkeypatch.setitem(sys.modules, "mlx_vlm", fake)
    monkeypatch.setitem(sys.modules, "mlx_vlm.prompt_utils", utils)

    reader = ocr.MlxReader("modele/fictif", prompt="Lis.", max_tokens=100)
    assert reader("page.png") == "# Titre\nTexte lu"
    assert calls["load"] == "modele/fictif"
    assert calls["gen"] == ("<img>Lis.", ["page.png"], 100, 0.0)


def test_disagreements_types():
    first = "La dose est de 4o mg et le texte reste stable."
    second = "La dose est de 40 mg et le texte stable ajout."
    ds = ocr.disagreements(first, second)
    kinds = {d["type"] for d in ds}
    assert {"different", "seulement_1", "seulement_2"} <= kinds
    diff = next(d for d in ds if d["type"] == "different")
    assert (diff["lecture1"], diff["lecture2"]) == ("4o", "40")
    assert first[diff["pos1"][0]:diff["pos1"][1]] == "4o"


def test_disagreements_ignore_accents():
    assert ocr.disagreements("une etude", "une étude", ignore_case_accents=True) == []
    assert ocr.disagreements("une etude", "une étude")


def test_agreement_rate():
    assert ocr.agreement_rate("a b c d", "a b c d") == 1.0
    assert ocr.agreement_rate("a b c d", "a b") == 0.5


def test_compare_dirs(demo):
    items = ocr.compare_dirs(demo / "lecture1", demo / "lecture2")
    pairs = {(i["page"], i["lecture1"], i["lecture2"]) for i in items}
    assert ("0001", "4o", "40") in pairs
    assert ("0001", "attentlve", "attentive") in pairs
    assert [i["id"] for i in items] == list(range(len(items)))
