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
from .bce_client import search_by_nace_list, generate_mock_companies
from .cbeapi_client import search_by_postal_codes as _cbeapi_search


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
    source: str = "kbo",
    cbeapi_max_pages: int = 5,
    nace_progress_callback=None,
) -> Phase2Result:
    """
    Exécute la Phase 2 : recherche BCE pour tous les codes NACE du profil.

    Args:
        session_id: ID de la session en cours
        profile: Fiche profil Phase 1 (dict)
        source: Source des données —
            "kbo"     → KBO Open Data (index SQLite local, recommandé)
            "cbe_api" → CBE API en ligne (données fraîches + coordonnées)
            "mock"    → Données fictives (tests uniquement)
        cbeapi_max_pages: Pages max par code postal pour CBE API (défaut 5 = ~30s/postal)
        nace_progress_callback:
            fn(nace_code, found, total, pct, status)
            status = "running" | "done" | "error"

    Returns:
        Phase2Result avec statistiques et liste des entreprises uniques
    """
    result = Phase2Result()
    all_companies: dict[str, dict] = {}  # bce_number → company

    nace_codes: list[dict] = profile.get("nace_codes", [])
    target_locations: list[dict] = profile.get("target_locations", [])

    logger.info(
        f"Phase 2 démarrée — {len(nace_codes)} codes NACE, source={source}"
    )

    use_mock = source == "mock"

    if use_mock:
        # ── Mode mock : boucle code par code ──────────────────────────────────
        for i, nace_item in enumerate(nace_codes):
            nace_code = nace_item.get("code", "").strip()
            weight    = nace_item.get("weight", 0.5)
            label     = nace_item.get("label", "")
            if not nace_code:
                continue

            if nace_progress_callback:
                nace_progress_callback(nace_code, 0, 0, 0.0, "running")

            try:
                companies = generate_mock_companies(
                    nace_code, target_locations, count=random.randint(25, 65)
                )
            except Exception as e:
                logger.error(f"Erreur mock NACE={nace_code}: {e}")
                result.warnings.append(f"NACE {nace_code} : erreur mock ({e})")
                if nace_progress_callback:
                    nace_progress_callback(nace_code, 0, 0, 0.0, "error")
                continue

            for company in companies:
                company["nace_weight"] = weight
                company["nace_label"]  = label

            new_added = 0
            for company in companies:
                bce = company.get("bce_number", "")
                if bce and bce not in all_companies:
                    company["matched_nace_codes"] = [nace_code]
                    all_companies[bce] = company
                    new_added += 1
                elif bce:
                    mcodes = all_companies[bce].setdefault("matched_nace_codes", [nace_code])
                    if nace_code not in mcodes:
                        mcodes.append(nace_code)

            result.companies_by_nace[nace_code] = {
                "label": label, "weight": weight,
                "found": len(companies), "new_unique": new_added,
            }
            if nace_progress_callback:
                nace_progress_callback(nace_code, len(companies), len(companies), 1.0, "done")

    elif source == "cbe_api":
        # ── CBE API : recherche par codes postaux + filtre NACE local ─────────
        nace_code_list = [n.get("code", "").strip() for n in nace_codes if n.get("code", "").strip()]
        postal_codes   = [loc.get("postal_code", "").strip() for loc in target_locations if loc.get("postal_code", "")]

        # Initialiser les stats
        for nace_item in nace_codes:
            code = nace_item.get("code", "").strip()
            if code:
                result.companies_by_nace[code] = {
                    "label": nace_item.get("label", ""),
                    "weight": nace_item.get("weight", 0),
                    "found": 0, "new_unique": 0,
                }

        if not postal_codes:
            result.warnings.append(
                "Aucun code postal dans le profil. "
                "La CBE API recherche par code postal — ajoutez une zone cible en Phase 1."
            )
        else:
            if nace_progress_callback:
                nace_progress_callback("__batch__", 0, 0, 0.0, "running")

            def _cbeapi_progress(found: int, total: int):
                if nace_progress_callback:
                    nace_progress_callback("__batch__", found, total, min(found / max(total, 1), 1.0), "running")

            try:
                batch = _cbeapi_search(
                    postal_codes, nace_code_list,
                    max_results=2000,
                    max_pages_per_postal=cbeapi_max_pages,
                    progress_callback=_cbeapi_progress,
                )

                for company in batch:
                    bce = company.get("bce_number", "")
                    if bce:
                        all_companies[bce] = company

                # Stats par code NACE
                for company in all_companies.values():
                    for code in company.get("matched_nace_codes", []):
                        if code in result.companies_by_nace:
                            result.companies_by_nace[code]["found"]     += 1
                            result.companies_by_nace[code]["new_unique"] += 1

                if nace_progress_callback:
                    nace_progress_callback("__batch__", len(all_companies), len(all_companies), 1.0, "done")
                logger.success(f"CBE API terminée — {len(all_companies)} entreprises uniques")

            except Exception as e:
                logger.error(f"Erreur CBE API: {e}")
                result.warnings.append(f"Erreur CBE API : {e}")
                if nace_progress_callback:
                    nace_progress_callback("__batch__", 0, 0, 0.0, "error")

    else:
        # ── Mode réel KBO : UNE SEULE requête batch pour tous les codes NACE ──
        nace_code_list = [n.get("code", "").strip() for n in nace_codes if n.get("code", "").strip()]

        # Initialiser les stats pour tous les codes (y compris ceux à 0 résultat)
        for nace_item in nace_codes:
            code = nace_item.get("code", "").strip()
            if code:
                result.companies_by_nace[code] = {
                    "label": nace_item.get("label", ""),
                    "weight": nace_item.get("weight", 0),
                    "found": 0, "new_unique": 0,
                }

        if nace_progress_callback:
            nace_progress_callback("__batch__", 0, 0, 0.0, "running")

        try:
            batch = search_by_nace_list(nace_code_list, max_results=2000)

            for company in batch:
                bce = company.get("bce_number", "")
                if bce:
                    all_companies[bce] = company

            # Calculer les stats par code à partir des résultats batch
            for company in all_companies.values():
                for code in company.get("matched_nace_codes", []):
                    if code in result.companies_by_nace:
                        result.companies_by_nace[code]["found"]     += 1
                        result.companies_by_nace[code]["new_unique"] += 1

            if nace_progress_callback:
                nace_progress_callback(
                    "__batch__", len(all_companies), len(all_companies), 1.0, "done"
                )
            logger.success(f"Batch KBO terminé — {len(all_companies)} entreprises uniques")

        except Exception as e:
            logger.error(f"Erreur recherche batch KBO: {e}")
            result.warnings.append(f"Erreur de recherche KBO : {e}")
            if nace_progress_callback:
                nace_progress_callback("__batch__", 0, 0, 0.0, "error")

    # --------------------------------------------------------
    # Agrégation finale
    # --------------------------------------------------------
    result.unique_companies = list(all_companies.values())
    result.total_companies  = len(result.unique_companies)

    # Garantir matched_nace_count cohérent pour toutes les entreprises
    for company in result.unique_companies:
        codes = company.get("matched_nace_codes", [])
        company["matched_nace_count"] = len(codes)

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
