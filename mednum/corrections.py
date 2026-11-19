"""Corrections vérifiées : remplacement de mots, recollage des coupures, zéros lus « o ».

Format d'un fichier de corrections (JSON) :
    [{"page": "0012", "lu": "mot_lu", "correct": "mot_imprimé"}, ...]
    [{"page": "0012", "lu": "exem- ple", "correct": "exemple", "exact": true}, ...]

Une correction ne s'applique qu'à sa page. Sans ``exact``, elle remplace le mot
entier (y compris sa forme coupée « pré-fixe » quand préfixe + mot == correction)
en conservant la casse. Avec ``exact``, la chaîne est remplacée telle quelle
(utile pour les coupures « exem-\\nple »).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .text import match_case, split_front_matter


def apply_word(text: str, wrong: str, right: str) -> tuple[str, int]:
    pattern = re.compile(r"(?<![\w-])(?:(\w+)-)?(" + re.escape(wrong) + r")(?!\w)", re.IGNORECASE)
    count = 0

    def repl(m):
        nonlocal count
        prefix, word = m.group(1), m.group(2)
        count += 1
        if prefix and (prefix + word).lower() == right.lower().replace("-", ""):
            return match_case(prefix, right)
        if prefix and right.lower().startswith(prefix.lower() + "-"):
            return match_case(prefix, right)
        return (prefix + "-" if prefix else "") + match_case(word, right)

    return pattern.sub(repl, text), count


def apply_exact(text: str, wrong: str, right: str) -> tuple[str, int]:
    return text.replace(wrong, right), text.count(wrong)


def fix_zero_as_o(text: str, codes: list[str] | None = None) -> tuple[str, int]:
    """Remplace un « o » lu à la place d'un zéro.

    Toujours : contexte numérique strict (« 1o5 », « 4o ans », « o,5 », « 1,o »).
    Avec ``codes`` (ex. ["T", "N", "M"]) : « No » -> « N0 » quand le code est collé
    à un autre code de la liste ou isolé (« T2No », « No »).
    """
    total = 0
    text, n = re.subn(r"(?<=\d)[oO](?=\d)", "0", text); total += n
    text, n = re.subn(r"(?<=\d)[oO](?![^\W\d_])", "0", text); total += n
    text, n = re.subn(r"(?<![\w.,])[oO](?=[.,]\d)", "0", text); total += n
    text, n = re.subn(r"(?<=\d[.,])[oO](?!\w)", "0", text); total += n
    if codes:
        alt = "|".join(re.escape(c) for c in codes)
        code_tok = rf"(?:{alt})(?:\d[a-d]?|[oO])"
        rx = re.compile(rf"(?<![\w])(?:[a-z]?)(?:{code_tok})+(?![\w])")

        def repl(m):
            return re.sub(rf"({alt})[oO]", r"\g<1>0", m.group())

        new = rx.sub(repl, text)
        total += sum(1 for a, b in zip(text, new) if a != b)
        text = new
    return text, total


def hyphen_join_candidates(text: str, vocabulary: Counter | None = None) -> list[dict]:
    """Coupures de fin de ligne restées dans le texte (« exem- ple », « exem-\\nple »).

    Si un ``vocabulary`` (compteur de mots du livre) est fourni, une coupure n'est
    proposée que si le mot recollé y existe ailleurs : c'est une preuve, pas une devinette.
    """
    out = []
    for m in re.finditer(r"(?<![\w-])(\w{2,})-[ \t]*\n?[ \t]*(\w{2,})(?![\w-])", text):
        if "\n" not in m.group() and " " not in m.group():
            continue  # vrai trait d'union, pas une coupure
        joined = m.group(1) + m.group(2)
        if m.group(2)[:1].isupper():
            continue
        if vocabulary is not None and vocabulary.get(joined.lower(), 0) == 0:
            continue
        out.append({"lu": m.group(), "correct": joined, "exact": True})
    return out


def vocabulary_of(folder: str | Path) -> Counter:
    vocab: Counter = Counter()
    for md in Path(folder).glob("*.md"):
        vocab.update(w.lower() for w in re.findall(r"\w+", md.read_text(encoding="utf-8")))
    return vocab


def apply_file(corrections: list[dict], folder: str | Path, write: bool = False,
               zero_codes: list[str] | None = None, zero_pages: list[str] | None = None) -> list[dict]:
    """Applique les corrections page par page. Renvoie le journal (remplacements par correction).

    Rien n'est écrit sans ``write=True``. Une correction sans effet est signalée (0).
    """
    folder = Path(folder)
    by_page: dict[str, list[dict]] = {}
    for item in corrections:
        by_page.setdefault(str(item["page"]), []).append(item)
    for page in zero_pages or []:
        by_page.setdefault(str(page), [])
    log = []
    for page, items in sorted(by_page.items()):
        path = folder / f"{page}.md"
        if not path.exists():
            log.append({"page": page, "erreur": "page absente"})
            continue
        head, body = split_front_matter(path.read_text(encoding="utf-8"))
        new = body
        for item in items:
            fn = apply_exact if item.get("exact") else apply_word
            new, count = fn(new, item["lu"], item["correct"])
            log.append({**item, "remplacements": count})
        if zero_pages and page in [str(p) for p in zero_pages]:
            new, count = fix_zero_as_o(new, zero_codes)
            log.append({"page": page, "lu": "o", "correct": "0", "remplacements": count})
        if write and new != body:
            path.write_text(head + new, encoding="utf-8")
    return log


def load(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
