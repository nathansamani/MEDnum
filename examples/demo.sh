#!/bin/sh
# Démonstration de bout en bout sur des données SYNTHÉTIQUES (aucun modèle requis,
# tesseract facultatif pour l'étape « markers place » et « review locate »).
set -e
OUT="${1:-examples/output}"
mednum demo "$OUT"

echo "== Couche texte"
mednum textlayer analyze "$OUT/numerique.pdf"
mednum textlayer analyze "$OUT/scanne.pdf"

echo "== Audit de la première lecture (seconde lecture comme témoin)"
mednum audit "$OUT/lecture1" --images "$OUT/pages" --second "$OUT/lecture2" --detail

echo "== Désaccords entre les deux lectures"
mednum ocr compare "$OUT/lecture1" "$OUT/lecture2" -o "$OUT/douteux.json"

echo "== Repérage et planches de vérification"
mednum --lang eng review locate "$OUT/douteux.json" --images "$OUT/pages" || true
mednum review sheets "$OUT/douteux.json" --images "$OUT/pages" -o "$OUT/planches"

echo "== Marqueurs de marge"
mednum markers detect "$OUT/pages/0001.png"
mednum markers detect "$OUT/pages/0004.png" --kind carre

echo "== Score contre la référence"
mednum bench "$OUT/ref" "$OUT/lecture1" "$OUT/lecture2" --detail
