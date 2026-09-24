"""
Étape 3 : le modèle qui estime le prix d'un logement.

Principe :
- on prédit le PRIX AU M² (plus stable que le prix total), puis on multiplie par la surface ;
- on apprend sur le log du prix au m² : une erreur de 10 % pèse pareil sur un studio
  que sur un grand appartement ;
- on compare 3 algorithmes classiques de scikit-learn (régression linéaire, forêt aléatoire,
  gradient boosting) à une méthode simple de référence (prix médian au m² du secteur × surface) ;
- validation temporelle : chaque modèle est testé sur les derniers mois, qu'il n'a jamais vus ;
- le modèle retenu (gradient boosting) est complété par deux modèles "quantiles" qui donnent
  la fourchette basse / haute (10 % et 90 %).

Variables utilisées = uniquement ce qu'on connaît pour n'importe quelle annonce :
position (latitude, longitude, secteur), surface, nombre de pièces, cave/parking, date.
"""
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

VARIABLES = ["latitude", "longitude", "code_secteur", "surface", "nb_pieces",
             "surface_par_piece", "a_dependance", "mois"]

PARAMS = dict(max_iter=600, learning_rate=0.05, max_leaf_nodes=63,
              min_samples_leaf=30, l2_regularization=1.0, random_state=0)


def preparer(df):
    """Construit les variables du modèle à partir d'une table de biens."""
    X = pd.DataFrame(index=df.index)
    X["latitude"] = df["latitude"]
    X["longitude"] = df["longitude"]
    X["code_secteur"] = df["code_commune"].astype(int)
    X["surface"] = df["surface"]
    X["nb_pieces"] = df["nb_pieces"]
    X["surface_par_piece"] = df["surface"] / df["nb_pieces"]
    X["a_dependance"] = (df["nb_dependances"] > 0).astype(int)
    # Temps en mois depuis janvier 2020 : capte la tendance du marché
    X["mois"] = (df["date"].dt.year - 2020) * 12 + df["date"].dt.month
    return X[VARIABLES]


def _nouveau_modele(quantile=None):
    categorie = [VARIABLES.index("code_secteur")]
    if quantile is None:
        return HistGradientBoostingRegressor(categorical_features=categorie, **PARAMS)
    return HistGradientBoostingRegressor(loss="quantile", quantile=quantile,
                                         categorical_features=categorie, **PARAMS)


def candidats():
    """Les 3 algorithmes comparés. Même entrée, même cible (log du prix au m²)."""
    numeriques = [v for v in VARIABLES if v != "code_secteur"]
    lineaire = make_pipeline(
        ColumnTransformer([
            ("secteur", OneHotEncoder(handle_unknown="ignore"), ["code_secteur"]),
            ("chiffres", StandardScaler(), numeriques),
        ]),
        LinearRegression(),
    )
    foret = RandomForestRegressor(n_estimators=150, min_samples_leaf=5, max_features=0.5,
                                  n_jobs=-1, random_state=0)
    return {
        "Régression linéaire": lineaire,
        "Forêt aléatoire (Random Forest)": foret,
        "Gradient boosting (retenu)": _nouveau_modele(),
    }


def _entrainer_trio(X, y_log, q_bas, q_haut):
    return {
        "central": _nouveau_modele().fit(X, y_log),
        "bas": _nouveau_modele(q_bas).fit(X, y_log),
        "haut": _nouveau_modele(q_haut).fit(X, y_log),
    }


def _predire_trio(modeles, X, surface):
    out = {k: np.exp(m.predict(X)) * surface for k, m in modeles.items()}
    # sécurité : la fourchette doit encadrer l'estimation centrale
    out["bas"] = np.minimum(out["bas"], out["central"])
    out["haut"] = np.maximum(out["haut"], out["central"])
    return out


def mesures(y, p):
    """Indicateurs lisibles par un métier, pas seulement par un data scientist."""
    ecart = np.abs(p - y) / y
    return {
        "erreur_mediane_pct": round(float(np.median(ecart) * 100), 1),
        "part_a_moins_de_10pct": round(float((ecart < 0.10).mean() * 100), 1),
        "erreur_moyenne_eur": round(float(np.mean(np.abs(p - y)))),
        "r2": round(float(1 - ((p - y) ** 2).sum() / ((y - y.mean()) ** 2).sum()), 3),
    }


def evaluer_et_entrainer(ventes, nb_mois_test, q_bas, q_haut, dossier):
    """Évalue sur les derniers mois, puis ré-entraîne sur tout l'historique et sauvegarde."""
    date_coupure = ventes["date"].max() - pd.DateOffset(months=nb_mois_test)
    appr = ventes[ventes["date"] <= date_coupure]
    test = ventes[ventes["date"] > date_coupure]

    # 1) Méthode simple de référence : médiane du secteur × surface
    mediane_secteur = appr.groupby("secteur")["prix_m2"].median()
    p_ref = test["secteur"].map(mediane_secteur).values * test["surface"].values

    y = test["prix"].values
    X_appr, X_test, y_appr = preparer(appr), preparer(test), np.log(appr["prix_m2"])

    # 2) Comparaison des 3 algorithmes, sur exactement les mêmes données
    comparaison = {"Méthode simple (médiane du secteur × surface)": mesures(y, p_ref)}
    for nom, algo in candidats().items():
        algo.fit(X_appr, y_appr)
        comparaison[nom] = mesures(y, np.exp(algo.predict(X_test)) * test["surface"].values)
        print(f"  {nom:48s} erreur médiane {comparaison[nom]['erreur_mediane_pct']:>5} %")

    # 3) Modèle retenu + fourchette
    modeles = _entrainer_trio(X_appr, y_appr, q_bas, q_haut)
    pred = _predire_trio(modeles, X_test, test["surface"].values)
    dans_fourchette = (y >= pred["bas"]) & (y <= pred["haut"])
    rapport = {
        "periode_apprentissage": [str(appr["date"].min().date()), str(date_coupure.date())],
        "periode_test": [str(test["date"].min().date()), str(test["date"].max().date())],
        "nb_ventes_apprentissage": int(len(appr)),
        "nb_ventes_test": int(len(test)),
        "comparaison": comparaison,
        "reference_mediane_secteur": comparaison["Méthode simple (médiane du secteur × surface)"],
        "modele": mesures(y, pred["central"]),
        "fourchette_couverture_pct": round(float(dans_fourchette.mean() * 100), 1),
        "fourchette_cible_pct": round((q_haut - q_bas) * 100),
    }
    erreurs_test = pd.DataFrame({"secteur": test["secteur"].values, "reel": y,
                                 "estime": pred["central"], "reference": p_ref})

    # 4) Modèle final, entraîné sur tout l'historique, pour l'application
    modeles_finaux = _entrainer_trio(preparer(ventes), np.log(ventes["prix_m2"]), q_bas, q_haut)
    os.makedirs(dossier, exist_ok=True)
    joblib.dump({"modeles": modeles_finaux, "date_max": ventes["date"].max()},
                os.path.join(dossier, "modele.joblib"), compress=3)
    with open(os.path.join(dossier, "evaluation.json"), "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    return rapport, erreurs_test


def charger(dossier):
    return joblib.load(os.path.join(dossier, "modele.joblib"))


def estimer(paquet, biens):
    """Estime des biens (DataFrame avec latitude, longitude, code_commune, surface,
    nb_pieces, nb_dependances). Date = dernière date connue du marché."""
    biens = biens.copy()
    biens["date"] = paquet["date_max"]
    pred = _predire_trio(paquet["modeles"], preparer(biens), biens["surface"].values)
    return pd.DataFrame({"prix_estime": pred["central"], "fourchette_basse": pred["bas"],
                         "fourchette_haute": pred["haut"]}, index=biens.index)
