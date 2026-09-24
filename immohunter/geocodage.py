"""
Adresse -> coordonnées GPS, via le service public de géocodage de l'IGN (Géoplateforme,
successeur de l'API Adresse). Gratuit, sans clé.
"""
import requests

URL = "https://data.geopf.fr/geocodage/search"


def geocoder(adresse, timeout=5):
    """Renvoie {latitude, longitude, code_commune, label} ou None si introuvable."""
    try:
        rep = requests.get(URL, params={"q": adresse, "limit": 1}, timeout=timeout)
        rep.raise_for_status()
        resultats = rep.json().get("features", [])
    except (requests.RequestException, ValueError):
        return None
    if not resultats or resultats[0]["properties"].get("score", 0) < 0.5:
        return None
    lon, lat = resultats[0]["geometry"]["coordinates"]
    props = resultats[0]["properties"]
    return {"latitude": lat, "longitude": lon,
            "code_commune": props.get("citycode"), "label": props.get("label")}
