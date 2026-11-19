"""Lecture des pages par un modèle de vision local, double lecture et désaccords.

Un « lecteur » est tout objet appelable ``lecteur(chemin_image) -> str``.
``MlxReader`` enveloppe mlx_vlm (importé seulement à l'usage) ; les tests
utilisent des lecteurs simulés.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path
from typing import Callable, Iterable

from .text import fold, strip_tags

DEFAULT_PROMPT = ("Transcris fidèlement tout le texte de cette page en Markdown, dans l'ordre de lecture. "
                  "Tableaux en Markdown. N'invente rien, ne résume rien, ne traduis rien.")

Reader = Callable[[str], str]


class MlxReader:
    """Lecteur fondé sur mlx_vlm (Apple Silicon). Le modèle est chargé au premier appel."""

    def __init__(self, model_id: str, prompt: str = DEFAULT_PROMPT, max_tokens: int = 6000,
                 temperature: float = 0.0):
        self.model_id, self.prompt = model_id, prompt
        self.max_tokens, self.temperature = max_tokens, temperature
        self._model = self._processor = None
        self.load_seconds = 0.0

    def _load(self):
        if self._model is None:
            from mlx_vlm import load  # dépendance optionnelle

            t0 = time.time()
            self._model, self._processor = load(self.model_id)
            self.load_seconds = round(time.time() - t0, 1)

    def __call__(self, image: str) -> str:
        self._load()
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        formatted = apply_chat_template(self._processor, self._model.config, self.prompt, num_images=1)
        result = generate(self._model, self._processor, formatted, image=[str(image)],
                          max_tokens=self.max_tokens, temperature=self.temperature, verbose=False)
        return getattr(result, "text", result)


def read_pages(reader: Reader, images: Iterable[Path], out_dir: Path, overwrite: bool = False,
               log: Callable[[str], None] | None = print) -> list[dict]:
    """Lit chaque image et écrit ``<out_dir>/<page>.md``. Reprend là où on s'est arrêté."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for image in images:
        image = Path(image)
        target = out_dir / f"{image.stem}.md"
        if target.exists() and not overwrite:
            continue
        t0 = time.time()
        text = reader(str(image))
        target.write_text(text, encoding="utf-8")
        row = {"page": image.stem, "s": round(time.time() - t0, 1), "chars": len(text)}
        report.append(row)
        if log:
            log(f"{row['page']} {row['s']} s {row['chars']} car")
    (out_dir / "run.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


TOKEN = re.compile(r"\w+(?:['’]\w+)*|[<>≤≥±=%]")


def tokens(text: str) -> list[tuple[int, int, str]]:
    """Mots avec positions dans le texte (balises HTML neutralisées en espaces)."""
    clean = re.sub(r"</?[a-zA-Z][^<>]*>", lambda m: " " * len(m.group()), text)
    return [(m.start(), m.end(), m.group()) for m in TOKEN.finditer(clean)]


def disagreements(first: str, second: str, context: int = 5, ignore_case_accents: bool = False) -> list[dict]:
    """Désaccords mot à mot entre deux lectures de la même page.

    Chaque désaccord donne les mots de chaque lecture et un contexte tiré de la
    première. Ce sont des candidats à l'arbitrage visuel, pas des erreurs certaines.
    """
    a, b = tokens(first), tokens(second)
    key = (lambda t: fold(t)) if ignore_case_accents else (lambda t: t)
    sm = difflib.SequenceMatcher(None, [key(t[2]) for t in a], [key(t[2]) for t in b], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        ctx = " ".join(t[2] for t in a[max(0, i1 - context):min(len(a), i2 + context)])
        out.append({
            "type": {"replace": "different", "delete": "seulement_1", "insert": "seulement_2"}[op],
            "lecture1": " ".join(t[2] for t in a[i1:i2]),
            "lecture2": " ".join(t[2] for t in b[j1:j2]),
            "pos1": [a[i1][0], a[i2 - 1][1]] if i2 > i1 else [a[i1 - 1][1] if i1 else 0] * 2,
            "contexte": ctx,
        })
    return out


def agreement_rate(first: str, second: str) -> float:
    """Part des mots de la première lecture confirmés par la seconde."""
    a = [fold(t[2]) for t in tokens(strip_tags(first))]
    b = [fold(t[2]) for t in tokens(strip_tags(second))]
    if not a:
        return 1.0 if not b else 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(blk.size for blk in sm.get_matching_blocks()) / len(a)


def compare_dirs(dir1: Path, dir2: Path, min_len: int = 1) -> list[dict]:
    """Désaccords de toutes les pages présentes dans les deux dossiers de lectures."""
    items = []
    for p1 in sorted(Path(dir1).glob("*.md")):
        p2 = Path(dir2) / p1.name
        if not p2.exists():
            continue
        t1, t2 = p1.read_text(encoding="utf-8"), p2.read_text(encoding="utf-8")
        for d in disagreements(t1, t2):
            if max(len(d["lecture1"]), len(d["lecture2"])) < min_len:
                continue
            items.append({"page": p1.stem, **d})
    for i, item in enumerate(items):
        item["id"] = i
    return items
