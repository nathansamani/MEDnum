"""Banc d'essai : score d'une transcription candidate contre une référence vérifiée sur l'image.

Dossier de référence : ``<page>.md`` (texte vérifié) et, facultatif,
``<page>.critical.json`` = liste de ``{"texte": "...", "type": "valeur"}`` (valeurs
critiques) et ``{"texte": "A", "type": "marqueur", "contexte": "début de la ligne"}``.

Mesures :
- **WER** : distance d'édition sur les mots / nombre de mots de la référence, après
  uniformisation (NFC, minuscules, mise en forme Markdown retirée, coupures recollées) ;
- **mots présents** : part des mots de la référence retrouvés (sans ordre) ;
- **valeurs critiques** : part retrouvée telle quelle (espaces ignorés) ;
- **marqueurs** : « [X] » retrouvé peu avant le contexte (hors tableau), ou la lettre
  seule près du contexte (dans un tableau).
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


def norm_words(text: str, letters: list[str] | None = None) -> list[str]:
    letters = letters or ["A", "B", "C"]
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"tableau\s*:", " ", text)
    text = re.sub(r"\[(%s)\]" % "|".join(re.escape(l.lower()) for l in letters), " ", text)
    text = re.sub(r"\[figure[^\]]*\]|\[illisible\]", " ", text)
    text = re.sub(r"(?m)^\s*[-•■▪·]\s+|^-{2,}$", " ", text)
    text = re.sub(r"[#*_|`]+", " ", text)
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return re.findall(r"[\wµ⁰¹²³⁴⁵⁶⁷⁸⁹⁻₀₁₂₃₄₅₆₇₈₉]+|[<>≤≥±=%/]", text)


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]


def squash(text: str) -> str:
    """Forme compacte pour retrouver une valeur : compatibilité Unicode (m² ~ m2),
    apostrophes et tirets unifiés, coupures recollées, espaces retirés."""
    text = re.sub(r"<[^>]+>", "", text)
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = text.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", "", text).lower()


def score_page(ref_md: str, critical: list[dict], cand: str, letters: list[str] | None = None,
               window: int = 400) -> dict:
    rw, cw = norm_words(ref_md, letters), norm_words(cand, letters)
    # référence vide (page blanche) : 0 si le candidat est vide aussi, 1 sinon
    wer = edit_distance(rw, cw) / len(rw) if rw else float(bool(cw))
    present = sum((Counter(rw) & Counter(cw)).values()) / len(rw) if rw else 1.0
    flat = squash(cand)
    values = [c for c in critical if c.get("type") != "marqueur" and c.get("texte")]
    found = sum(squash(c["texte"]) in flat for c in values)
    marks = [c for c in critical if c.get("type") == "marqueur"]
    lower = unicodedata.normalize("NFKC", cand).lower()
    table_lines = [l.lower() for l in ref_md.splitlines() if l.strip().startswith("|")]
    m_ok = m_n = t_ok = t_n = 0
    for r in marks:
        letter = r["texte"].strip().lower()[:1]
        ws = re.findall(r"\w{4,}", unicodedata.normalize("NFKC", r.get("contexte", "")).lower())[:3]
        in_table = any(all(w in l for w in ws[:2]) for l in table_lines) if ws else False
        anchor = next((lower.find(w) for w in ws if lower.find(w) >= 0), -1)
        if in_table:
            t_n += 1
            near = lower[max(0, anchor - window // 2):anchor + window // 2] if anchor >= 0 else ""
            t_ok += bool(re.search(rf"(^|[\s|\]\[]){re.escape(letter)}($|[\s|\]\[])", near))
        else:
            m_n += 1
            m_ok += bool(anchor >= 0 and f"[{letter}]" in lower[max(0, anchor - window):anchor + 50])
    return {"wer": round(wer, 4), "presents": round(present, 4), "critiques": [found, len(values)],
            "marqueurs": [m_ok, m_n], "marqueurs_tableau": [t_ok, t_n]}


def score_dirs(ref_dir: str | Path, cand_dir: str | Path, letters: list[str] | None = None,
               window: int = 400) -> dict:
    ref_dir, cand_dir = Path(ref_dir), Path(cand_dir)
    rows = []
    for ref in sorted(ref_dir.glob("*.md")):
        cand = cand_dir / ref.name
        if not cand.exists():
            continue
        crit_path = ref_dir / f"{ref.stem}.critical.json"
        crit = json.loads(crit_path.read_text(encoding="utf-8")) if crit_path.exists() else []
        rows.append({"page": ref.stem, **score_page(ref.read_text(encoding="utf-8"), crit,
                                                    cand.read_text(encoding="utf-8"), letters, window)})
    return {"pages": rows, "total": aggregate(rows)}


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {"pages": 0}
    n = len(rows)
    s = lambda key, i: sum(r[key][i] for r in rows)
    return {
        "pages": n,
        "wer": round(sum(r["wer"] for r in rows) / n, 4),
        "presents": round(sum(r["presents"] for r in rows) / n, 4),
        "critiques": [s("critiques", 0), s("critiques", 1)],
        "marqueurs": [s("marqueurs", 0), s("marqueurs", 1)],
        "marqueurs_tableau": [s("marqueurs_tableau", 0), s("marqueurs_tableau", 1)],
    }


def format_total(name: str, total: dict) -> str:
    if not total.get("pages"):
        return f"{name} : aucune page"
    cf, ct = total["critiques"]
    mf, mt = total["marqueurs"]
    tf, tt = total["marqueurs_tableau"]
    return (f"{name} ({total['pages']} pages) | WER {100 * total['wer']:.1f} % | mots présents "
            f"{100 * total['presents']:.1f} % | critiques {cf}/{ct} | marqueurs {mf}/{mt} | tableau {tf}/{tt}")
