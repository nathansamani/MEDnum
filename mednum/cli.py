"""Interface en ligne de commande ``mednum``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import image_for, load_config


def _dump(obj, path: str | None):
    text = json.dumps(obj, ensure_ascii=False, indent=1)
    if path:
        Path(path).write_text(text, encoding="utf-8")
        print(f"écrit : {path}")
    else:
        print(text)


def _cfg(args) -> dict:
    overrides: dict = {}
    if args.lang:
        overrides["tesseract_lang"] = args.lang
    if args.watermark:
        overrides["watermarks"] = args.watermark
    if args.image_pattern:
        overrides["image_pattern"] = args.image_pattern
    return load_config(args.config, overrides)


# --- ocr ---------------------------------------------------------------------------

def cmd_ocr_read(args, cfg):
    from .ocr import DEFAULT_PROMPT, MlxReader, read_pages

    prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else (args.prompt or DEFAULT_PROMPT)
    images = sorted(p for p in Path(args.images).iterdir()
                    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"})
    if args.pages:
        wanted = set(args.pages.split(","))
        images = [p for p in images if p.stem in wanted]
    reader = MlxReader(args.model, prompt, args.max_tokens)
    read_pages(reader, images, Path(args.out), overwrite=args.overwrite)


def cmd_ocr_compare(args, cfg):
    from .ocr import compare_dirs

    items = compare_dirs(Path(args.first), Path(args.second), args.min_len)
    _dump(items, args.out)
    print(f"{len(items)} désaccords", file=sys.stderr)


# --- audit -------------------------------------------------------------------------

def cmd_audit(args, cfg):
    from .audit import audit_folder, summary

    rows = audit_folder(args.folder, args.images, args.second, cfg)
    print(json.dumps(summary(rows), ensure_ascii=False))
    flagged = [r for r in rows if r["problemes"]]
    for r in flagged if args.detail else flagged[:60]:
        print(r["page"], r["encre_pct"], r["mots"], r["problemes"])
    if args.json:
        _dump(rows, args.json)


# --- textlayer ---------------------------------------------------------------------

def cmd_tl_analyze(args, cfg):
    from .textlayer import analyze_pdf

    res = analyze_pdf(args.pdf, cfg["textlayer"])
    print(json.dumps(res["verdict"], ensure_ascii=False))
    if args.json:
        _dump(res, args.json)


def cmd_tl_extract(args, cfg):
    from .textlayer import extract_layer

    pages = extract_layer(args.pdf, args.out, only_digital=not args.all, cfg=cfg["textlayer"], name=args.name)
    print(f"{len(pages)} pages écrites dans {args.out}")


def cmd_tl_correct(args, cfg):
    from .text import split_front_matter
    from .textlayer import apply_proposals, proposals

    exclude = set(args.exclude.split(",")) if args.exclude else set()
    found = {}
    for md in sorted(Path(args.folder).glob("*.md")):
        if md.stem in exclude:
            continue
        layer = Path(args.layer) / args.layer_name.format(page=md.stem)
        if not layer.exists():
            continue
        head, body = split_front_matter(md.read_text(encoding="utf-8"))
        props = proposals(body, layer.read_text(encoding="utf-8"), cfg["correct"], args.accents)
        if not props:
            continue
        found[md.stem] = [[a, b] for _, _, a, b in props]
        if args.ecrire:
            md.write_text(head + apply_proposals(body, props), encoding="utf-8")
    _dump(found, args.out)
    print(f"{len(found)} pages, {sum(len(v) for v in found.values())} remplacements"
          + ("" if args.ecrire else " proposés (rien écrit ; --ecrire pour appliquer)"), file=sys.stderr)


# --- markers -----------------------------------------------------------------------

def cmd_markers_detect(args, cfg):
    from .markers import detect_letters, detect_squares

    out = {}
    for image in args.images:
        if args.kind == "lettre":
            out[image] = detect_letters(image, cfg["markers"]["letter"])
        else:
            out[image] = detect_squares(image, cfg["markers"]["square"])
    _dump(out, args.json)


def cmd_markers_place(args, cfg):
    from . import tesseract
    from .markers import detect_letters, detect_squares, lines_in_range, place

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for md in sorted(Path(args.folder).glob("*.md")):
        image = image_for(args.images, md.stem, cfg["image_pattern"])
        if not image.exists():
            continue
        if args.kind == "lettre":
            found = detect_letters(image, cfg["markers"]["letter"])
        else:
            found = detect_squares(image, cfg["markers"]["square"])["carres"]
        lines = tesseract.lines_of(tesseract.words(image, cfg["tesseract_lang"])) if found else []
        text, placed = place(md.read_text(encoding="utf-8"), found, lines)
        (out_dir / md.name).write_text(text, encoding="utf-8")
        row = {"page": md.stem, "marqueurs": len(found), "places": placed}
        if args.kind == "carre":
            row["portees"] = [{"lettre": m["lettre"], "lignes": lines_in_range(lines, *m["cadre_px"])} for m in found]
        report.append(row)
        print(md.stem, len(found), "marqueurs,", placed, "placés", flush=True)
    (out_dir / "marqueurs.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


# --- review ------------------------------------------------------------------------

def cmd_review_locate(args, cfg):
    from . import tesseract
    from .review import locate_all

    items = json.loads(Path(args.items).read_text(encoding="utf-8"))
    locate_all(items, args.images, tesseract.Cache(cfg["tesseract_lang"]), cfg["image_pattern"])
    _dump(items, args.out or args.items)
    print(f"{sum(1 for i in items if i.get('bbox'))}/{len(items)} localisés", file=sys.stderr)


def cmd_review_sheets(args, cfg):
    from .review import make_sheets

    items = json.loads(Path(args.items).read_text(encoding="utf-8"))
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8")) if args.decisions else {}
    index = make_sheets(items, args.images, args.out, cfg["review"], cfg["image_pattern"], decisions)
    print(f"{len(index)} planches dans {args.out}")


def cmd_review_apply(args, cfg):
    from .review import apply_decisions

    items = json.loads(Path(args.items).read_text(encoding="utf-8"))
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    log = apply_decisions(items, decisions, args.folder, args.ecrire)
    _dump(log, args.log)
    if not args.ecrire:
        print("rien écrit (--ecrire pour appliquer)", file=sys.stderr)


# --- fix ---------------------------------------------------------------------------

def cmd_fix_words(args, cfg):
    from .corrections import apply_file, load

    corrections = load(args.corrections) if args.corrections else []
    zero_pages = args.zero_pages.split(",") if args.zero_pages else None
    log = apply_file(corrections, args.folder, args.ecrire, cfg["zero_fix"]["codes"], zero_pages)
    print(json.dumps({"operations": len(log), "sans_effet": [l for l in log if l.get("remplacements") == 0]},
                     ensure_ascii=False, indent=1))
    if not args.ecrire:
        print("rien écrit (--ecrire pour appliquer)", file=sys.stderr)


def cmd_fix_hyphens(args, cfg):
    from .corrections import hyphen_join_candidates, vocabulary_of

    vocab = vocabulary_of(args.folder)
    items = []
    for md in sorted(Path(args.folder).glob("*.md")):
        for c in hyphen_join_candidates(md.read_text(encoding="utf-8"), None if args.all else vocab):
            items.append({"page": md.stem, **c})
    _dump(items, args.out)


# --- bench / demo ------------------------------------------------------------------

def cmd_bench(args, cfg):
    from .bench import format_total, score_dirs

    for cand in args.candidates:
        res = score_dirs(args.ref, cand, cfg["bench"]["marker_letters"], cfg["bench"]["marker_window"])
        print(format_total(cand, res["total"]))
        if args.detail:
            for r in res["pages"]:
                print(f"   {r['page']} WER {100 * r['wer']:5.1f} % présents {100 * r['presents']:5.1f} % "
                      f"critiques {r['critiques'][0]}/{r['critiques'][1]} marqueurs {r['marqueurs'][0]}/{r['marqueurs'][1]}")


def cmd_demo(args, cfg):
    from .synthetic import build_demo

    build_demo(args.out)
    print(f"données synthétiques écrites dans {args.out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mednum", description="Numériser des manuels scannés et vérifier le résultat.")
    p.add_argument("--version", action="version", version=f"mednum {__version__}")
    p.add_argument("-c", "--config", help="fichier de configuration JSON ou TOML")
    p.add_argument("--lang", help="langue tesseract (défaut : fra)")
    p.add_argument("--watermark", action="append", help="motif de ligne à ignorer (répétable)")
    p.add_argument("--image-pattern", help="nom des images de page, ex. 'page-{page}.png'")
    sub = p.add_subparsers(dest="cmd", required=True)

    ocr = sub.add_parser("ocr", help="lecture par modèle de vision, double lecture").add_subparsers(dest="sub", required=True)
    s = ocr.add_parser("read", help="lire des images avec un modèle mlx_vlm")
    s.add_argument("--model", required=True, help="identifiant du modèle (ex. dépôt Hugging Face local)")
    s.add_argument("--images", required=True)
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--prompt")
    s.add_argument("--prompt-file")
    s.add_argument("--max-tokens", type=int, default=6000)
    s.add_argument("--pages", help="identifiants séparés par des virgules")
    s.add_argument("--overwrite", action="store_true")
    s.set_defaults(func=cmd_ocr_read)
    s = ocr.add_parser("compare", help="désaccords entre deux lectures")
    s.add_argument("first"); s.add_argument("second")
    s.add_argument("-o", "--out")
    s.add_argument("--min-len", type=int, default=1)
    s.set_defaults(func=cmd_ocr_compare)

    s = sub.add_parser("audit", help="pages blanches, texte inventé, mots perdus, valeurs critiques, mots collés")
    s.add_argument("folder")
    s.add_argument("--images")
    s.add_argument("--second", help="dossier de la seconde lecture")
    s.add_argument("--json")
    s.add_argument("--detail", action="store_true")
    s.set_defaults(func=cmd_audit)

    tl = sub.add_parser("textlayer", help="couche texte d'un PDF").add_subparsers(dest="sub", required=True)
    s = tl.add_parser("analyze", help="la couche est-elle numérique ?")
    s.add_argument("pdf"); s.add_argument("--json")
    s.set_defaults(func=cmd_tl_analyze)
    s = tl.add_parser("extract", help="écrire le texte des pages numériques")
    s.add_argument("pdf"); s.add_argument("-o", "--out", required=True)
    s.add_argument("--all", action="store_true", help="aussi les pages non numériques")
    s.add_argument("--name", default="{page:04d}.txt")
    s.set_defaults(func=cmd_tl_extract)
    s = tl.add_parser("correct", help="corriger les mots par alignement sur la couche")
    s.add_argument("folder"); s.add_argument("layer")
    s.add_argument("--layer-name", default="{page}.txt")
    s.add_argument("--exclude", help="pages à exclure (pages image), séparées par des virgules")
    s.add_argument("--accents", action="store_true", help="seulement restaurer des accents")
    s.add_argument("--ecrire", action="store_true")
    s.add_argument("-o", "--out")
    s.set_defaults(func=cmd_tl_correct)

    mk = sub.add_parser("markers", help="marqueurs de marge").add_subparsers(dest="sub", required=True)
    s = mk.add_parser("detect", help="détecter les marqueurs d'images")
    s.add_argument("images", nargs="+")
    s.add_argument("--kind", choices=["lettre", "carre"], default="lettre")
    s.add_argument("--json")
    s.set_defaults(func=cmd_markers_detect)
    s = mk.add_parser("place", help="insérer [X] dans les transcriptions (ancrage tesseract)")
    s.add_argument("folder"); s.add_argument("--images", required=True); s.add_argument("-o", "--out", required=True)
    s.add_argument("--kind", choices=["lettre", "carre"], default="lettre")
    s.set_defaults(func=cmd_markers_place)

    rv = sub.add_parser("review", help="arbitrage visuel").add_subparsers(dest="sub", required=True)
    s = rv.add_parser("locate", help="localiser les mots douteux sur l'image")
    s.add_argument("items"); s.add_argument("--images", required=True); s.add_argument("-o", "--out")
    s.set_defaults(func=cmd_review_locate)
    s = rv.add_parser("sheets", help="planches de vérification")
    s.add_argument("items"); s.add_argument("--images", required=True); s.add_argument("-o", "--out", required=True)
    s.add_argument("--decisions")
    s.set_defaults(func=cmd_review_sheets)
    s = rv.add_parser("apply", help="appliquer les arbitrages")
    s.add_argument("items"); s.add_argument("decisions"); s.add_argument("folder")
    s.add_argument("--ecrire", action="store_true"); s.add_argument("--log")
    s.set_defaults(func=cmd_review_apply)

    fx = sub.add_parser("fix", help="corrections vérifiées").add_subparsers(dest="sub", required=True)
    s = fx.add_parser("words", help="appliquer un fichier de corrections et/ou les zéros lus « o »")
    s.add_argument("folder"); s.add_argument("--corrections")
    s.add_argument("--zero-pages", help="pages où corriger o -> 0, séparées par des virgules")
    s.add_argument("--ecrire", action="store_true")
    s.set_defaults(func=cmd_fix_words)
    s = fx.add_parser("hyphens", help="lister les coupures de ligne à recoller")
    s.add_argument("folder"); s.add_argument("-o", "--out")
    s.add_argument("--all", action="store_true", help="sans exiger le mot recollé ailleurs dans le livre")
    s.set_defaults(func=cmd_fix_hyphens)

    s = sub.add_parser("bench", help="score contre des pages de référence")
    s.add_argument("ref"); s.add_argument("candidates", nargs="+")
    s.add_argument("--detail", action="store_true")
    s.set_defaults(func=cmd_bench)

    s = sub.add_parser("demo", help="générer des données synthétiques")
    s.add_argument("out")
    s.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args, _cfg(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
