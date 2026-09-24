-- Pour chaque code postal : le secteur (code commune) le plus fréquent et son point central.
-- Sert à positionner une annonce dont on ne connaît que le code postal.
WITH comptage AS (
    SELECT
        code_postal,
        code_commune,
        secteur,
        COUNT(*)                                                    AS nb_ventes,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latitude)       AS latitude,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY longitude)      AS longitude,
        ROW_NUMBER() OVER (PARTITION BY code_postal ORDER BY COUNT(*) DESC) AS rang
    FROM ventes
    WHERE code_postal IS NOT NULL
    GROUP BY code_postal, code_commune, secteur
)
SELECT code_postal, code_commune, secteur, latitude, longitude, nb_ventes
FROM comptage
WHERE rang = 1
ORDER BY code_postal;
