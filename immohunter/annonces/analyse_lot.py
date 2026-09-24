"""
Analyse d'un lot d'annonces : pour chaque annonce, estimation + verdict.

Entrée : un CSV d'annonces (séparateur ;) avec au minimum les colonnes
    prix, surface_m2, nb_pieces, code_postal
Colonnes facultatives utilisées si présentes :
    latitude, longitude       -> position précise (sinon : centre du code postal)
    cave, nb_parking          -> issues de l'enrichissement IA (enrichissement.py)

Sortie : le même CSV avec prix_estime, fourchette_basse, fourchette_haute, verdict, ecart_pct.
"""
import pandas as pd

from immohunter import base, modele
from immohunter.verdict import verdict


def analyser(fichier_annonces, fichier_ventes, dossier_modeles, fichier_sortie):
    ann = pd.read_csv(fichier_annonces, sep=";", dtype={"code_postal": str})
    for col in ["prix", "surface_m2", "nb_pieces"]:
        ann[col] = pd.to_numeric(ann[col], errors="coerce")
    ann = ann.dropna(subset=["prix", "surface_m2", "nb_pieces", "code_postal"])

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
    ann.to_csv(fichier_sortie, sep=";", index=False, encoding="utf-8-sig")
    print(f"  {len(ann)} annonces analysées -> {fichier_sortie}")
    print(ann["verdict"].value_counts().to_string())
    return ann
