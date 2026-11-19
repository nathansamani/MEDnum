"""Couche texte d'un PDF : est-elle numérique (fiable) ou une OCR plaquée ?
Et correction des mots d'une transcription par alignement sur cette couche.

Une vraie couche numérique a des polices embarquées, pas de police « invisible »
d'OCR, peu de pages réduites à une image pleine page, et peu de mots coupés.
La correction ne touche ni à la structure ni à l'ordre : elle remplace au plus
quelques mots alignés, avec des garde-fous stricts.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from .text import accent_count, fold, match_case


def _pymupdf():
    try:
        import pymupdf
    except ImportError:  # anciennes versions
        import fitz as pymupdf
    return pymupdf


def page_info(page, cfg: dict) -> dict:
    """Diagnostic d'une page PyMuPDF."""
    area = abs(page.rect) or 1.0
    fonts = page.get_fonts(full=True)
    names = [f[3] for f in fonts]
    embedded = [f for f in fonts if f[1] and f[1] != "n/a"]
    ocr_font = any(any(o.lower() in (n or "").lower() for o in cfg["ocr_font_names"]) for n in names)
    cover = 0.0
    for img in page.get_images(full=True):
        for rect in page.get_image_rects(img[0]):
            cover = max(cover, abs(rect & page.rect) / area)
    text = page.get_text("text")
    lines = [l for l in text.splitlines() if l.strip()]
    hyphen = sum(1 for l in lines if re.search(r"\w-$", l.rstrip())) / max(1, len(lines))
    is_image = cover >= cfg["image_page_cover"]
    return {
        "page": page.number + 1, "polices": len(fonts), "polices_embarquees": len(embedded),
        "police_ocr": ocr_font, "couverture_image": round(cover, 3), "page_image": is_image,
        "mots": len(text.split()), "taux_mots_coupes": round(hyphen, 3),
        "numerique": bool(text.strip()) and not ocr_font and not is_image
                     and len(embedded) > 0 and hyphen <= cfg["max_hyphen_rate"],
    }


def analyze_pdf(pdf: str | Path, cfg: dict | None = None) -> dict:
    """Diagnostic par page et verdict global sur la couche texte."""
    from .config import DEFAULTS

    cfg = {**DEFAULTS["textlayer"], **(cfg or {})}
    doc = _pymupdf().open(str(pdf))
    pages = [page_info(p, cfg) for p in doc]
    n = max(1, len(pages))
    digital = sum(p["numerique"] for p in pages)
    verdict = {
        "pages": len(pages),
        "pages_numeriques": digital,
        "pages_image": [p["page"] for p in pages if p["page_image"]],
        "pages_police_ocr": [p["page"] for p in pages if p["police_ocr"]],
        "couche_numerique": digital / n >= 0.5,
    }
    return {"verdict": verdict, "detail": pages}


def extract_layer(pdf: str | Path, out_dir: str | Path, only_digital: bool = True,
                  cfg: dict | None = None, name: str = "{page:04d}.txt") -> list[int]:
    """Écrit le texte de chaque page (numérique seulement, par défaut)."""
    from .config import DEFAULTS

    cfg = {**DEFAULTS["textlayer"], **(cfg or {})}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for page in _pymupdf().open(str(pdf)):
        if only_digital and not page_info(page, cfg)["numerique"]:
            continue
        (out_dir / name.format(page=page.number + 1)).write_text(page.get_text("text"), encoding="utf-8")
        written.append(page.number + 1)
    return written


TOK = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿœŒæÆ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿœŒ]+)*|\d+(?:[.,]\d+)?")


def proposals(body: str, layer: str, cfg: dict | None = None, accents_only: bool = False) -> list[tuple]:
    """Remplacements proposés : (début, fin, mot lu, mot de la couche).

    Garde-fous : jamais de nombre, pas de mot de ``min_len`` lettres ou moins,
    pas de troncature (coupure de ligne), extension limitée, similarité minimale ;
    sur les mots identiques à l'accent près, seuls des accents peuvent être ajoutés.
    """
    from .config import DEFAULTS

    cfg = {**DEFAULTS["correct"], **(cfg or {})}
    A = [(m.start(), m.end(), m.group()) for m in TOK.finditer(body)]
    L = [m.group() for m in TOK.finditer(layer.replace("-\n", ""))]
    sm = difflib.SequenceMatcher(None, [fold(a[2]) for a in A], [fold(x) for x in L], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and not accents_only and i2 - i1 == j2 - j1 and i2 - i1 <= cfg["max_span"]:
            for k in range(i2 - i1):
                a, b = A[i1 + k], L[j1 + k]
                na, nb = fold(a[2]), fold(b)
                if (na != nb
                        and difflib.SequenceMatcher(None, na, nb).ratio() >= cfg["min_ratio"]
                        and not any(ch.isdigit() for ch in na + nb)
                        and len(na) >= cfg["min_len"] and len(nb) >= cfg["min_len"]
                        and not (len(nb) < len(na) and na.startswith(nb))
                        and not (len(na) < len(nb) and nb.startswith(na) and len(nb) - len(na) > cfg["max_extension"])):
                    out.append((a[0], a[1], a[2], match_case(a[2], b)))
        elif op == "equal":
            for k in range(i2 - i1):
                a, b = A[i1 + k], L[j1 + k]
                ra, rb = a[2].replace("’", "'"), b.replace("’", "'")
                if (ra.lower() != rb.lower() and not any(ch.isdigit() for ch in ra)
                        and len(ra) >= cfg["min_len"] and accent_count(rb) > accent_count(ra)):
                    out.append((a[0], a[1], a[2], match_case(a[2], rb)))
    return out


def apply_proposals(body: str, props: list[tuple]) -> str:
    for start, end, _, new in sorted(props, reverse=True):
        body = body[:start] + new + body[end:]
    return body
