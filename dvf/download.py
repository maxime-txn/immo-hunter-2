#!/usr/bin/env python3
"""
Telecharge les transactions DVF depuis les fichiers CSV data.gouv.fr.
Usage: python3.12 dvf/download.py
"""
import requests
import csv
import os
import io

# ── CONFIG ────────────────────────────────────────────────
CODE_COMMUNE = "75116"      # Paris 16e
DEPARTEMENT = "75"
NOM = "Paris 16e"
ANNEES = [2020, 2021, 2022, 2023, 2024, 2025]
OUTPUT = "output/dvf_paris16.csv"
# ──────────────────────────────────────────────────────────

# URL directe des CSV geo-dvf (data.gouv.fr)
BASE_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv"
# Format: {BASE_URL}/{ANNEE}/communes/{DEP}/{CODE_COMMUNE}.csv


def download_year(session, annee):
    url = "{}/{}/communes/{}/{}.csv".format(BASE_URL, annee, DEPARTEMENT, CODE_COMMUNE)
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text))
            rows = list(reader)
            return rows
        else:
            print("[DVF] {} : HTTP {} - essai URL alternative...".format(annee, resp.status_code))
            # URL alternative
            url2 = "https://files.data.gouv.fr/geo-dvf/2024-12/csv/{}/communes/{}/{}.csv".format(
                annee, DEPARTEMENT, CODE_COMMUNE)
            resp2 = session.get(url2, timeout=30)
            if resp2.status_code == 200:
                reader = csv.DictReader(io.StringIO(resp2.text))
                return list(reader)
            print("[DVF] {} : HTTP {}".format(annee, resp2.status_code))
            return []
    except Exception as e:
        print("[DVF] {} : Erreur {}".format(annee, str(e)[:50]))
        return []


def main():
    print("""
+==================================================+
|   DVF — Transactions immobilieres                 |
+==================================================+
  Zone    : {} ({})
  Annees  : {} - {}
+==================================================+
""".format(NOM, CODE_COMMUNE, ANNEES[0], ANNEES[-1]))

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })

    all_rows = []

    for annee in ANNEES:
        rows = download_year(session, annee)
        all_rows.extend(rows)
        # Compter les ventes
        ventes = [r for r in rows if r.get("nature_mutation") == "Vente"]
        apparts = [r for r in ventes if r.get("type_local") == "Appartement"]
        print("[DVF] {} : {} lignes, {} ventes, {} appartements".format(
            annee, len(rows), len(ventes), len(apparts)))

    if not all_rows:
        print("Aucune transaction trouvee.")
        return

    # Sauvegarder
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    keys = list(all_rows[0].keys())
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, delimiter=";")
        w.writeheader()
        w.writerows(all_rows)

    # Stats
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
""".format(len(all_rows), len(ventes), len(apparts), len(maisons), OUTPUT))


if __name__ == "__main__":
    main()
