-- Les ventes réelles les plus proches d'un bien : même taille (± 25 %),
-- vendues dans les 24 derniers mois, triées par distance (formule de haversine, en mètres).
-- Paramètres : $lat, $lon, $surface
SELECT
    date,
    adresse,
    secteur,
    surface,
    nb_pieces,
    prix,
    ROUND(prix_m2)                                                  AS prix_m2,
    latitude,
    longitude,
    ROUND(2 * 6371000 * ASIN(SQRT(
          POWER(SIN(RADIANS(latitude - $lat) / 2), 2)
        + COS(RADIANS($lat)) * COS(RADIANS(latitude))
        * POWER(SIN(RADIANS(longitude - $lon) / 2), 2)
    )))                                                             AS distance_m
FROM ventes
WHERE surface BETWEEN $surface * 0.75 AND $surface * 1.25
  AND date >= (SELECT MAX(date) FROM ventes) - INTERVAL '24 months'
ORDER BY distance_m
LIMIT 10;
