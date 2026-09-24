"""
Immo-Hunter : configuration de la zone analysée.

Pour analyser une autre ville, il suffit de changer ce fichier
puis de relancer : python pipeline.py --tout
"""

# ── ZONE ──────────────────────────────────────────────────────
NOM_ZONE = "Paris"
DEPARTEMENT = "75"
# Communes à garder (codes INSEE). None = tout le département.
# Exemple Lyon : DEPARTEMENT = "69", COMMUNES = ["69381", ..., "69389"]
COMMUNES = None

# ── DONNÉES DVF (ventes notariales, data.gouv.fr) ────────────
ANNEES = [2021, 2022, 2023, 2024, 2025]   # années disponibles sur data.gouv.fr (09/2026)
TYPES_BIENS = ["Appartement"]          # ajouter "Maison" hors Paris

# ── RÈGLES DE NETTOYAGE ──────────────────────────────────────
SURFACE_MIN, SURFACE_MAX = 9, 400      # m²
PRIX_M2_MIN, PRIX_M2_MAX = 3_000, 40_000  # € / m², bornes larges anti-erreurs de saisie

# ── MODÈLE ────────────────────────────────────────────────────
# Validation "comme dans la vraie vie" : on entraîne sur le passé,
# on teste sur la période la plus récente, jamais vue par le modèle.
NB_MOIS_TEST = 6

# ── VERDICT SUR UNE ANNONCE ──────────────────────────────────
# Fourchette de marché = intervalle qui contient 80 % des ventes réelles.
QUANTILE_BAS, QUANTILE_HAUT = 0.10, 0.90

# ── CHEMINS ───────────────────────────────────────────────────
DOSSIER_BRUT = "data/brut"
FICHIER_VENTES = "data/ventes.parquet"
DOSSIER_MODELES = "modeles"
DOSSIER_RAPPORTS = "rapports"

# ── MODULE OPTIONNEL : ANNONCES EN LIGNE ────────────────────
# Collecte d'annonces (Playwright) + enrichissement IA (API Claude).
# Usage personnel uniquement, dans le respect des conditions d'utilisation du site.
city = "Paris 16eme"
property_type = "apartment"
price_min = None
price_max = None
max_pages = 5
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_DIR = "data/annonces"
