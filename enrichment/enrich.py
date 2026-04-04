#!/usr/bin/env python3
"""
Enrichissement IA — Claude analyse chaque description et extrait 30+ features.
Lit le CSV brut, produit un CSV enrichi pret pour PostgreSQL.

Usage: python3.12 enrichment/enrich.py
Prerequis: export ANTHROPIC_API_KEY=sk-ant-xxx
"""
import csv
import json
import os
import sys
import time
import glob

try:
    from anthropic import Anthropic
except ImportError:
    print("pip3.12 install anthropic --break-system-packages")
    sys.exit(1)

PROMPT = """Analyse cette annonce immobiliere et extrais les informations en JSON.
Reponds UNIQUEMENT avec un objet JSON, sans texte avant ou apres.

Annonce:
Titre: {titre}
Prix: {prix} EUR
Surface: {surface} m2
Pieces: {pieces}
Chambres: {chambres}
Type: {type_bien}
Description: {description}

Extrais ces champs (null si inconnu):
{{
  "etage": null,
  "dernier_etage": false,
  "ascenseur": false,
  "balcon": false,
  "terrasse": false,
  "jardin": false,
  "surface_jardin_m2": null,
  "piscine": false,
  "garage": false,
  "nb_parking": null,
  "cave": false,
  "sous_sol": false,
  "cheminee": false,
  "parquet": false,
  "cuisine_equipee": false,
  "double_vitrage": false,
  "exposition": null,
  "luminosite": null,
  "calme": false,
  "vue_degagee": false,
  "vis_a_vis": null,
  "etat_general": null,
  "travaux_necessaires": false,
  "annee_construction": null,
  "style_architecture": null,
  "dpe_lettre": null,
  "ges_lettre": null,
  "proche_gare": false,
  "distance_gare_min": null,
  "proche_commerces": false,
  "proche_ecoles": false,
  "quartier": null,
  "copropriete": null,
  "charges_copro_mois": null,
  "taxe_fonciere_an": null,
  "meuble": false,
  "coup_de_coeur": false,
  "points_forts": [],
  "points_faibles": []
}}"""


def load_csv(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


def save_csv(rows, path):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def enrich_row(client, row):
    desc = row.get("description", "")
    if not desc or len(desc) < 30:
        return {}

    prompt = PROMPT.format(
        titre=row.get("titre", ""),
        prix=row.get("prix", ""),
        surface=row.get("surface_m2", ""),
        pieces=row.get("nb_pieces", ""),
        chambres=row.get("nb_chambres", ""),
        type_bien=row.get("type_bien", ""),
        description=desc[:2000],
    )

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # Nettoyer si necessaire
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        # Convertir les listes en strings pour CSV
        for k, v in data.items():
            if isinstance(v, list):
                data[k] = ", ".join(str(x) for x in v)
            elif isinstance(v, bool):
                data[k] = "true" if v else "false"
            elif v is None:
                data[k] = ""
        return data
    except Exception as e:
        print("  Erreur IA: {}".format(str(e)[:50]))
        return {}


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Erreur: export ANTHROPIC_API_KEY=sk-ant-xxx")
        sys.exit(1)

    # Trouver le CSV le plus recent
    csvs = glob.glob("output/annonces_*.csv")
    if not csvs:
        print("Erreur: aucun CSV dans output/. Lance d'abord main.py")
        sys.exit(1)

    csv_path = max(csvs, key=os.path.getmtime)
    print("Lecture: {}".format(csv_path))

    rows = load_csv(csv_path)
    print("{} annonces".format(len(rows)))

    with_desc = [r for r in rows if r.get("description") and len(r["description"]) > 30]
    print("{} avec description a enrichir".format(len(with_desc)))

    # Priorite: petites surfaces d'abord (studios, 2P...)
    def priority(r):
        surface = r.get("surface_m2", "")
        try:
            return float(surface)
        except (ValueError, TypeError):
            return 9999

    rows.sort(key=priority)
    petits = [r for r in rows if priority(r) < 50]
    print("{} petites surfaces (<50m2) en priorite".format(len(petits)))

    if not with_desc:
        print("Aucune description a enrichir.")
        sys.exit(0)

    client = Anthropic(api_key=api_key)
    enriched = 0
    out_path = csv_path.replace(".csv", "_enrichi.csv")

    # Reprendre si un fichier enrichi existe deja
    already_done = set()
    if os.path.exists(out_path):
        existing = load_csv(out_path)
        for r in existing:
            if r.get("etage") or r.get("ascenseur") or r.get("balcon"):
                url = r.get("url", "")
                titre = r.get("titre", "")
                if url:
                    already_done.add(url)
                elif titre:
                    already_done.add(titre)
        if already_done:
            # Charger les donnees enrichies existantes
            rows = existing
            print("{} deja enrichies, reprise...".format(len(already_done)))

    for i, row in enumerate(rows):
        if not row.get("description") or len(row["description"]) < 30:
            continue

        # Skip si deja enrichi
        key = row.get("url") or row.get("titre", "")
        if key in already_done:
            enriched += 1
            continue

        features = enrich_row(client, row)
        if features:
            row.update(features)
            enriched += 1
            already_done.add(key)

        if (i + 1) % 10 == 0:
            print("  {}/{} enrichies...".format(enriched, i + 1))

        # Sauvegarde toutes les 20 enrichissements
        if enriched % 20 == 0 and enriched > 0:
            save_csv(rows, out_path)
            print("  [sauvegarde {} annonces]".format(enriched))

        time.sleep(0.5)

    print("\n{} annonces enrichies sur {}".format(enriched, len(rows)))

    # Sauvegarde finale
    save_csv(rows, out_path)
    print("Exporte: {}".format(out_path))
    print("\nPret pour PostgreSQL: COPY annonces FROM '{}' DELIMITER ';' CSV HEADER;".format(
        os.path.abspath(out_path)))


if __name__ == "__main__":
    main()
