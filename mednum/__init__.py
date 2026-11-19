"""MEDnum : numériser des manuels scannés avec des modèles de vision locaux,
puis vérifier et corriger le résultat.

Modules :
- ``ocr``       lecture des pages (mlx_vlm), double lecture, désaccords ;
- ``audit``     pages blanches, texte inventé, mots perdus, valeurs critiques, mots collés ;
- ``textlayer`` couche texte d'un PDF : diagnostic et correction par alignement ;
- ``markers``   marqueurs de marge (lettre, carré coloré + cadre) ;
- ``review``    planches de vérification visuelle et application des arbitrages ;
- ``bench``     score contre des pages de référence (WER, valeurs critiques, marqueurs) ;
- ``corrections`` corrections de mots vérifiées, recollage des coupures, zéros lus « o ».
"""

__version__ = "0.1.0"
