"""
predict.py — Prédiction des prix immobiliers
Projet : immo-hunter
Auteur : Maxime Teixeira Novais — M2 Data Science & BI, EDC Paris

Le script entraîne un modèle sur les transactions DVF
puis prédit le prix des annonces en ligne.
Résultat exporté en CSV → à importer dans Power BI.
"""

import glob
import os
import sys

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, r2_score
from datetime import date
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 1. CHARGEMENT
# ============================================================

print("=" * 60)
print("1. CHARGEMENT DES DONNÉES")
print("=" * 60)

# Découverte automatique des fichiers
dvf_files = glob.glob("output/dvf_*.csv")
if not dvf_files:
    print("Erreur : aucun fichier DVF dans output/")
    sys.exit(1)
dvf_path = max(dvf_files, key=os.path.getmtime)

enrichi_files = glob.glob("output/annonces_*_enrichi.csv")
annonces_files = glob.glob("output/annonces_*.csv")
# Préférer le fichier enrichi s'il existe
if enrichi_files:
    ann_path = max(enrichi_files, key=os.path.getmtime)
elif annonces_files:
    ann_path = max(annonces_files, key=os.path.getmtime)
else:
    print("Erreur : aucun fichier annonces dans output/")
    sys.exit(1)

print(f"DVF      : {dvf_path}")
print(f"Annonces : {ann_path}")

dvf = pd.read_csv(dvf_path, sep=";", low_memory=False)
annonces = pd.read_csv(ann_path, sep=";", low_memory=False)

print(f"DVF : {dvf.shape[0]} lignes, {dvf.shape[1]} colonnes")
print(f"Annonces : {annonces.shape[0]} lignes, {annonces.shape[1]} colonnes")

# ============================================================
# 2. NETTOYAGE DVF
# ============================================================

print("\n" + "=" * 60)
print("2. NETTOYAGE DVF")
print("=" * 60)

dvf = dvf[dvf["type_local"] == "Appartement"].copy()
dvf = dvf.dropna(subset=["valeur_fonciere", "surface_reelle_bati",
                          "nombre_pieces_principales", "longitude", "latitude"])
dvf = dvf[
    (dvf["valeur_fonciere"] > 50000) &
    (dvf["surface_reelle_bati"] >= 9) &
    (dvf["surface_reelle_bati"] <= 300) &
    (dvf["nombre_pieces_principales"] >= 1)
]

dvf = dvf.drop_duplicates(subset=["id_mutation"], keep="first")

# Temporalité
dvf["date_mutation"] = pd.to_datetime(dvf["date_mutation"], errors="coerce")
dvf["annee"] = dvf["date_mutation"].dt.year
dvf["mois"] = dvf["date_mutation"].dt.month

# Outliers prix/m²
dvf["prix_m2"] = dvf["valeur_fonciere"] / dvf["surface_reelle_bati"]
q_bas = dvf["prix_m2"].quantile(0.05)
q_haut = dvf["prix_m2"].quantile(0.95)
dvf = dvf[(dvf["prix_m2"] >= q_bas) & (dvf["prix_m2"] <= q_haut)]

print(f"Transactions retenues : {dvf.shape[0]}")
print(f"Prix moyen : {dvf['valeur_fonciere'].mean():,.0f} €")
print(f"Surface moyenne : {dvf['surface_reelle_bati'].mean():.0f} m²")
print(f"Prix/m² moyen : {dvf['prix_m2'].mean():,.0f} €")

# ============================================================
# 3. FEATURE ENGINEERING DVF
# ============================================================

print("\n" + "=" * 60)
print("3. FEATURE ENGINEERING")
print("=" * 60)

# Surface Carrez si disponible, sinon surface réelle
dvf["lot1_surface_carrez"] = pd.to_numeric(dvf["lot1_surface_carrez"], errors="coerce")
dvf["surface_best"] = dvf["lot1_surface_carrez"].fillna(dvf["surface_reelle_bati"])

# Nombre de lots
dvf["nombre_lots"] = pd.to_numeric(dvf["nombre_lots"], errors="coerce").fillna(1)

# Prix/m² médian par micro-quartier (cellule géographique ~100m)
dvf["geo_cell"] = (dvf["latitude"].round(3).astype(str) + "_" +
                   dvf["longitude"].round(3).astype(str))
zone_medians = dvf.groupby("geo_cell")["prix_m2"].median()
dvf["prix_m2_zone"] = dvf["geo_cell"].map(zone_medians)

FEATURES = [
    "surface_best",
    "nombre_pieces_principales",
    "annee",
    "mois",
    "longitude",
    "latitude",
    "nombre_lots",
    "prix_m2_zone",
]

print(f"Features : {len(FEATURES)}")
for f in FEATURES:
    non_null = dvf[f].notna().sum()
    print(f"  {f:30s} : {non_null}/{len(dvf)} ({non_null/len(dvf)*100:.0f}%)")

# ============================================================
# 4. ENTRAÎNEMENT + CROSS-VALIDATION
# ============================================================

print("\n" + "=" * 60)
print("4. ENTRAÎNEMENT DES MODÈLES (5-fold CV)")
print("=" * 60)

X = dvf[FEATURES].copy()
y = dvf["valeur_fonciere"].copy()

# Supprimer les lignes avec NaN dans les features
mask = X.notna().all(axis=1)
X = X[mask]
y = y[mask]
print(f"Échantillons valides : {len(X)}")

models = {
    "Régression Linéaire": Pipeline([
        ("scaler", StandardScaler()),
        ("model", LinearRegression()),
    ]),
    "Random Forest": RandomForestRegressor(
        n_estimators=200, max_depth=15, min_samples_leaf=5,
        random_state=42, n_jobs=-1,
    ),
    "Gradient Boosting": GradientBoostingRegressor(
        n_estimators=300, max_depth=6, learning_rate=0.1,
        min_samples_leaf=10, random_state=42,
    ),
}

kf = KFold(n_splits=5, shuffle=True, random_state=42)

best_r2 = -1
best_name = None
best_model = None
cv_results = {}

for name, model in models.items():
    r2_scores = cross_val_score(model, X, y, cv=kf, scoring="r2")
    mae_scores = -cross_val_score(model, X, y, cv=kf, scoring="neg_mean_absolute_error")

    r2_mean = r2_scores.mean()
    r2_std = r2_scores.std()
    mae_mean = mae_scores.mean()

    cv_results[name] = {"r2_mean": r2_mean, "r2_std": r2_std, "mae_mean": mae_mean}

    print(f"\n{name}:")
    print(f"  R² = {r2_mean:.3f} (± {r2_std:.3f})")
    print(f"  MAE = {mae_mean:,.0f} €")

    if r2_mean > best_r2:
        best_r2 = r2_mean
        best_name = name
        best_model = model

# Refit le meilleur sur tout le dataset
best_model.fit(X, y)

print(f"\n{'─' * 60}")
print(f"Meilleur modèle : {best_name} (R² = {best_r2:.3f})")

# Feature importances
if hasattr(best_model, "feature_importances_"):
    importances = sorted(
        zip(FEATURES, best_model.feature_importances_), key=lambda x: -x[1]
    )
    print(f"\nImportance des features :")
    for feat, imp in importances:
        bar = "█" * int(imp * 40)
        print(f"  {feat:30s} {imp:.3f} {bar}")

# Validation finale train/test
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
best_model.fit(X_train, y_train)
y_pred_test = best_model.predict(X_test)
r2_final = r2_score(y_test, y_pred_test)
mae_final = mean_absolute_error(y_test, y_pred_test)
print(f"\nValidation hold-out (20%) :")
print(f"  R² = {r2_final:.3f} | MAE = {mae_final:,.0f} €")

# Refit final sur tout le dataset
best_model.fit(X, y)

# ============================================================
# 5. PRÉDICTION SUR LES ANNONCES
# ============================================================

print("\n" + "=" * 60)
print("5. PRÉDICTION SUR LES ANNONCES")
print("=" * 60)

ann = annonces.dropna(subset=["prix", "surface_m2", "nb_pieces"]).copy()
ann["prix"] = pd.to_numeric(ann["prix"], errors="coerce")
ann["surface_m2"] = pd.to_numeric(ann["surface_m2"], errors="coerce")
ann["nb_pieces"] = pd.to_numeric(ann["nb_pieces"], errors="coerce")
ann = ann.dropna(subset=["prix", "surface_m2", "nb_pieces"])
ann = ann[(ann["surface_m2"] >= 9) & (ann["surface_m2"] <= 300) & (ann["prix"] > 50000)]

# Mapper les features annonces → features DVF
median_lon = dvf["longitude"].median()
median_lat = dvf["latitude"].median()
median_lots = dvf["nombre_lots"].median()
median_pm2_zone = dvf["prix_m2_zone"].median()

ann["surface_best"] = ann["surface_m2"]
ann["nombre_pieces_principales"] = ann["nb_pieces"]
ann["annee"] = 2025
ann["mois"] = 6
ann["longitude"] = median_lon
ann["latitude"] = median_lat
ann["nombre_lots"] = median_lots
ann["prix_m2_zone"] = median_pm2_zone

ann["prix_predit"] = best_model.predict(ann[FEATURES])
ann["ecart_pct"] = ((ann["prix"] - ann["prix_predit"]) / ann["prix_predit"]) * 100

print(f"Annonces analysées : {ann.shape[0]}")
print(f"Prix demandé moyen : {ann['prix'].mean():,.0f} €")
print(f"Prix prédit moyen  : {ann['prix_predit'].mean():,.0f} €")
print(f"Écart médian       : {ann['ecart_pct'].median():+.1f}%")

# ============================================================
# 6. ANALYSE DES PRIMES — FEATURES ENRICHIES
# ============================================================

print("\n" + "=" * 60)
print("6. ANALYSE DES PRIMES (features enrichies)")
print("=" * 60)

# --- 6a. Parser les features booléennes ---
BOOL_FEATURES = [
    "ascenseur", "balcon", "terrasse", "cave", "garage", "parquet",
    "cheminee", "calme", "vue_degagee", "cuisine_equipee",
    "double_vitrage", "dernier_etage", "proche_gare", "travaux_necessaires",
]

for col in BOOL_FEATURES:
    if col in ann.columns:
        ann[f"{col}_bool"] = ann[col].astype(str).str.lower().map(
            {"true": 1, "false": 0, "1": 1, "0": 0}
        )

# --- 6b. DPE ordinal ---
DPE_MAP = {"A": 7, "B": 6, "A/B": 6.5, "C": 5, "D": 4, "D-E": 3.5, "E": 3, "F": 2, "G": 1}
if "dpe_lettre" in ann.columns:
    ann["dpe_score"] = ann["dpe_lettre"].map(DPE_MAP)

# --- 6c. Étage ---
if "etage" in ann.columns:
    ann["etage_num"] = pd.to_numeric(ann["etage"], errors="coerce")

# --- 6d. État général ordinal ---
ETAT_MAP = {
    "à rénover": 1, "a renover": 1,
    "à rafraîchir": 2, "a rafraichir": 2,
    "bon état": 3, "bon etat": 3, "bon": 3, "correct": 3, "bien entretenu": 3,
    "très bon état": 4, "tres bon etat": 4, "très bon": 4, "bonnes prestations": 4,
    "rénové": 5, "renove": 5, "refait à neuf": 5, "refait a neuf": 5,
    "parfait état": 5, "parfait etat": 5, "excellent état": 5, "excellent etat": 5,
    "neuf": 5, "état neuf": 5,
}
if "etat_general" in ann.columns:
    ann["etat_score"] = ann["etat_general"].str.lower().str.strip().map(ETAT_MAP)

# --- 6e. Score qualité ---
enriched_cols = BOOL_FEATURES + ["dpe_lettre", "etage", "etat_general", "exposition", "quartier"]
ann["score_qualite"] = 0
for col in enriched_cols:
    if col in ann.columns:
        ann["score_qualite"] += (
            ann[col].notna() & (ann[col] != "") & (ann[col].astype(str) != "nan")
        ).astype(int)

# --- 6f. Tableau des primes/décotes ---
print(f"\n{'Feature':<25s} {'Avec(méd)':>10s} {'Sans(méd)':>10s} {'Prime':>8s} {'N(avec)':>8s}")
print("─" * 65)

primes_data = []

for col in BOOL_FEATURES:
    bool_col = f"{col}_bool"
    if bool_col not in ann.columns:
        continue
    group_true = ann[ann[bool_col] == 1]["ecart_pct"]
    group_false = ann[ann[bool_col] == 0]["ecart_pct"]
    if len(group_true) < 20 or len(group_false) < 20:
        continue
    med_true = group_true.median()
    med_false = group_false.median()
    delta = med_true - med_false
    print(f"  {col:<23s} {med_true:>+9.1f}% {med_false:>+9.1f}% {delta:>+7.1f}% {len(group_true):>7d}")
    primes_data.append({
        "feature": col, "type": "boolean",
        "ecart_avec": round(med_true, 1), "ecart_sans": round(med_false, 1),
        "prime_pct": round(delta, 1), "n_avec": len(group_true),
    })

# DPE par lettre
if "dpe_score" in ann.columns:
    dpe_valid = ann.dropna(subset=["dpe_score"])
    if len(dpe_valid) >= 20:
        print(f"\n{'DPE':<25s} {'Écart méd.':>10s} {'N':>8s}")
        print("─" * 45)
        for lettre in ["A", "B", "C", "D", "E", "F", "G"]:
            grp = dpe_valid[dpe_valid["dpe_lettre"] == lettre]["ecart_pct"]
            if len(grp) >= 3:
                print(f"  DPE {lettre:<19s} {grp.median():>+9.1f}% {len(grp):>7d}")
                primes_data.append({
                    "feature": f"DPE {lettre}", "type": "dpe",
                    "ecart_avec": round(grp.median(), 1), "ecart_sans": None,
                    "prime_pct": None, "n_avec": len(grp),
                })

# État général
if "etat_score" in ann.columns:
    etat_valid = ann.dropna(subset=["etat_score"])
    if len(etat_valid) >= 20:
        print(f"\n{'État général':<25s} {'Écart méd.':>10s} {'N':>8s}")
        print("─" * 45)
        etat_labels = {1: "À rénover", 2: "À rafraîchir", 3: "Bon état", 4: "Très bon", 5: "Rénové/Neuf"}
        for score, label in etat_labels.items():
            grp = etat_valid[etat_valid["etat_score"] == score]["ecart_pct"]
            if len(grp) >= 3:
                print(f"  {label:<23s} {grp.median():>+9.1f}% {len(grp):>7d}")
                primes_data.append({
                    "feature": label, "type": "etat",
                    "ecart_avec": round(grp.median(), 1), "ecart_sans": None,
                    "prime_pct": None, "n_avec": len(grp),
                })

# ============================================================
# 7. EXPORT CSV POUR POWER BI
# ============================================================

print("\n" + "=" * 60)
print("7. EXPORT")
print("=" * 60)

# 7a. Annonces avec prédictions enrichies
export_cols = [
    "titre", "prix", "surface_m2", "nb_pieces",
    "prix_predit", "ecart_pct", "score_qualite",
    "type_bien", "url",
]
# Ajouter les features enrichies si elles existent
for col in ["ascenseur", "balcon", "terrasse", "cave", "garage",
            "dpe_lettre", "dpe_score", "etage", "etat_general", "etat_score", "quartier"]:
    if col in ann.columns:
        export_cols.append(col)

export = ann[export_cols].copy()
export["prix_predit"] = export["prix_predit"].round(0).astype(int)
export["ecart_pct"] = export["ecart_pct"].round(1)
export.to_csv("output/annonces_avec_prediction.csv", index=False, sep=";")
print(f"  annonces_avec_prediction.csv ({export.shape[0]} lignes, {len(export_cols)} colonnes)")

# 7b. Résumé par nb_pieces
pbi = ann.groupby("nb_pieces").agg(
    prix_demande_moyen=("prix", "mean"),
    prix_predit_moyen=("prix_predit", "mean"),
    ecart_median=("ecart_pct", "median"),
    nb_annonces=("prix", "count"),
).reset_index()
pbi = pbi[pbi["nb_annonces"] >= 10]
pbi["prix_demande_moyen"] = pbi["prix_demande_moyen"].round(0).astype(int)
pbi["prix_predit_moyen"] = pbi["prix_predit_moyen"].round(0).astype(int)
pbi["ecart_median"] = pbi["ecart_median"].round(1)
pbi.to_csv("output/prediction_powerbi.csv", index=False, sep=";")
print(f"  prediction_powerbi.csv ({pbi.shape[0]} lignes)")

# 7c. Table des primes
if primes_data:
    primes_df = pd.DataFrame(primes_data)
    primes_df.to_csv("output/prediction_primes.csv", index=False, sep=";")
    print(f"  prediction_primes.csv ({len(primes_data)} lignes)")

# 7d. Métadonnées du modèle
meta = pd.DataFrame([
    {"metric": "modele", "value": best_name},
    {"metric": "r2_cv_mean", "value": f"{best_r2:.3f}"},
    {"metric": "r2_cv_std", "value": f"{cv_results[best_name]['r2_std']:.3f}"},
    {"metric": "mae_cv_mean", "value": f"{cv_results[best_name]['mae_mean']:.0f}"},
    {"metric": "r2_holdout", "value": f"{r2_final:.3f}"},
    {"metric": "mae_holdout", "value": f"{mae_final:.0f}"},
    {"metric": "nb_features", "value": str(len(FEATURES))},
    {"metric": "nb_transactions_dvf", "value": str(len(X))},
    {"metric": "nb_annonces_analysees", "value": str(len(ann))},
    {"metric": "ecart_median_pct", "value": f"{ann['ecart_pct'].median():.1f}"},
    {"metric": "date_prediction", "value": date.today().isoformat()},
])
meta.to_csv("output/prediction_metadata.csv", index=False, sep=";")
print(f"  prediction_metadata.csv")

print(f"\n{'=' * 60}")
print(f"TERMINÉ — {best_name} (R² CV = {best_r2:.3f})")
print(f"Importe les CSV dans Power BI")
print(f"{'=' * 60}")
