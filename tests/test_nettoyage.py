import pandas as pd

from immohunter.nettoyage import COLONNES, nettoyer


def ligne(mutation, type_local, surface, prix, lot="1", pieces="2"):
    base = {c: None for c in COLONNES}
    base.update({"id_mutation": mutation, "date_mutation": "2024-03-01", "nature_mutation": "Vente",
                 "valeur_fonciere": prix, "code_postal": "75016", "code_commune": "75116",
                 "nom_commune": "Paris 16e Arrondissement", "lot1_numero": lot,
                 "type_local": type_local, "surface_reelle_bati": surface,
                 "nombre_pieces_principales": pieces if type_local != "Dépendance" else None,
                 "longitude": "2.27", "latitude": "48.85"})
    return base


def test_garde_un_appartement_avec_sa_cave():
    brut = pd.DataFrame([ligne("A", "Appartement", "50", "600000"),
                         ligne("A", "Dépendance", None, "600000", lot="2")])
    ventes, _ = nettoyer(brut, ["Appartement"])
    assert len(ventes) == 1
    assert ventes.loc[0, "prix_m2"] == 12_000
    assert ventes.loc[0, "nb_dependances"] == 1


def test_exclut_une_vente_de_deux_appartements():
    # Le prix (1,2 M€) est le prix TOTAL des deux lots : le diviser par 50 m² serait faux.
    brut = pd.DataFrame([ligne("B", "Appartement", "50", "1200000", lot="1"),
                         ligne("B", "Appartement", "50", "1200000", lot="2")])
    ventes, _ = nettoyer(brut, ["Appartement"])
    assert ventes.empty


def test_supprime_les_doublons_de_parcelles():
    brut = pd.DataFrame([ligne("C", "Appartement", "40", "480000")] * 2)
    ventes, _ = nettoyer(brut, ["Appartement"])
    assert len(ventes) == 1
