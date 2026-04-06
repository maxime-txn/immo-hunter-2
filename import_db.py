#!/usr/bin/env python3
"""Importe les CSV annonces + DVF dans PostgreSQL."""
import csv
import os
import sys

try:
    import psycopg2
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg2-binary", "--break-system-packages"])
    import psycopg2

DB_NAME = "immo_hunter"
DB_USER = "teixeiramaxime"
DB_HOST = "localhost"
DB_PORT = "5432"


def connect():
    for kwargs in [
        {"dbname": DB_NAME, "user": DB_USER, "host": DB_HOST, "port": DB_PORT},
        {"dbname": DB_NAME, "user": DB_USER},
        {"dbname": DB_NAME},
    ]:
        try:
            conn = psycopg2.connect(**kwargs)
            conn.autocommit = True
            print("Connecte a {}".format(DB_NAME))
            return conn
        except Exception:
            continue
    print("Impossible de se connecter. Verifie que la base immo_hunter existe dans pgAdmin.")
    sys.exit(1)


def create_tables(cur):
    cur.execute("DROP TABLE IF EXISTS annonces CASCADE;")
    cur.execute("DROP TABLE IF EXISTS dvf CASCADE;")

    cur.execute("""
    CREATE TABLE annonces (
        id SERIAL PRIMARY KEY,
        plateforme VARCHAR(50),
        titre TEXT,
        prix INTEGER,
        surface_m2 NUMERIC(10,2),
        nb_pieces INTEGER,
        nb_chambres INTEGER,
        localisation VARCHAR(200),
        code_postal VARCHAR(5),
        type_bien VARCHAR(50),
        url TEXT,
        description TEXT,
        prix_m2 NUMERIC(10,2),
        ascenseur BOOLEAN DEFAULT FALSE,
        balcon BOOLEAN DEFAULT FALSE,
        terrasse BOOLEAN DEFAULT FALSE,
        parking BOOLEAN DEFAULT FALSE,
        cave BOOLEAN DEFAULT FALSE,
        gardien BOOLEAN DEFAULT FALSE,
        parquet BOOLEAN DEFAULT FALSE,
        cheminee BOOLEAN DEFAULT FALSE,
        calme BOOLEAN DEFAULT FALSE,
        lumineux BOOLEAN DEFAULT FALSE,
        renove BOOLEAN DEFAULT FALSE,
        dernier_etage BOOLEAN DEFAULT FALSE,
        etage INTEGER,
        dpe VARCHAR(1)
    );
    """)

    cur.execute("""
    CREATE TABLE dvf (
        id SERIAL PRIMARY KEY,
        id_mutation VARCHAR(50),
        date_mutation DATE,
        nature_mutation VARCHAR(50),
        valeur_fonciere NUMERIC(15,2),
        adresse_numero VARCHAR(20),
        adresse_nom_voie VARCHAR(200),
        code_postal VARCHAR(5),
        code_commune VARCHAR(10),
        nom_commune VARCHAR(100),
        type_local VARCHAR(50),
        surface_reelle_bati NUMERIC(10,2),
        nombre_pieces_principales INTEGER,
        surface_terrain NUMERIC(10,2),
        longitude NUMERIC(12,8),
        latitude NUMERIC(12,8),
        prix_m2 NUMERIC(10,2)
    );
    """)
    print("Tables creees.")


def safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def safe_float(val):
    if not val:
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


def import_annonces(cur, filepath):
    print("Import annonces...")
    count = 0
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            try:
                cur.execute("""
                    INSERT INTO annonces (plateforme, titre, prix, surface_m2, nb_pieces, nb_chambres,
                                         localisation, code_postal, type_bien, url, description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row.get("plateforme"),
                    row.get("titre"),
                    safe_int(row.get("prix")),
                    safe_float(row.get("surface_m2")),
                    safe_int(row.get("nb_pieces")),
                    safe_int(row.get("nb_chambres")),
                    row.get("localisation"),
                    row.get("code_postal"),
                    row.get("type_bien"),
                    row.get("url"),
                    row.get("description"),
                ))
                count += 1
            except Exception:
                continue
    print("  {} annonces importees.".format(count))


def import_dvf(cur, filepath):
    print("Import DVF...")
    count = 0
    errors = 0
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            try:
                date = row.get("date_mutation")
                if not date:
                    continue
                cur.execute("""
                    INSERT INTO dvf (id_mutation, date_mutation, nature_mutation, valeur_fonciere,
                                     adresse_numero, adresse_nom_voie, code_postal, code_commune,
                                     nom_commune, type_local, surface_reelle_bati,
                                     nombre_pieces_principales, surface_terrain, longitude, latitude)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row.get("id_mutation"),
                    date,
                    row.get("nature_mutation"),
                    safe_float(row.get("valeur_fonciere")),
                    row.get("adresse_numero"),
                    row.get("adresse_nom_voie"),
                    row.get("code_postal"),
                    row.get("code_commune"),
                    row.get("nom_commune"),
                    row.get("type_local"),
                    safe_float(row.get("surface_reelle_bati")),
                    safe_int(row.get("nombre_pieces_principales")),
                    safe_float(row.get("surface_terrain")),
                    safe_float(row.get("longitude")),
                    safe_float(row.get("latitude")),
                ))
                count += 1
            except Exception:
                errors += 1
                continue
    print("  {} lignes DVF importees ({} erreurs).".format(count, errors))


def enrich_sql(cur):
    print("Enrichissement SQL...")

    cur.execute("""
    UPDATE annonces SET
        prix_m2 = CASE WHEN surface_m2 > 0 THEN ROUND(prix::numeric / surface_m2, 2) END,
        ascenseur = description ILIKE '%%ascenseur%%',
        balcon = description ILIKE '%%balcon%%',
        terrasse = description ILIKE '%%terrasse%%',
        parking = description ILIKE '%%parking%%' OR description ILIKE '%%garage%%' OR description ILIKE '%%stationnement%%',
        cave = description ILIKE '%%cave%%',
        gardien = description ILIKE '%%gardien%%' OR description ILIKE '%%concierge%%',
        parquet = description ILIKE '%%parquet%%',
        cheminee = description ILIKE '%%chemin%%e%%',
        calme = description ILIKE '%%calme%%' OR description ILIKE '%%silencieu%%',
        lumineux = description ILIKE '%%lumin%%' OR description ILIKE '%%clair%%' OR description ILIKE '%%ensolei%%',
        renove = description ILIKE '%%r%%nov%%' OR description ILIKE '%%refait%%' OR description ILIKE '%%neuf%%',
        dernier_etage = description ILIKE '%%dernier %%tage%%'
    WHERE description IS NOT NULL AND description != '';
    """)

    cur.execute("""
    UPDATE dvf SET
        prix_m2 = CASE WHEN surface_reelle_bati > 0 THEN ROUND(valeur_fonciere / surface_reelle_bati, 2) END
    WHERE valeur_fonciere > 0;
    """)

    print("  Enrichissement termine.")


def print_stats(cur):
    cur.execute("SELECT COUNT(*) FROM annonces")
    total_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annonces WHERE description IS NOT NULL AND description != ''")
    desc_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annonces WHERE ascenseur = TRUE")
    asc_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annonces WHERE prix_m2 IS NOT NULL")
    pm2_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM dvf")
    total_d = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM dvf WHERE type_local = 'Appartement'")
    appt_d = cur.fetchone()[0]
    cur.execute("SELECT ROUND(AVG(prix_m2)) FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 50000")
    avg_a = cur.fetchone()[0]
    cur.execute("SELECT ROUND(AVG(prix_m2)) FROM dvf WHERE prix_m2 IS NOT NULL AND prix_m2 < 50000 AND type_local = 'Appartement'")
    avg_d = cur.fetchone()[0]

    print("""
============================================================
  IMPORT + ENRICHISSEMENT TERMINE
============================================================
  ANNONCES SeLoger
    Total           : {}
    Avec description: {}
    Avec ascenseur  : {}
    Prix/m2 calcule : {}
    Prix/m2 moyen   : {} EUR

  DVF (ventes reelles)
    Total           : {}
    Appartements    : {}
    Prix/m2 moyen   : {} EUR
============================================================
""".format(total_a, desc_a, asc_a, pm2_a, avg_a, total_d, appt_d, avg_d))


def main():
    import glob

    # Découverte automatique des fichiers
    ann_files = sorted(glob.glob("output/annonces_*.csv"), key=os.path.getmtime)
    ann_files = [f for f in ann_files if "_enrichi" not in f and "_prediction" not in f]
    dvf_files = sorted(glob.glob("output/dvf_*.csv"), key=os.path.getmtime)

    if not ann_files:
        print("Erreur : aucun CSV annonces dans output/")
        return
    if not dvf_files:
        print("Erreur : aucun CSV DVF dans output/")
        return

    ann_path = ann_files[-1]
    dvf_path = dvf_files[-1]
    print("Annonces : {}".format(ann_path))
    print("DVF      : {}".format(dvf_path))

    conn = connect()
    cur = conn.cursor()

    create_tables(cur)
    import_annonces(cur, ann_path)
    import_dvf(cur, dvf_path)
    enrich_sql(cur)
    print_stats(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
