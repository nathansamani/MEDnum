"""Marqueurs imprimés en marge (niveaux, rangs, priorités…) et leur report dans le texte.

Deux familles, entièrement paramétrables (couleurs, zones, tailles, lettres) :

- **lettre de marge** : une lettre (noire ou colorée) seule dans la marge. Sa forme
  est reconnue au nombre de trous (A = 1, B = 2 dans la plupart des polices ; C = 0).
  Une vraie lettre de marge a un espace vide à sa droite ; un numéro de titre touche
  le texte et est écarté.
- **carré coloré + cadre** : un carré plein de couleur avec une lettre blanche, et
  un cadre de la même couleur qui délimite la portée du marqueur.

Les détections ne créent aucun texte : ``insert_marker`` ajoute seulement « [X] »
devant une ligne retrouvée mot pour mot dans la transcription.
"""
from __future__ import annotations

import re
from statistics import median

import numpy as np
from PIL import Image
from scipy import ndimage

from .text import fold

CHANNELS = {"r": 0, "g": 1, "b": 2}


def color_mask(arr: np.ndarray, rule: dict) -> np.ndarray:
    """Masque des pixels d'un tableau RGB (int) qui respectent une règle de couleur.

    Règle : ``{"min": [r, g, b], "max": [r, g, b], "diff": [["r", "g", 60], ...]}``
    (``diff`` : canal1 - canal2 >= valeur). Toutes les clés sont facultatives.
    """
    mask = np.ones(arr.shape[:2], dtype=bool)
    lo, hi = rule.get("min"), rule.get("max")
    for c in range(3):
        if lo is not None:
            mask &= arr[..., c] >= lo[c]
        if hi is not None:
            mask &= arr[..., c] <= hi[c]
    for c1, c2, d in rule.get("diff", []):
        mask &= (arr[..., CHANNELS[c1]] - arr[..., CHANNELS[c2]]) >= d
    return mask


def count_holes(mask: np.ndarray, min_size: int = 4) -> int:
    """Nombre de trous (zones de fond entièrement entourées) d'une forme binaire."""
    if not mask.any():
        return 0
    ys, xs = np.where(mask)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    pad = np.pad(crop, 1)
    lab, n = ndimage.label(~pad)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    return sum(1 for i in range(1, n + 1) if i not in border and sizes[i - 1] >= min_size)


def _rgb(image) -> np.ndarray:
    if isinstance(image, np.ndarray):
        return image.astype(int)
    return np.asarray(Image.open(image).convert("RGB")).astype(int)


def detect_letters(image, cfg: dict) -> list[dict]:
    """Lettres de marge. ``cfg`` = section ``markers.letter`` de la configuration."""
    im = _rgb(image)
    h, w, _ = im.shape
    x0, x1 = int(w * cfg["zone_x"][0]), int(w * cfg["zone_x"][1])
    strip = im[:int(h * cfg["max_y"]), x0:x1]
    ink_any = np.zeros(im.shape[:2], dtype=bool)
    for rule in cfg["colors"].values():
        ink_any |= color_mask(im, rule)
    holes_map = {int(k): v for k, v in cfg["holes_to_letter"].items()}
    out = []
    for color, rule in cfg["colors"].items():
        lab, _ = ndimage.label(color_mask(strip, rule))
        for i, sl in enumerate(ndimage.find_objects(lab), 1):
            if sl is None:
                continue
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            if not (cfg["height"][0] * h < hh < cfg["height"][1] * h and cfg["width"][0] * w < ww < cfg["width"][1] * w):
                continue
            if sl[1].stop >= x1 - x0 - 1:
                continue  # touche le bord intérieur de la zone : fait partie du texte
            gx0 = sl[1].stop + x0 + 2
            right = ink_any[sl[0], gx0:gx0 + max(1, int(ww * 0.9))]
            if right.sum() > cfg["empty_right"]:
                continue  # du texte colle à droite : numéro de titre, pas une lettre de marge
            k = count_holes(lab[sl] == i)
            out.append({"lettre": holes_map.get(k, ""), "trous": k, "couleur": color,
                        "x": sl[1].start + x0, "y": (sl[0].start + sl[0].stop) // 2,
                        "y_rel": round(sl[0].start / h, 3), "x_rel": round((sl[1].start + x0) / w, 3),
                        "hauteur": hh, "largeur": ww})
    return sorted(out, key=lambda d: (d["y"], d["x"]))


def detect_squares(image, cfg: dict) -> dict:
    """Carrés colorés à lettre blanche et cadres. ``cfg`` = section ``markers.square``."""
    a = _rgb(image)
    h, w, _ = a.shape
    squares, lines = [], []
    for label, rule in cfg["labels"].items():
        m = color_mask(a, rule)
        filled = ndimage.binary_opening(ndimage.binary_closing(m, structure=np.ones((5, 5))),
                                        structure=np.ones((9, 9)))
        lab, _ = ndimage.label(filled)
        for sl in ndimage.find_objects(lab):
            if sl is None:
                continue
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            xr0, xr1 = sl[1].start / w, sl[1].stop / w
            in_zone = any(z0 <= xr0 and xr1 <= z1 for z0, z1 in cfg["zones_x"])
            if not (cfg["height"][0] * h < hh < cfg["height"][1] * h
                    and cfg["width"][0] * w < ww < cfg["width"][1] * w and in_zone):
                continue
            white = a[sl].min(axis=2) > 200
            wl, wn = ndimage.label(white)
            if wn == 0:
                continue
            sizes = ndimage.sum(white, wl, range(1, wn + 1))
            glyph = wl == (int(np.argmax(sizes)) + 1)
            k = count_holes(glyph)
            side = "gauche" if xr1 < 0.5 else "droite"
            ymid = (sl[0].start + sl[0].stop) // 2
            best = (0, ymid, ymid)
            reach = cfg["frame_search"]
            cols = (range(sl[1].stop - 4, min(w, sl[1].stop + reach)) if side == "gauche"
                    else range(max(0, sl[1].start - reach), sl[1].start + 4))
            for xc in cols:
                col = m[:, xc]
                if not col[ymid]:
                    continue
                top = ymid
                while top > 0 and col[top - 1]:
                    top -= 1
                bot = ymid
                while bot < h - 1 and col[bot + 1]:
                    bot += 1
                if bot - top > best[0]:
                    best = (bot - top, top, bot)
            expected = rule.get("holes")
            squares.append({"lettre": label, "trous": k, "forme_ok": expected is None or expected == k,
                            "x": sl[1].start, "y": ymid, "y_rel": round(sl[0].start / h, 3), "cote": side,
                            "cadre": [round(best[1] / h, 3), round(best[2] / h, 3)],
                            "cadre_px": [best[1], best[2]]})
        # Traits de cadre sans carré (portée qui continue depuis la page précédente).
        for bx0, bx1 in cfg["frame_bands_x"]:
            for xc in range(int(w * bx0), int(w * bx1)):
                col = m[:, xc]
                y = 0
                while y < h:
                    if col[y]:
                        s = y
                        while y < h and col[y]:
                            y += 1
                        if y - s > cfg["frame_min_height"] * h:
                            lines.append({"lettre": label, "haut": round(s / h, 3), "bas": round((y - 1) / h, 3)})
                    y += 1
    merged: list[dict] = []
    for line in sorted(lines, key=lambda d: (d["lettre"], d["haut"])):
        if merged and merged[-1]["lettre"] == line["lettre"] and line["haut"] <= merged[-1]["bas"] + 0.01:
            merged[-1]["bas"] = max(merged[-1]["bas"], line["bas"])
        else:
            merged.append(dict(line))
    return {"carres": sorted(squares, key=lambda d: d["y"]), "cadres": merged}


# --- Report dans la transcription -------------------------------------------------

def anchor_for(marker: dict, lines: list[dict], skip: set[str] | None = None) -> str | None:
    """Texte de la ligne (tesseract) la plus proche du marqueur, à la même hauteur, côté texte."""
    skip = skip or set()
    candidates = []
    for line in lines:
        if not [w for w in line["words"] if len(w["text"]) > 1 or w["text"].isdigit()]:
            continue
        dy = abs((line["y0"] + line["y1"]) / 2 - marker["y"])
        if marker.get("cote", "gauche") == "droite":
            dx = marker["x"] - line["x1"]
        else:
            dx = line["x0"] - marker["x"]
        if dy < 3 * (line["y1"] - line["y0"] + 1) and dx >= 0:
            candidates.append((dy, dx, line))
    if not candidates:
        return None
    line = min(candidates, key=lambda c: (c[0], c[1]))[2]
    kept = [w["text"] for w in line["words"] if not (w["text"] in skip and abs(w["x"] - marker["x"]) < 5)]
    return " ".join(kept[:8])


def lines_in_range(lines: list[dict], top: int, bottom: int) -> list[str]:
    """Lignes de texte comprises dans une portée verticale (cadre)."""
    return [" ".join(w["text"] for w in l["words"]) for l in lines if l["y0"] >= top - 2 and l["y1"] <= bottom + 2]


def insert_marker(markdown: str, anchor: str, label: str) -> tuple[str, bool]:
    """Insère ``[label]`` au début de la ligne qui contient le début de l'ancre."""
    toks = [t for t in re.findall(r"\w+", fold(anchor)) if len(t) > 2][:4]
    if len(toks) < 2:
        return markdown, False
    lines = markdown.split("\n")
    head = toks[:3]
    best = None
    for i, line in enumerate(lines):
        flat = set(re.findall(r"\w+", fold(line)))
        # tolère un mot mal lu par tesseract parmi les trois premiers
        if sum(t in flat for t in head) >= max(2, len(head) - 1):
            score = sum(t in flat for t in toks)
            if best is None or score > best[0]:
                best = (score, i)
    if best is not None:
        i = best[1]
        line = lines[i]
        if f"[{label}]" in line:
            return markdown, True
        prefix = re.match(r"^(\s*(?:#+\s*|[-*•■]\s*|\d+[.)]\s*|\|\s*)?)", line).group(1)
        lines[i] = prefix + f"[{label}] " + line[len(prefix):]
        return "\n".join(lines), True
    return markdown, False


def place(markdown: str, markers: list[dict], lines: list[dict]) -> tuple[str, int]:
    """Insère tous les marqueurs dotés d'une lettre. Renvoie (texte, nombre placé)."""
    placed = 0
    skip = {m["lettre"] for m in markers}
    for m in markers:
        if not m.get("lettre"):
            continue
        anchor = anchor_for(m, lines, skip)
        if anchor:
            markdown, ok = insert_marker(markdown, anchor, m["lettre"])
            placed += ok
    return markdown, placed


def char_height(lines: list[dict]) -> float:
    hs = [w["h"] for l in lines for w in l["words"] if len(w["text"]) > 3]
    return median(hs) if hs else 20.0
