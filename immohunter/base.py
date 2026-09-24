"""
Couche SQL : DuckDB lit directement le fichier des ventes (parquet), sans serveur.
Les requêtes sont dans le dossier sql/, en SQL standard (compatible PostgreSQL).
"""
from pathlib import Path

import duckdb

DOSSIER_SQL = Path(__file__).resolve().parent.parent / "sql"


def connexion(fichier_ventes):
    con = duckdb.connect()
    con.execute(f"CREATE VIEW ventes AS SELECT * FROM read_parquet('{fichier_ventes}')")
    return con


def ajouter_annonces(con, fichier_annonces_analysees):
    """Rend les annonces analysées (sortie de analyse_lot) interrogeables en SQL : table `annonces`."""
    con.execute("CREATE OR REPLACE VIEW annonces AS SELECT * FROM "
                f"read_csv('{fichier_annonces_analysees}', delim=';', header=true)")


def requete(con, nom, **parametres):
    sql = (DOSSIER_SQL / f"{nom}.sql").read_text(encoding="utf-8")
    return con.execute(sql, parametres or None).df()
