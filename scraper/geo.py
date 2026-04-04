"""Filtre geographique."""
import re
import unicodedata


def normalize(text):
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = clean.lower().strip()
    clean = re.sub(r"[\s\-_']+", " ", clean)
    clean = clean.replace("saint ", "st ")
    return clean


def city_matches(text, target):
    if not text or not target:
        return False
    return normalize(target) in normalize(text)


def filter_by_city(results, city):
    out = []
    for r in results:
        if city_matches(r.get("localisation", ""), city):
            out.append(r)
        elif city_matches(r.get("url", ""), city):
            out.append(r)
        elif city_matches(r.get("titre", ""), city):
            out.append(r)
    return out


def city_to_slug(city):
    s = normalize(city)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")
