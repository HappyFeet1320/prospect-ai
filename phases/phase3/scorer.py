"""
Phase 3 — Moteur de scoring des entreprises.

Trois critères pondérés :
  1. Alignement sectoriel   (40 %) — correspondance NACE
  2. Proximité géographique (30 %) — distance haversine vs rayon cible
  3. Potentiel structurel   (30 %) — taille, forme juridique, ancienneté

Score global : 0.0 → 1.0
Seuil validation : ≥ 0.45 (fallback 0.35 si < 15 entreprises)
"""

from __future__ import annotations
from datetime import datetime

from .geo import min_distance_to_targets


# ============================================================
# Constantes de pondération
# ============================================================

WEIGHT_SECTORAL    = 0.40
WEIGHT_GEO         = 0.30
WEIGHT_STRUCTURAL  = 0.30


# ============================================================
# Critère 1 — Alignement sectoriel (40 %)
# ============================================================

def score_sectoral(company: dict, profile: dict) -> tuple[float, str]:
    """
    Compare le NACE cherché et les NACE du profil.

    Retourne (score 0-1, explication).
    """
    profile_nace_codes: list[dict] = profile.get("nace_codes", [])
    profile_codes = {n["code"]: n.get("weight", 0.5) for n in profile_nace_codes}

    nace_searched = company.get("nace_searched", "")
    nace_main     = company.get("nace_main", "")
    nace_list     = company.get("nace_list", [])  # liste éventuelle de NACE BCE

    # Priorité 1 — correspondance exacte sur le NACE utilisé pour la recherche
    if nace_searched and nace_searched in profile_codes:
        weight = profile_codes[nace_searched]
        score = 0.6 + weight * 0.4           # 0.60 → 1.00 selon le poids
        return round(min(score, 1.0), 3), f"NACE {nace_searched} exact (poids {int(weight*100)}%)"

    # Priorité 2 — correspondance sur le NACE principal de l'entreprise
    if nace_main and nace_main in profile_codes:
        weight = profile_codes[nace_main]
        score = 0.5 + weight * 0.3
        return round(min(score, 1.0), 3), f"NACE principal {nace_main} dans profil (poids {int(weight*100)}%)"

    # Priorité 3 — correspondance partielle (sous-branche = mêmes 3 premiers chiffres)
    for pc in profile_codes:
        for nc in [nace_searched, nace_main] + (nace_list or []):
            if nc and pc[:3] == nc[:3] and pc != nc:
                return 0.40, f"Sous-secteur proche ({nc} ~ {pc})"

    # Priorité 4 — secteur similaire (mêmes 2 premiers chiffres)
    for pc in profile_codes:
        for nc in [nace_searched, nace_main] + (nace_list or []):
            if nc and pc[:2] == nc[:2]:
                return 0.20, f"Secteur adjacent ({nc[:2]}xx)"

    return 0.0, "Aucune correspondance NACE"


# ============================================================
# Critère 2 — Proximité géographique (30 %)
# ============================================================

def score_geographic(company: dict, profile: dict) -> tuple[float, str]:
    """
    Calcule le score de proximité selon la distance minimale
    entre l'entreprise et les zones cibles de l'opérateur.
    """
    target_locations: list[dict] = profile.get("target_locations", [])
    radius_km: float = float(profile.get("search_radius_km", 30))

    if not target_locations:
        return 0.5, "Pas de zone cible définie"

    postal   = company.get("postal_code", "")
    city     = company.get("city", "")
    province = company.get("province", "")

    dist = min_distance_to_targets(postal, city, province, target_locations)

    if dist >= 9999:
        return 0.30, "Localisation inconnue"

    # Score selon distance vs rayon
    if dist <= radius_km * 0.25:
        score, label = 1.0, f"{dist:.0f} km — Zone cœur"
    elif dist <= radius_km * 0.60:
        score, label = 0.75, f"{dist:.0f} km — Zone proche"
    elif dist <= radius_km:
        score, label = 0.50, f"{dist:.0f} km — Dans le rayon"
    elif dist <= radius_km * 1.5:
        score, label = 0.25, f"{dist:.0f} km — Légèrement hors rayon"
    else:
        score, label = 0.0, f"{dist:.0f} km — Hors zone"

    return round(score, 3), label


# ============================================================
# Critère 3 — Potentiel structurel (30 %)
# ============================================================

_PREMIUM_FORMS = {
    "SA", "SRL", "SC", "NV", "BV",           # sociétés de capitaux
    "SE", "SCE",                               # sociétés européennes
    "ASBL", "AISBL", "VZW",                   # associations (selon secteur)
}
_MICRO_FORMS = {"SNC", "SCS", "VOF", "CommV"}

def score_structural(company: dict, profile: dict) -> tuple[float, str]:
    """
    Évalue le potentiel structurel de l'entreprise.

    Points attribués :
      +0.30 — ancienneté ≥ 5 ans
      +0.20 — forme juridique SA / SRL / NV / BV
      +0.20 — plusieurs codes NACE (diversité activité)
      +0.15 — effectif connu ≥ 10 personnes
      +0.15 — statut actif vérifié
    Plafond à 1.0.
    """
    score = 0.0
    reasons = []

    # Ancienneté
    creation_year = company.get("creation_year") or company.get("start_year")
    if creation_year:
        try:
            age = datetime.now().year - int(creation_year)
            if age >= 10:
                score += 0.30
                reasons.append(f"{age} ans d'existence")
            elif age >= 5:
                score += 0.20
                reasons.append(f"{age} ans d'existence")
            elif age >= 2:
                score += 0.10
                reasons.append(f"{age} ans (jeune)")
        except (ValueError, TypeError):
            pass

    # Forme juridique
    legal_form = (company.get("legal_form") or "").upper()
    if any(f in legal_form for f in _PREMIUM_FORMS):
        score += 0.20
        reasons.append(f"Forme {company.get('legal_form', '')}")
    elif any(f in legal_form for f in _MICRO_FORMS):
        score += 0.05
        reasons.append("Micro-entreprise")

    # Diversité NACE
    nace_list = company.get("nace_list") or []
    if len(nace_list) >= 3:
        score += 0.20
        reasons.append(f"{len(nace_list)} activités NACE")
    elif len(nace_list) == 2:
        score += 0.10
        reasons.append("2 activités NACE")

    # Effectif
    employees = company.get("employees") or company.get("staff_count")
    if employees:
        try:
            emp = int(employees)
            if emp >= 50:
                score += 0.20
                reasons.append(f"{emp} employés")
            elif emp >= 10:
                score += 0.15
                reasons.append(f"{emp} employés")
            elif emp >= 5:
                score += 0.05
                reasons.append(f"{emp} employés")
        except (ValueError, TypeError):
            pass

    # Statut actif
    status = (company.get("status") or "").lower()
    if status in ("actif", "active", "actieve"):
        score += 0.10
        reasons.append("Entreprise active")

    score = min(score, 1.0)
    explanation = " | ".join(reasons) if reasons else "Données structurelles insuffisantes"
    return round(score, 3), explanation


# ============================================================
# Score global
# ============================================================

def compute_score(company: dict, profile: dict) -> dict:
    """
    Calcule le score global (0.0–1.0) et le détail par critère.

    Retourne un dict :
    {
        "score": float,
        "sectoral_score": float, "sectoral_reason": str,
        "geo_score": float,      "geo_reason": str,
        "structural_score": float, "structural_reason": str,
        "stars": int (1-5),
    }
    """
    s_sec, r_sec = score_sectoral(company, profile)
    s_geo, r_geo = score_geographic(company, profile)
    s_str, r_str = score_structural(company, profile)

    global_score = round(
        s_sec * WEIGHT_SECTORAL +
        s_geo * WEIGHT_GEO      +
        s_str * WEIGHT_STRUCTURAL,
        4,
    )

    # Conversion score → étoiles (suggestion automatique, modifiable par l'opérateur)
    if global_score >= 0.80:
        stars = 5
    elif global_score >= 0.65:
        stars = 4
    elif global_score >= 0.50:
        stars = 3
    elif global_score >= 0.35:
        stars = 2
    else:
        stars = 1

    return {
        "score":              global_score,
        "sectoral_score":     s_sec,
        "sectoral_reason":    r_sec,
        "geo_score":          s_geo,
        "geo_reason":         r_geo,
        "structural_score":   s_str,
        "structural_reason":  r_str,
        "stars":              stars,
    }
