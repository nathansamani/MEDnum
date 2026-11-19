"""Audit indépendant d'un dossier de pages transcrites.

Pour chaque page : encre réelle de l'image, page blanche avec texte (texte
inventé), page encrée sans texte, texte dans une autre langue, mots de la
seconde lecture absents de la sortie, valeurs critiques perdues, mots collés.
"""
from __future__ import annotations

import collections
import re
import unicodedata
from pathlib import Path

from PIL import Image

from .config import image_for
from .text import drop_watermarks, fold, read_body, strip_tags, words


def ink_ratio(image: str | Path, gray: int = 200, size: tuple[int, int] = (300, 400)) -> float:
    """Part de pixels sombres d'une image réduite (0 = page blanche)."""
    img = Image.open(image).convert("L").resize(size)
    data = img.tobytes()
    return sum(1 for v in data if v < gray) / len(data)


def critical_values(text: str, units: list[str]) -> set[str]:
    """Valeurs « critiques » : comparaisons chiffrées et nombres suivis d'une unité."""
    text = unicodedata.normalize("NFKC", strip_tags(text)).replace(" ", " ").replace("\xa0", " ")
    text = re.sub(r"(?<=\d) (?=\d{3}\b)", "", text)          # 10 000 -> 10000
    unit_rx = "|".join(re.escape(u) for u in sorted(units, key=len, reverse=True))
    rx = re.compile(r"[<>≤≥]=?\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?(?:%s)(?![\w])" % unit_rx)
    return {re.sub(r"\s", "", v.replace(",", ".")) for v in rx.findall(text)}


def lost_words(reference: str, output: str, min_len: int = 4) -> collections.Counter:
    """Mots présents dans ``reference`` (seconde lecture) mais absents de ``output``."""
    return collections.Counter(words(reference, min_len)) - collections.Counter(words(output, min_len))


def foreign_hits(text: str, stopwords: list[str]) -> int:
    if not stopwords:
        return 0
    rx = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(w) for w in stopwords), re.IGNORECASE)
    return len(rx.findall(text))


def glued_words(output: str, reference: str = "", min_len: int = 3) -> list[str]:
    """Mots collés : « motmot » là où la seconde lecture a « mot mot »,
    ou transition minuscule→Majuscule à l'intérieur d'un mot (« finDébut »)."""
    found = []
    out_tokens = re.findall(r"\w+", strip_tags(output))
    if reference:
        ref = [fold(t) for t in re.findall(r"\w+", strip_tags(reference))]
        pairs = {ref[i] + ref[i + 1]: f"{ref[i]} {ref[i + 1]}" for i in range(len(ref) - 1)
                 if len(ref[i]) >= min_len and len(ref[i + 1]) >= min_len}
        known = set(ref)
        for tok in out_tokens:
            f = fold(tok)
            if f in pairs and f not in known:
                found.append(f"{tok} -> {pairs[f]}")
    for tok in out_tokens:
        if re.search(r"[a-zà-ÿ]{%d,}[A-ZÀ-Þ][a-zà-ÿ]{%d,}" % (min_len, min_len), tok):
            found.append(tok)
    return sorted(set(found))


def audit_page(output: str, image: str | Path | None = None, second: str = "", cfg: dict | None = None,
               watermarks: list[str] | None = None) -> dict:
    """Problèmes d'une page. ``cfg`` est la section ``audit`` de la configuration."""
    from .config import DEFAULTS

    cfg = {**DEFAULTS["audit"], **(cfg or {})}
    watermarks = watermarks or []
    out = drop_watermarks(output, watermarks)
    second = drop_watermarks(second, watermarks)
    level = ink_ratio(image, cfg["ink_gray"]) if image and Path(image).exists() else None
    n_words = len(strip_tags(out).split())
    problems = []
    if level is not None and level < cfg["blank_ink"] and n_words > 0:
        problems.append("blanche_avec_texte")
    if level is not None and level >= cfg["blank_ink"] and n_words < cfg["min_words_inked"]:
        problems.append("encre_sans_texte")
    if foreign_hits(out, cfg["foreign_words"]) >= cfg["foreign_min_hits"]:
        problems.append("langue_etrangere")
    lost = lost_words(second, out, cfg["min_word_len"]) if second else collections.Counter()
    n_lost = sum(lost.values())
    if n_lost >= cfg["lost_words_max"]:
        problems.append(f"mots_perdus:{n_lost}")
    crit = sorted(critical_values(second, cfg["critical_units"]) - critical_values(out, cfg["critical_units"])) if second else []
    if crit:
        problems.append("valeurs_perdues:" + ",".join(crit[:8]))
    glued = glued_words(out, second)
    if glued:
        problems.append("mots_colles:" + ",".join(glued[:8]))
    return {"encre_pct": None if level is None else round(level * 100, 3), "mots": n_words,
            "mots_perdus": dict(lost.most_common(20)), "valeurs_perdues": crit, "mots_colles": glued,
            "problemes": problems}


def audit_folder(output_dir: str | Path, images_dir: str | Path | None = None,
                 second_dir: str | Path | None = None, cfg: dict | None = None) -> list[dict]:
    """Audit de toutes les pages ``*.md`` d'un dossier. ``cfg`` = configuration complète."""
    from .config import DEFAULTS

    cfg = cfg or DEFAULTS
    rows = []
    for md in sorted(Path(output_dir).glob("*.md")):
        page = md.stem
        image = image_for(images_dir, page, cfg["image_pattern"]) if images_dir else None
        second = read_body(Path(second_dir) / md.name) if second_dir else ""
        res = audit_page(read_body(md), image, second, cfg["audit"], cfg["watermarks"])
        rows.append({"page": page, **res})
    return rows


def summary(rows: list[dict]) -> dict:
    flagged = [r for r in rows if r["problemes"]]
    kinds = collections.Counter(p.split(":")[0] for r in flagged for p in r["problemes"])
    return {"pages": len(rows), "signalees": len(flagged), "types": dict(kinds)}
