"""Données SYNTHÉTIQUES pour les tests et la démonstration (aucun contenu réel).

Produit des pages image (Pillow) et des PDF (PyMuPDF) : page de texte, tableau,
page blanche, lettre de marge, carré coloré avec cadre ; ainsi que deux
« lectures » simulées comportant des erreurs typiques des modèles.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAGE = (1240, 1754)  # A4 à 150 dpi

TEXT_LINES = [  # sans accents : la police par défaut de Pillow ne les dessine pas
    "Chapitre 1 - Exemple de page de test",
    "La dose initiale est de 5 mg par jour pendant 3 semaines.",
    "Le seuil d'alerte vaut 12 % pour les sujets de plus de 40 ans.",
    "Une surveillance attentive reste utile chez tous les patients.",
    "Les mesures sont reprises au bout de vingt minutes de repos.",
    "Ce paragraphe contient seulement du texte fictif pour les essais.",
]
TABLE = [["Parametre", "Valeur", "Unite"], ["Volume", "250", "ml"], ["Duree", "48", "h"], ["Taux", "7,5", "%"]]


def font(size: int = 28):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow ancien
        return ImageFont.load_default()


def text_page(lines=TEXT_LINES, size=PAGE, x=200, y0=150, step=60, font_size=28) -> tuple[Image.Image, list]:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    f = font(font_size)
    boxes = []
    for i, line in enumerate(lines):
        y = y0 + i * step
        d.text((x, y), line, fill="black", font=f)
        boxes.append((x, y, line))
    return img, boxes


def table_page(rows=TABLE, size=PAGE, x0=200, y0=200, col=260, row=70, font_size=28) -> Image.Image:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    f = font(font_size)
    for r, cells in enumerate(rows):
        for c, cell in enumerate(cells):
            box = (x0 + c * col, y0 + r * row, x0 + (c + 1) * col, y0 + (r + 1) * row)
            d.rectangle(box, outline="black", width=2)
            d.text((box[0] + 15, box[1] + 18), cell, fill="black", font=f)
    return img


def table_markdown(rows=TABLE) -> str:
    head = "| " + " | ".join(rows[0]) + " |"
    sep = "|" + "---|" * len(rows[0])
    return "\n".join([head, sep] + ["| " + " | ".join(r) + " |" for r in rows[1:]]) + "\n"


def blank_page(size=PAGE) -> Image.Image:
    return Image.new("RGB", size, "white")


def add_margin_letter(img: Image.Image, letter: str, y: int, x: int = 75, color=(0, 0, 0), font_size=34):
    ImageDraw.Draw(img).text((x, y), letter, fill=color, font=font(font_size))
    return img


def add_square_marker(img: Image.Image, letter: str, y: int, color, x: int = 40, side: int = 44,
                      frame_to: int | None = None, font_size=34):
    """Carré plein + lettre blanche + cadre (trait vertical à droite du carré, puis horizontaux)."""
    d = ImageDraw.Draw(img)
    d.rectangle((x, y, x + side, y + side), fill=color)
    f = font(font_size)
    bb = d.textbbox((0, 0), letter, font=f)
    d.text((x + (side - (bb[2] - bb[0])) // 2 - bb[0], y + (side - (bb[3] - bb[1])) // 2 - bb[1]),
           letter, fill="white", font=f)
    if frame_to:
        fx = x + side + 7
        top, bottom = y - 10, frame_to
        d.rectangle((fx, top, fx + 3, bottom), fill=color)
        d.rectangle((fx, top, img.width - 100, top + 3), fill=color)
        d.rectangle((fx, bottom - 3, img.width - 100, bottom), fill=color)
    return img


def digital_pdf(path: Path, pages: list[str]):
    """PDF à couche numérique (polices embarquées)."""
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page(width=595, height=842)
        html = "".join(f"<p>{line}</p>" for line in text.splitlines())
        page.insert_htmlbox(pymupdf.Rect(60, 60, 535, 780), html)
    doc.save(str(path))


def scanned_pdf(path: Path, images: list[Path], hidden_text: list[str] | None = None):
    """PDF de pages image, avec éventuellement une couche OCR invisible (police non embarquée)."""
    import pymupdf

    doc = pymupdf.open()
    for i, image in enumerate(images):
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, filename=str(image))
        if hidden_text:
            page.insert_text((60, 80), hidden_text[i], fontname="helv", fontsize=10, render_mode=3)
    doc.save(str(path))


def build_demo(out: str | Path) -> dict:
    """Jeu complet : pages/, ref/, lecture1/, lecture2/, PDF numérique et PDF scanné."""
    out = Path(out)
    for sub in ("pages", "ref", "lecture1", "lecture2"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    # 0001 : texte + lettres de marge
    img, boxes = text_page()
    add_margin_letter(img, "A", boxes[1][1])
    add_margin_letter(img, "B", boxes[3][1], color=(200, 30, 30))
    img.save(out / "pages" / "0001.png")
    ref1 = "\n".join(TEXT_LINES[:1]) + "\n" + "[A] " + TEXT_LINES[1] + "\n" + TEXT_LINES[2] + "\n" + \
           "[B] " + TEXT_LINES[3] + "\n" + "\n".join(TEXT_LINES[4:]) + "\n"
    (out / "ref" / "0001.md").write_text(ref1, encoding="utf-8")
    (out / "ref" / "0001.critical.json").write_text(json.dumps([
        {"texte": "5 mg", "type": "valeur"}, {"texte": "12 %", "type": "valeur"}, {"texte": "40 ans", "type": "valeur"},
        {"texte": "A", "type": "marqueur", "contexte": TEXT_LINES[1]},
        {"texte": "B", "type": "marqueur", "contexte": TEXT_LINES[3]},
    ], ensure_ascii=False), encoding="utf-8")
    plain = "\n".join(TEXT_LINES) + "\n"
    # Lecture 1 : une faute de lecture et un zéro lu « o » ; lecture 2 : un mot perdu.
    (out / "lecture1" / "0001.md").write_text(
        plain.replace("attentive", "attentlve").replace("40 ans", "4o ans"), encoding="utf-8")
    (out / "lecture2" / "0001.md").write_text(plain.replace(" de repos", ""), encoding="utf-8")
    # 0002 : tableau
    table_page().save(out / "pages" / "0002.png")
    (out / "ref" / "0002.md").write_text(table_markdown(), encoding="utf-8")
    (out / "lecture1" / "0002.md").write_text(table_markdown(), encoding="utf-8")
    (out / "lecture2" / "0002.md").write_text(table_markdown().replace("250", "25O"), encoding="utf-8")
    # 0003 : page blanche, lecture 1 invente du texte
    blank_page().save(out / "pages" / "0003.png")
    (out / "ref" / "0003.md").write_text("", encoding="utf-8")
    (out / "lecture1" / "0003.md").write_text("The function of the page is a definition of the model which is shown.\n", encoding="utf-8")
    (out / "lecture2" / "0003.md").write_text("", encoding="utf-8")
    # 0004 : carré coloré + cadre
    img, boxes = text_page()
    add_square_marker(img, "A", boxes[1][1] - 8, (230, 110, 100), frame_to=boxes[2][1] + 50)
    add_square_marker(img, "B", boxes[4][1] - 8, (40, 170, 90), frame_to=boxes[5][1] + 50)
    img.save(out / "pages" / "0004.png")
    for sub in ("lecture1", "lecture2"):
        (out / sub / "0004.md").write_text(plain, encoding="utf-8")
    ref4 = plain.replace(TEXT_LINES[1], "[A] " + TEXT_LINES[1]).replace(TEXT_LINES[4], "[B] " + TEXT_LINES[4])
    (out / "ref" / "0004.md").write_text(ref4, encoding="utf-8")
    # PDF
    digital_pdf(out / "numerique.pdf", ["\n".join(TEXT_LINES), table_markdown()])
    scanned_pdf(out / "scanne.pdf", [out / "pages" / "0001.png", out / "pages" / "0002.png"],
                hidden_text=["texte ocr invisible", "autre texte"])
    return {"dossier": str(out)}
