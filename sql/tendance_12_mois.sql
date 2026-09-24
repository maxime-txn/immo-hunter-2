-- Le marché monte-t-il ou baisse-t-il ?
-- Compare, pour chaque secteur, le prix médian au m² des 12 derniers mois
-- à celui des 12 mois précédents.
WITH fin AS (
    SELECT MAX(date) AS date_fin FROM ventes
),
periodes AS (
    SELECT
        v.secteur,
        v.prix_m2,
        CASE
            WHEN v.date >  f.date_fin - INTERVAL '12 months' THEN 'recent'
            WHEN v.date >  f.date_fin - INTERVAL '24 months' THEN 'precedent'
        END AS periode
    FROM ventes v
    CROSS JOIN fin f
),
medianes AS (
    SELECT
        secteur,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix_m2)
            FILTER (WHERE periode = 'recent')                       AS median_recent,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix_m2)
            FILTER (WHERE periode = 'precedent')                    AS median_precedent,
        COUNT(*) FILTER (WHERE periode = 'recent')                  AS nb_ventes_recent
    FROM periodes
    WHERE periode IS NOT NULL
    GROUP BY secteur
)
SELECT
    secteur,
    nb_ventes_recent,
    ROUND(median_recent)                                            AS prix_m2_12_derniers_mois,
    ROUND(median_precedent)                                         AS prix_m2_12_mois_avant,
    ROUND(100.0 * (median_recent - median_precedent) / median_precedent, 1) AS variation_pct,
    RANK() OVER (ORDER BY median_recent DESC)                       AS rang_prix
FROM medianes
ORDER BY rang_prix;
