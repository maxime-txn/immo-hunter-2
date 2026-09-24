import pandas as pd

from immohunter import base


def test_croisement_compare_prix_affiche_et_prix_vendu(tmp_path):
    # 2 ventes réelles à 10 000 €/m² dans le 16e, 2 annonces affichées à 11 000 €/m²
    ventes = pd.DataFrame({
        "date": pd.to_datetime(["2025-11-01", "2025-12-01"]), "secteur": ["Paris 16e"] * 2,
        "prix_m2": [10_000.0, 10_000.0]})
    ventes.to_parquet(tmp_path / "ventes.parquet", index=False)
    annonces = pd.DataFrame({
        "secteur": ["Paris 16e"] * 2, "prix": [550_000, 770_000], "surface": [50, 70],
        "ecart_pct": [4.0, 12.0], "verdict": ["Au prix du marché", "Surévalué"]})
    annonces.to_csv(tmp_path / "annonces.csv", sep=";", index=False)

    con = base.connexion(str(tmp_path / "ventes.parquet"))
    base.ajouter_annonces(con, str(tmp_path / "annonces.csv"))
    r = base.requete(con, "croisement_annonces_dvf").iloc[0]

    assert r["ecart_affiche_vs_vendu_pct"] == 10.0
    assert r["part_annonces_au_dessus_pct"] == 50.0
