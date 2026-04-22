#!/usr/bin/env python3
"""
Importe les CSV annonces enrichies + DVF dans PostgreSQL.
Crée des vues SQL prêtes pour l'analyse dans pgAdmin.

Usage: python import_db.py
"""
import csv
import glob
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


# ============================================================
# SCHEMA
# ============================================================

def create_tables(cur):
    cur.execute("DROP TABLE IF EXISTS annonces CASCADE;")
    cur.execute("DROP TABLE IF EXISTS dvf CASCADE;")

    # Table annonces avec TOUTES les features IA (50+)
    cur.execute("""
    CREATE TABLE annonces (
        id SERIAL PRIMARY KEY,

        -- Données brutes scraping
        plateforme VARCHAR(50),
        titre TEXT,
        prix INTEGER,
        surface_m2 NUMERIC(10,2),
        nb_pieces INTEGER,
        nb_chambres INTEGER,
        localisation VARCHAR(200),
        code_postal VARCHAR(5),
        type_bien VARCHAR(50),
        url TEXT UNIQUE,
        description TEXT,

        -- Calculé
        prix_m2 NUMERIC(10,2),

        -- Structure du bien (IA)
        etage INTEGER,
        nb_etages_immeuble INTEGER,
        dernier_etage BOOLEAN DEFAULT FALSE,
        rez_de_chaussee BOOLEAN DEFAULT FALSE,
        hauteur_sous_plafond_cm INTEGER,
        ascenseur BOOLEAN DEFAULT FALSE,

        -- Pièces d'eau (IA)
        nb_sdb INTEGER,
        nb_wc INTEGER,
        surface_sejour_m2 NUMERIC(10,2),

        -- Extérieurs (IA)
        balcon BOOLEAN DEFAULT FALSE,
        nb_balcons INTEGER,
        terrasse BOOLEAN DEFAULT FALSE,
        surface_terrasse_m2 NUMERIC(10,2),
        loggia BOOLEAN DEFAULT FALSE,
        roof_top BOOLEAN DEFAULT FALSE,
        jardin BOOLEAN DEFAULT FALSE,
        surface_jardin_m2 NUMERIC(10,2),
        piscine BOOLEAN DEFAULT FALSE,

        -- Stationnement / annexes (IA)
        garage BOOLEAN DEFAULT FALSE,
        nb_parking INTEGER,
        cave BOOLEAN DEFAULT FALSE,
        sous_sol BOOLEAN DEFAULT FALSE,

        -- Intérieur (IA)
        cheminee BOOLEAN DEFAULT FALSE,
        parquet BOOLEAN DEFAULT FALSE,
        cuisine_equipee BOOLEAN DEFAULT FALSE,
        cuisine_type VARCHAR(50),
        double_vitrage BOOLEAN DEFAULT FALSE,
        triple_vitrage BOOLEAN DEFAULT FALSE,
        climatisation BOOLEAN DEFAULT FALSE,
        type_chauffage VARCHAR(30),

        -- Sécurité (IA)
        digicode BOOLEAN DEFAULT FALSE,
        interphone BOOLEAN DEFAULT FALSE,
        gardien BOOLEAN DEFAULT FALSE,
        residence_securisee BOOLEAN DEFAULT FALSE,

        -- Cadre de vie (IA)
        exposition VARCHAR(20),
        lumineux BOOLEAN DEFAULT FALSE,
        calme BOOLEAN DEFAULT FALSE,
        vue_degagee BOOLEAN DEFAULT FALSE,
        vue_type VARCHAR(20),
        vis_a_vis BOOLEAN DEFAULT FALSE,
        etage_eleve BOOLEAN DEFAULT FALSE,

        -- État et énergie (IA)
        etat_general VARCHAR(30),
        travaux_necessaires BOOLEAN DEFAULT FALSE,
        annee_construction INTEGER,
        dpe_lettre CHAR(1),
        dpe_valeur INTEGER,
        ges_lettre CHAR(1),
        ges_valeur INTEGER,

        -- Localisation (IA)
        proche_transports BOOLEAN DEFAULT FALSE,
        distance_metro_min INTEGER,
        nom_station_metro VARCHAR(100),
        ligne_metro VARCHAR(50),
        proche_commerces BOOLEAN DEFAULT FALSE,
        proche_ecoles BOOLEAN DEFAULT FALSE,
        quartier VARCHAR(100),

        -- Copropriété (IA)
        copropriete BOOLEAN DEFAULT FALSE,
        nb_lots_copro INTEGER,
        charges_copro_mois NUMERIC(10,2),
        taxe_fonciere_an NUMERIC(10,2),
        travaux_copro_prevus BOOLEAN DEFAULT FALSE,

        -- Divers (IA)
        meuble BOOLEAN DEFAULT FALSE,
        mandat_exclusif BOOLEAN DEFAULT FALSE,
        viager BOOLEAN DEFAULT FALSE,
        coup_de_coeur BOOLEAN DEFAULT FALSE,
        points_forts TEXT,
        points_faibles TEXT
    );
    """)

    # Table DVF
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
        nombre_lots INTEGER,
        lot1_surface_carrez NUMERIC(10,2),
        surface_terrain NUMERIC(10,2),
        longitude NUMERIC(12,8),
        latitude NUMERIC(12,8),
        prix_m2 NUMERIC(10,2)
    );
    """)

    # Index pour performances
    cur.execute("CREATE INDEX idx_annonces_prix_m2 ON annonces(prix_m2);")
    cur.execute("CREATE INDEX idx_annonces_nb_pieces ON annonces(nb_pieces);")
    cur.execute("CREATE INDEX idx_annonces_dpe ON annonces(dpe_lettre);")
    cur.execute("CREATE INDEX idx_annonces_etat ON annonces(etat_general);")
    cur.execute("CREATE INDEX idx_dvf_date ON dvf(date_mutation);")
    cur.execute("CREATE INDEX idx_dvf_type ON dvf(type_local);")
    cur.execute("CREATE INDEX idx_dvf_prix_m2 ON dvf(prix_m2);")

    print("Tables + index crees.")


# ============================================================
# IMPORT CSV
# ============================================================

def safe_int(val):
    if not val or val in ("", "null", "None"):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_float(val):
    if not val or val in ("", "null", "None"):
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


def safe_bool(val):
    if not val or val in ("", "null", "None"):
        return False
    return str(val).lower().strip() in ("true", "1", "oui", "yes")


def safe_str(val, max_len=None):
    if not val or val in ("null", "None"):
        return None
    s = str(val).strip()
    if not s:
        return None
    if max_len:
        s = s[:max_len]
    return s


def safe_dpe(val):
    if not val or val in ("", "null", "None"):
        return None
    v = str(val).strip().upper()
    return v if len(v) == 1 and v in "ABCDEFG" else None


def import_annonces(cur, filepath):
    print("Import annonces : {}".format(filepath))
    count = 0
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            try:
                prix = safe_int(row.get("prix"))
                surface = safe_float(row.get("surface_m2"))
                prix_m2 = round(prix / surface, 2) if prix and surface and surface > 0 else None

                cur.execute("""
                    INSERT INTO annonces (
                        plateforme, titre, prix, surface_m2, nb_pieces, nb_chambres,
                        localisation, code_postal, type_bien, url, description, prix_m2,
                        etage, nb_etages_immeuble, dernier_etage, rez_de_chaussee,
                        hauteur_sous_plafond_cm, ascenseur,
                        nb_sdb, nb_wc, surface_sejour_m2,
                        balcon, nb_balcons, terrasse, surface_terrasse_m2,
                        loggia, roof_top, jardin, surface_jardin_m2, piscine,
                        garage, nb_parking, cave, sous_sol,
                        cheminee, parquet, cuisine_equipee, cuisine_type,
                        double_vitrage, triple_vitrage, climatisation, type_chauffage,
                        digicode, interphone, gardien, residence_securisee,
                        exposition, lumineux, calme, vue_degagee, vue_type,
                        vis_a_vis, etage_eleve,
                        etat_general, travaux_necessaires, annee_construction,
                        dpe_lettre, dpe_valeur, ges_lettre, ges_valeur,
                        proche_transports, distance_metro_min, nom_station_metro, ligne_metro,
                        proche_commerces, proche_ecoles, quartier,
                        copropriete, nb_lots_copro, charges_copro_mois, taxe_fonciere_an,
                        travaux_copro_prevus,
                        meuble, mandat_exclusif, viager, coup_de_coeur,
                        points_forts, points_faibles
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT (url) DO NOTHING
                """, (
                    safe_str(row.get("plateforme")),
                    safe_str(row.get("titre")),
                    prix,
                    surface,
                    safe_int(row.get("nb_pieces")),
                    safe_int(row.get("nb_chambres")),
                    safe_str(row.get("localisation")),
                    safe_str(row.get("code_postal"), 5),
                    safe_str(row.get("type_bien")),
                    safe_str(row.get("url")),
                    safe_str(row.get("description")),
                    prix_m2,
                    # Structure
                    safe_int(row.get("etage")),
                    safe_int(row.get("nb_etages_immeuble")),
                    safe_bool(row.get("dernier_etage")),
                    safe_bool(row.get("rez_de_chaussee")),
                    safe_int(row.get("hauteur_sous_plafond_cm")),
                    safe_bool(row.get("ascenseur")),
                    # Pièces d'eau
                    safe_int(row.get("nb_sdb")),
                    safe_int(row.get("nb_wc")),
                    safe_float(row.get("surface_sejour_m2")),
                    # Extérieurs
                    safe_bool(row.get("balcon")),
                    safe_int(row.get("nb_balcons")),
                    safe_bool(row.get("terrasse")),
                    safe_float(row.get("surface_terrasse_m2")),
                    safe_bool(row.get("loggia")),
                    safe_bool(row.get("roof_top")),
                    safe_bool(row.get("jardin")),
                    safe_float(row.get("surface_jardin_m2")),
                    safe_bool(row.get("piscine")),
                    # Annexes
                    safe_bool(row.get("garage")),
                    safe_int(row.get("nb_parking")),
                    safe_bool(row.get("cave")),
                    safe_bool(row.get("sous_sol")),
                    # Intérieur
                    safe_bool(row.get("cheminee")),
                    safe_bool(row.get("parquet")),
                    safe_bool(row.get("cuisine_equipee")),
                    safe_str(row.get("cuisine_type"), 50),
                    safe_bool(row.get("double_vitrage")),
                    safe_bool(row.get("triple_vitrage")),
                    safe_bool(row.get("climatisation")),
                    safe_str(row.get("type_chauffage"), 30),
                    # Sécurité
                    safe_bool(row.get("digicode")),
                    safe_bool(row.get("interphone")),
                    safe_bool(row.get("gardien")),
                    safe_bool(row.get("residence_securisee")),
                    # Cadre de vie
                    safe_str(row.get("exposition"), 20),
                    safe_bool(row.get("lumineux")),
                    safe_bool(row.get("calme")),
                    safe_bool(row.get("vue_degagee")),
                    safe_str(row.get("vue_type"), 20),
                    safe_bool(row.get("vis_a_vis")),
                    safe_bool(row.get("etage_eleve")),
                    # État et énergie
                    safe_str(row.get("etat_general"), 30),
                    safe_bool(row.get("travaux_necessaires")),
                    safe_int(row.get("annee_construction")),
                    safe_dpe(row.get("dpe_lettre")),
                    safe_int(row.get("dpe_valeur")),
                    safe_dpe(row.get("ges_lettre")),
                    safe_int(row.get("ges_valeur")),
                    # Localisation
                    safe_bool(row.get("proche_transports")),
                    safe_int(row.get("distance_metro_min")),
                    safe_str(row.get("nom_station_metro"), 100),
                    safe_str(row.get("ligne_metro"), 50),
                    safe_bool(row.get("proche_commerces")),
                    safe_bool(row.get("proche_ecoles")),
                    safe_str(row.get("quartier"), 100),
                    # Copropriété
                    safe_bool(row.get("copropriete")),
                    safe_int(row.get("nb_lots_copro")),
                    safe_float(row.get("charges_copro_mois")),
                    safe_float(row.get("taxe_fonciere_an")),
                    safe_bool(row.get("travaux_copro_prevus")),
                    # Divers
                    safe_bool(row.get("meuble")),
                    safe_bool(row.get("mandat_exclusif")),
                    safe_bool(row.get("viager")),
                    safe_bool(row.get("coup_de_coeur")),
                    safe_str(row.get("points_forts")),
                    safe_str(row.get("points_faibles")),
                ))
                count += 1
            except Exception as e:
                continue
    print("  {} annonces importees.".format(count))


def import_dvf(cur, filepath):
    print("Import DVF : {}".format(filepath))
    count = 0
    errors = 0
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            try:
                date = row.get("date_mutation")
                if not date:
                    continue
                vf = safe_float(row.get("valeur_fonciere"))
                surface = safe_float(row.get("surface_reelle_bati"))
                prix_m2 = round(vf / surface, 2) if vf and surface and surface > 0 else None

                cur.execute("""
                    INSERT INTO dvf (
                        id_mutation, date_mutation, nature_mutation, valeur_fonciere,
                        adresse_numero, adresse_nom_voie, code_postal, code_commune,
                        nom_commune, type_local, surface_reelle_bati,
                        nombre_pieces_principales, nombre_lots, lot1_surface_carrez,
                        surface_terrain, longitude, latitude, prix_m2
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    row.get("id_mutation"),
                    date,
                    row.get("nature_mutation"),
                    vf,
                    row.get("adresse_numero"),
                    row.get("adresse_nom_voie"),
                    row.get("code_postal"),
                    row.get("code_commune"),
                    row.get("nom_commune"),
                    row.get("type_local"),
                    surface,
                    safe_int(row.get("nombre_pieces_principales")),
                    safe_int(row.get("nombre_lots")),
                    safe_float(row.get("lot1_surface_carrez")),
                    safe_float(row.get("surface_terrain")),
                    safe_float(row.get("longitude")),
                    safe_float(row.get("latitude")),
                    prix_m2,
                ))
                count += 1
            except Exception:
                errors += 1
                continue
    print("  {} lignes DVF importees ({} erreurs).".format(count, errors))


# ============================================================
# VUES SQL POUR ANALYSE PGADMIN
# ============================================================

def create_views(cur):
    print("Creation des vues SQL...")

    # ── Vue 1 : Résumé par nombre de pièces ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_resume_pieces AS
    SELECT
        nb_pieces,
        COUNT(*) AS nb_annonces,
        ROUND(AVG(prix)) AS prix_moyen,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix)) AS prix_median,
        ROUND(AVG(prix_m2)) AS prix_m2_moyen,
        ROUND(AVG(surface_m2), 1) AS surface_moyenne
    FROM annonces
    WHERE prix > 50000 AND surface_m2 >= 9
    GROUP BY nb_pieces
    ORDER BY nb_pieces;
    """)

    # ── Vue 2 : Impact DPE sur le prix/m² ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_impact_dpe AS
    SELECT
        dpe_lettre,
        COUNT(*) AS nb_annonces,
        ROUND(AVG(prix_m2)) AS prix_m2_moyen,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix_m2)) AS prix_m2_median,
        ROUND(AVG(surface_m2), 1) AS surface_moyenne
    FROM annonces
    WHERE dpe_lettre IS NOT NULL AND prix_m2 IS NOT NULL AND prix_m2 < 30000
    GROUP BY dpe_lettre
    ORDER BY dpe_lettre;
    """)

    # ── Vue 3 : Impact état général sur le prix/m² ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_impact_etat AS
    SELECT
        etat_general,
        COUNT(*) AS nb_annonces,
        ROUND(AVG(prix_m2)) AS prix_m2_moyen,
        ROUND(AVG(prix)) AS prix_moyen,
        ROUND(AVG(surface_m2), 1) AS surface_moyenne
    FROM annonces
    WHERE etat_general IS NOT NULL AND prix_m2 IS NOT NULL
    GROUP BY etat_general
    ORDER BY prix_m2_moyen DESC;
    """)

    # ── Vue 4 : Premium des équipements ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_premium_equipements AS
    SELECT
        'ascenseur' AS equipement,
        ROUND(AVG(CASE WHEN ascenseur THEN prix_m2 END)) AS prix_m2_avec,
        ROUND(AVG(CASE WHEN NOT ascenseur THEN prix_m2 END)) AS prix_m2_sans,
        ROUND(AVG(CASE WHEN ascenseur THEN prix_m2 END) - AVG(CASE WHEN NOT ascenseur THEN prix_m2 END)) AS delta,
        SUM(CASE WHEN ascenseur THEN 1 ELSE 0 END) AS nb_avec
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    UNION ALL
    SELECT 'balcon',
        ROUND(AVG(CASE WHEN balcon THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN NOT balcon THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN balcon THEN prix_m2 END) - AVG(CASE WHEN NOT balcon THEN prix_m2 END)),
        SUM(CASE WHEN balcon THEN 1 ELSE 0 END)
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    UNION ALL
    SELECT 'terrasse',
        ROUND(AVG(CASE WHEN terrasse THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN NOT terrasse THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN terrasse THEN prix_m2 END) - AVG(CASE WHEN NOT terrasse THEN prix_m2 END)),
        SUM(CASE WHEN terrasse THEN 1 ELSE 0 END)
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    UNION ALL
    SELECT 'cave',
        ROUND(AVG(CASE WHEN cave THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN NOT cave THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN cave THEN prix_m2 END) - AVG(CASE WHEN NOT cave THEN prix_m2 END)),
        SUM(CASE WHEN cave THEN 1 ELSE 0 END)
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    UNION ALL
    SELECT 'parking',
        ROUND(AVG(CASE WHEN garage THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN NOT garage THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN garage THEN prix_m2 END) - AVG(CASE WHEN NOT garage THEN prix_m2 END)),
        SUM(CASE WHEN garage THEN 1 ELSE 0 END)
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    UNION ALL
    SELECT 'gardien',
        ROUND(AVG(CASE WHEN gardien THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN NOT gardien THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN gardien THEN prix_m2 END) - AVG(CASE WHEN NOT gardien THEN prix_m2 END)),
        SUM(CASE WHEN gardien THEN 1 ELSE 0 END)
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    UNION ALL
    SELECT 'parquet',
        ROUND(AVG(CASE WHEN parquet THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN NOT parquet THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN parquet THEN prix_m2 END) - AVG(CASE WHEN NOT parquet THEN prix_m2 END)),
        SUM(CASE WHEN parquet THEN 1 ELSE 0 END)
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    UNION ALL
    SELECT 'dernier_etage',
        ROUND(AVG(CASE WHEN dernier_etage THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN NOT dernier_etage THEN prix_m2 END)),
        ROUND(AVG(CASE WHEN dernier_etage THEN prix_m2 END) - AVG(CASE WHEN NOT dernier_etage THEN prix_m2 END)),
        SUM(CASE WHEN dernier_etage THEN 1 ELSE 0 END)
    FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000
    ORDER BY delta DESC NULLS LAST;
    """)

    # ── Vue 5 : Comparaison annonces vs DVF (marché réel) ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_annonces_vs_dvf AS
    SELECT
        a.nb_pieces,
        COUNT(DISTINCT a.id) AS nb_annonces,
        ROUND(AVG(a.prix_m2)) AS prix_m2_annonces,
        d.prix_m2_dvf,
        ROUND(AVG(a.prix_m2) - d.prix_m2_dvf) AS ecart_prix_m2,
        ROUND((AVG(a.prix_m2) - d.prix_m2_dvf) / d.prix_m2_dvf * 100, 1) AS ecart_pct
    FROM annonces a
    LEFT JOIN (
        SELECT
            nombre_pieces_principales AS nb_pieces,
            ROUND(AVG(prix_m2)) AS prix_m2_dvf
        FROM dvf
        WHERE type_local = 'Appartement'
          AND prix_m2 IS NOT NULL AND prix_m2 BETWEEN 3000 AND 30000
          AND nature_mutation = 'Vente'
        GROUP BY nombre_pieces_principales
    ) d ON a.nb_pieces = d.nb_pieces
    WHERE a.prix_m2 IS NOT NULL AND a.prix_m2 < 30000
    GROUP BY a.nb_pieces, d.prix_m2_dvf
    ORDER BY a.nb_pieces;
    """)

    # ── Vue 6 : Évolution DVF par trimestre ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_dvf_evolution AS
    SELECT
        EXTRACT(YEAR FROM date_mutation) AS annee,
        EXTRACT(QUARTER FROM date_mutation) AS trimestre,
        COUNT(*) AS nb_ventes,
        ROUND(AVG(prix_m2)) AS prix_m2_moyen,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix_m2)) AS prix_m2_median,
        ROUND(AVG(valeur_fonciere)) AS prix_moyen,
        ROUND(AVG(surface_reelle_bati), 1) AS surface_moyenne
    FROM dvf
    WHERE type_local = 'Appartement'
      AND nature_mutation = 'Vente'
      AND prix_m2 IS NOT NULL AND prix_m2 BETWEEN 3000 AND 30000
    GROUP BY annee, trimestre
    ORDER BY annee, trimestre;
    """)

    # ── Vue 7 : Bonnes affaires (sous-évaluées) ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_bonnes_affaires AS
    SELECT
        titre,
        prix,
        surface_m2,
        nb_pieces,
        prix_m2,
        dpe_lettre,
        etat_general,
        etage,
        ascenseur,
        balcon,
        cave,
        quartier,
        url
    FROM annonces
    WHERE prix_m2 IS NOT NULL
      AND prix_m2 < (SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY prix_m2)
                     FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000)
      AND surface_m2 >= 9
      AND prix > 50000
    ORDER BY prix_m2 ASC;
    """)

    # ── Vue 8 : Couverture enrichissement IA ──
    cur.execute("""
    CREATE OR REPLACE VIEW v_couverture_ia AS
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN etage IS NOT NULL THEN 1 ELSE 0 END) AS etage,
        SUM(CASE WHEN nb_sdb IS NOT NULL THEN 1 ELSE 0 END) AS nb_sdb,
        SUM(CASE WHEN dpe_lettre IS NOT NULL THEN 1 ELSE 0 END) AS dpe,
        SUM(CASE WHEN etat_general IS NOT NULL THEN 1 ELSE 0 END) AS etat,
        SUM(CASE WHEN exposition IS NOT NULL THEN 1 ELSE 0 END) AS exposition,
        SUM(CASE WHEN vue_type IS NOT NULL THEN 1 ELSE 0 END) AS vue_type,
        SUM(CASE WHEN type_chauffage IS NOT NULL THEN 1 ELSE 0 END) AS chauffage,
        SUM(CASE WHEN quartier IS NOT NULL THEN 1 ELSE 0 END) AS quartier,
        SUM(CASE WHEN hauteur_sous_plafond_cm IS NOT NULL THEN 1 ELSE 0 END) AS hauteur_plafond,
        SUM(CASE WHEN ascenseur THEN 1 ELSE 0 END) AS ascenseur,
        SUM(CASE WHEN balcon THEN 1 ELSE 0 END) AS balcon,
        SUM(CASE WHEN cave THEN 1 ELSE 0 END) AS cave,
        SUM(CASE WHEN terrasse THEN 1 ELSE 0 END) AS terrasse,
        SUM(CASE WHEN gardien THEN 1 ELSE 0 END) AS gardien,
        SUM(CASE WHEN residence_securisee THEN 1 ELSE 0 END) AS securisee,
        SUM(CASE WHEN proche_transports THEN 1 ELSE 0 END) AS transports,
        SUM(CASE WHEN charges_copro_mois IS NOT NULL THEN 1 ELSE 0 END) AS charges,
        SUM(CASE WHEN nom_station_metro IS NOT NULL THEN 1 ELSE 0 END) AS station_metro
    FROM annonces;
    """)

    print("  8 vues creees.")


# ============================================================
# STATS
# ============================================================

def print_stats(cur):
    cur.execute("SELECT COUNT(*) FROM annonces")
    total_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annonces WHERE dpe_lettre IS NOT NULL")
    dpe_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annonces WHERE etat_general IS NOT NULL")
    etat_a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annonces WHERE etage IS NOT NULL")
    etage_a = cur.fetchone()[0]
    cur.execute("SELECT ROUND(AVG(prix_m2)) FROM annonces WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000")
    avg_a = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM dvf")
    total_d = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM dvf WHERE type_local = 'Appartement' AND nature_mutation = 'Vente'")
    appt_d = cur.fetchone()[0]
    cur.execute("SELECT ROUND(AVG(prix_m2)) FROM dvf WHERE prix_m2 IS NOT NULL AND prix_m2 < 30000 AND type_local = 'Appartement'")
    avg_d = cur.fetchone()[0]

    print("""
============================================================
  IMPORT TERMINE
============================================================
  ANNONCES
    Total             : {}
    Avec DPE          : {}
    Avec etat_general : {}
    Avec etage        : {}
    Prix/m2 moyen     : {} EUR

  DVF
    Total             : {}
    Appartements      : {}
    Prix/m2 moyen     : {} EUR

  VUES SQL DISPONIBLES (pgAdmin > immo_hunter > Views)
    v_resume_pieces        Résumé prix par nb de pièces
    v_impact_dpe           Impact du DPE sur le prix/m²
    v_impact_etat          Impact de l'état sur le prix/m²
    v_premium_equipements  Prime des équipements (+/- EUR/m²)
    v_annonces_vs_dvf      Annonces vs marché réel DVF
    v_dvf_evolution        Évolution DVF par trimestre
    v_bonnes_affaires      Annonces sous-évaluées
    v_couverture_ia        Couverture de l'enrichissement IA
============================================================
""".format(total_a, dpe_a, etat_a, etage_a, avg_a, total_d, appt_d, avg_d))


# ============================================================
# MAIN
# ============================================================

def main():
    # Préférer le CSV enrichi s'il existe
    enrichi_files = sorted(glob.glob("output/annonces_*_enrichi.csv"), key=os.path.getmtime)
    ann_files = sorted(glob.glob("output/annonces_*.csv"), key=os.path.getmtime)
    ann_files = [f for f in ann_files if "_enrichi" not in f and "_prediction" not in f]
    dvf_files = sorted(glob.glob("output/dvf_*.csv"), key=os.path.getmtime)

    ann_path = enrichi_files[-1] if enrichi_files else (ann_files[-1] if ann_files else None)
    dvf_path = dvf_files[-1] if dvf_files else None

    if not ann_path:
        print("Erreur : aucun CSV annonces dans output/")
        return
    if not dvf_path:
        print("Erreur : aucun CSV DVF dans output/")
        return

    print("Annonces : {}".format(ann_path))
    print("DVF      : {}".format(dvf_path))

    conn = connect()
    cur = conn.cursor()

    create_tables(cur)
    import_annonces(cur, ann_path)
    import_dvf(cur, dvf_path)
    create_views(cur)
    print_stats(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
