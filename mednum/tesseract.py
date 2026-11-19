"""Mots à coordonnées via tesseract (sortie TSV). Sert à localiser, pas à transcrire."""
from __future__ import annotations

import csv
import io
import shutil
import subprocess
from pathlib import Path


def available() -> bool:
    return shutil.which("tesseract") is not None


def parse_tsv(tsv: str) -> list[dict]:
    """Mots (niveau 5) d'une sortie TSV tesseract."""
    words = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        if not text or row.get("level") != "5":
            continue
        try:
            words.append({
                "text": text,
                "x": int(row["left"]), "y": int(row["top"]),
                "w": int(row["width"]), "h": int(row["height"]),
                "conf": float(row["conf"]),
                "line": (row["block_num"], row["par_num"], row["line_num"]),
            })
        except (KeyError, ValueError):
            continue
    return words


def words(image: str | Path, lang: str = "fra", psm: int = 3, timeout: int = 180) -> list[dict]:
    out = subprocess.run(["tesseract", str(image), "stdout", "-l", lang, "--psm", str(psm), "tsv"],
                         capture_output=True, text=True, timeout=timeout).stdout
    return parse_tsv(out)


def lines_of(words_: list[dict]) -> list[dict]:
    """Regroupe les mots par ligne tesseract, triés de gauche à droite."""
    groups: dict = {}
    for w in words_:
        groups.setdefault(w["line"], []).append(w)
    lines = []
    for ws in groups.values():
        ws.sort(key=lambda w: w["x"])
        lines.append({"words": ws, "x0": ws[0]["x"], "x1": ws[-1]["x"] + ws[-1]["w"],
                      "y0": min(w["y"] for w in ws), "y1": max(w["y"] + w["h"] for w in ws)})
    return sorted(lines, key=lambda l: (l["y0"], l["x0"]))


class Cache:
    """Mémorise les mots tesseract par image (une page est souvent consultée plusieurs fois)."""

    def __init__(self, lang: str = "fra", reader=None):
        self.lang = lang
        self.reader = reader or (lambda image: words(image, lang=self.lang))
        self._data: dict[str, list[dict]] = {}

    def __call__(self, image: str | Path) -> list[dict]:
        key = str(image)
        if key not in self._data:
            self._data[key] = self.reader(image)
        return self._data[key]
