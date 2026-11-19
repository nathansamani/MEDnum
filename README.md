# MEDnum

Boîte à outils libre pour **numériser des manuels scannés** (médicaux ou autres) avec des
**modèles de vision locaux**, puis **vérifier et corriger** le résultat.

Un modèle de vision lit très bien une page… presque toujours. Les erreurs qui restent sont
rares, discrètes et graves : un chiffre changé dans une dose, un mot inventé sur une page
blanche, une ligne sautée, un marqueur de marge oublié. MEDnum ne promet pas une lecture
parfaite : il fournit les outils pour **trouver ces erreurs et les trancher sur l'image**.

Tout tourne en local (Apple Silicon pour la lecture par `mlx_vlm`) ; rien n'est envoyé en ligne.

## Méthode

1. **Double lecture** : deux modèles différents lisent chaque page (`mednum ocr read`).
   Leurs désaccords mot à mot (`mednum ocr compare`) sont les seuls endroits à regarder ;
   là où deux modèles indépendants s'accordent, l'erreur est rare.
2. **Arbitrage sur image** : chaque mot douteux est localisé sur la page par tesseract
   (`mednum review locate`), puis présenté sur des **planches** : les deux lectures, le
   contexte et l'extrait d'image (`mednum review sheets`). Un humain note sa décision
   (`1`, `2` ou le texte juste) ; `mednum review apply` l'applique, par position, en
   refusant tout passage modifié depuis la comparaison.
3. **Couche texte** : si le PDF possède une vraie couche numérique (polices embarquées,
   pas de police d'OCR invisible, pas de pages réduites à une image, peu de mots coupés),
   `mednum textlayer analyze` le dit et `mednum textlayer correct` corrige les mots de la
   transcription par alignement, avec des garde-fous : jamais de nombre, pas de mot de
   deux lettres ou moins, pas de troncature (coupure de ligne), accents seulement ajoutés.
   Une couche OCR plaquée sur des pages image n'est **pas** une référence.
4. **Marqueurs de marge** : niveaux, rangs ou priorités imprimés en marge
   (`mednum markers`) — lettre seule (reconnue à son nombre de trous, avec un espace vide à
   droite pour l'écarter des numéros de titre) ou carré coloré à lettre blanche avec un
   cadre qui délimite sa portée. Couleurs, zones, tailles et lettres sont paramétrables.
   Le report dans le texte n'ajoute que `[X]` devant une ligne retrouvée.
5. **Audit** (`mednum audit`) : page blanche avec du texte (texte inventé), page encrée
   sans texte, texte dans une autre langue, mots de la seconde lecture perdus, valeurs
   critiques (nombres avec unité, seuils) absentes, mots collés.
6. **Corrections vérifiées** (`mednum fix`) : liste de mots vérifiés sur l'image, recollage
   des coupures de ligne (proposé seulement si le mot recollé existe ailleurs dans le
   livre), zéros lus « o » (contexte numérique, et codes alphanumériques configurables).
7. **Banc d'essai** (`mednum bench`) : WER, mots présents, valeurs critiques et marqueurs
   contre des pages de référence vérifiées à la main.

## Résultats mesurés

Banc de **37 pages de manuels scannés** (texte courant, tableaux, encadrés), référence
vérifiée sur l'image, WER moyen par page :

| Lecture                                   | WER    |
|-------------------------------------------|--------|
| Couche texte existante du PDF (OCR)       | 21 %   |
| dots.mocr                                 | 2,3 %  |
| GLM-OCR                                   | 4,3 %  |
| Qwen3-VL 32B                              | 7,6 %  |
| PaddleOCR-VL                              | 12,2 % |

Conclusions pratiques : la couche texte d'un scan n'est pas fiable ; les meilleurs modèles
locaux font quelques erreurs par centaine de mots, ce qui reste trop pour des doses ou des
seuils — d'où la double lecture, l'audit et l'arbitrage visuel.

## Installation

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"        # numpy, scipy, Pillow, PyMuPDF, pytest
pip install -e ".[mlx]"         # lecture par modèle de vision (Apple Silicon)
brew install tesseract tesseract-lang   # repérage des mots et ancrage des marqueurs
```

## Démarrage rapide

```sh
mednum demo work/demo                       # données synthétiques
sh examples/demo.sh work/demo               # parcours complet sans modèle
pytest                                      # tests hors ligne, sans modèle
```

Sur un vrai livre (une image par page, `0001.png`, `0002.png`…) :

```sh
mednum ocr read --model <modèle-A> --images pages/ -o lecture1/
mednum ocr read --model <modèle-B> --images pages/ -o lecture2/
mednum audit lecture1/ --images pages/ --second lecture2/ --detail
mednum ocr compare lecture1/ lecture2/ -o douteux.json
mednum review locate douteux.json --images pages/
mednum review sheets douteux.json --images pages/ -o planches/
# remplir decisions.json : {"0": "2", "1": "1", "2": "texte juste", "3": "?"}
mednum review apply douteux.json decisions.json lecture1/ --ecrire
mednum markers place lecture1/ --images pages/ -o finale/ --kind lettre
```

Options globales : `-c config.toml`, `--lang` (tesseract, défaut `fra`), `--watermark`
(motif de ligne à ignorer, répétable ; aucun par défaut), `--image-pattern`.
Tous les seuils, couleurs et zones sont dans `mednum/config.py` et se surchargent par
fichier (voir `examples/config.exemple.toml`).

## Modules

| Module        | Rôle |
|---------------|------|
| `ocr`         | lecteur `mlx_vlm`, lecture d'un dossier avec reprise, désaccords entre deux lectures |
| `audit`       | encre, pages blanches, texte inventé, mots perdus, valeurs critiques, mots collés |
| `textlayer`   | diagnostic de la couche texte d'un PDF, extraction, correction par alignement |
| `markers`     | lettres de marge, carrés colorés + cadres, report `[X]` dans le texte |
| `review`      | repérage tesseract, planches visuelles, application des arbitrages |
| `corrections` | corrections vérifiées, coupures, zéros lus « o » |
| `bench`       | WER, mots présents, valeurs critiques, marqueurs |
| `synthetic`   | pages et PDF synthétiques pour les tests et la démo |

## Limites

- **Les modèles se trompent**, y compris quand deux modèles sont d'accord. L'arbitrage
  visuel reste nécessaire pour tout ce qui compte (doses, seuils, unités, négations).
- La repérage des mots douteux dépend de tesseract ; sur une page très dégradée, la
  boîte peut tomber à côté : la planche montre toujours le contexte pour s'en rendre compte.
- La détection des marqueurs repose sur des couleurs et des formes : chaque nouvelle mise
  en page demande d'ajuster la configuration et de vérifier quelques pages à l'œil.
- La correction par couche texte ne vaut que si la couche est réellement numérique.
- Les fichiers de corrections et de décisions sont propres à un livre : ils ne se
  réutilisent pas d'un livre à l'autre.
- Respectez les droits d'auteur : MEDnum ne fournit aucun contenu et ne doit servir qu'à
  numériser des documents que vous avez le droit de reproduire.

## English summary

MEDnum is an open-source toolkit to digitise scanned textbooks with **local vision models**
and to **check and fix** the output. Method: two independent model readings per page, a
word-level diff of their disagreements, visual arbitration on contact sheets (image crop +
both readings), correction against a genuine digital PDF text layer (with strict guards),
detection of margin markers (plain letters or coloured squares with frames), and an audit
for hallucinated text, blank pages, lost words and missing critical values. On a 37-page
benchmark of scanned textbooks, mean WER was 21 % for the existing text layer, 2.3 % for
dots.mocr, 4.3 % for GLM-OCR, 7.6 % for Qwen3-VL 32B and 12.2 % for PaddleOCR-VL. Models
still make mistakes: human visual arbitration remains necessary. All settings (paths,
colours, thresholds, watermarks, tesseract language) are options or config entries. Tests
run offline on synthetic data, without any model. MIT licence.

## Licence

MIT — voir `LICENSE`.
