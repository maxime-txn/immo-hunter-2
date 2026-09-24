"""
Immo-Hunter : application web.
Lancer en local : streamlit run app.py
"""
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from immohunter import base, modele
from immohunter.geocodage import geocoder
from immohunter.verdict import AU_DESSUS, EN_DESSOUS, SOUS_EVALUE, SUREVALUE, verdict

BLEU, GRIS, ROUGE = "#2a78d6", "#85837e", "#e34948"
GITHUB = "https://github.com/maxime-txn/immo-hunter-2"
LINKEDIN = "https://www.linkedin.com/in/mtxn"

st.set_page_config(page_title="Immo-Hunter · Le juste prix d'un logement", page_icon="🏠",
                   layout="centered")


# ── Chargements (mis en cache) ───────────────────────────────
@st.cache_resource
def charger_modele():
    return modele.charger(config.DOSSIER_MODELES)


@st.cache_resource
def connexion():
    return base.connexion(config.FICHIER_VENTES)


@st.cache_data
def sql(nom, **params):
    return base.requete(connexion(), nom, **params)


@st.cache_data
def lire_json(chemin):
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def euros(x):
    return f"{x:,.0f} €".replace(",", " ")


def pct(x, signe=False):
    """Pourcentage à la française : 12,2 % ; +1,6 %."""
    return (f"{x:+.1f}" if signe else f"{x:.1f}").replace(".", ",") + " %"


def euros_arrondis(x):
    """Une estimation n'a pas une précision à l'euro près : arrondi au millier."""
    return euros(round(x, -3))


paquet = charger_modele()
centres = sql("centres_codes_postaux")
secteurs = sorted(centres["secteur"].unique(), key=lambda s: (len(s), s))
evaluation = lire_json(f"{config.DOSSIER_MODELES}/evaluation.json")
entonnoir = lire_json(f"{config.DOSSIER_RAPPORTS}/nettoyage.json")
date_max = pd.Timestamp(paquet["date_max"])

# ── En-tête ──────────────────────────────────────────────────
st.title("Immo-Hunter")
st.markdown(
    f"**Ce logement est-il au juste prix ?** Estimation fondée sur "
    f"**{entonnoir['ventes_finales']:,} ventes réelles** enregistrées chez les notaires "
    f"({config.NOM_ZONE}, jusqu'à {date_max:%m/%Y}).".replace(",", " "))

onglet_annonce, onglet_marche, onglet_methode = st.tabs(
    ["Vérifier une annonce", "Le marché", "Comment ça marche"])

# ── 1. Vérifier une annonce ──────────────────────────────────
with onglet_annonce:
    with st.form("bien"):
        adresse = st.text_input("Adresse du bien", placeholder="ex. 12 rue de Passy, Paris")
        c1, c2 = st.columns(2)
        surface = c1.number_input("Surface (m²)", min_value=9, max_value=400, value=50)
        pieces = c2.number_input("Nombre de pièces", min_value=1, max_value=10, value=2)
        c3, c4 = st.columns(2)
        prix_demande = c3.number_input("Prix demandé (€), facultatif", min_value=0, value=0,
                                       step=10_000)
        dependance = c4.checkbox("Cave ou parking inclus")
        secteur_manuel = st.selectbox("Secteur (si l'adresse n'est pas trouvée)",
                                      ["Déduire de l'adresse"] + secteurs)
        lancer = st.form_submit_button("Analyser", type="primary", width="stretch")

    if lancer:
        position = geocoder(adresse) if adresse.strip() else None
        if position and position["code_commune"] not in set(centres["code_commune"]):
            st.error(f"« {position['label']} » est hors de la zone couverte ({config.NOM_ZONE}).")
            st.stop()
        if position is None:
            if secteur_manuel == "Déduire de l'adresse":
                st.warning("Adresse introuvable : choisissez le secteur dans la liste.")
                st.stop()
            ligne = centres[centres["secteur"] == secteur_manuel].iloc[0]
            position = {"latitude": ligne["latitude"], "longitude": ligne["longitude"],
                        "code_commune": ligne["code_commune"], "label": secteur_manuel}
            st.info(f"Estimation au niveau du secteur ({secteur_manuel}), moins précise "
                    "qu'avec une adresse.")

        bien = pd.DataFrame([{**position, "surface": surface, "nb_pieces": pieces,
                              "nb_dependances": int(dependance)}])
        est = modele.estimer(paquet, bien).iloc[0]

        st.caption(f"📍 {position['label']}")
        if prix_demande > 0:
            v = verdict(prix_demande, est["prix_estime"], est["fourchette_basse"],
                        est["fourchette_haute"])
            message = (f"**{v['verdict']}** : le prix demandé est **{v['ecart_pct']:+.0f} %** "
                       f"par rapport à l'estimation.")
            if v["verdict"] == SUREVALUE:
                st.error(message, icon="🔺")
            elif v["verdict"] == AU_DESSUS:
                st.warning(message, icon="↗️")
            elif v["verdict"] in (SOUS_EVALUE, EN_DESSOUS):
                st.success(message, icon="↘️")
            else:
                st.info(message, icon="✅")

        m1, m2 = st.columns(2)
        m1.metric("Prix estimé", euros_arrondis(est["prix_estime"]),
                  help="Prix de vente probable, pas prix d'annonce.")
        m2.metric("Prix au m²", euros(round(est["prix_estime"] / surface, -1)))
        st.markdown(f"**Fourchette de marché** : {euros_arrondis(est['fourchette_basse'])} à "
                    f"{euros_arrondis(est['fourchette_haute'])}  \n"
                    f"<small>8 ventes comparables sur 10 se situent dans cet intervalle. "
                    f"Un prix d'annonce inclut souvent une marge de négociation (≈ 5 %).</small>",
                    unsafe_allow_html=True)

        comp = sql("ventes_comparables", lat=position["latitude"], lon=position["longitude"],
                   surface=float(surface))
        st.subheader("Ventes réelles les plus proches")
        st.caption("Même taille (± 25 %), vendues dans les 24 derniers mois. Source : DVF.")
        carte = pd.concat([
            comp[["latitude", "longitude"]].assign(couleur=BLEU, taille=12),
            pd.DataFrame([{"latitude": position["latitude"], "longitude": position["longitude"],
                           "couleur": ROUGE, "taille": 20}]),
        ])
        st.map(carte, latitude="latitude", longitude="longitude", color="couleur",
               size="taille", zoom=15, height=280)
        st.caption("🔴 le bien analysé · 🔵 les ventes comparables")
        tableau = comp.drop(columns=["latitude", "longitude"]).assign(
            date=comp["date"].dt.strftime("%m/%Y"),
            prix=comp["prix"].map(euros),
            prix_m2=comp["prix_m2"].map(euros),
            distance_m=comp["distance_m"].astype(int).astype(str) + " m",
        ).rename(columns={"date": "Date", "adresse": "Adresse", "secteur": "Secteur",
                          "surface": "m²", "nb_pieces": "Pièces", "prix": "Prix",
                          "prix_m2": "Prix / m²", "distance_m": "Distance"})
        st.dataframe(tableau, hide_index=True, width="stretch")

# ── 2. Le marché ─────────────────────────────────────────────
with onglet_marche:
    choix = st.selectbox("Secteur", secteurs, index=secteurs.index("Paris 16e")
                         if "Paris 16e" in secteurs else 0)
    tendance = sql("tendance_12_mois")
    ligne = tendance[tendance["secteur"] == choix].iloc[0]
    k1, k2, k3 = st.columns(3)
    k1.metric("Prix médian / m² (12 mois)", euros(ligne["prix_m2_12_derniers_mois"]),
              None if pd.isna(ligne["variation_pct"]) else pct(ligne["variation_pct"], True) + " sur 1 an")
    k2.metric("Ventes (12 mois)", f"{ligne['nb_ventes_recent']:,}".replace(",", " "))
    k3.metric("Rang (du plus cher)", f"{ligne['rang_prix']} / {len(tendance)}")

    zone = sql("evolution_trimestrielle", secteur=None)
    local = sql("evolution_trimestrielle", secteur=choix)
    fig = go.Figure()
    fig.add_scatter(x=zone["trimestre"], y=zone["prix_m2_median"], name=f"Tout {config.NOM_ZONE}",
                    line=dict(color=GRIS, width=2),
                    hovertemplate="%{x|%m/%Y} : %{y:,.0f} €/m²<extra>" + config.NOM_ZONE + "</extra>")
    fig.add_scatter(x=local["trimestre"], y=local["prix_m2_median"], name=choix,
                    line=dict(color=BLEU, width=2),
                    hovertemplate="%{x|%m/%Y} : %{y:,.0f} €/m²<extra>" + choix + "</extra>")
    fig.update_layout(title=dict(text="Prix médian au m², par trimestre", x=0),
                      height=360, margin=dict(l=0, r=0, t=50, b=0), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15), separators=", ",
                      yaxis=dict(rangemode="tozero", ticksuffix=" €", gridcolor="#e4e3df"),
                      xaxis=dict(gridcolor="#e4e3df"), plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")

    t = tendance.dropna(subset=["variation_pct"]).sort_values("variation_pct")
    if len(t):
        bar = go.Figure(go.Bar(
            x=t["variation_pct"], y=t["secteur"], orientation="h",
            marker_color=[ROUGE if v > 0 else BLEU for v in t["variation_pct"]],
            hovertemplate="%{y} : %{x:+.1f} %<extra></extra>"))
        bar.update_layout(title=dict(text="Variation du prix au m² sur 12 mois", x=0),
                          height=28 * len(t) + 80, margin=dict(l=0, r=0, t=50, b=0),
                          xaxis=dict(ticksuffix=" %", zeroline=True, zerolinecolor="#52514e",
                                     gridcolor="#e4e3df"), separators=", ",
                          plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(bar, width="stretch")

# ── 3. Comment ça marche ─────────────────────────────────────
with onglet_methode:
    mod, ref = evaluation["modele"], evaluation["reference_mediane_secteur"]
    st.markdown(f"""
**1. Données** : ventes notariales DVF (data.gouv.fr). {entonnoir['lignes_brutes']:,} lignes brutes,
{entonnoir['ventes_finales']:,} ventes d'un seul logement retenues après nettoyage.

**2. Modèle** : gradient boosting (scikit-learn) sur la position, la surface, le nombre de pièces,
la présence d'une cave ou d'un parking et la date. Deux modèles supplémentaires calculent la fourchette basse et haute.

**3. Test honnête** : entraîné sur le passé, testé sur les {evaluation['nb_ventes_test']:,} ventes les plus
récentes ({evaluation['periode_test'][0]} → {evaluation['periode_test'][1]}), jamais vues par le modèle.
""".replace(",", " "))
    c1, c2, c3 = st.columns(3)
    c1.metric("Erreur médiane", pct(mod["erreur_mediane_pct"]),
              pct(mod["erreur_mediane_pct"] - ref["erreur_mediane_pct"], True).replace(" %", " pt")
              + " vs méthode simple", delta_color="inverse")
    c2.metric("Estimées à ± 10 %", pct(mod["part_a_moins_de_10pct"]),
              pct(mod["part_a_moins_de_10pct"] - ref["part_a_moins_de_10pct"], True).replace(" %", " pt"))
    c3.metric("Fourchette fiable", pct(evaluation["fourchette_couverture_pct"]),
              f"cible {evaluation['fourchette_cible_pct']} %", delta_color="off")
    st.image(f"{config.DOSSIER_RAPPORTS}/precision_modele.png")
    st.markdown("""
**Limites** : DVF ne contient ni l'étage, ni l'état, ni le DPE, ni la vue. Deux appartements de même
surface dans la même rue peuvent valoir ±20 % selon ces critères : le modèle ne peut pas les voir.
C'est la raison du module d'enrichissement IA des annonces (voir le code).
""")

st.divider()
st.caption(f"Projet de Maxime Teixeira · M2 Data Science & BI, EDC Paris · "
           f"[Code source]({GITHUB}) · [LinkedIn]({LINKEDIN})")
