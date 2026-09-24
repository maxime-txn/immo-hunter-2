#!/usr/bin/env python3
"""
Immo-Hunter : pipeline de bout en bout.

    python pipeline.py --tout                 # DVF -> nettoyage -> modèle -> rapports
    python pipeline.py --collecte             # 1. télécharger les ventes DVF
    python pipeline.py --nettoyage            # 2. construire data/ventes.parquet
    python pipeline.py --modele               # 3. évaluer, entraîner, générer les rapports

Module optionnel « annonces en ligne » :
    python pipeline.py --annonces-collecte          # scraper les annonces (config.py)
    python pipeline.py --annonces-enrichissement    # extraire 50+ infos des descriptions (API Claude)
    python pipeline.py --annonces-analyse           # verdict par annonce + croisement avec DVF
"""
import argparse
import glob
import json
import os

import pandas as pd

import config
from immohunter import base, collecte_dvf, modele, nettoyage, rapports


def etape(titre):
    print(f"\n── {titre} " + "─" * (56 - len(titre)))


def collecte():
    etape("1. Collecte des ventes DVF")
    collecte_dvf.telecharger(config.DEPARTEMENT, config.ANNEES, config.DOSSIER_BRUT)


def construire_base():
    etape("2. Nettoyage")
    fichiers = sorted(glob.glob(os.path.join(config.DOSSIER_BRUT, f"dvf_{config.DEPARTEMENT}_*.csv.gz")))
    if not fichiers:
        raise SystemExit("Aucun fichier DVF : lancer d'abord --collecte")
    brut = nettoyage.lire_brut(fichiers)
    ventes, entonnoir = nettoyage.nettoyer(
        brut, config.TYPES_BIENS, config.COMMUNES,
        surface=(config.SURFACE_MIN, config.SURFACE_MAX),
        prix_m2=(config.PRIX_M2_MIN, config.PRIX_M2_MAX))
    ventes.to_parquet(config.FICHIER_VENTES, index=False)
    os.makedirs(config.DOSSIER_RAPPORTS, exist_ok=True)
    with open(os.path.join(config.DOSSIER_RAPPORTS, "nettoyage.json"), "w", encoding="utf-8") as f:
        json.dump(entonnoir, f, ensure_ascii=False, indent=2)
    for k, v in entonnoir.items():
        print(f"  {k:32s} {v:>9,}".replace(",", " "))


def entrainer():
    etape("3. Modèle")
    ventes = pd.read_parquet(config.FICHIER_VENTES)
    rapport, erreurs_test = modele.evaluer_et_entrainer(
        ventes, config.NB_MOIS_TEST, config.QUANTILE_BAS, config.QUANTILE_HAUT,
        config.DOSSIER_MODELES)
    ref, mod = rapport["reference_mediane_secteur"], rapport["modele"]
    print(f"  Test : {rapport['nb_ventes_test']} ventes du {rapport['periode_test'][0]} "
          f"au {rapport['periode_test'][1]}")
    print(f"  Erreur médiane     : {mod['erreur_mediane_pct']} % (méthode simple : {ref['erreur_mediane_pct']} %)")
    print(f"  Estimées à ±10 %   : {mod['part_a_moins_de_10pct']} % (méthode simple : {ref['part_a_moins_de_10pct']} %)")
    print(f"  Fourchette 80 %    : contient le vrai prix dans {rapport['fourchette_couverture_pct']} % des cas")

    etape("4. Rapports")
    tendance = base.requete(base.connexion(config.FICHIER_VENTES), "tendance_12_mois")
    rapports.generer(ventes, tendance, erreurs_test, config.NOM_ZONE, config.DOSSIER_RAPPORTS)
    print(f"  Graphiques -> {config.DOSSIER_RAPPORTS}/")


def main():
    p = argparse.ArgumentParser(description="Immo-Hunter : pipeline complet")
    p.add_argument("--tout", action="store_true")
    p.add_argument("--collecte", action="store_true")
    p.add_argument("--nettoyage", action="store_true")
    p.add_argument("--modele", action="store_true")
    p.add_argument("--annonces-collecte", action="store_true")
    p.add_argument("--annonces-enrichissement", action="store_true")
    p.add_argument("--annonces-analyse", metavar="FICHIER_CSV", nargs="?", const="auto",
                   help="sans fichier : prend le dernier CSV de data/annonces/ (enrichi si possible)")
    a = p.parse_args()

    print(f"Immo-Hunter · zone : {config.NOM_ZONE} (département {config.DEPARTEMENT})")
    if a.tout or a.collecte:
        collecte()
    if a.tout or a.nettoyage:
        construire_base()
    if a.tout or a.modele:
        entrainer()
    if a.annonces_collecte:
        from immohunter.annonces.collecte import main as collecter_annonces
        collecter_annonces()
    if a.annonces_enrichissement:
        from immohunter.annonces.enrichissement import main as enrichir
        enrichir()
    if a.annonces_analyse:
        from immohunter.annonces.analyse_lot import analyser
        fichier = a.annonces_analyse
        if fichier == "auto":
            candidats = [f for f in glob.glob(os.path.join(config.OUTPUT_DIR, "annonces_*.csv"))
                         if "_verdicts" not in f]
            if not candidats:
                raise SystemExit("Aucun CSV d'annonces : lancer d'abord --annonces-collecte")
            enrichis = [f for f in candidats if "_enrichi" in f]
            fichier = max(enrichis or candidats, key=os.path.getmtime)
        etape("5. Croisement annonces × ventes réelles")
        sortie = fichier.replace(".csv", "_verdicts.csv")
        analyser(fichier, config.FICHIER_VENTES, config.DOSSIER_MODELES, sortie)
    if not any(vars(a).values()):
        p.print_help()


if __name__ == "__main__":
    main()
