-- Prix médian au m² par trimestre, pour un secteur ou pour toute la zone ($secteur = NULL).
SELECT
    DATE_TRUNC('quarter', date)                                     AS trimestre,
    COUNT(*)                                                        AS nb_ventes,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix_m2))     AS prix_m2_median
FROM ventes
WHERE $secteur IS NULL OR secteur = $secteur
GROUP BY trimestre
HAVING COUNT(*) >= 30
ORDER BY trimestre;
