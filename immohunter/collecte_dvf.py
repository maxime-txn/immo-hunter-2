"""
Étape 1 : télécharger les ventes notariales DVF (Demandes de Valeurs Foncières).

Source : https://files.data.gouv.fr/geo-dvf/ (open data, Licence Ouverte Etalab).
Un fichier par année et par département, déjà géolocalisé (latitude / longitude).
"""
import os

import requests

URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/departements/{dep}.csv.gz"


def chemin_fichier(dossier, dep, annee):
    return os.path.join(dossier, f"dvf_{dep}_{annee}.csv.gz")


def telecharger(dep, annees, dossier):
    """Télécharge les fichiers manquants. Renvoie la liste des fichiers présents."""
    os.makedirs(dossier, exist_ok=True)
    fichiers = []
    for annee in annees:
        chemin = chemin_fichier(dossier, dep, annee)
        if os.path.exists(chemin):
            print(f"  {annee} : déjà présent")
            fichiers.append(chemin)
            continue
        url = URL.format(annee=annee, dep=dep)
        rep = requests.get(url, timeout=120)
        if rep.status_code != 200:
            print(f"  {annee} : indisponible sur data.gouv.fr (HTTP {rep.status_code}), ignoré")
            continue
        with open(chemin, "wb") as f:
            f.write(rep.content)
        print(f"  {annee} : téléchargé ({len(rep.content) / 1e6:.1f} Mo)")
        fichiers.append(chemin)
    return fichiers
