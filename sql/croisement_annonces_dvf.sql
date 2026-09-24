-- Croisement des deux sources, par secteur :
--   annonces en ligne  = le marché d'AUJOURD'HUI (prix demandés)
--   ventes DVF         = ce qui s'est réellement VENDU (publié avec plusieurs mois de retard)
-- On compare le prix au m² affiché au prix au m² vendu sur les 12 derniers mois publiés,
-- et on mesure la part d'annonces au-dessus de l'estimation du modèle.
WITH fin AS (
    SELECT MAX(date) AS date_fin FROM ventes
),
ventes_recentes AS (
    SELECT
        v.secteur,
        COUNT(*)                                                    AS nb_ventes,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v.prix_m2)      AS prix_m2_vendu
    FROM ventes v
    CROSS JOIN fin f
    WHERE v.date > f.date_fin - INTERVAL '12 months'
    GROUP BY v.secteur
),
annonces_secteur AS (
    SELECT
        secteur,
        COUNT(*)                                                    AS nb_annonces,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix / surface) AS prix_m2_affiche,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ecart_pct)      AS ecart_median_estimation,
        100.0 * AVG(CASE WHEN verdict IN ('Surévalué', 'Au-dessus du marché') THEN 1 ELSE 0 END)
                                                                    AS part_au_dessus
    FROM annonces
    GROUP BY secteur
)
SELECT
    a.secteur,
    a.nb_annonces,
    v.nb_ventes,
    ROUND(a.prix_m2_affiche)                                        AS prix_m2_affiche,
    ROUND(v.prix_m2_vendu)                                          AS prix_m2_vendu,
    ROUND(100.0 * (a.prix_m2_affiche - v.prix_m2_vendu) / v.prix_m2_vendu, 1) AS ecart_affiche_vs_vendu_pct,
    ROUND(a.ecart_median_estimation, 1)                             AS ecart_median_vs_estimation_pct,
    ROUND(a.part_au_dessus, 1)                                      AS part_annonces_au_dessus_pct
FROM annonces_secteur a
JOIN ventes_recentes v USING (secteur)
ORDER BY ecart_affiche_vs_vendu_pct DESC;
