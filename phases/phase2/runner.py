"""
Phase 2 — Runner d'orchestration BCE.
Coordonne la recherche sur tous les codes NACE du profil,
déduplique les résultats et sauvegarde en base de données.
"""

import random
from dataclasses import dataclass, field
from loguru import logger

from database.connection import get_session as get_db
from database.models import Session as DbSession, Company
from .bce_client import search_by_nace, generate_mock_companies


# ============================================================
# Structure de résultat Phase 2
# ============================================================

@dataclass
class Phase2Result:
    """Résultat complet de la Phase 2."""
    total_companies: int = 0
    companies_by_nace: dict = field(default_factory=dict)
    companies_by_province: dict = field(default_factory=dict)
    unique_companies: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ============================================================
# Runner principal
# ============================================================

def run_phase2(
    session_id: str,
    profile: dict,
    use_mock: bool = False,
    nace_progress_callback=None,
) -> Phase2Result:
    """
    Exécute la Phase 2 : recherche BCE pour tous les codes NACE du profil.

    Args:
        session_id: ID de la session en cours
        profile: Fiche profil Phase 1 (dict)
        use_mock: Utiliser des données fictives au lieu de la vraie BCE
        nace_progress_callback:
            fn(nace_code, found, total, pct, status)
            status = "running" | "done" | "error"

    Returns:
        Phase2Result avec statistiques et liste des entreprises uniques
    """
    result = Phase2Result()
    all_companies: dict[str, dict] = {}  # bce_number → company (déduplication)

    nace_codes: list[dict] = profile.get("nace_codes", [])
    target_locations: list[dict] = profile.get("target_locations", [])
    max_per_nace: int = 500

    logger.info(
        f"Phase 2 démarrée — {len(nace_codes)} codes NACE, "
        f"mock={'oui' if use_mock else 'non'}"
    )

    for i, nace_item in enumerate(nace_codes):
        nace_code = nace_item.get("code", "").strip()
        weight = nace_item.get("weight", 0.5)
        label = nace_item.get("label", "")

        if not nace_code:
            continue

        # Notifier : démarrage de ce code NACE
        if nace_progress_callback:
            nace_progress_callback(nace_code, 0, 0, 0.0, "running")

        logger.info(f"Recherche [{i+1}/{len(nace_codes)}] NACE={nace_code} — {label}")

        companies = []
        try:
            if use_mock:
                mock_count = random.randint(25, 65)
                companies = generate_mock_companies(
                    nace_code, target_locations, count=mock_count
                )
            else:
                def on_page(found, total):
                    pct = min(found / max(total, 1), 0.99)
                    if nace_progress_callback:
                        nace_progress_callback(nace_code, found, total, pct, "running")

                companies = search_by_nace(
                    nace_code,
                    max_results=max_per_nace,
                    progress_callback=on_page,
                )

        except Exception as e:
            logger.error(f"Erreur recherche NACE={nace_code}: {e}")
            result.warnings.append(f"NACE {nace_code} : erreur de recherche ({e})")
            if nace_progress_callback:
                nace_progress_callback(nace_code, 0, 0, 0.0, "error")
            continue

        # Enrichir chaque entreprise avec le poids NACE
        for company in companies:
            company["nace_weight"] = weight
            company["nace_label"] = label

        # Déduplication par numéro BCE
        new_added = 0
        for company in companies:
            bce = company.get("bce_number", "")
            if bce and bce not in all_companies:
                all_companies[bce] = company
                new_added += 1

        result.companies_by_nace[nace_code] = {
            "label": label,
            "weight": weight,
            "found": len(companies),
            "new_unique": new_added,
        }

        logger.info(
            f"NACE={nace_code} → {len(companies)} trouvées, "
            f"{new_added} nouvelles uniques"
        )

        # Notifier : terminé
        if nace_progress_callback:
            nace_progress_callback(nace_code, len(companies), len(companies), 1.0, "done")

    # --------------------------------------------------------
    # Agrégation finale
    # --------------------------------------------------------
    result.unique_companies = list(all_companies.values())
    result.total_companies = len(result.unique_companies)

    # Statistiques géographiques
    for company in result.unique_companies:
        province = company.get("province") or company.get("city") or "Inconnue"
        result.companies_by_province[province] = (
            result.companies_by_province.get(province, 0) + 1
        )

    # Avertissements volume
    if result.total_companies < 20:
        result.warnings.append(
            f"Seulement {result.total_companies} entreprises trouvées. "
            "Pensez à élargir les codes NACE ou le rayon géographique."
        )
    elif result.total_companies > 500:
        result.warnings.append(
            f"{result.total_companies} entreprises trouvées (> 500). "
            "Des pré-filtres automatiques seront appliqués en Phase 3."
        )

    logger.success(
        f"Phase 2 terminée — {result.total_companies} entreprises uniques"
    )

    # Sauvegarde en base
    _save_to_database(session_id, result)

    return result


# ============================================================
# Sauvegarde en base de données
# ============================================================

def _save_to_database(session_id: str, result: Phase2Result) -> None:
    """Supprime les anciens résultats et sauvegarde les nouveaux en base."""
    try:
        with get_db() as db:
            # Supprimer les anciennes entreprises Phase 2 de cette session
            old = db.query(Company).filter(
                Company.session_id == session_id
            ).all()
            for c in old:
                db.delete(c)
            db.flush()

            # Insérer les nouvelles entreprises
            for company_data in result.unique_companies:
                company = Company(
                    session_id=session_id,
                    bce_number=company_data.get("bce_number", ""),
                )
                company.phase2_data = company_data
                db.add(company)

            db.commit()

        logger.success(
            f"Phase 2 DB : {len(result.unique_companies)} entreprises sauvegardées"
        )

    except Exception as e:
        logger.error(f"Erreur sauvegarde Phase 2 : {e}")


def validate_phase2(session_id: str) -> None:
    """Marque la Phase 2 comme validée et passe à la Phase 3."""
    with get_db() as db:
        session_obj = db.get(DbSession, session_id)
        if session_obj:
            session_obj.p2_validated = True
            session_obj.current_phase = 3
            db.commit()
    logger.info(f"Phase 2 validée — session {session_id[:8]}")
