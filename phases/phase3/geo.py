"""
Module géographique — Coordonnées belges et calcul de distances.
Utilisé par le scoring Phase 3 pour la proximité géographique.
"""

import math

# ============================================================
# Table de référence : code postal belge → (latitude, longitude)
# ============================================================

POSTAL_COORDS: dict[str, tuple[float, float]] = {
    # --- Bruxelles-Capitale ---
    "1000": (50.8503, 4.3517), "1020": (50.8821, 4.3389), "1030": (50.8674, 4.3798),
    "1040": (50.8352, 4.3893), "1050": (50.8180, 4.3700), "1060": (50.8252, 4.3261),
    "1070": (50.8413, 4.3070), "1080": (50.8655, 4.3182), "1090": (50.8800, 4.3310),
    "1140": (50.8795, 4.4120), "1150": (50.8374, 4.4289), "1160": (50.8132, 4.4168),
    "1170": (50.7837, 4.4196), "1180": (50.7980, 4.3290), "1190": (50.8090, 4.3460),
    "1200": (50.8490, 4.4282), "1210": (50.8573, 4.3616),

    # --- Brabant wallon ---
    "1300": (50.7167, 4.6000), "1310": (50.7380, 4.6710), "1320": (50.6380, 4.7080),
    "1330": (50.6560, 4.5630), "1340": (50.6567, 4.5862), "1348": (50.6686, 4.6136),
    "1350": (50.5990, 4.7840), "1360": (50.5810, 4.8380), "1370": (50.5580, 4.8730),
    "1380": (50.6510, 4.4460), "1390": (50.6220, 4.5210), "1400": (50.5980, 4.3284),
    "1410": (50.7072, 4.3938), "1420": (50.6830, 4.3660), "1430": (50.6303, 4.3904),
    "1440": (50.5880, 4.5420), "1450": (50.5770, 4.7170), "1460": (50.5770, 4.6380),
    "1470": (50.5650, 4.5770), "1480": (50.5760, 4.4240), "1490": (50.6120, 4.4040),

    # --- Brabant flamand ---
    "1500": (50.8050, 4.0940), "1600": (50.8370, 4.1680), "1700": (50.9050, 4.2890),
    "1730": (50.9200, 4.2360), "1800": (50.9220, 4.3290), "1830": (50.9360, 4.2350),
    "1850": (50.9240, 4.3200), "1900": (50.8540, 4.5260), "1930": (50.8180, 4.5010),
    "1950": (50.8430, 4.4460), "1970": (50.8780, 4.4930), "1980": (50.8640, 4.5600),
    "1990": (50.8770, 4.5980),
    "3000": (50.8800, 4.7005), "3010": (50.8530, 4.6630), "3020": (50.8400, 4.6750),
    "3200": (50.9760, 4.9100), "3300": (50.9750, 4.9700),

    # --- Liège ---
    "4000": (50.6450, 5.5730), "4020": (50.6280, 5.5680), "4030": (50.6000, 5.6220),
    "4040": (50.6778, 5.6244), "4100": (50.5863, 5.4949), "4120": (50.5640, 5.5220),
    "4130": (50.5380, 5.5660), "4140": (50.5850, 5.6610), "4200": (50.5800, 5.3450),
    "4300": (50.6640, 5.2540), "4400": (50.5920, 5.3380), "4500": (50.6150, 5.2640),
    "4600": (50.7190, 5.6920), "4680": (50.7680, 5.7350), "4700": (50.7430, 6.0580),
    "4800": (50.5899, 5.8643), "4900": (50.5220, 5.9320), "4960": (50.4330, 5.9770),

    # --- Namur ---
    "5000": (50.4674, 4.8719), "5020": (50.4370, 4.8820), "5030": (50.5698, 4.7035),
    "5060": (50.4150, 4.7420), "5100": (50.4820, 4.8590), "5140": (50.5270, 4.8560),
    "5300": (50.4750, 4.9960), "5500": (50.2279, 4.9151), "5570": (49.9700, 5.0850),
    "5600": (50.3600, 4.5550),

    # --- Hainaut ---
    "6000": (50.4114, 4.4440), "6010": (50.4010, 4.4520), "6020": (50.4190, 4.4370),
    "6030": (50.4180, 4.4670), "6060": (50.4720, 4.4880), "6200": (50.4560, 4.5040),
    "6220": (50.4220, 4.5380), "6460": (50.1990, 4.2750),
    "7000": (50.4542, 3.9523), "7100": (50.4800, 4.0290), "7130": (50.4820, 4.1350),
    "7500": (50.6068, 3.3876), "7700": (50.7390, 3.2480), "7800": (50.7470, 3.9310),

    # --- Luxembourg belge ---
    "6600": (50.1200, 5.3830), "6700": (49.7350, 5.5770), "6800": (49.8898, 5.4134),
    "6900": (50.2278, 5.3302), "6980": (50.1510, 5.5610),

    # --- Anvers ---
    "2000": (51.2211, 4.3997), "2018": (51.2038, 4.4180), "2020": (51.2323, 4.4220),
    "2050": (51.2200, 4.3700), "2060": (51.2290, 4.3980), "2100": (51.2350, 4.4700),
    "2200": (51.2043, 4.5449), "2300": (51.1640, 4.7460), "2500": (51.1345, 4.4860),
    "2800": (51.0323, 4.4804), "2900": (51.2260, 4.5930),

    # --- Gand (Flandre orientale) ---
    "9000": (51.0543, 3.7174), "9030": (51.0500, 3.6600), "9040": (51.0700, 3.7700),
    "9050": (51.0150, 3.7180), "9100": (51.1060, 3.9920), "9200": (51.0280, 3.9730),
    "9300": (50.9350, 3.9760), "9400": (50.9490, 3.8340), "9600": (50.7990, 3.8870),
    "9700": (50.8500, 3.5800), "9800": (50.9060, 3.5770),

    # --- Bruges (Flandre occidentale) ---
    "8000": (51.2093, 3.2247), "8200": (51.1866, 3.2027), "8300": (51.3600, 3.3000),
    "8400": (51.2270, 2.9090), "8500": (50.8290, 3.2630), "8800": (50.9250, 3.1240),
    "8900": (50.8530, 2.8770),

    # --- Limbourg ---
    "3500": (50.9307, 5.3325), "3600": (50.8820, 5.4550), "3700": (50.7850, 5.6990),
    "3800": (50.8080, 5.2470), "3900": (50.9600, 5.5940),
}

# Centres géographiques des provinces belges (fallback si postal inconnu)
PROVINCE_CENTERS: dict[str, tuple[float, float]] = {
    "Bruxelles-Capitale":  (50.8503, 4.3517),
    "Brabant wallon":      (50.6500, 4.5500),
    "Brabant flamand":     (50.8800, 4.6000),
    "Anvers":              (51.2211, 4.3997),
    "Gand":                (51.0543, 3.7174),
    "Flandre orientale":   (50.9900, 3.8500),
    "Flandre occidentale": (51.0500, 3.2200),
    "Liège":               (50.6450, 5.5730),
    "Hainaut":             (50.4500, 4.0000),
    "Namur":               (50.4674, 4.8719),
    "Luxembourg":          (49.9000, 5.4500),
    "Limbourg":            (50.9307, 5.3325),
}


def get_coords(postal_code: str, city: str = "", province: str = "") -> tuple[float, float] | None:
    """
    Retourne les coordonnées (lat, lon) pour un code postal belge.
    Fallback sur la province puis None.
    """
    if postal_code:
        # Correspondance exacte
        coords = POSTAL_COORDS.get(postal_code)
        if coords:
            return coords
        # Correspondance par préfixe 3 chiffres
        prefix3 = postal_code[:3]
        for code, c in POSTAL_COORDS.items():
            if code.startswith(prefix3):
                return c
        # Correspondance par préfixe 2 chiffres
        prefix2 = postal_code[:2]
        for code, c in POSTAL_COORDS.items():
            if code.startswith(prefix2):
                return c

    if province:
        return PROVINCE_CENTERS.get(province)

    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance en km entre deux points géographiques (formule haversine)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def min_distance_to_targets(
    company_postal: str,
    company_city: str,
    company_province: str,
    target_locations: list[dict],
) -> float:
    """
    Retourne la distance minimale (en km) entre l'entreprise et
    l'une des zones cibles de l'opérateur.
    Retourne 9999 si les coordonnées sont introuvables.
    """
    company_coords = get_coords(company_postal, company_city, company_province)
    if not company_coords:
        return 9999.0

    min_dist = 9999.0
    for loc in target_locations:
        target_coords = get_coords(
            loc.get("postal_code", ""),
            loc.get("city", ""),
            loc.get("province", ""),
        )
        if target_coords:
            dist = haversine_km(
                company_coords[0], company_coords[1],
                target_coords[0], target_coords[1],
            )
            min_dist = min(min_dist, dist)

    return min_dist


def get_province_from_postal(postal: str) -> str:
    """Détermine la province belge à partir du code postal."""
    if not postal or not postal.isdigit():
        return "Inconnue"
    code = int(postal)
    if 1000 <= code <= 1299:
        return "Bruxelles-Capitale"
    elif 1300 <= code <= 1499:
        return "Brabant wallon"
    elif 1500 <= code <= 1999 or 3000 <= code <= 3499:
        return "Brabant flamand"
    elif 2000 <= code <= 2999:
        return "Anvers"
    elif 3500 <= code <= 3999:
        return "Limbourg"
    elif 4000 <= code <= 4999:
        return "Liège"
    elif 5000 <= code <= 5999:
        return "Namur"
    elif 6000 <= code <= 6599:
        return "Hainaut"
    elif 6600 <= code <= 6999:
        return "Luxembourg"
    elif 7000 <= code <= 7999:
        return "Hainaut"
    elif 8000 <= code <= 8999:
        return "Flandre occidentale"
    elif 9000 <= code <= 9999:
        return "Flandre orientale / Gand"
    return "Inconnue"
