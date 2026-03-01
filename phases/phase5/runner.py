"""
Phase 5 — Orchestration de la génération des kits de préparation.

Charge les entreprises sélectionnées (notation ≥ 3 en Phase 4),
génère un kit LLM par entreprise, et sauvegarde en base (PreparationKit).
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select

from database.connection import get_session
from database.models import Company, PreparationKit, Session as DbSession

from .generator import generate_kit


# ============================================================
# Structures de données
# ============================================================

@dataclass
class Phase5Result:
    session_id:      str
    total_companies: int
    generated_count: int
    failed_count:    int
    companies:       list[dict] = field(default_factory=list)
    warnings:        list[str]  = field(default_factory=list)


# ============================================================
# Orchestration principale
# ============================================================

def run_phase5(
    session_id: str,
    profile: dict,
    progress_callback=None,
) -> Phase5Result:
    """
    Génère les kits de préparation pour les entreprises sélectionnées en Phase 4.

    Args:
        session_id:        ID de session.
        profile:           Profil opérateur (Phase 1).
        progress_callback: fn(company_name, current, total, status)
                           status = 'running' | 'done' | 'error'

    Returns:
        Phase5Result avec la liste des entreprises et leurs kits.
    """
    warnings: list[str] = []

    # ── Charger les entreprises éligibles ────────────────────
    # Eligible = toutes les entreprises enrichies en Phase 4
    with get_session() as db:
        stmt = (
            select(Company)
            .where(Company.session_id == session_id)
            .where(Company.phase4_data_json.isnot(None))
        )
        companies_db: list[Company] = list(db.execute(stmt).scalars().all())

    total = len(companies_db)
    if total == 0:
        return Phase5Result(
            session_id=session_id,
            total_companies=0,
            generated_count=0,
            failed_count=0,
            warnings=[
                "Aucune entreprise enrichie trouvée pour la Phase 5. "
                "Lancez d'abord l'enrichissement en Phase 4."
            ],
        )

    logger.info("Phase 5 démarrée — {} entreprises à traiter", total)

    generated: list[dict] = []
    failed = 0

    for i, company_db in enumerate(companies_db):
        company_data = company_db.phase2_data
        company_data["company_id"]    = company_db.company_id
        company_data["bce_number"]    = company_db.bce_number or ""
        company_data["phase3_score"]  = company_db.phase3_score or 0.0
        company_data["phase4_dossier"] = company_db.phase4_data
        company_data["operator_rating"] = company_db.operator_rating
        company_data["operator_notes"]  = company_db.operator_notes or ""

        name = company_data.get("denomination", f"Entreprise {i+1}")

        if progress_callback:
            progress_callback(name, i, total, "running")

        try:
            kit = generate_kit(company_data, profile)
            _save_kit(company_db.company_id, kit)

            company_data["phase5_kit"] = kit
            generated.append(company_data)

            if progress_callback:
                progress_callback(name, i + 1, total, "done")

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Phase 5 — erreur kit {} :\n{}", name[:40], tb)
            failed += 1
            # Message d'erreur complet pour le débogage
            error_type = type(e).__name__
            error_msg  = str(e)[:300]
            warnings.append(
                f"Échec kit « {name[:50]} » — {error_type}: {error_msg}"
            )
            if progress_callback:
                progress_callback(name, i + 1, total, "error")

        if i < total - 1:
            # Pause entre kits : limite Groq ≈ 6 000 tokens/min sur tier gratuit
            time.sleep(5.0)

    if failed > 0:
        warnings.append(f"{failed} kit(s) n'ont pas pu être générés.")

    logger.success(
        "Phase 5 terminée — {}/{} kits générés, {} échecs",
        len(generated), total, failed,
    )

    return Phase5Result(
        session_id=session_id,
        total_companies=total,
        generated_count=len(generated),
        failed_count=failed,
        companies=generated,
        warnings=warnings,
    )


def _save_kit(company_id: str, kit: dict) -> None:
    """Persiste le kit de préparation dans la table preparation_kits."""
    with get_session() as db:
        existing = db.execute(
            select(PreparationKit).where(PreparationKit.company_id == company_id)
        ).scalar_one_or_none()

        if existing:
            prep = existing
        else:
            prep = PreparationKit(company_id=company_id)
            db.add(prep)

        prep.message_variants      = kit.get("message_variants", [])
        prep.ambiguous_situations  = kit.get("ambiguous_situations", [])
        prep.questions_to_ask      = kit.get("questions_to_ask", [])
        prep.risk_flags            = kit.get("risk_flags", [])
        prep.executive_summary     = kit.get("executive_summary", "")

        db.commit()

    logger.debug("Phase 5 — kit sauvegardé pour {}", company_id[:8])


# ============================================================
# Validation Phase 5
# ============================================================

def validate_phase5(session_id: str) -> None:
    """Marque Phase 5 comme validée."""
    with get_session() as db:
        session_db = db.get(DbSession, session_id)
        if session_db:
            session_db.p5_validated  = True
            session_db.current_phase = 5
            session_db.status        = "completed"
            db.commit()
    logger.info("Phase 5 validée — session {} terminée", session_id)


# ============================================================
# Chargement depuis la DB
# ============================================================

def load_phase5_results(session_id: str) -> list[dict]:
    """
    Recharge les kits Phase 5 depuis la DB.
    Retourne les entreprises avec kit, triées par score décroissant.
    """
    results = []

    with get_session() as db:
        stmt = (
            select(Company)
            .where(Company.session_id == session_id)
            .where(Company.phase4_data_json.isnot(None))
        )
        companies_db = list(db.execute(stmt).scalars().all())

        # Accès à la relation preparation_kit DANS la session pour éviter
        # le DetachedInstanceError (lazy-load impossible hors session)
        for c in companies_db:
            kit_obj = c.preparation_kit
            data    = c.phase2_data
            results.append({
                **data,
                "company_id":      c.company_id,
                "bce_number":      c.bce_number or "",
                "phase3_score":    c.phase3_score or 0.0,
                "phase4_dossier":  c.phase4_data,
                "operator_rating": c.operator_rating,
                "operator_notes":  c.operator_notes or "",
                "phase5_kit": {
                    "message_variants":     kit_obj.message_variants     if kit_obj else [],
                    "ambiguous_situations": kit_obj.ambiguous_situations  if kit_obj else [],
                    "questions_to_ask":     kit_obj.questions_to_ask      if kit_obj else [],
                    "risk_flags":           kit_obj.risk_flags            if kit_obj else [],
                    "executive_summary":    kit_obj.executive_summary     if kit_obj else "",
                } if kit_obj else None,
            })

    results.sort(key=lambda x: x["phase3_score"], reverse=True)
    return results
