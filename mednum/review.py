"""Arbitrage visuel : localiser les mots douteux sur l'image, fabriquer des planches
(extrait d'image + lectures concurrentes), puis appliquer les décisions.

Flux type :
    1. ``mednum ocr compare lecture1/ lecture2/ -o douteux.json``
    2. ``mednum review locate douteux.json --images pages/``   (ajoute bbox)
    3. ``mednum review sheets douteux.json --images pages/ -o planches/``
    4. un humain remplit ``decisions.json`` : {"<id>": "1" | "2" | "<texte>" | "?"}
    5. ``mednum review apply douteux.json decisions.json lecture1/ --ecrire``
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import image_for
from .ocr import tokens
from .text import fold


def locate(item: dict, page_words: list[dict], window: int = 5) -> tuple[list[int] | None, float]:
    """Boîte (x, y, l, h) du mot douteux sur l'image, par son contexte, sinon par le mot seul."""
    if not page_words:
        return None, 0.0
    wl = [fold(w["text"].strip(".,;:()«»")) for w in page_words]
    best = (0.0, None)
    ctx = " ".join(fold(item.get("contexte") or "").split())
    if ctx:
        for j in range(len(page_words)):
            s = difflib.SequenceMatcher(None, ctx, " ".join(wl[max(0, j - window):j + window + 1])).ratio()
            if s > best[0]:
                best = (s, j)
    targets = [t for t in (item.get("lecture1"), item.get("lecture2"), item.get("mot")) if t]
    if targets and best[1] is not None:
        # affiner : dans la fenêtre retenue, le mot le plus proche des lectures
        j0 = best[1]
        lo, hi = max(0, j0 - window), min(len(page_words), j0 + window + 1)
        sub = max(range(lo, hi), key=lambda j: max(difflib.SequenceMatcher(None, fold(t), wl[j]).ratio() for t in targets))
        best = (best[0], sub)
    elif targets:
        for j, w in enumerate(wl):
            s = max(difflib.SequenceMatcher(None, fold(t), w).ratio() for t in targets)
            if s > best[0]:
                best = (s, j)
    if best[1] is None:
        return None, 0.0
    w = page_words[best[1]]
    return [w["x"], w["y"], w["w"], w["h"]], round(best[0], 2)


def locate_all(items: list[dict], images_dir: str | Path, words_of, pattern: str = "{page}.png") -> list[dict]:
    """Ajoute ``bbox`` et ``score`` à chaque élément. ``words_of(image)`` -> mots tesseract."""
    for item in items:
        image = image_for(images_dir, str(item["page"]), pattern)
        item["bbox"], item["score"] = locate(item, words_of(image) if image.exists() else [])
    return items


def _font(path: str | None, size: int):
    if path:
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def make_sheets(items: list[dict], images_dir: str | Path, out_dir: str | Path, cfg: dict | None = None,
                pattern: str = "{page}.png", decisions: dict | None = None) -> list[dict]:
    """Planches PNG : pour chaque élément, ses lectures, son contexte et l'extrait d'image.

    Les éléments déjà tranchés dans ``decisions`` (valeur autre que « ? ») sont sautés.
    """
    from .config import DEFAULTS

    cfg = {**DEFAULTS["review"], **(cfg or {})}
    decisions = decisions or {}
    todo = [it for it in items if decisions.get(str(it["id"]), "?") == "?"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    font = _font(cfg["font"], cfg["font_size"])
    W, ROW, PER, PAD = cfg["sheet_width"], cfg["row_height"], cfg["rows_per_sheet"], cfg["context_px"]
    index = []
    for s in range(0, len(todo), PER):
        chunk = todo[s:s + PER]
        sheet = Image.new("RGB", (W, ROW * len(chunk)), "white")
        d = ImageDraw.Draw(sheet)
        for k, it in enumerate(chunk):
            y = k * ROW
            d.text((5, y + 3), f"#{it['id']} p{it['page']}  lecture 1 : «{it.get('lecture1', '')}»   "
                               f"lecture 2 : «{it.get('lecture2', '')}»", fill="blue", font=font)
            d.text((5, y + 25), f"contexte : {(it.get('contexte') or '')[:130]}", fill="darkgreen", font=font)
            if it.get("bbox"):
                image = image_for(images_dir, str(it["page"]), pattern)
                if image.exists():
                    im = Image.open(image).convert("RGB")
                    L, T, Wd, H = it["bbox"]
                    crop = im.crop((max(0, L - PAD), max(0, T - 30), min(im.width, L + Wd + PAD), min(im.height, T + H + 30)))
                    crop.thumbnail((W, ROW - 50))
                    sheet.paste(crop, (0, y + 48))
            d.line((0, y + ROW - 1, W, y + ROW - 1), fill="gray")
        name = out_dir / f"planche_{s // PER:03d}.png"
        sheet.save(name)
        index.append({"planche": name.name, "ids": [it["id"] for it in chunk]})
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def _span_matches(text: str, start: int, end: int, expected: str) -> bool:
    found = [fold(t[2]) for t in tokens(text[start:end])]
    return found == [fold(t[2]) for t in tokens(expected)]


def apply_decisions(items: list[dict], decisions: dict, folder: str | Path, write: bool = False) -> list[dict]:
    """Applique les arbitrages à la première lecture (dossier ``folder``).

    Décision par identifiant : « 1 » garde la lecture 1, « 2 » prend la lecture 2,
    tout autre texte remplace le passage, « ? » ou absence = non tranché.
    Les remplacements se font par position (celle de ``ocr compare``), de la fin
    vers le début ; un passage qui ne correspond plus au fichier est refusé.
    """
    folder = Path(folder)
    by_page: dict[str, list[dict]] = {}
    for it in items:
        dec = str(decisions.get(str(it["id"]), "?"))
        if dec in ("?", "", "1"):
            continue
        new = it.get("lecture2", "") if dec == "2" else dec
        by_page.setdefault(str(it["page"]), []).append({**it, "nouveau": new})
    log = []
    for page, its in sorted(by_page.items()):
        path = folder / f"{page}.md"
        if not path.exists():
            log += [{"id": it["id"], "page": page, "statut": "page absente"} for it in its]
            continue
        text = path.read_text(encoding="utf-8")
        for it in sorted(its, key=lambda i: i["pos1"][0], reverse=True):
            start, end = it["pos1"]
            if start == end:  # insertion : mot présent seulement dans la lecture 2
                piece = it["nouveau"]
                pre = "" if start == 0 or text[start - 1].isspace() else " "
                text = text[:start] + pre + piece + text[end:]
                log.append({"id": it["id"], "page": page, "statut": "insere", "texte": piece})
                continue
            if not _span_matches(text, start, end, it.get("lecture1", "")):
                log.append({"id": it["id"], "page": page, "statut": "refuse : texte modifié depuis la comparaison"})
                continue
            text = text[:start] + it["nouveau"] + text[end:]
            log.append({"id": it["id"], "page": page, "statut": "remplace",
                        "avant": it.get("lecture1"), "apres": it["nouveau"]})
        text = re.sub(r"[ \t]{2,}", " ", text) if any(not i["nouveau"] for i in its) else text
        if write:
            path.write_text(text, encoding="utf-8")
    return log
