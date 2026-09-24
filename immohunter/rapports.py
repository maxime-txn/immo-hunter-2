"""
Graphiques du README, générés automatiquement à chaque exécution du pipeline.
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import numpy as np  # noqa: E402

FOND = "#fcfcfb"
TEXTE = "#0b0b0b"
TEXTE_2 = "#52514e"
GRILLE = "#e4e3df"
BLEU = "#2a78d6"      # série principale
GRIS = "#85837e"      # référence / contexte (gris volontaire : mise en avant du modèle)
ROUGE = "#e34948"     # hausse (pôle chaud du couple divergent)

plt.rcParams.update({
    "figure.facecolor": FOND, "axes.facecolor": FOND, "savefig.facecolor": FOND,
    "axes.edgecolor": GRILLE, "axes.labelcolor": TEXTE_2, "xtick.color": TEXTE_2,
    "ytick.color": TEXTE_2, "text.color": TEXTE, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRILLE, "grid.linewidth": 0.8, "axes.axisbelow": True,
})

EUROS = mtick.FuncFormatter(lambda x, _: f"{x:,.0f} €".replace(",", " "))


def pct_fr(x, signe=False):
    """Pourcentage à la française : virgule décimale, espace avant %."""
    if round(x, 1) == 0:
        return "0,0 %"
    txt = f"{x:+.1f}" if signe else f"{x:.1f}"
    return txt.replace(".", ",") + " %"


def _titre(ax, titre, sous_titre):
    ax.set_title(titre, loc="left", fontsize=13, fontweight="bold", pad=22)
    ax.text(0, 1.02, sous_titre, transform=ax.transAxes, fontsize=9.5, color=TEXTE_2)


def evolution_prix(ventes, nom_zone, chemin):
    """Prix médian au m² par trimestre sur toute la zone."""
    trim = (ventes.set_index("date")["prix_m2"].resample("QS").agg(["median", "size"]))
    trim = trim[trim["size"] >= 100]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(trim.index, trim["median"], color=BLEU, linewidth=2)
    ax.scatter(trim.index[[0, -1]], trim["median"].iloc[[0, -1]], color=BLEU, s=40, zorder=3,
               edgecolor=FOND, linewidth=2)
    for i, ha in [(0, "left"), (-1, "right")]:
        ax.annotate(f"{trim['median'].iloc[i]:,.0f} €/m²".replace(",", " "),
                    (trim.index[i], trim["median"].iloc[i]), xytext=(0, 10),
                    textcoords="offset points", ha=ha, fontsize=9.5, color=TEXTE)
    ax.yaxis.set_major_formatter(EUROS)
    ax.set_ylim(0, trim["median"].max() * 1.15)   # axe à zéro : on ne grossit pas les variations
    _titre(ax, f"{nom_zone} : prix médian au m² des appartements vendus",
           "Par trimestre, ventes notariales DVF")
    fig.tight_layout()
    fig.savefig(chemin, dpi=160)
    plt.close(fig)


def precision(erreurs_test, chemin):
    """Part des ventes estimées à moins de X % du prix réel : modèle vs méthode simple."""
    seuils = np.arange(0, 31)
    e_mod = np.abs(erreurs_test["estime"] - erreurs_test["reel"]) / erreurs_test["reel"] * 100
    e_ref = np.abs(erreurs_test["reference"] - erreurs_test["reel"]) / erreurs_test["reel"] * 100
    part_mod = [(e_mod <= s).mean() * 100 for s in seuils]
    part_ref = [(e_ref <= s).mean() * 100 for s in seuils]

    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(seuils, part_ref, color=GRIS, linewidth=2, label="Méthode simple : médiane du secteur × surface")
    ax.plot(seuils, part_mod, color=BLEU, linewidth=2, label="Modèle Immo-Hunter")
    for serie, dx, dy, ha, couleur in [(part_mod, -8, 6, "right", BLEU), (part_ref, 8, -14, "left", GRIS)]:
        ax.scatter([10], [serie[10]], color=couleur, s=40, zorder=3, edgecolor=FOND, linewidth=2)
        ax.annotate(f"{serie[10]:.0f} %", (10, serie[10]), xytext=(dx, dy), ha=ha,
                    textcoords="offset points", fontsize=9.5, color=TEXTE)
    ax.set_xlabel("Écart toléré entre l'estimation et le prix réel de vente")
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"± {x:.0f} %"))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f} %"))
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right", frameon=False)
    _titre(ax, "Part des ventes estimées correctement",
           "Test sur les derniers mois, jamais vus par le modèle")
    fig.tight_layout()
    fig.savefig(chemin, dpi=160)
    plt.close(fig)


def tendance_secteurs(tendance, chemin):
    """Variation du prix médian au m² sur 12 mois, par secteur."""
    t = tendance.dropna(subset=["variation_pct"]).sort_values("variation_pct")
    couleurs = [ROUGE if v > 0 else BLEU for v in t["variation_pct"]]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(t) + 1.4))
    ax.barh(t["secteur"], t["variation_pct"], color=couleurs, height=0.7)
    ax.axvline(0, color=TEXTE_2, linewidth=0.8)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(
        lambda x, _: "0 %" if x == 0 else f"{x:+.0f} %"))
    ax.grid(axis="y", visible=False)
    marge = max(abs(t["variation_pct"].min()), abs(t["variation_pct"].max())) * 0.25
    ax.set_xlim(min(t["variation_pct"].min(), 0) - marge, max(t["variation_pct"].max(), 0) + marge)
    for y, v in enumerate(t["variation_pct"]):
        ax.annotate(pct_fr(v, signe=True), (v, y), xytext=(4 if v >= 0 else -4, 0),
                    textcoords="offset points", va="center", ha="left" if v >= 0 else "right",
                    fontsize=8.5, color=TEXTE_2)
    _titre(ax, "Le marché monte-t-il ou baisse-t-il ?",
           "Prix médian au m² des 12 derniers mois vs les 12 mois précédents")
    fig.tight_layout()
    fig.savefig(chemin, dpi=160)
    plt.close(fig)


def generer(ventes, tendance, erreurs_test, nom_zone, dossier):
    os.makedirs(dossier, exist_ok=True)
    evolution_prix(ventes, nom_zone, os.path.join(dossier, "evolution_prix.png"))
    precision(erreurs_test, os.path.join(dossier, "precision_modele.png"))
    if tendance["variation_pct"].notna().any():
        tendance_secteurs(tendance, os.path.join(dossier, "tendance_secteurs.png"))
