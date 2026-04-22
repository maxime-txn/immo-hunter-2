"""
predict.py — Prédiction des prix immobiliers
Projet : immo-hunter
Auteur : Maxime Teixeira Novais — M2 Data Science & BI, EDC Paris

Entraîne sur DVF (maisons + appartements), prédit les annonces,
et permet de prédire un bien spécifique.
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

dvf_files = glob.glob("output/dvf_*.csv")
if not dvf_files:
    print("Erreur : aucun fichier DVF dans output/")
    sys.exit(1)
dvf_path = max(dvf_files, key=os.path.getmtime)

enrichi_files = glob.glob("output/annonces_*_enrichi.csv")
annonces_files = [f for f in glob.glob("output/annonces_*.csv")
                  if "_enrichi" not in f and "_prediction" not in f]
ann_path = (max(enrichi_files, key=os.path.getmtime) if enrichi_files
            else max(annonces_files, key=os.path.getmtime) if annonces_files else None)
if not ann_path:
    print("Erreur : aucun fichier annonces dans output/")
    sys.exit(1)

print(f"DVF      : {dvf_path}")
print(f"Annonces : {ann_path}")

dvf = pd.read_csv(dvf_path, sep=";", low_memory=False)
annonces = pd.read_csv(ann_path, sep=";", low_memory=False)

print(f"DVF : {dvf.shape[0]} lignes | Annonces : {annonces.shape[0]} lignes")

# ============================================================
# 2. NETTOYAGE DVF — MAISONS + APPARTEMENTS
# ============================================================

print("\n" + "=" * 60)
print("2. NETTOYAGE DVF")
print("=" * 60)

# Garder maisons ET appartements
dvf = dvf[dvf["type_local"].isin(["Maison", "Appartement"])].copy()
dvf["valeur_fonciere"] = pd.to_numeric(dvf["valeur_fonciere"], errors="coerce")
dvf["surface_reelle_bati"] = pd.to_numeric(dvf["surface_reelle_bati"], errors="coerce")
dvf["nombre_pieces_principales"] = pd.to_numeric(dvf["nombre_pieces_principales"], errors="coerce")
dvf["surface_terrain"] = pd.to_numeric(dvf["surface_terrain"], errors="coerce")
dvf["longitude"] = pd.to_numeric(dvf["longitude"], errors="coerce")
dvf["latitude"] = pd.to_numeric(dvf["latitude"], errors="coerce")

dvf = dvf.dropna(subset=["valeur_fonciere", "surface_reelle_bati", "nombre_pieces_principales"])
dvf = dvf[
    (dvf["valeur_fonciere"] > 50000) &
    (dvf["surface_reelle_bati"] >= 9) &
    (dvf["nombre_pieces_principales"] >= 1)
]

dvf = dvf.drop_duplicates(subset=["id_mutation"], keep="first")

# Temporalité
dvf["date_mutation"] = pd.to_datetime(dvf["date_mutation"], errors="coerce")
dvf["annee"] = dvf["date_mutation"].dt.year
dvf["mois"] = dvf["date_mutation"].dt.month

# Flag maison
dvf["est_maison"] = (dvf["type_local"] == "Maison").astype(int)

# Surface terrain (0 pour les apparts)
dvf["surface_terrain"] = dvf["surface_terrain"].fillna(0)

# Outliers prix/m²
dvf["prix_m2"] = dvf["valeur_fonciere"] / dvf["surface_reelle_bati"]
q_bas = dvf["prix_m2"].quantile(0.05)
q_haut = dvf["prix_m2"].quantile(0.95)
dvf = dvf[(dvf["prix_m2"] >= q_bas) & (dvf["prix_m2"] <= q_haut)]

nb_maisons = dvf["est_maison"].sum()
nb_apparts = len(dvf) - nb_maisons
print(f"Transactions retenues : {len(dvf)} ({nb_maisons} maisons, {nb_apparts} appartements)")
print(f"Prix moyen : {dvf['valeur_fonciere'].mean():,.0f} €")
print(f"Surface bâtie moyenne : {dvf['surface_reelle_bati'].mean():.0f} m²")
print(f"Prix/m² moyen : {dvf['prix_m2'].mean():,.0f} €")

# ============================================================
# 3. FEATURE ENGINEERING
# ============================================================

print("\n" + "=" * 60)
print("3. FEATURE ENGINEERING")
print("=" * 60)

# Surface Carrez ou réelle
dvf["lot1_surface_carrez"] = pd.to_numeric(dvf.get("lot1_surface_carrez", pd.Series(dtype=float)), errors="coerce")
dvf["surface_best"] = dvf["lot1_surface_carrez"].fillna(dvf["surface_reelle_bati"])

# Nombre de lots
dvf["nombre_lots"] = pd.to_numeric(dvf.get("nombre_lots", pd.Series(dtype=float)), errors="coerce").fillna(1)

# Prix/m² médian par micro-quartier
has_geo = dvf["longitude"].notna() & dvf["latitude"].notna()
if has_geo.sum() > 10:
    dvf.loc[has_geo, "geo_cell"] = (dvf.loc[has_geo, "latitude"].round(3).astype(str) + "_" +
                                     dvf.loc[has_geo, "longitude"].round(3).astype(str))
    zone_medians = dvf.groupby("geo_cell")["prix_m2"].median()
    dvf["prix_m2_zone"] = dvf["geo_cell"].map(zone_medians)
else:
    dvf["prix_m2_zone"] = dvf["prix_m2"].median()

# Remplir geo manquants par médiane
dvf["longitude"] = dvf["longitude"].fillna(dvf["longitude"].median())
dvf["latitude"] = dvf["latitude"].fillna(dvf["latitude"].median())
dvf["prix_m2_zone"] = dvf["prix_m2_zone"].fillna(dvf["prix_m2"].median())

FEATURES = [
    "surface_best",
    "nombre_pieces_principales",
    "surface_terrain",
    "est_maison",
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

mask = X.notna().all(axis=1)
X = X[mask]
y = y[mask]
print(f"Échantillons valides : {len(X)}")

n_splits = min(5, len(X))
if n_splits < 2:
    print("Pas assez de données pour la cross-validation.")
    sys.exit(1)

models = {
    "Régression Linéaire": Pipeline([
        ("scaler", StandardScaler()),
        ("model", LinearRegression()),
    ]),
    "Random Forest": RandomForestRegressor(
        n_estimators=200, max_depth=12, min_samples_leaf=3,
        random_state=42, n_jobs=-1,
    ),
    "Gradient Boosting": GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.08,
        min_samples_leaf=5, random_state=42,
    ),
}

kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

best_r2 = -999
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

# Refit sur tout le dataset
best_model.fit(X, y)

print(f"\n{'─' * 60}")
print(f"Meilleur modèle : {best_name} (R² = {best_r2:.3f})")

if hasattr(best_model, "feature_importances_"):
    importances = sorted(
        zip(FEATURES, best_model.feature_importances_), key=lambda x: -x[1]
    )
    print(f"\nImportance des features :")
    for feat, imp in importances:
        bar = "█" * int(imp * 40)
        print(f"  {feat:30s} {imp:.3f} {bar}")

# Validation hold-out
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
best_model.fit(X_train, y_train)
y_pred_test = best_model.predict(X_test)
r2_final = r2_score(y_test, y_pred_test)
mae_final = mean_absolute_error(y_test, y_pred_test)
print(f"\nValidation hold-out (20%) :")
print(f"  R² = {r2_final:.3f} | MAE = {mae_final:,.0f} €")

# Refit final
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
ann = ann[(ann["surface_m2"] >= 9) & (ann["prix"] > 50000)]

# Mapper features
median_lon = dvf["longitude"].median()
median_lat = dvf["latitude"].median()
median_lots = dvf["nombre_lots"].median()
median_pm2_zone = dvf["prix_m2_zone"].median()

ann["surface_best"] = ann["surface_m2"]
ann["nombre_pieces_principales"] = ann["nb_pieces"]
ann["surface_terrain"] = 0  # par défaut appart
ann.loc[ann["type_bien"].str.lower().isin(["maison", "villa"]), "surface_terrain"] = dvf.loc[dvf["est_maison"] == 1, "surface_terrain"].median()
ann["est_maison"] = ann["type_bien"].str.lower().isin(["maison", "villa"]).astype(int)
ann["annee"] = 2025
ann["mois"] = 6
ann["longitude"] = median_lon
ann["latitude"] = median_lat
ann["nombre_lots"] = median_lots
ann["prix_m2_zone"] = median_pm2_zone

# Utiliser surface_jardin_m2 comme surface_terrain si disponible
if "surface_jardin_m2" in ann.columns:
    sj = pd.to_numeric(ann["surface_jardin_m2"], errors="coerce")
    ann.loc[sj.notna() & (sj > 0), "surface_terrain"] = sj[sj.notna() & (sj > 0)]

ann["prix_predit"] = best_model.predict(ann[FEATURES])
ann["ecart_pct"] = ((ann["prix"] - ann["prix_predit"]) / ann["prix_predit"]) * 100

print(f"Annonces analysées : {ann.shape[0]}")
print(f"Prix demandé moyen : {ann['prix'].mean():,.0f} €")
print(f"Prix prédit moyen  : {ann['prix_predit'].mean():,.0f} €")
print(f"��cart médian       : {ann['ecart_pct'].median():+.1f}%")

# Top bonnes affaires (maisons)
maisons_ann = ann[ann["est_maison"] == 1].sort_values("ecart_pct")
if len(maisons_ann) > 0:
    print(f"\n  Top 5 bonnes affaires (maisons) :")
    for _, r in maisons_ann.head(5).iterrows():
        print(f"    {r['titre'][:50]:50s} demandé {r['prix']:>10,.0f} € | prédit {r['prix_predit']:>10,.0f} € | écart {r['ecart_pct']:+.1f}%")

# ============================================================
# 6. ESTIMATION BIEN SPÉCIFIQUE — MAISON JUNOT (CHÂTAIGNERAIE)
#    Méthode : 3 approches croisées + ajustements qualitatifs
# ============================================================

print("\n" + "=" * 70)
print("6. ESTIMATION — MAISON D'ARCHITECTE, CHÂTAIGNERAIE")
print("=" * 70)

prix_demande = 1_795_000

print("""
  FICHE DESCRIPTIVE
  ──────────────────────────────────────────────────────────────────
  Type              : Maison d'architecte (1956, béton)
  Localisation      : La Celle-Saint-Cloud — Quartier Châtaigneraie
  Surface habitable : 240 m²
  Terrain           : 760 m²
  Pièces / Chambres : 9 pièces / 5 chambres / 1 SdB
  Exposition        : Sud / Sud-Ouest, traversant
  DPE               : A (52 kWh/m²/an) — Énergie 980-1340 €/an
  État              : Rénové haut de gamme, matériaux premium
  Chauffage         : Non précisé (DPE A → PAC probable)
  Stationnement     : Abri voiture, portail électrique
  Équipements       : Sauna, salle de sport (32.93 m²), alarme,
                      interphone, internet fibre
  Annexes           : 2 caves (9.36 + 11.33 m²), atelier (17.72 m²)
  Pièce principale  : Double réception 40 m²
  Prix affiché      : 1,795,000 € (honoraires vendeur)
  Prix/m²           : 7,479 €/m²
  ──────────────────────────────────────────────────────────────────
""")

# ─────────────────────────────────────────────────────────────────
# MÉTHODE A — Modèle ML (entraîné sur DVF 2024-2025)
# ─────────────────────────────────────────────────────────────────

print("  MÉTHODE A — MODÈLE ML (DVF 2024-2025)")
print("  " + "─" * 64)

junot = pd.DataFrame([{
    "surface_best": 240,
    "nombre_pieces_principales": 9,
    "surface_terrain": 760,
    "est_maison": 1,
    "annee": 2025,
    "mois": 4,
    "longitude": median_lon,
    "latitude": median_lat,
    "nombre_lots": 1,
    "prix_m2_zone": median_pm2_zone,
}])

prix_ml = best_model.predict(junot[FEATURES])[0]
print(f"  Modèle : {best_name} (R² CV = {best_r2:.3f}, MAE = {cv_results[best_name]['mae_mean']:,.0f} €)")
print(f"  Prix prédit brut    : {prix_ml:>12,.0f} €")
print(f"  Prix/m² prédit      : {prix_ml/240:>12,.0f} €/m²")

# ─────────────────────────────────────────────────────────────────
# MÉTHODE B — Comparables DVF (ventes réelles 2024-2025)
# ─────────────────────────────────────────────────────────────────

print(f"\n  MÉTHODE B — COMPARABLES DVF (ventes réelles 2024-2025)")
print("  " + "─" * 64)

dvf_maisons = dvf[dvf["est_maison"] == 1].copy()
dvf_maisons["prix_m2"] = dvf_maisons["valeur_fonciere"] / dvf_maisons["surface_reelle_bati"]

# Score de similarité pondéré pour chaque transaction DVF
def similarity_score(row, target_surface=240, target_pieces=9, target_terrain=760):
    """Score de similarité (plus bas = plus proche)."""
    s_surf = abs(row["surface_reelle_bati"] - target_surface) / target_surface
    s_pieces = abs(row["nombre_pieces_principales"] - target_pieces) / target_pieces
    s_terrain = abs(row["surface_terrain"] - target_terrain) / max(target_terrain, 1) if row["surface_terrain"] > 0 else 0.5
    return s_surf * 0.40 + s_pieces * 0.30 + s_terrain * 0.30

dvf_maisons["sim_score"] = dvf_maisons.apply(similarity_score, axis=1)
dvf_maisons = dvf_maisons.sort_values("sim_score")

# Top 8 comparables DVF
top_dvf = dvf_maisons.head(8).copy()
print(f"  {len(dvf_maisons)} maisons DVF disponibles — Top 8 comparables :\n")
print(f"  {'Surface':>8s} {'Terrain':>8s} {'Pièces':>7s} {'Prix':>12s} {'€/m²':>8s} {'Sim.':>5s}")
print("  " + "─" * 54)
for _, r in top_dvf.iterrows():
    print(f"  {r['surface_reelle_bati']:>7.0f}m² {r['surface_terrain']:>7.0f}m² {r['nombre_pieces_principales']:>5.0f}p "
          f"{r['valeur_fonciere']:>11,.0f}€ {r['prix_m2']:>7,.0f}€ {r['sim_score']:>5.2f}")

# Prix/m² pondéré par similarité (inverse du score)
top_dvf["poids"] = 1 / (top_dvf["sim_score"] + 0.01)
prix_m2_dvf_pondere = np.average(top_dvf["prix_m2"], weights=top_dvf["poids"])
prix_dvf_comps = prix_m2_dvf_pondere * 240

# Aussi calculer la médiane brute des maisons >= 200m²
dvf_200plus = dvf_maisons[dvf_maisons["surface_reelle_bati"] >= 200]
prix_m2_median_200 = dvf_200plus["prix_m2"].median() if len(dvf_200plus) > 0 else dvf_maisons["prix_m2"].median()
prix_dvf_median = prix_m2_median_200 * 240

print(f"\n  Prix/m² pondéré (similarité)  : {prix_m2_dvf_pondere:>7,.0f} €/m²")
print(f"  → Prix comparable pondéré     : {prix_dvf_comps:>12,.0f} €")
print(f"  Prix/m² médian (maisons≥200m²): {prix_m2_median_200:>7,.0f} €/m² (N={len(dvf_200plus)})")
print(f"  → Prix médian brut            : {prix_dvf_median:>12,.0f} €")

# ─────────────────────────────────────────────────────────────────
# MÉTHODE C — Comparables annonces (en vente actuellement)
# ─────────────────────────────────────────────────────────────────

print(f"\n  MÉTHODE C — COMPARABLES ANNONCES (en vente)")
print("  " + "─" * 64)

ann_maisons = ann[ann["est_maison"] == 1].copy()
ann_maisons["prix_m2_ann"] = ann_maisons["prix"] / ann_maisons["surface_m2"]

# Exclure l'annonce aberrante (14.7M pour 120m²)
ann_maisons = ann_maisons[ann_maisons["prix_m2_ann"] < 20000]

# Score similarité annonces
def sim_annonce(row, target_surface=240, target_pieces=9):
    s_surf = abs(row["surface_m2"] - target_surface) / target_surface
    s_pieces = abs(row["nb_pieces"] - target_pieces) / target_pieces
    return s_surf * 0.50 + s_pieces * 0.50

ann_maisons["sim_score"] = ann_maisons.apply(sim_annonce, axis=1)
ann_maisons = ann_maisons.sort_values("sim_score")

top_ann = ann_maisons.head(8).copy()
print(f"  {len(ann_maisons)} maisons en vente — Top 8 comparables :\n")
print(f"  {'Surface':>8s} {'Pièces':>7s} {'Prix':>12s} {'€/m²':>8s} {'DPE':>4s} {'État':>15s} {'Sim.':>5s}")
print("  " + "─" * 65)
for _, r in top_ann.iterrows():
    dpe = str(r.get("dpe_lettre", "")) if pd.notna(r.get("dpe_lettre")) else "-"
    etat = str(r.get("etat_general", "")) if pd.notna(r.get("etat_general")) else "-"
    print(f"  {r['surface_m2']:>7.0f}m² {r['nb_pieces']:>5.0f}p "
          f"{r['prix']:>11,.0f}€ {r['prix_m2_ann']:>7,.0f}€ {dpe:>4s} {etat:>15s} {r['sim_score']:>5.2f}")

# Prix/m² pondéré par similarité
top_ann["poids"] = 1 / (top_ann["sim_score"] + 0.01)
prix_m2_ann_pondere = np.average(top_ann["prix_m2_ann"], weights=top_ann["poids"])
prix_ann_comps = prix_m2_ann_pondere * 240

# Médiane des maisons >= 180m²
ann_180plus = ann_maisons[ann_maisons["surface_m2"] >= 180]
prix_m2_median_ann = ann_180plus["prix_m2_ann"].median() if len(ann_180plus) > 0 else ann_maisons["prix_m2_ann"].median()
prix_ann_median = prix_m2_median_ann * 240

print(f"\n  Prix/m² pondéré (similarité)  : {prix_m2_ann_pondere:>7,.0f} €/m²")
print(f"  → Prix comparable pondéré     : {prix_ann_comps:>12,.0f} €")
print(f"  Prix/m² médian (maisons≥180m²): {prix_m2_median_ann:>7,.0f} €/m² (N={len(ann_180plus)})")
print(f"  → Prix médian brut            : {prix_ann_median:>12,.0f} €")

# ─────────────────────────────────────────────────────────────────
# SYNTHÈSE — Prix de base croisé (3 méthodes)
# ─────────────────────────────────────────────────────────────────

print(f"\n  SYNTHÈSE DES 3 MÉTHODES")
print("  " + "─" * 64)

prix_base_ml = prix_ml
prix_base_dvf = prix_dvf_comps
prix_base_ann = prix_ann_comps

print(f"  A. Modèle ML (DVF)             : {prix_base_ml:>12,.0f} €  ({prix_base_ml/240:>6,.0f} €/m²)")
print(f"  B. Comparables DVF pondérés     : {prix_base_dvf:>12,.0f} €  ({prix_base_dvf/240:>6,.0f} €/m²)")
print(f"  C. Comparables annonces pondérés: {prix_base_ann:>12,.0f} €  ({prix_base_ann/240:>6,.0f} €/m²)")

# Moyenne pondérée : DVF comps (40%), ML (30%), Annonces (30%)
prix_base = prix_base_dvf * 0.40 + prix_base_ml * 0.30 + prix_base_ann * 0.30
print(f"\n  Prix de base croisé (40/30/30) : {prix_base:>12,.0f} €  ({prix_base/240:>6,.0f} €/m²)")

# ─────────────────────────────────────────────────────────────────
# AJUSTEMENTS QUALITATIFS — Feature par feature
# ─────────────────────────────────────────────────────────────────

print(f"\n  AJUSTEMENTS QUALITATIFS (caractéristiques du bien)")
print("  " + "─" * 64)

adjustments = []

# 1. DPE A — exceptionnel (< 2% du parc), économie énergie massive
adj_dpe = ("DPE A (52 kWh — top 2% du parc)", +0.08, "Économie énergie ~3000€/an vs DPE D, très recherché")
adjustments.append(adj_dpe)

# 2. Rénovation haut de gamme complète
adj_renov = ("Rénové haut de gamme complet", +0.12, "Matériaux premium, aucun travaux à prévoir")
adjustments.append(adj_renov)

# 3. Exposition Sud/Sud-Ouest traversant
adj_expo = ("Exposition Sud/SO, traversant", +0.04, "Double orientation, luminosité optimale")
adjustments.append(adj_expo)

# 4. Double réception 40m²
adj_recep = ("Double réception 40 m²", +0.03, "Pièce de vie exceptionnelle")
adjustments.append(adj_recep)

# 5. Terrain 760m² (vs médiane DVF maisons)
terrain_median_dvf = dvf_maisons["surface_terrain"].median()
if terrain_median_dvf > 0:
    ratio_terrain = (760 - terrain_median_dvf) / terrain_median_dvf
    adj_terrain_pct = min(max(ratio_terrain * 0.10, -0.05), 0.08)
else:
    adj_terrain_pct = 0.03
adj_terrain = (f"Terrain 760 m² (méd. DVF: {terrain_median_dvf:.0f} m²)", adj_terrain_pct, "Jardin arboré, belle parcelle")
adjustments.append(adj_terrain)

# 6. Sauna + salle de sport (32.93 m²)
adj_sport = ("Sauna + salle de sport (33 m²)", +0.02, "Équipement rare, valeur ajoutée loisirs")
adjustments.append(adj_sport)

# 7. 2 caves + atelier (38 m² d'annexes)
adj_annexes = ("Caves (21 m²) + atelier (18 m²)", +0.02, "39 m² d'annexes utiles")
adjustments.append(adj_annexes)

# 8. Alarme + interphone + portail élec.
adj_secu = ("Sécurité (alarme, interphone, portail)", +0.01, "Confort sécuritaire")
adjustments.append(adj_secu)

# 9. Quartier Châtaigneraie (prime quartier)
adj_quartier = ("Quartier Châtaigneraie (recherché)", +0.05, "Un des meilleurs quartiers de LCSC")
adjustments.append(adj_quartier)

# 10. Points négatifs
adj_sdb = ("1 seule SdB pour 5 chambres", -0.03, "Sous-dimensionné, rénovation probable")
adjustments.append(adj_sdb)

adj_parking = ("Abri voiture (pas de garage fermé)", -0.02, "Pas de garage, simple abri")
adjustments.append(adj_parking)

adj_beton = ("Construction béton 1956", -0.01, "Architecture datée, charges isolation")
adjustments.append(adj_beton)

# Afficher le tableau des ajustements
total_adj = 0
print(f"\n  {'Caractéristique':<42s} {'Impact':>8s}  Justification")
print("  " + "─" * 90)
for label, pct, justif in adjustments:
    signe = "+" if pct >= 0 else ""
    symbole = "+" if pct >= 0 else "−"
    color = symbole
    print(f"  {label:<42s} {signe}{pct*100:>5.1f}%   {justif}")
    total_adj += pct

print("  " + "─" * 90)
signe_tot = "+" if total_adj >= 0 else ""
print(f"  {'TOTAL AJUSTEMENTS':<42s} {signe_tot}{total_adj*100:>5.1f}%")

# ─────────────────────────────────────────────────────────────────
# ESTIMATION FINALE
# ─────────────────────────────────────────────────────────────────

print(f"\n  ESTIMATION FINALE")
print("  " + "=" * 64)

prix_ajuste = prix_base * (1 + total_adj)
marge_basse = prix_ajuste * 0.92   # -8% marge d'erreur
marge_haute = prix_ajuste * 1.08   # +8% marge d'erreur

ecart_final = ((prix_demande - prix_ajuste) / prix_ajuste) * 100

print(f"""
  Prix de base (3 méthodes)      : {prix_base:>12,.0f} €
  Ajustements qualitatifs        : {signe_tot}{total_adj*100:.1f}% ({prix_base * total_adj:>+12,.0f} €)
  ─────────────────────────────────────────────────
  PRIX ESTIMÉ                    : {prix_ajuste:>12,.0f} €  ({prix_ajuste/240:>6,.0f} €/m²)
  Fourchette (±8%)               : {marge_basse:>12,.0f} € — {marge_haute:>12,.0f} €
  ─────────────────────────────────────────────────
  Prix demandé Junot             : {prix_demande:>12,} €  ({prix_demande/240:>6,.0f} €/m²)
  Écart demandé vs estimé        :       {ecart_final:>+6.1f} %
""")

if ecart_final > 15:
    verdict = "SURÉVALUÉ"
    conseil = "Marge de négociation significative — viser"
    cible = prix_ajuste * 1.05
    print(f"  VERDICT : {verdict}")
    print(f"  {conseil} ~{cible:,.0f} € (-{(1-cible/prix_demande)*100:.0f}%)")
elif ecart_final > 5:
    verdict = "LÉGÈREMENT AU-DESSUS DU MARCHÉ"
    cible = prix_ajuste
    print(f"  VERDICT : {verdict}")
    print(f"  Négociation raisonnable → viser ~{cible:,.0f} € (-{(1-cible/prix_demande)*100:.0f}%)")
elif ecart_final > -5:
    verdict = "PRIX COHÉRENT AVEC LE MARCHÉ"
    print(f"  VERDICT : {verdict}")
    print(f"  Offre possible autour de {prix_ajuste*0.97:,.0f} € à {prix_ajuste:,.0f} €")
else:
    verdict = "BONNE AFFAIRE"
    print(f"  VERDICT : {verdict}")
    print(f"  Prix attractif — agir rapidement")

print(f"""
  CONTEXTE MARCHÉ La Celle-Saint-Cloud (DVF 2024-2025)
  ────────────────────────────────────────────────────
  Maisons vendues              : {len(dvf_maisons)}
  Prix/m² médian (toutes)      : {dvf_maisons['prix_m2'].median():>7,.0f} €/m²
  Prix/m² médian (≥200m²)      : {prix_m2_median_200:>7,.0f} €/m²
  Maisons en vente (annonces)  : {len(ann_maisons)}
  Prix/m² médian annonces      : {ann_maisons['prix_m2_ann'].median():>7,.0f} €/m²
""")

# ============================================================
# 7. ANALYSE DES PRIMES — FEATURES ENRICHIES
# ============================================================

print("\n" + "=" * 60)
print("7. ANALYSE DES PRIMES (features enrichies)")
print("=" * 60)

BOOL_FEATURES = [
    "ascenseur", "balcon", "terrasse", "cave", "garage", "parquet",
    "cheminee", "calme", "vue_degagee", "cuisine_equipee",
    "double_vitrage", "triple_vitrage", "dernier_etage", "etage_eleve",
    "proche_transports", "travaux_necessaires",
    "lumineux", "gardien", "residence_securisee", "climatisation",
    "loggia", "roof_top", "piscine", "jardin",
    "vis_a_vis", "travaux_copro_prevus", "mandat_exclusif",
]

for col in BOOL_FEATURES:
    if col in ann.columns:
        ann[f"{col}_bool"] = ann[col].astype(str).str.lower().map(
            {"true": 1, "false": 0, "1": 1, "0": 0}
        )

DPE_MAP = {"A": 7, "B": 6, "A/B": 6.5, "C": 5, "D": 4, "D-E": 3.5, "E": 3, "F": 2, "G": 1}
if "dpe_lettre" in ann.columns:
    ann["dpe_score"] = ann["dpe_lettre"].map(DPE_MAP)

if "etage" in ann.columns:
    ann["etage_num"] = pd.to_numeric(ann["etage"], errors="coerce")

ETAT_MAP = {
    "a_renover": 1, "à rénover": 1, "a renover": 1,
    "a_rafraichir": 2, "à rafraîchir": 2, "a rafraichir": 2,
    "bon": 3, "correct": 3, "bien entretenu": 3,
    "tres_bon": 4, "très bon": 4,
    "renove": 5, "rénové": 5, "refait_a_neuf": 5, "neuf": 5,
}
if "etat_general" in ann.columns:
    ann["etat_score"] = ann["etat_general"].str.lower().str.strip().map(ETAT_MAP)

enriched_cols = BOOL_FEATURES + [
    "dpe_lettre", "etage", "etat_general", "exposition", "quartier",
    "nb_sdb", "type_chauffage", "vue_type", "hauteur_sous_plafond_cm",
    "nom_station_metro", "charges_copro_mois",
]
ann["score_qualite"] = 0
for col in enriched_cols:
    if col in ann.columns:
        ann["score_qualite"] += (
            ann[col].notna() & (ann[col] != "") & (ann[col].astype(str) != "nan")
        ).astype(int)

print(f"\n{'Feature':<25s} {'Avec(méd)':>10s} {'Sans(méd)':>10s} {'Prime':>8s} {'N(avec)':>8s}")
print("─" * 65)

primes_data = []
min_n = max(5, len(ann) // 10)

for col in BOOL_FEATURES:
    bool_col = f"{col}_bool"
    if bool_col not in ann.columns:
        continue
    group_true = ann[ann[bool_col] == 1]["ecart_pct"]
    group_false = ann[ann[bool_col] == 0]["ecart_pct"]
    if len(group_true) < min_n or len(group_false) < min_n:
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

if "dpe_score" in ann.columns:
    dpe_valid = ann.dropna(subset=["dpe_score"])
    if len(dpe_valid) >= 5:
        print(f"\n{'DPE':<25s} {'Écart méd.':>10s} {'N':>8s}")
        print("─" * 45)
        for lettre in ["A", "B", "C", "D", "E", "F", "G"]:
            grp = dpe_valid[dpe_valid["dpe_lettre"] == lettre]["ecart_pct"]
            if len(grp) >= 2:
                print(f"  DPE {lettre:<19s} {grp.median():>+9.1f}% {len(grp):>7d}")
                primes_data.append({
                    "feature": f"DPE {lettre}", "type": "dpe",
                    "ecart_avec": round(grp.median(), 1), "ecart_sans": None,
                    "prime_pct": None, "n_avec": len(grp),
                })

if "etat_score" in ann.columns:
    etat_valid = ann.dropna(subset=["etat_score"])
    if len(etat_valid) >= 5:
        print(f"\n{'État général':<25s} {'Écart méd.':>10s} {'N':>8s}")
        print("─" * 45)
        etat_labels = {1: "À rénover", 2: "À rafraîchir", 3: "Bon état", 4: "Très bon", 5: "Rénové/Neuf"}
        for score, label in etat_labels.items():
            grp = etat_valid[etat_valid["etat_score"] == score]["ecart_pct"]
            if len(grp) >= 2:
                print(f"  {label:<23s} {grp.median():>+9.1f}% {len(grp):>7d}")
                primes_data.append({
                    "feature": label, "type": "etat",
                    "ecart_avec": round(grp.median(), 1), "ecart_sans": None,
                    "prime_pct": None, "n_avec": len(grp),
                })

# ============================================================
# 8. EXPORT
# ============================================================

print("\n" + "=" * 60)
print("8. EXPORT")
print("=" * 60)

export_cols = [
    "titre", "prix", "surface_m2", "nb_pieces", "type_bien",
    "prix_predit", "ecart_pct", "score_qualite", "url",
]
for col in ["ascenseur", "balcon", "terrasse", "cave", "garage", "jardin",
            "dpe_lettre", "dpe_score", "etage", "etat_general", "etat_score", "quartier"]:
    if col in ann.columns:
        export_cols.append(col)

export = ann[export_cols].copy()
export["prix_predit"] = export["prix_predit"].round(0).astype(int)
export["ecart_pct"] = export["ecart_pct"].round(1)
export.to_csv("output/annonces_avec_prediction.csv", index=False, sep=";")
print(f"  annonces_avec_prediction.csv ({export.shape[0]} lignes)")

pbi = ann.groupby("nb_pieces").agg(
    prix_demande_moyen=("prix", "mean"),
    prix_predit_moyen=("prix_predit", "mean"),
    ecart_median=("ecart_pct", "median"),
    nb_annonces=("prix", "count"),
).reset_index()
pbi = pbi[pbi["nb_annonces"] >= 3]
pbi["prix_demande_moyen"] = pbi["prix_demande_moyen"].round(0).astype(int)
pbi["prix_predit_moyen"] = pbi["prix_predit_moyen"].round(0).astype(int)
pbi["ecart_median"] = pbi["ecart_median"].round(1)
pbi.to_csv("output/prediction_powerbi.csv", index=False, sep=";")
print(f"  prediction_powerbi.csv ({pbi.shape[0]} lignes)")

if primes_data:
    primes_df = pd.DataFrame(primes_data)
    primes_df.to_csv("output/prediction_primes.csv", index=False, sep=";")
    print(f"  prediction_primes.csv ({len(primes_data)} lignes)")

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
print(f"{'=' * 60}")
