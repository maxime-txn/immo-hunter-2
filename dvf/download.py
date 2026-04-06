#!/usr/bin/env python3
"""
Telecharge les transactions DVF depuis data.gouv.fr.
Utilise l'API geo.api.gouv.fr pour trouver le code commune.

Usage: python dvf/download.py
"""
import csv
import io
import os
import sys

import requests

# Ajouter le dossier parent au path pour importer config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.geo import city_to_slug

BASE_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv"


def lookup_commune(postal_code):
    """Trouve le code commune et département via l'API geo.gouv.fr.
    Gère le cas spécial de Paris (arrondissements) et Lyon/Marseille."""
    departement = postal_code[:2]

    # Paris : 750XX → code commune 751XX pour DVF
    if postal_code.startswith("750"):
        arr = postal_code[3:]  # "16" pour 75016
        code_commune = "751{}".format(arr)
        nom = "Paris {}e".format(int(arr))
        return code_commune, "75", nom

    # Lyon : 6900X → 6938X
    if postal_code.startswith("6900"):
        arr = postal_code[4]
        code_commune = "6938{}".format(arr)
        nom = "Lyon {}e".format(arr)
        return code_commune, "69", nom

    # Marseille : 130XX → 132XX
    if postal_code.startswith("130") and len(postal_code) == 5:
        arr = postal_code[3:]
        code_commune = "132{}".format(arr)
        nom = "Marseille {}e".format(int(arr))
        return code_commune, "13", nom

    # Cas général : API geo.gouv.fr
    url = "https://geo.api.gouv.fr/communes?codePostal={}&fields=nom,code,codeDepartement".format(
        postal_code
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        communes = resp.json()
        if not communes:
            print("Aucune commune trouvee pour le code postal {}".format(postal_code))
            sys.exit(1)
        if len(communes) == 1:
            c = communes[0]
        else:
            print("Communes trouvees pour {} :".format(postal_code))
            for i, c in enumerate(communes):
                print("  [{}] {} ({})".format(i, c["nom"], c["code"]))
            c = communes[0]
        return c["code"], c["codeDepartement"], c["nom"]
    except Exception as e:
        print("Erreur API geo.gouv.fr : {}".format(e))
        sys.exit(1)


def download_year(session, annee, departement, code_commune):
    """Telecharge les transactions DVF pour une annee et commune."""
    url = "{}/{}/communes/{}/{}.csv".format(BASE_URL, annee, departement, code_commune)
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text))
            return list(reader)
        else:
            # URL alternative (archive)
            url2 = "https://files.data.gouv.fr/geo-dvf/2024-12/csv/{}/communes/{}/{}.csv".format(
                annee, departement, code_commune)
            resp2 = session.get(url2, timeout=30)
            if resp2.status_code == 200:
                reader = csv.DictReader(io.StringIO(resp2.text))
                return list(reader)
            print("[DVF] {} : HTTP {}".format(annee, resp2.status_code))
            return []
    except Exception as e:
        print("[DVF] {} : Erreur {}".format(annee, str(e)[:80]))
        return []


def download(postal_code=None, annees=None, output_path=None):
    """Point d'entree principal. Retourne le chemin du fichier CSV."""
    postal_code = postal_code or config.postal_code
    annees = annees or getattr(config, "dvf_annees", [2024, 2025])

    code_commune, departement, nom = lookup_commune(postal_code)
    slug = city_to_slug(nom)

    if output_path is None:
        output_path = "{}/dvf_{}.csv".format(config.OUTPUT_DIR, slug)

    print("""
+==================================================+
|   DVF — Transactions immobilieres                 |
+==================================================+
  Zone    : {} ({})
  Commune : {}
  Dept    : {}
  Annees  : {}
+==================================================+
""".format(nom, postal_code, code_commune, departement,
           ", ".join(str(a) for a in annees)))

    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})

    all_rows = []
    for annee in annees:
        rows = download_year(session, annee, departement, code_commune)
        all_rows.extend(rows)
        ventes = [r for r in rows if r.get("nature_mutation") == "Vente"]
        apparts = [r for r in ventes if r.get("type_local") == "Appartement"]
        print("[DVF] {} : {} lignes, {} ventes, {} appartements".format(
            annee, len(rows), len(ventes), len(apparts)))

    if not all_rows:
        print("Aucune transaction trouvee.")
        return None

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    keys = list(all_rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, delimiter=";")
        w.writeheader()
        w.writerows(all_rows)

    ventes = [r for r in all_rows if r.get("nature_mutation") == "Vente"]
    apparts = [r for r in ventes if r.get("type_local") == "Appartement"]
    maisons = [r for r in ventes if r.get("type_local") == "Maison"]

    print("""
  TOTAL
  {} lignes brutes
  {} ventes
  {} appartements
  {} maisons
  Exporte : {}
""".format(len(all_rows), len(ventes), len(apparts), len(maisons), output_path))

    return output_path


if __name__ == "__main__":
    download()
