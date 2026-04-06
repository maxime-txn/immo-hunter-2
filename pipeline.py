#!/usr/bin/env python3
"""
pipeline.py — Lance tout le pipeline immo-hunter en une commande.

Usage:
    python pipeline.py              # Scrape SeLoger + DVF
    python pipeline.py --enrich     # + Enrichissement IA (ANTHROPIC_API_KEY requis)
    python pipeline.py --predict    # + Prédiction ML
    python pipeline.py --all        # Scrape + DVF + Enrichissement + Predict + DB
    python pipeline.py --dvf-only   # DVF seulement
"""
import argparse
import os
import sys
import time


def step(num, title):
    print("\n" + "=" * 60)
    print(f"  ÉTAPE {num} — {title}")
    print("=" * 60)


def run_scrape():
    step(1, "SCRAPING SELOGER")
    import config
    print(f"  Ville : {config.city}")
    print(f"  Code postal : {config.postal_code}")
    print(f"  Type : {config.property_type}")
    print(f"  Pages max : {config.max_pages}")
    print()
    from scrape import main as scrape_main
    scrape_main()


def run_dvf():
    step(2, "TÉLÉCHARGEMENT DVF")
    from dvf.download import download
    download()


def run_enrich():
    step(3, "ENRICHISSEMENT IA (Claude)")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ANTHROPIC_API_KEY non définie — enrichissement ignoré.")
        print("  Pour activer : export ANTHROPIC_API_KEY=sk-ant-xxx")
        return False
    from enrichment.enrich import main as enrich_main
    enrich_main()
    return True


def run_predict():
    step(4, "PRÉDICTION ML")
    # Exécuter predict.py comme script (il utilise print pour l'affichage)
    exec(open("predict.py").read())


def run_db():
    step(5, "IMPORT POSTGRESQL")
    try:
        from import_db import main as db_main
        db_main()
    except Exception as e:
        print(f"  Import DB ignoré : {e}")
        print("  Vérifie que PostgreSQL est lancé et la base immo_hunter existe.")


def main():
    parser = argparse.ArgumentParser(description="Immo-Hunter — Pipeline complet")
    parser.add_argument("--enrich", action="store_true",
                        help="Ajouter l'enrichissement IA après scrape + DVF")
    parser.add_argument("--predict", action="store_true",
                        help="Ajouter la prédiction ML après scrape + DVF")
    parser.add_argument("--db", action="store_true",
                        help="Ajouter l'import PostgreSQL")
    parser.add_argument("--all", action="store_true",
                        help="Tout lancer (scrape + DVF + enrichissement + predict + DB)")
    parser.add_argument("--dvf-only", action="store_true",
                        help="Télécharger DVF seulement")
    args = parser.parse_args()

    import config

    print("""
╔══════════════════════════════════════════════════════════╗
║   IMMO-HUNTER — Pipeline                                ║
╠══════════════════════════════════════════════════════════╣
║  Ville       : {:<40s} ║
║  Code postal : {:<40s} ║
║  DVF années  : {:<40s} ║
╚══════════════════════════════════════════════════════════╝
""".format(
        config.city,
        config.postal_code,
        ", ".join(str(a) for a in getattr(config, "dvf_annees", [2024, 2025])),
    ))

    start = time.time()

    if args.dvf_only:
        run_dvf()
    else:
        # 1. Scrape + DVF (toujours)
        run_scrape()
        run_dvf()
        # 2. Enrichissement (si demandé)
        if args.enrich or args.all:
            run_enrich()
        # 3. Prédiction (si demandé)
        if args.predict or args.all:
            run_predict()
        # 4. DB (si demandé)
        if args.db or args.all:
            run_db()

    elapsed = time.time() - start
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print("\n" + "=" * 60)
    print(f"  PIPELINE TERMINÉ en {minutes}m {seconds}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
