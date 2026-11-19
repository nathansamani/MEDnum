"""Configuration : toutes les valeurs propres à un livre ou à une mise en page.

Une configuration se charge depuis un fichier JSON (ou TOML si Python >= 3.11).
Toute clé absente garde sa valeur par défaut ; les clés inconnues sont refusées
pour éviter les fautes de frappe silencieuses.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    # Langue(s) tesseract utilisée(s) pour localiser les mots (ex. "fra", "eng", "fra+eng").
    "tesseract_lang": "fra",
    # Lignes à ignorer partout (filigranes, mentions de diffusion…), en expressions régulières.
    "watermarks": [],
    # Modèle de nom des images de page ; {page} est remplacé par l'identifiant de page.
    "image_pattern": "{page}.png",
    "audit": {
        # Seuil de gris (0-255) en dessous duquel un pixel compte comme de l'encre.
        "ink_gray": 200,
        # Part d'encre en dessous de laquelle la page est considérée blanche.
        "blank_ink": 0.001,
        # Nombre minimal de mots attendus sur une page encrée.
        "min_words_inked": 15,
        # Mots-outils d'une langue étrangère : leur abondance signale un texte inventé.
        "foreign_words": ["the", "function", "definition", "which", "where", "is a", "of the"],
        "foreign_min_hits": 5,
        # Mots de la seconde lecture absents de la sortie au-delà duquel on signale la page.
        "lost_words_max": 20,
        "min_word_len": 4,
        # Unités qui rendent un nombre « critique » (dose, seuil, durée…).
        "critical_units": ["%", "mg", "g", "kg", "µg", "cm", "mm", "ml", "mL", "l", "mmol",
                           "UI", "Gy", "ans", "mois", "jours", "jour", "semaines", "semaine", "h", "min"],
    },
    "textlayer": {
        # Part de surface couverte par une image au-delà de laquelle la page est une page image.
        "image_page_cover": 0.85,
        # Noms de polices typiques d'une couche OCR invisible.
        "ocr_font_names": ["GlyphLessFont", "GlyphLess"],
        # Taux de lignes terminées par un tiret au-delà duquel la couche est suspecte.
        "max_hyphen_rate": 0.25,
    },
    "correct": {
        "max_span": 2,          # nombre maximal de mots remplacés d'un bloc
        "min_len": 3,           # pas de mots de 2 lettres ou moins
        "min_ratio": 0.5,       # similarité minimale entre mot lu et mot proposé
        "max_extension": 2,     # un mot lu peut être complété de 2 lettres au plus
    },
    "zero_fix": {
        # Codes alphabétiques suivis d'un chiffre où un « o » est en fait un zéro
        # (ex. ["T", "N", "M"] pour des classifications). Vide : seulement le contexte numérique.
        "codes": [],
    },
    "markers": {
        # Lettres de marge : forme reconnue au nombre de trous de la lettre.
        "letter": {
            "zone_x": [0.035, 0.11],        # bande de marge, en fraction de largeur
            "max_y": 0.95,                  # ignorer le bas de page (folio)
            "height": [0.008, 0.03],        # hauteur relative de la lettre
            "width": [0.004, 0.03],
            "holes_to_letter": {"1": "A", "2": "B"},
            "colors": {
                "noir": {"max": [120, 120, 120]},
                "rouge": {"min": [130, 0, 0], "max": [255, 130, 120], "diff": [["r", "g", 60]]},
            },
            "empty_right": 3,               # pixels d'encre tolérés juste à droite
        },
        # Carrés colorés en marge avec lettre blanche et cadre de même couleur.
        "square": {
            "zones_x": [[0.0, 0.16], [0.84, 1.0]],
            "height": [0.015, 0.045],
            "width": [0.02, 0.06],
            "labels": {
                "A": {"min": [200, 0, 0], "max": [255, 170, 150], "diff": [["r", "g", 60]], "holes": 1},
                "B": {"min": [0, 120, 0], "max": [90, 255, 255], "diff": [["g", "r", 70], ["g", "b", 30]], "holes": 2},
            },
            "frame_search": 14,             # pixels explorés à côté du carré pour le trait du cadre
            "frame_bands_x": [[0.10, 0.15], [0.85, 0.90]],
            "frame_min_height": 0.04,
        },
    },
    "review": {
        "sheet_width": 1500,
        "row_height": 95,
        "rows_per_sheet": 24,
        "context_px": 450,
        "font": None,           # chemin d'une police TrueType ; None = police par défaut de Pillow
        "font_size": 19,
    },
    "bench": {
        "marker_letters": ["A", "B", "C"],
        "marker_window": 400,
    },
}


def _merge(base: dict, override: dict, path: str = "") -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        where = f"{path}{key}"
        if key not in base:
            raise KeyError(f"clé de configuration inconnue : {where}")
        if isinstance(base[key], dict) and isinstance(value, dict) and key not in ("labels", "colors", "holes_to_letter"):
            out[key] = _merge(base[key], value, where + ".")
        else:
            out[key] = value
    return out


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Configuration par défaut, fusionnée avec un fichier puis avec ``overrides``."""
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        path = Path(path)
        if path.suffix == ".toml":
            import tomllib  # Python >= 3.11

            data = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        cfg = _merge(cfg, data)
    if overrides:
        cfg = _merge(cfg, overrides)
    return cfg


def image_for(images_dir: str | Path, page: str, pattern: str = "{page}.png") -> Path:
    """Chemin de l'image d'une page. Essaie le modèle puis les extensions courantes."""
    images_dir = Path(images_dir)
    candidate = images_dir / pattern.format(page=page)
    if candidate.exists():
        return candidate
    for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"):
        alt = images_dir / f"{page}{ext}"
        if alt.exists():
            return alt
    return candidate
