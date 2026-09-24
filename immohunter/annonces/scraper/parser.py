"""Extraction de donnees depuis du texte."""
import re


def parse_price(text):
    if not text:
        return None
    m = re.search(r"(\d[\d\s]*\d)\s*\u20ac", text)
    if m:
        s = re.sub(r"\s+", "", m.group(1))
        if s.isdigit() and 10000 < int(s) < 100000000:
            return int(s)
    return None


def parse_surface(text):
    if not text:
        return None
    m = re.search(r"([\d,]+)\s*m[\u00b22]", text, re.IGNORECASE)
    if m:
        v = float(m.group(1).replace(",", "."))
        if 5 < v < 10000:
            return v
    return None


def parse_rooms(text):
    if not text:
        return None
    m = re.search(r"(\d+)\s*pi[eè]ce", text, re.IGNORECASE)
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 30 else None


def parse_bedrooms(text):
    if not text:
        return None
    m = re.search(r"(\d+)\s*chambre", text, re.IGNORECASE)
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 20 else None


def parse_location(text):
    if not text:
        return None, None
    m = re.search(r"([A-Z\u00c0-\u00dc][a-z\u00e0-\u00fc\-\s]+?)\s*\((\d{5})\)", text)
    if m:
        return m.group(1).strip(), m.group(2)
    return None, None


def parse_type(text):
    if not text:
        return None
    for t in ["maison", "villa", "appartement", "loft", "duplex", "terrain", "studio"]:
        if t in text.lower():
            return t.capitalize()
    return None
