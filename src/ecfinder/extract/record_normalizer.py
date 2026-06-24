"""Normalize common PFAS names and abbreviations."""

from __future__ import annotations


PFAS_ALIASES = {
    "PFOA": "perfluorooctanoic acid",
    "PFOS": "perfluorooctanesulfonic acid",
    "PFHxA": "perfluorohexanoic acid",
    "PFHxS": "perfluorohexanesulfonic acid",
    "PFBA": "perfluorobutanoic acid",
    "PFBS": "perfluorobutanesulfonic acid",
    "FOSA": "perfluorooctane sulfonamide",
    "6:2 FTOH": "6:2 fluorotelomer alcohol",
    "8:2 FTOH": "8:2 fluorotelomer alcohol",
}


def normalize_name(name: str | None) -> dict:
    if not name:
        return {"input": name, "canonical": None, "aliases": [], "confidence": 0.0}
    stripped = name.strip()
    canonical = PFAS_ALIASES.get(stripped.upper(), PFAS_ALIASES.get(stripped, stripped))
    aliases = [key for key, value in PFAS_ALIASES.items() if value == canonical and key != stripped]
    return {"input": name, "canonical": canonical, "aliases": aliases, "confidence": 0.9 if canonical != stripped else 0.7}
