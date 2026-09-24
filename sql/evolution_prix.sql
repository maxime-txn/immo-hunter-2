-- Évolution du prix médian au m² par secteur et par année,
-- avec la variation par rapport à l'année précédente (fonction de fenêtre LAG).
WITH annuel AS (
    SELECT
        secteur,
        annee,
        COUNT(*)                                                    AS nb_ventes,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix_m2)        AS prix_m2_median
    FROM ventes
    GROUP BY secteur, annee
)
SELECT
    secteur,
    annee,
    nb_ventes,
    ROUND(prix_m2_median)                                           AS prix_m2_median,
    ROUND(100.0 * (prix_m2_median - LAG(prix_m2_median) OVER w)
          / LAG(prix_m2_median) OVER w, 1)                          AS variation_pct
FROM annuel
WINDOW w AS (PARTITION BY secteur ORDER BY annee)
ORDER BY secteur, annee;
