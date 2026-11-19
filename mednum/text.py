"""Outils de texte partagés : uniformisation, mots, en-tête de page, filigranes."""
from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

TAG = re.compile(r"</?[a-zA-Z][^<>]*>")


def strip_tags(text: str) -> str:
    """Retire les balises HTML (tableaux produits par certains modèles)."""
    return html.unescape(TAG.sub(" ", text))


def fold(text: str) -> str:
    """Minuscules sans accents (comparaison tolérante)."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text).lower())
    text = text.replace("œ", "oe").replace("æ", "ae").replace("’", "'")
    return "".join(c for c in text if not unicodedata.combining(c))


def accent_count(word: str) -> int:
    return sum(1 for c in unicodedata.normalize("NFKD", word) if unicodedata.combining(c))


def words(text: str, min_len: int = 4) -> list[str]:
    """Mots repliés d'au moins ``min_len`` caractères (lettres ou chiffres)."""
    return re.findall(r"[a-z0-9]{%d,}" % min_len, fold(strip_tags(text)))


def split_front_matter(raw: str) -> tuple[str, str]:
    """Sépare un en-tête ``---\\n...\\n---`` du corps. Renvoie (en-tête, corps)."""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            return "---" + parts[1] + "---", parts[2]
    return "", raw


def read_body(path: str | Path) -> str:
    path = Path(path)
    return split_front_matter(path.read_text(encoding="utf-8"))[1] if path.exists() else ""


def drop_watermarks(text: str, patterns: list[str]) -> str:
    """Retire les lignes qui correspondent à l'un des motifs (liste vide : rien n'est retiré)."""
    if not patterns:
        return text
    rx = re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)
    return "\n".join(line for line in text.splitlines() if not rx.search(line))


def match_case(source: str, target: str) -> str:
    """Reporte la casse de ``source`` (tout majuscule / initiale) sur ``target``."""
    if source.isupper() and len(source) > 1:
        return target.upper()
    if source[:1].isupper():
        return target[:1].upper() + target[1:]
    if source[:1].islower() and target[:1].isupper() and not target.isupper():
        return target[:1].lower() + target[1:]
    return target


def page_ids(folder: str | Path, suffix: str = ".md") -> list[str]:
    """Identifiants de page (noms de fichiers sans extension) d'un dossier, triés."""
    return sorted(p.name[: -len(suffix)] for p in Path(folder).glob(f"*{suffix}")
                  if not p.name.startswith("."))
