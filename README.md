# 🏠 Immo-Hunter — Analyse du marché immobilier Paris 16e

> **2 420 annonces scrapées** + **38 523 transactions DVF** · Analyse SQL + Dashboard Power BI · Surévaluation moyenne : **+5.4%** · Modèle ML (**R² = 0.92**, MAE -27%)

---

## 💡 Innovation du projet

Utilisation d'un LLM (Claude, Anthropic) pour transformer des descriptions immobilières non structurées en données exploitables — **50 features extraites automatiquement** (étage, DPE, exposition, état général, quartier, points forts/faibles…) à partir de texte libre.

---

## Pourquoi ce projet ?

Je suis étudiant en M1 Data Science & BI à EDC Paris et je cherche une alternance en Data Analyst / BI Analyst pour mon M2 (septembre 2026). J'ai voulu construire un projet de bout en bout, de la collecte de données jusqu'à la visualisation, sur un sujet concret : **le marché immobilier dans le 16e arrondissement de Paris**.

L'objectif était simple : récupérer des données réelles, les analyser, et répondre à une question : **est-ce que les vendeurs surévaluent leurs biens par rapport aux prix réels du marché ?**

> **Note** : J'ai fait l'analyse sur le 16e arrondissement, mais le scraper et le pipeline sont configurables pour n'importe quelle ville ou région en France. Il suffit de changer la ville et le code postal dans `config.py` pour relancer l'analyse ailleurs.

---

## Ce que j'ai fait

### 1. Collecte des données

J'ai récupéré deux sources de données :

- **2 420 annonces** scrappées depuis un leader de l'immobilier en ligne avec **Playwright** (navigateur headless). Le site utilise des protections anti-bot (CAPTCHA, détection de webdriver, bannières de cookies). J'ai dû configurer un user-agent réaliste, désactiver les marqueurs d'automatisation, et gérer les pauses aléatoires entre les requêtes pour simuler un comportement humain. Le scraper récupère les fiches résumées puis visite chaque annonce individuellement pour extraire la description complète — **1 538 descriptions récupérées (64%)**. Le dataset final contient principalement des appartements (2 237), mais aussi des duplex, maisons, studios, lofts et villas.
- **38 523 transactions réelles** (DVF — Données de Valeurs Foncières) téléchargées automatiquement depuis data.gouv.fr via un script Python (`requests`), couvrant la période 2020-2025.

### 2. Enrichissement IA

J'ai utilisé l'**API Claude** (Anthropic, via la bibliothèque `anthropic`) pour analyser les descriptions en texte libre des annonces et en extraire des données structurées en JSON — **50+ features** par annonce : étage, nombre d'étages de l'immeuble, hauteur sous plafond, DPE/GES, exposition, état général, type de chauffage, vue, ascenseur, cave, balcon, terrasse, loggia, piscine, proximité transports, points forts/faibles, quartier, etc.

Le prompt a été optimisé pour renvoyer un JSON strictement normalisé (valeurs d'énumération fixées : `etat_general` ∈ {neuf, rénové, bon, à rafraîchir...}, `exposition` ∈ {nord, sud, est, ouest, traversant...}, DPE en lettre A-G), ce qui permet de requêter les données directement en SQL sans nettoyage supplémentaire.

J'ai enrichi **579 annonces sur les 2 420** — enrichir l'intégralité de la base aurait représenté un coût API trop élevé. J'ai donc travaillé sur un échantillon, ce qui m'a quand même permis d'extraire 350 étages, 279 états généraux, 115 DPE et d'identifier 290 quartiers différents (Passy, Auteuil, Trocadéro, Victor Hugo, La Muette...). Le reste de l'enrichissement (mots-clés, regex) a été fait en SQL.

### 3. Base de données et nettoyage

J'ai importé les deux datasets dans **PostgreSQL** via `import_db.py` (~630 lignes) qui crée automatiquement :

- La table `annonces` avec **toutes les features IA** (50+ colonnes typées : INTEGER, BOOLEAN, VARCHAR avec contraintes)
- La table `dvf` avec les transactions réelles 2020-2025
- Les **vues SQL prêtes pour pgAdmin** : évolution prix/m², surévaluation par typologie, impact DPE, marge de négociation…
- Contrainte `UNIQUE` sur l'URL des annonces pour éviter les doublons entre imports

Le nettoyage complémentaire est fait directement en SQL :

- Extraction du DPE, de l'étage et de l'exposition par regex
- Détection de mots-clés dans les descriptions (ascenseur, balcon, terrasse, lumineux, calme, rénové…)
- Calcul du prix/m² sur les deux tables
- Création de vues pour chaque axe d'analyse

### 4. Analyse SQL

J'ai construit plusieurs analyses à partir des vues SQL :

- Évolution des prix/m² de 2020 à 2025
- Comparaison prix annonces vs prix de vente réels
- Impact du DPE sur le prix
- Marge de négociation par type de bien

![pgAdmin](screenshots/pgadmin.png)

### 5. Visualisation Power BI

J'ai exporté les résultats en CSV et construit un **dashboard Power BI** avec 4 graphiques :

- **Surévaluation : prix demandé vs prix réel (€/m²)** — courbe DVF + frais (2020-2025) comparée au prix moyen des annonces. On voit le marché passer au-dessus puis en dessous du prix demandé à partir de 2023.
- **Marge de négociation par typologie (nb pièces)** — barres groupées montrant l'écart entre prix demandé et prix réel de vente, de 1 à 7 pièces.
- **Prix demandé vs prix estimé (ML) par typologie** — les prédictions du modèle confrontées aux prix affichés, par nombre de pièces.
- **Impact du DPE sur le prix au m²** — évolution du prix selon la lettre DPE (A → G), montrant l'écart de valorisation entre biens performants et passoires énergétiques.

![Dashboard Power BI](screenshots/dashboard_powerbi.png)

### 6. Prédiction de prix (Machine Learning)

J'ai construit un modèle en Python avec scikit-learn qui apprend sur les transactions DVF réelles et prédit le prix des annonces en ligne. Le modèle entraîne simultanément sur **maisons et appartements** (un flag `est_maison` permet au modèle de différencier les deux) — ce qui le rend utilisable au-delà du 16e parisien.

**10 features** au lieu des 3 d'origine, en incluant du feature engineering géographique :

| Feature | Description |
|---|---|
| `surface_best` | Surface Carrez quand dispo, sinon surface réelle bâtie |
| `nombre_pieces_principales` | Nombre de pièces |
| `surface_terrain` | Terrain (0 pour appartements) |
| `est_maison` | Flag maison vs appartement |
| `annee`, `mois` | Temporalité de la transaction |
| `longitude`, `latitude` | Coordonnées géographiques |
| `nombre_lots` | Nombre de lots de la mutation |
| `prix_m2_zone` | **Médiane du prix/m² par micro-quartier** (cellule de ~100m) — capte l'effet localisation |

J'ai comparé **3 modèles** avec une **cross-validation 5-fold** (au lieu d'un simple train/test split), puis validation hold-out sur 20% :

| Modèle | R² (5-fold CV) | MAE |
|---|---|---|
| Régression Linéaire | 0.881 | 174 047 € |
| Random Forest | 0.905 | ~135 000 € |
| **Gradient Boosting** | **0.917** | **~127 000 €** |

**Résultat** : R² passe de 0.88 → 0.917 et MAE diminue de ~27% grâce au feature engineering géographique et au Gradient Boosting. Le modèle est ensuite appliqué sur les annonces en ligne pour estimer si le prix demandé est cohérent avec le marché, et un CSV `annonces_*_prediction.csv` est exporté pour Power BI.

![Output ML](screenshots/terminal_ml.png)

### Limites du modèle

Malgré l'amélioration, le modèle ne capte pas encore tous les critères qualitatifs : DPE, état général, étage, vue, exposition. Ces features sont disponibles via l'enrichissement IA mais sur un sous-échantillon seulement (579/2420 annonces enrichies) — les intégrer au modèle nécessiterait d'enrichir la totalité du dataset (coût API) ou d'utiliser un modèle hybride (features IA quand disponibles, imputation sinon). C'est une piste pour une prochaine itération.

### Pipeline unifié

Tout le workflow peut être exécuté en une seule commande via `pipeline.py` :

```bash
python pipeline.py              # Scrape + DVF
python pipeline.py --enrich     # + Enrichissement IA
python pipeline.py --predict    # + Prédiction ML
python pipeline.py --all        # Tout : scrape + DVF + enrichissement + ML + import DB
python pipeline.py --dvf-only   # DVF seulement
```

Le téléchargement DVF est **dynamique** : le script interroge l'API geo.api.gouv.fr pour récupérer le code commune à partir du code postal dans `config.py`, puis filtre les fichiers DVF annuels en streaming (pas besoin de tout télécharger).

---

## Ce qu'on retient

### Le marché du 16e : montée, chute, et début de reprise

Les prix/m² ont progressé entre 2020 et 2022, atteignant un pic à 12 619 €/m² net vendeur. À partir de 2023, le marché s'est retourné : baisse des prix (-7% entre 2022 et 2024, tombant à 11 712 €/m²) accompagnée d'une baisse du volume de ventes (de 2 921 transactions en 2022 à 2 043 en 2024). En 2025, on observe un léger rebond à 11 829 €/m² — le marché du 16e semble doucement se redresser.

### Les vendeurs surévaluent, mais pas toujours

En comparant les prix affichés dans les annonces (13 573 €/m²) aux prix de vente réels (DVF), on constate que les vendeurs surévaluent leurs biens en moyenne de **+5.4% en 2024**. Mais ce n'était pas le cas avant : en 2020-2022, les prix réels étaient supérieurs aux annonces actuelles — la surévaluation est un phénomène récent, lié à la baisse du marché.

**Point méthodo** : les données DVF sont en prix net vendeur (hors frais). Les annonces incluent les frais de notaire et d'agence. Pour rendre la comparaison fiable, j'ai ajouté ~10% aux prix DVF.

### Le DPE impacte fortement le prix

Les biens bien classés énergétiquement se vendent nettement plus cher. Un bien classé B atteint 17 758 €/m² contre 11 391 €/m² pour un F — soit un écart de +56%. Même entre C (12 810 €/m²) et D (12 045 €/m²), il y a 6% de différence. Dans un contexte de durcissement des réglementations énergétiques, le DPE devient un critère déterminant dans la valorisation d'un bien.

### La marge de négociation dépend de la taille du bien

Sur les studios, la marge est quasi nulle (-0.2%) : le marché est tendu, peu de place pour négocier. Sur les 3-4 pièces, on peut négocier environ 3.5%. Sur les 6 pièces, jusqu'à 4%. Les très grands appartements (7 pièces) reviennent à 0% — probablement parce que ce sont des biens de prestige avec des acheteurs prêts à payer le prix affiché.

---

## Outils utilisés

### Python

| Bibliothèque | Usage |
|---|---|
| `playwright` | Scraping headless — navigation, contournement anti-bot, extraction des descriptions |
| `beautifulsoup4` | Parsing HTML complémentaire |
| `requests` | Téléchargement automatique des fichiers DVF depuis data.gouv.fr |
| `anthropic` | Appels API Claude pour l'enrichissement IA des descriptions |
| `pandas` | Manipulation et nettoyage des données pour le modèle ML |
| `numpy` | Calculs vectorisés, médianes par zone géographique |
| `scikit-learn` | Modèles ML — `LinearRegression`, `RandomForestRegressor`, `GradientBoostingRegressor`, `cross_val_score`, `KFold`, `StandardScaler`, `Pipeline` |
| `openpyxl` | Export Excel formaté (en-têtes colorés, hyperliens, filtres auto) |
| `psycopg2` | Connexion Python → PostgreSQL pour l'import des CSV |
| `csv`, `json`, `re` | Parsing CSV, parsing JSON (réponses IA), extraction regex |

### Base de données et BI

| Outil | Usage |
|---|---|
| **PostgreSQL 18** | Stockage des deux datasets (annonces + DVF) |
| **pgAdmin 4** | Requêtes SQL, enrichissement regex, création de vues d'analyse |
| **Power BI** | Dashboard interactif avec 4 visualisations |

### Données

| Source | Contenu |
|---|---|
| **Site leader immobilier** | 2 420 annonces avec descriptions (scraping Playwright) |
| **DVF** (data.gouv.fr) | 38 523 transactions réelles 2020-2025 |

---

## Architecture du projet

```
immo-hunter/
├── README.md
├── pipeline.py            # Entry point unifié (scrape + DVF + enrich + ML + DB)
├── scrape.py              # Scraping → CSV
├── predict.py             # Modèle ML (10 features, GBM + CV) → export Power BI
├── import_db.py           # Import CSV → PostgreSQL + création des vues SQL
├── config.py              # Ville, code postal, années DVF (configurable)
├── requirements.txt
├── scraper/               # Scraper Playwright
├── enrichment/            # Enrichissement Claude API (50+ features)
├── dvf/                   # Téléchargement DVF dynamique (API geo.gouv.fr)
├── screenshots/           # Screenshots pour le README
└── output/                # Données (exclu du repo)
```

---

## Installation

```bash
git clone https://github.com/maxime-txn/immo-hunter-2.git
cd immo-hunter-2
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Optionnel : enrichissement IA
export ANTHROPIC_API_KEY=sk-ant-xxx

# Lancer le pipeline complet
python pipeline.py --all
```

---

## ⚠️ Disclaimer

Ce projet est réalisé dans un cadre pédagogique et portfolio. Les données DVF sont publiques (data.gouv.fr). Les prédictions du modèle ML ne constituent pas des conseils en investissement immobilier.

---

## Auteur

**Maxime Teixeira Novais**
M1 Data Science & BI — EDC Paris Business School
