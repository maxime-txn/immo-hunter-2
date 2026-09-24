"""
Analyse d'un lot d'annonces : pour chaque annonce, estimation + verdict.

Entrée : un CSV d'annonces (séparateur ;) avec au minimum les colonnes
    prix, surface_m2, nb_pieces, code_postal
Colonnes facultatives utilisées si présentes :
    latitude, longitude       -> position précise (sinon : centre du code postal)
    cave, nb_parking          -> issues de l'enrichissement IA (enrichissement.py)

Sorties :
  - le même CSV avec prix_estime, fourchette_basse, fourchette_haute, verdict, ecart_pct
    (données d'annonces : reste en local, jamais publié) ;
  - data/croisement_annonces.csv : le croisement annonces × ventes DVF par secteur
    (chiffres agrégés, publiables), calculé en SQL (sql/croisement_annonces_dvf.sql).
"""
import json
import os

import pandas as pd

from immohunter import base, modele
from immohunter.verdict import verdict

FICHIER_CROISEMENT = "data/croisement_annonces.csv"
FICHIER_RESUME = "rapports/croisement_annonces.json"


def analyser(fichier_annonces, fichier_ventes, dossier_modeles, fichier_sortie):
    ann = pd.read_csv(fichier_annonces, sep=";", dtype={"code_postal": str})
    for col in ["prix", "surface_m2", "nb_pieces"]:
        ann[col] = pd.to_numeric(ann[col], errors="coerce")
    ann = ann.dropna(subset=["prix", "surface_m2", "nb_pieces", "code_postal"])
    # Le modèle est entraîné sur des appartements : on écarte maisons, villas, terrains
    if "type_bien" in ann:
        ann = ann[~ann["type_bien"].fillna("").str.lower().isin(["maison", "villa", "terrain"])]
    # Mêmes garde-fous que pour les ventes DVF (erreurs de saisie, annonces aberrantes)
    prix_m2 = ann["prix"] / ann["surface_m2"]
    ann = ann[ann["surface_m2"].between(9, 400) & prix_m2.between(3_000, 40_000)]
    ann = ann.drop_duplicates(subset=["prix", "surface_m2", "nb_pieces", "code_postal"])

    # Position : coordonnées si connues, sinon centre du code postal (calculé en SQL sur DVF)
    centres = base.requete(base.connexion(fichier_ventes), "centres_codes_postaux")
    ann = ann.merge(centres[["code_postal", "code_commune", "secteur", "latitude", "longitude"]],
                    on="code_postal", how="inner", suffixes=("_annonce", ""))
    for col in ["latitude", "longitude"]:
        if f"{col}_annonce" in ann:
            ann[col] = ann[f"{col}_annonce"].fillna(ann[col])

    ann["surface"] = ann["surface_m2"]
    ann["nb_dependances"] = 0
    if "cave" in ann:
        ann["nb_dependances"] += ann["cave"].astype(str).str.lower().eq("true").astype(int)
    if "nb_parking" in ann:
        ann["nb_dependances"] += pd.to_numeric(ann["nb_parking"], errors="coerce").fillna(0)

    paquet = modele.charger(dossier_modeles)
    ann = ann.join(modele.estimer(paquet, ann))
    verdicts = ann.apply(lambda r: verdict(r["prix"], r["prix_estime"], r["fourchette_basse"],
                                           r["fourchette_haute"]), axis=1, result_type="expand")
    ann = ann.join(verdicts)
    ann.to_csv(fichier_sortie, sep=";", index=False, encoding="utf-8")
    print(f"  {len(ann)} annonces analysées -> {fichier_sortie}")
    print(ann["verdict"].value_counts().to_string())

    # Croisement avec les ventes réelles, en SQL
    con = base.connexion(fichier_ventes)
    base.ajouter_annonces(con, fichier_sortie)
    croisement = base.requete(con, "croisement_annonces_dvf")
    croisement.to_csv(FICHIER_CROISEMENT, index=False)
    fin_dvf = con.execute("SELECT MAX(date) FROM ventes").fetchone()[0]
    resume = {
        "date_collecte_annonces": str(pd.Timestamp(os.path.getmtime(fichier_annonces), unit="s").date()),
        "derniere_vente_dvf": str(pd.Timestamp(fin_dvf).date()),
        "nb_annonces": int(len(ann)),
        "ecart_median_vs_estimation_pct": round(float(ann["ecart_pct"].median()), 1),
        "part_annonces_au_dessus_pct": round(float(ann["verdict"].isin(
            ["Surévalué", "Au-dessus du marché"]).mean() * 100), 1),
        "repartition_verdicts": ann["verdict"].value_counts().to_dict(),
    }
    with open(FICHIER_RESUME, "w", encoding="utf-8") as f:
        json.dump(resume, f, ensure_ascii=False, indent=2)
    print("\n  Croisement annonces × ventes réelles :")
    print(croisement.to_string(index=False))
    return ann, croisement
