"""
Phase 3 — Orchestration du scoring.

Charge les entreprises Phase 2 depuis la DB, applique le scorer,
sauvegarde les résultats et sélectionne les top entreprises.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select

from config.settings import settings
from database.connection import get_session
from database.models import Company, Session as DbSession

from .scorer import compute_score


# ============================================================
# Structures de données
# ============================================================

@dataclass
class Phase3Result:
    session_id:         str
    total_scored:       int
    selected_count:     int
    threshold_used:     float
    companies:          list[dict] = field(default_factory=list)  # triées par score desc
    warnings:           list[str]  = field(default_factory=list)


# ============================================================
# Scoring principal
# ============================================================

def run_phase3(
    session_id: str,
    profile: dict,
    progress_callback=None,
) -> Phase3Result:
    """
    Score toutes les entreprises Phase 2 de la session.

    Args:
        session_id:        ID de session.
        profile:           Profil opérateur (Phase 1).
        progress_callback: fn(current: int, total: int) appelée pendant le scoring.

    Returns:
        Phase3Result avec toutes les entreprises scorées et la sélection.
    """
    warnings = []

    with get_session() as db:
        # Charger les entreprises Phase 2
        stmt = select(Company).where(Company.session_id == session_id)
        companies_db: list[Company] = list(db.execute(stmt).scalars().all())

    total = len(companies_db)
    if total == 0:
        logger.warning("Phase 3 : aucune entreprise en base pour session {}", session_id)
        return Phase3Result(
            session_id=session_id,
            total_scored=0,
            selected_count=0,
            threshold_used=settings.PHASE3_MIN_SCORE,
            warnings=["Aucune entreprise trouvée — relancez d'abord la Phase 2."],
        )

    logger.info("Phase 3 démarrée — {} entreprises à scorer", total)

    # --------------------------------------------------------
    # Scoring
    # --------------------------------------------------------
    scored_companies: list[dict] = []

    for i, company_db in enumerate(companies_db):
        company_data = company_db.phase2_data
        company_data["company_id"] = company_db.company_id
        company_data["bce_number"] = company_db.bce_number or ""

        detail = compute_score(company_data, profile)

        scored_companies.append({
            **company_data,
            "phase3_score":         detail["score"],
            "phase3_score_detail":  detail,
            "operator_rating":      company_db.operator_rating,
            "is_phase3_selected":   False,  # sera mis à jour après tri
        })

        if progress_callback:
            progress_callback(i + 1, total)

    # Trier par score décroissant
    scored_companies.sort(key=lambda c: c["phase3_score"], reverse=True)

    # --------------------------------------------------------
    # Sélection selon seuil
    # --------------------------------------------------------
    target     = settings.PHASE3_TARGET_COMPANIES
    threshold  = settings.PHASE3_MIN_SCORE
    fallback   = settings.PHASE3_MIN_SCORE_FALLBACK

    selected = [c for c in scored_companies if c["phase3_score"] >= threshold]

    if len(selected) < 30 and len(scored_companies) > 0:
        # Seuil de repli
        selected = [c for c in scored_companies if c["phase3_score"] >= fallback]
        threshold = fallback
        if len(selected) < 30:
            warnings.append(
                f"Seulement {len(selected)} entreprises dépassent le seuil de repli "
                f"({int(fallback*100)}%). Envisagez d'élargir votre profil ou la zone géographique."
            )
        else:
            warnings.append(
                f"Seuil abaissé à {int(fallback*100)}% (seulement {len(selected)} entreprises "
                f"au-dessus de {int(settings.PHASE3_MIN_SCORE*100)}%)."
            )

    # Limiter au nombre cible
    selected_top = selected[:target]
    selected_ids = {c["company_id"] for c in selected_top}

    # Marquer la sélection
    for c in scored_companies:
        c["is_phase3_selected"] = c["company_id"] in selected_ids

    if len(selected_top) < 20:
        warnings.append(
            f"Seulement {len(selected_top)} entreprises sélectionnées (objectif 100). "
            "Essayez d'utiliser plus de codes NACE ou d'élargir la zone géographique."
        )

    logger.info(
        "Phase 3 scoring terminé — {}/{} sélectionnées (seuil {:.0%})",
        len(selected_top), total, threshold,
    )

    # --------------------------------------------------------
    # Sauvegarde en base
    # --------------------------------------------------------
    _save_to_database(scored_companies)

    return Phase3Result(
        session_id=session_id,
        total_scored=total,
        selected_count=len(selected_top),
        threshold_used=threshold,
        companies=scored_companies,
        warnings=warnings,
    )


def _save_to_database(scored_companies: list[dict]) -> None:
    """Persiste scores et sélection dans la table companies."""
    with get_session() as db:
        for c in scored_companies:
            company_db = db.get(Company, c["company_id"])
            if company_db:
                company_db.phase3_score        = c["phase3_score"]
                company_db.phase3_score_detail = c["phase3_score_detail"]
                company_db.is_phase3_selected  = c["is_phase3_selected"]
        db.commit()

    logger.success("Phase 3 DB : {} entreprises sauvegardées", len(scored_companies))


# ============================================================
# Mise à jour de la notation opérateur
# ============================================================

def update_operator_rating(company_id: str, rating: int | None, selected: bool) -> None:
    """
    Met à jour la notation (étoiles 1-5) et la sélection manuelle.
    Appelé depuis l'UI quand l'opérateur clique.
    """
    with get_session() as db:
        company_db = db.get(Company, company_id)
        if company_db:
            company_db.operator_rating    = rating
            company_db.is_phase3_selected = selected
            db.commit()


def validate_phase3(session_id: str) -> None:
    """
    Marque la Phase 3 comme validée dans la session DB.
    """
    with get_session() as db:
        session_db = db.get(DbSession, session_id)
        if session_db:
            session_db.p3_validated  = True
            session_db.current_phase = 4
            db.commit()

    logger.info("Phase 3 validée — session {}", session_id)


# ============================================================
# Rechargement depuis la DB (pour l'UI après refresh)
# ============================================================

def load_phase3_results(session_id: str) -> list[dict]:
    """
    Recharge les résultats Phase 3 depuis la DB.
    Retourne une liste triée par score décroissant.
    """
    with get_session() as db:
        stmt = (
            select(Company)
            .where(Company.session_id == session_id)
            .where(Company.phase3_score.isnot(None))
        )
        companies_db = list(db.execute(stmt).scalars().all())

    result = []
    for c in companies_db:
        data = c.phase2_data
        result.append({
            **data,
            "company_id":        c.company_id,
            "bce_number":        c.bce_number or "",
            "phase3_score":      c.phase3_score or 0.0,
            "phase3_score_detail": c.phase3_score_detail,
            "is_phase3_selected": c.is_phase3_selected,
            "operator_rating":   c.operator_rating,
        })

    result.sort(key=lambda c: c["phase3_score"], reverse=True)
    return result
