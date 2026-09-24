#!/usr/bin/env python3
"""
Enrichissement IA — Claude analyse chaque description et extrait 30+ features.
Lit le CSV brut, produit un CSV enrichi pret pour PostgreSQL.

Usage: python enrichment/enrich.py
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
    print("pip install anthropic")
    sys.exit(1)

# Prompt optimisé : 50+ features normalisées pour SQL
PROMPT = """Tu es un expert immobilier. Analyse cette annonce et extrais les informations en JSON strict.
Reponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou apres.

REGLES :
- Booleens : true/false uniquement (jamais null pour un booleen)
- null si l'info n'est pas mentionnee dans l'annonce
- exposition : "nord", "sud", "est", "ouest", "nord-est", "nord-ouest", "sud-est", "sud-ouest", "traversant" ou null
- DPE/GES : une seule lettre majuscule A-G ou null
- etat_general : "neuf", "refait_a_neuf", "renove", "tres_bon", "bon", "correct", "a_rafraichir", "a_renover" ou null
- type_chauffage : "individuel_gaz", "individuel_electrique", "collectif_gaz", "collectif_electrique", "pompe_a_chaleur", "fioul", "bois" ou null
- vue_type : "jardin", "parc", "seine", "monument", "ville", "cour", "rue", "degagee" ou null
- etage : nombre entier (0 = RDC) ou null
- Nombres : entiers uniquement

Annonce :
Titre: {titre}
Prix: {prix} EUR | Surface: {surface} m2 | Pieces: {pieces} | Chambres: {chambres} | Type: {type_bien}

Description:
{description}

JSON :
{{
  "etage": null,
  "nb_etages_immeuble": null,
  "dernier_etage": false,
  "rez_de_chaussee": false,
  "hauteur_sous_plafond_cm": null,
  "ascenseur": false,

  "nb_sdb": null,
  "nb_wc": null,
  "surface_sejour_m2": null,

  "balcon": false,
  "nb_balcons": null,
  "terrasse": false,
  "surface_terrasse_m2": null,
  "loggia": false,
  "roof_top": false,
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
  "cuisine_type": null,
  "double_vitrage": false,
  "triple_vitrage": false,
  "climatisation": false,
  "type_chauffage": null,

  "digicode": false,
  "interphone": false,
  "gardien": false,
  "residence_securisee": false,

  "exposition": null,
  "lumineux": false,
  "calme": false,
  "vue_degagee": false,
  "vue_type": null,
  "vis_a_vis": false,
  "etage_eleve": false,

  "etat_general": null,
  "travaux_necessaires": false,
  "annee_construction": null,

  "dpe_lettre": null,
  "dpe_valeur": null,
  "ges_lettre": null,
  "ges_valeur": null,

  "proche_transports": false,
  "distance_metro_min": null,
  "nom_station_metro": null,
  "ligne_metro": null,
  "proche_commerces": false,
  "proche_ecoles": false,
  "quartier": null,

  "copropriete": false,
  "nb_lots_copro": null,
  "charges_copro_mois": null,
  "taxe_fonciere_an": null,
  "travaux_copro_prevus": false,

  "meuble": false,
  "mandat_exclusif": false,
  "viager": false,
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


def normalize_value(key, value):
    """Normalise les valeurs pour compatibilité PostgreSQL."""
    if isinstance(value, list):
        return ", ".join(str(x) for x in value) if value else ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    # Normaliser exposition
    if key == "exposition" and isinstance(value, str):
        return value.lower().strip()
    # Normaliser etat_general
    if key == "etat_general" and isinstance(value, str):
        return value.lower().strip().replace(" ", "_").replace("à", "a").replace("é", "e").replace("è", "e")
    # Normaliser type_chauffage, vue_type
    if key in ("type_chauffage", "vue_type") and isinstance(value, str):
        return value.lower().strip().replace(" ", "_").replace("à", "a").replace("é", "e")
    # DPE/GES lettre : toujours majuscule
    if key in ("dpe_lettre", "ges_lettre") and isinstance(value, str):
        v = value.strip().upper()
        return v if len(v) == 1 and v in "ABCDEFG" else ""
    return value


def enrich_row(client, row):
    """Enrichit une annonce via Claude API."""
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
        description=desc[:3000],
    )

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # Nettoyer markdown si présent
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        # Normaliser toutes les valeurs
        return {k: normalize_value(k, v) for k, v in data.items()}
    except json.JSONDecodeError as e:
        print("  Erreur JSON: {}".format(str(e)[:60]))
        return {}
    except Exception as e:
        print("  Erreur API: {}".format(str(e)[:120]))
        return {}


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Erreur: export ANTHROPIC_API_KEY=sk-ant-xxx")
        sys.exit(1)

    # Trouver le CSV le plus récent (exclure enrichi et prediction)
    csvs = glob.glob("data/annonces/annonces_*.csv")
    csvs = [c for c in csvs if "_enrichi" not in c and "_prediction" not in c]
    if not csvs:
        print("Erreur: aucun CSV dans data/annonces/")
        sys.exit(1)

    csv_path = max(csvs, key=os.path.getmtime)
    print("Lecture: {}".format(csv_path))

    rows = load_csv(csv_path)
    print("{} annonces".format(len(rows)))

    with_desc = [r for r in rows if r.get("description") and len(r["description"]) > 30]
    print("{} avec description a enrichir".format(len(with_desc)))

    if not with_desc:
        print("Aucune description a enrichir.")
        sys.exit(0)

    client = Anthropic(api_key=api_key)
    enriched = 0
    errors = 0
    out_path = csv_path.replace(".csv", "_enrichi.csv")

    # Reprendre si un fichier enrichi existe déjà
    already_done = set()
    if os.path.exists(out_path):
        existing = load_csv(out_path)
        for r in existing:
            # Considérer enrichi si au moins un champ IA est rempli
            if any(r.get(k) not in ("", None) for k in
                   ("etage", "ascenseur", "balcon", "dpe_lettre", "etat_general")):
                key = r.get("url") or r.get("titre", "")
                if key:
                    already_done.add(key)
        if already_done:
            rows = existing
            print("{} deja enrichies, reprise...".format(len(already_done)))

    start = time.time()

    for i, row in enumerate(rows):
        if not row.get("description") or len(row["description"]) < 30:
            continue

        key = row.get("url") or row.get("titre", "")
        if key in already_done:
            enriched += 1
            continue

        features = enrich_row(client, row)
        if features:
            row.update(features)
            enriched += 1
            already_done.add(key)
        else:
            errors += 1

        # Progression
        if (i + 1) % 10 == 0:
            elapsed = time.time() - start
            rate = (enriched / elapsed * 60) if elapsed > 0 else 0
            print("  {}/{} enrichies ({} erreurs) — {:.0f}/min".format(
                enriched, i + 1, errors, rate))

        # Sauvegarde toutes les 20
        if enriched > 0 and enriched % 20 == 0:
            save_csv(rows, out_path)
            print("  [sauvegarde {} annonces]".format(enriched))

        time.sleep(0.3)

    print("\n{} annonces enrichies sur {} ({} erreurs)".format(enriched, len(rows), errors))

    save_csv(rows, out_path)
    print("Exporte: {}".format(out_path))


if __name__ == "__main__":
    main()
