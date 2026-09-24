"""
Étape 2 : transformer les fichiers DVF bruts en une table propre, 1 ligne = 1 vente.

Le piège principal de DVF : une "mutation" (une vente chez le notaire) peut contenir
plusieurs lignes (plusieurs lots, une cave, un parking, un local commercial...)
et le prix (valeur_fonciere) est répété sur chaque ligne : c'est le prix TOTAL.
Si on divise ce prix total par la surface d'un seul appartement, on obtient
des prix au m² faux. On ne garde donc que les ventes d'UN seul logement
(avec éventuellement des dépendances : cave, parking).
"""
import pandas as pd

COLONNES = [
    "id_mutation", "date_mutation", "nature_mutation", "valeur_fonciere",
    "adresse_numero", "adresse_nom_voie", "code_postal", "code_commune", "nom_commune",
    "lot1_numero", "type_local", "surface_reelle_bati", "nombre_pieces_principales",
    "longitude", "latitude",
]
TYPES_PRINCIPAUX = ["Appartement", "Maison", "Local industriel. commercial ou assimilé"]


def lire_brut(fichiers):
    morceaux = [pd.read_csv(f, usecols=COLONNES, dtype=str) for f in fichiers]
    return pd.concat(morceaux, ignore_index=True)


def nom_secteur(nom_commune):
    """'Paris 16e Arrondissement' -> 'Paris 16e' ; les autres communes restent telles quelles."""
    return nom_commune.replace(" Arrondissement", "")


def nettoyer(brut, types_biens, communes=None, surface=(9, 400), prix_m2=(3_000, 40_000)):
    """Renvoie (ventes propres, entonnoir de nettoyage)."""
    entonnoir = {"lignes_brutes": len(brut), "mutations_brutes": brut["id_mutation"].nunique()}

    df = brut[brut["nature_mutation"] == "Vente"].copy()
    if communes:
        df = df[df["code_commune"].isin(communes)]
    entonnoir["mutations_vente"] = df["id_mutation"].nunique()

    # Une même ligne peut être répétée si la vente porte sur plusieurs parcelles
    df = df.drop_duplicates(subset=["id_mutation", "type_local", "lot1_numero",
                                    "surface_reelle_bati", "nombre_pieces_principales"])

    # Composition de chaque vente : combien de logements, de dépendances, de locaux ?
    compo = pd.crosstab(df["id_mutation"], df["type_local"])
    for t in TYPES_PRINCIPAUX + ["Dépendance"]:
        if t not in compo:
            compo[t] = 0
    nb_principaux = compo[TYPES_PRINCIPAUX].sum(axis=1)
    cible = compo[types_biens].sum(axis=1)
    mutations_ok = compo.index[(cible == 1) & (nb_principaux == 1)]
    entonnoir["ventes_1_seul_logement"] = len(mutations_ok)

    ventes = df[df["id_mutation"].isin(mutations_ok) & df["type_local"].isin(types_biens)].copy()
    ventes["nb_dependances"] = ventes["id_mutation"].map(compo["Dépendance"]).astype(int)

    # Typage
    for col in ["valeur_fonciere", "surface_reelle_bati", "nombre_pieces_principales",
                "longitude", "latitude"]:
        ventes[col] = pd.to_numeric(ventes[col], errors="coerce")
    ventes["date"] = pd.to_datetime(ventes["date_mutation"], errors="coerce")

    ventes = ventes.dropna(subset=["valeur_fonciere", "surface_reelle_bati", "date",
                                   "longitude", "latitude"])
    ventes = ventes[ventes["nombre_pieces_principales"] >= 1]
    ventes = ventes[ventes["surface_reelle_bati"].between(*surface)]
    entonnoir["apres_controles_surface_geo"] = len(ventes)

    ventes["prix_m2"] = ventes["valeur_fonciere"] / ventes["surface_reelle_bati"]
    ventes = ventes[ventes["prix_m2"].between(*prix_m2)]
    entonnoir["ventes_finales"] = len(ventes)

    ventes = ventes.rename(columns={
        "valeur_fonciere": "prix", "surface_reelle_bati": "surface",
        "nombre_pieces_principales": "nb_pieces", "type_local": "type_bien",
    })
    ventes["secteur"] = ventes["nom_commune"].map(nom_secteur)
    ventes["adresse"] = (ventes["adresse_numero"].fillna("") + " "
                         + ventes["adresse_nom_voie"].fillna("")).str.strip().str.title()
    ventes["annee"] = ventes["date"].dt.year

    colonnes_finales = ["id_mutation", "date", "annee", "prix", "surface", "nb_pieces",
                        "nb_dependances", "prix_m2", "type_bien", "secteur", "code_commune",
                        "code_postal", "adresse", "latitude", "longitude"]
    ventes = ventes[colonnes_finales].sort_values("date").reset_index(drop=True)
    ventes["nb_pieces"] = ventes["nb_pieces"].astype(int)
    return ventes, entonnoir
