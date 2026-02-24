"""
Client BCE/KBO — Banque-Carrefour des Entreprises belge.

Source des données : KBO Open Data (CSV officiels).
Pas de scraping — données 100 % officielles et fiables.

Mode réel  : lecture de l'index SQLite construit depuis les CSV KBO
Mode mock  : données fictives pour tests uniquement
"""

import re
import random
from loguru import logger

from .kbo_reader import (
    is_index_built,
    search_by_nace as _kbo_search,
    get_index_stats,
)


# ============================================================
# Test de disponibilité
# ============================================================

def test_bce_connection() -> tuple[bool, str]:
    """
    Vérifie si l'index KBO est disponible.
    Retourne (ok: bool, message: str).
    """
    if not is_index_built():
        return False, "Index KBO non construit — cliquez sur 'Construire l'index KBO'"
    stats = get_index_stats()
    return True, (
        f"Index KBO prêt — {stats['nb_enterprises']:,} entreprises, "
        f"{stats['nb_distinct_nace']:,} codes NACE ({stats['size_mb']} MB)"
    )


# ============================================================
# Recherche réelle KBO Open Data
# ============================================================

def search_by_nace(
    nace_code: str,
    max_results: int = 500,
    progress_callback=None,
) -> list[dict]:
    """
    Recherche des entreprises actives par code NACE depuis l'index KBO.

    Args:
        nace_code:        Code NACE (ex: "6201")
        max_results:      Résultats maximum
        progress_callback: fn(found, total) — appelé une fois après la recherche

    Returns:
        Liste de dicts entreprises (réelles, depuis KBO Open Data).
    """
    if not is_index_built():
        raise RuntimeError(
            "L'index KBO n'est pas construit. "
            "Lancez la construction depuis la page Phase 2."
        )

    logger.info("KBO Open Data — recherche NACE={}", nace_code)

    companies = _kbo_search(nace_code, max_results=max_results)

    if progress_callback:
        progress_callback(len(companies), len(companies))

    logger.info("KBO NACE={} → {} entreprises trouvées", nace_code, len(companies))
    return companies


# ============================================================
# Mode Mock — Données fictives (tests uniquement)
# ============================================================

_MOCK_LOCATIONS = [
    ("Bruxelles",        "1000", "Bruxelles-Capitale"),
    ("Ixelles",          "1050", "Bruxelles-Capitale"),
    ("Anderlecht",       "1070", "Bruxelles-Capitale"),
    ("Etterbeek",        "1040", "Bruxelles-Capitale"),
    ("Schaerbeek",       "1030", "Bruxelles-Capitale"),
    ("Liège",            "4000", "Liège"),
    ("Seraing",          "4100", "Liège"),
    ("Herstal",          "4040", "Liège"),
    ("Verviers",         "4800", "Liège"),
    ("Namur",            "5000", "Namur"),
    ("Charleroi",        "6000", "Hainaut"),
    ("Mons",             "7000", "Hainaut"),
    ("Wavre",            "1300", "Brabant wallon"),
    ("Braine-l'Alleud",  "1420", "Brabant wallon"),
    ("Waterloo",         "1410", "Brabant wallon"),
    ("Louvain-la-Neuve", "1348", "Brabant wallon"),
    ("Nivelles",         "1400", "Brabant wallon"),
    ("Gand",             "9000", "Flandre orientale"),
    ("Anvers",           "2000", "Anvers"),
    ("Bruges",           "8000", "Flandre occidentale"),
    ("Louvain",          "3000", "Brabant flamand"),
]

_MOCK_NAMES: dict[str, list[str]] = {
    "62": ["TechSolutions", "DevCorp", "CodeFactory", "DigitalPro", "SoftBel"],
    "63": ["DataCenter", "InfoServices", "HostingPro", "CloudBase"],
    "70": ["BusinessConsult", "ManagePro", "Strategia", "CorporateAdvisory"],
    "71": ["ArchiDesign", "EnginBel", "TechBuild", "DesignBureau"],
    "25": ["MetalWorks", "SteelCraft", "FabricMetal", "MetalPro", "SoudurePro"],
    "26": ["ElectroPro", "TechElec", "ComponentsTech", "CircuitPro"],
    "28": ["MachineWorks", "IndusMach", "TechMachine", "MecaPro"],
    "41": ["ConstructionPlus", "BuildPro", "ImmoConstruct", "ConstructionBel"],
    "43": ["ElecInstall", "PlomberiePro", "TechInstall", "FinishPro"],
    "46": ["TradeB2B", "CommerceGros", "TradePro", "DistribBel"],
    "47": ["RetailPro", "ShopBel", "RetailBel", "MagasinPro"],
    "49": ["LogisTrans", "TransportBel", "LogiPro", "FreightBel"],
    "56": ["RestoGroup", "FoodBel", "CuisinePro", "CateringBel"],
    "68": ["ImmoPro", "EstateManage", "ImmoBel", "PropertyBel"],
    "69": ["LexPro", "JuridConsult", "LawBel", "ComptaServices"],
    "72": ["ResearchBel", "LaboPro", "R&D Consult", "InnovateBel"],
    "73": ["AdPro", "MarketingBel", "PubAgency", "BrandBel"],
    "74": ["DesignBel", "CreativePro", "PhotoBel", "DesignStudio"],
    "78": ["HRPro", "RecrutBel", "TalentBel", "StaffPro"],
    "81": ["CleanBel", "FacilityPro", "MaintenanceBel", "CleanServices"],
    "85": ["EduBel", "FormationPro", "TrainingBel", "EcoleFormation"],
    "86": ["SantéBel", "ClinicPro", "MedServices", "CabinetMed"],
    "88": ["SocialBel", "ActionSociale", "CentreSocial", "AidePro"],
}

_LEGAL_FORMS = ["SA", "SRL", "SPRL", "SCRL", "ASBL", "SNC", "SE", "NV", "BV", "VZW"]
_STREETS = [
    "rue de la Paix", "avenue Louise", "boulevard du Roi",
    "rue de l'Industrie", "chaussée de Mons", "rue des Entrepreneurs",
    "avenue des Arts", "rue du Commerce", "rue de la Science",
    "boulevard de Waterloo",
]


def generate_mock_companies(
    nace_code: str,
    target_locations: list[dict],
    count: int = 40,
) -> list[dict]:
    """
    Génère des entreprises fictives pour tester le pipeline.
    ⚠️  Les entreprises générées N'EXISTENT PAS dans la réalité.
    """
    rng      = random.Random(hash(nace_code) & 0xFFFFFFFF)
    division = nace_code[:2]
    names    = _MOCK_NAMES.get(division, ["BelgianCo", "EntrepriseBel", "SociétéBel"])

    companies = []
    for _ in range(count):
        if target_locations and rng.random() < 0.6:
            loc      = rng.choice(target_locations)
            city     = loc.get("city", "Bruxelles")
            postal   = loc.get("postal_code", "1000")
            province = loc.get("province", "Bruxelles-Capitale")
        else:
            city, postal, province = rng.choice(_MOCK_LOCATIONS)

        bce        = f"0{rng.randint(100,999)}.{rng.randint(100,999)}.{rng.randint(100,999)}"
        legal_form = rng.choice(_LEGAL_FORMS)
        name       = rng.choice(names)
        suffix     = rng.choice(["", " Group", " Belgique", f" {rng.randint(1,99)}"])
        denomination = f"{name}{suffix} {legal_form}"

        nace_declared = [nace_code]
        if rng.random() < 0.35:
            try:
                sec = str(int(nace_code) + rng.choice([-2, -1, 1, 2])).zfill(4)
                nace_declared.append(sec)
            except ValueError:
                pass

        companies.append({
            "bce_number":          bce,
            "denomination":        denomination,
            "legal_form":          legal_form,
            "address_raw":         f"{rng.randint(1,200)}, {rng.choice(_STREETS)}, {postal} {city}",
            "postal_code":         postal,
            "city":                city,
            "province":            province,
            "creation_year":       2026 - rng.randint(1, 35),
            "nace_codes_declared": nace_declared,
            "nace_searched":       nace_code,
            "status":              "active",
            "source":              "mock_data",
        })

    return companies
