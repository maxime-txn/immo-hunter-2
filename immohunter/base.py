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


def requete(con, nom, **parametres):
    sql = (DOSSIER_SQL / f"{nom}.sql").read_text(encoding="utf-8")
    return con.execute(sql, parametres or None).df()
