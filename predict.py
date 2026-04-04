"""
predict.py — Prédiction des prix immobiliers Paris 16e
Projet : immo-hunter
Auteur : Maxime Teixeira Novais — M2 Data Science & BI, EDC Paris

Le script entraîne un modèle sur les transactions DVF (2020-2025)
puis prédit le prix des annonces en ligne.
Résultat exporté en CSV → à importer dans Power BI.
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 1. CHARGEMENT
# ============================================================

print("=" * 50)
print("1. CHARGEMENT DES DONNÉES")
print("=" * 50)

dvf = pd.read_csv("output/dvf_paris16.csv", sep=";", low_memory=False)
annonces = pd.read_csv("output/annonces_paris-16eme_enrichi.csv", sep=";", low_memory=False)

print(f"DVF : {dvf.shape[0]} lignes")
print(f"Annonces : {annonces.shape[0]} lignes")

# ============================================================
# 2. NETTOYAGE DVF
# ============================================================

print("\n" + "=" * 50)
print("2. NETTOYAGE DVF")
print("=" * 50)

# Garder les appartements avec données complètes
dvf = dvf[dvf["type_local"] == "Appartement"].copy()
dvf = dvf.dropna(subset=["valeur_fonciere", "surface_reelle_bati", "nombre_pieces_principales"])
dvf = dvf[
    (dvf["valeur_fonciere"] > 50000) &
    (dvf["surface_reelle_bati"] >= 9) &
    (dvf["surface_reelle_bati"] <= 300) &
    (dvf["nombre_pieces_principales"] >= 1)
]

# Dédoublonner (DVF duplique les lignes par lot)
dvf = dvf.drop_duplicates(subset=["id_mutation"], keep="first")

# Extraire l'année
dvf["annee"] = pd.to_datetime(dvf["date_mutation"], errors="coerce").dt.year

# Supprimer les prix aberrants (top/bottom 5%)
dvf["prix_m2"] = dvf["valeur_fonciere"] / dvf["surface_reelle_bati"]
q_bas = dvf["prix_m2"].quantile(0.05)
q_haut = dvf["prix_m2"].quantile(0.95)
dvf = dvf[(dvf["prix_m2"] >= q_bas) & (dvf["prix_m2"] <= q_haut)]

print(f"Transactions retenues : {dvf.shape[0]}")
print(f"Prix moyen : {dvf['valeur_fonciere'].mean():,.0f} €")
print(f"Surface moyenne : {dvf['surface_reelle_bati'].mean():.0f} m²")

# ============================================================
# 3. ENTRAÎNEMENT
# ============================================================

print("\n" + "=" * 50)
print("3. ENTRAÎNEMENT DES MODÈLES")
print("=" * 50)

features = ["surface_reelle_bati", "nombre_pieces_principales", "annee"]

X = dvf[features]
y = dvf["valeur_fonciere"]  # On prédit le prix total

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"Train : {X_train.shape[0]} | Test : {X_test.shape[0]}")

# Régression Linéaire
lr = LinearRegression()
lr.fit(X_train, y_train)
r2_lr = r2_score(y_test, lr.predict(X_test))
mae_lr = mean_absolute_error(y_test, lr.predict(X_test))
print(f"\nRégression Linéaire : R² = {r2_lr:.3f} | MAE = {mae_lr:,.0f} €")

# Random Forest
rf = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
rf.fit(X_train, y_train)
r2_rf = r2_score(y_test, rf.predict(X_test))
mae_rf = mean_absolute_error(y_test, rf.predict(X_test))
print(f"Random Forest :       R² = {r2_rf:.3f} | MAE = {mae_rf:,.0f} €")

# Garder le meilleur
if r2_rf > r2_lr:
    best, best_name = rf, "Random Forest"
else:
    best, best_name = lr, "Régression Linéaire"

print(f"\nMeilleur modèle : {best_name}")

# ============================================================
# 4. PRÉDICTION SUR LES ANNONCES
# ============================================================

print("\n" + "=" * 50)
print("4. PRÉDICTION SUR LES ANNONCES")
print("=" * 50)

ann = annonces.dropna(subset=["prix", "surface_m2", "nb_pieces"]).copy()
ann = ann[(ann["surface_m2"] >= 9) & (ann["surface_m2"] <= 300) & (ann["prix"] > 50000)]

ann["surface_reelle_bati"] = ann["surface_m2"]
ann["nombre_pieces_principales"] = ann["nb_pieces"]
ann["annee"] = 2025

# Prédire le prix
ann["prix_predit"] = best.predict(ann[features])
ann["ecart_pct"] = ((ann["prix"] - ann["prix_predit"]) / ann["prix_predit"]) * 100

print(f"Annonces analysées : {ann.shape[0]}")
print(f"Prix demandé moyen : {ann['prix'].mean():,.0f} €")
print(f"Prix prédit moyen  : {ann['prix_predit'].mean():,.0f} €")
print(f"Écart médian       : {ann['ecart_pct'].median():+.1f}%")

# ============================================================
# 5. EXPORT CSV POUR POWER BI
# ============================================================

print("\n" + "=" * 50)
print("5. EXPORT")
print("=" * 50)

# Tableau complet des annonces avec prédictions
export = ann[["titre", "prix", "surface_m2", "nb_pieces",
              "prix_predit", "ecart_pct", "type_bien", "url"]].copy()
export["prix_predit"] = export["prix_predit"].round(0).astype(int)
export["ecart_pct"] = export["ecart_pct"].round(1)
export.to_csv("output/annonces_avec_prediction.csv", index=False, sep=";")
print(f"✅ output/annonces_avec_prediction.csv ({export.shape[0]} lignes)")

# Tableau résumé par nb_pieces pour Power BI
pbi = ann.groupby("nb_pieces").agg(
    prix_demande_moyen=("prix", "mean"),
    prix_predit_moyen=("prix_predit", "mean"),
    nb_annonces=("prix", "count")
).reset_index()
pbi = pbi[pbi["nb_annonces"] >= 10]
pbi["prix_demande_moyen"] = pbi["prix_demande_moyen"].round(0).astype(int)
pbi["prix_predit_moyen"] = pbi["prix_predit_moyen"].round(0).astype(int)
pbi.to_csv("output/prediction_powerbi.csv", index=False, sep=";")
print(f"✅ output/prediction_powerbi.csv")

print("\n🎯 TERMINÉ — Importe prediction_powerbi.csv dans Power BI")
