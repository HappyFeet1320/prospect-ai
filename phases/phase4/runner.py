"""
Phase 4 — Orchestration de l'enrichissement.

Charge les entreprises sélectionnées en Phase 3, les enrichit une par une,
sauvegarde les dossiers en base et les décideurs dans la table decision_makers.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select

from database.connection import get_session
from database.models import Company, DecisionMaker, Session as DbSession

from .enricher import enrich_company


# Lock global pour les écritures SQLite (non thread-safe nativement)
_db_write_lock = threading.Lock()


# ============================================================
# Structures de données
# ============================================================

@dataclass
class Phase4Result:
    session_id:       str
    total_companies:  int
    enriched_count:   int
    failed_count:     int
    companies:        list[dict] = field(default_factory=list)
    warnings:         list[str]  = field(default_factory=list)


# ============================================================
# Orchestration principale
# ============================================================

def run_phase4(
    session_id: str,
    profile: dict,
    progress_callback=None,
) -> Phase4Result:
    """
    Enrichit toutes les entreprises sélectionnées (Phase 3).

    Args:
        session_id:        ID de session.
        profile:           Profil opérateur (Phase 1).
        progress_callback: fn(company_name, current, total, status)
                           status = 'running' | 'done' | 'error'

    Returns:
        Phase4Result avec la liste des dossiers enrichis.
    """
    warnings: list[str] = []

    # ── Charger les entreprises sélectionnées ─────────────────
    with get_session() as db:
        stmt = (
            select(Company)
            .where(Company.session_id == session_id)
            .where(Company.is_phase3_selected.is_(True))
        )
        companies_db: list[Company] = list(db.execute(stmt).scalars().all())

    total = len(companies_db)
    if total == 0:
        return Phase4Result(
            session_id=session_id,
            total_companies=0,
            enriched_count=0,
            failed_count=0,
            warnings=["Aucune entreprise sélectionnée en Phase 3. Validez d'abord la Phase 3."],
        )

    MAX_WORKERS = 3
    logger.info(
        "Phase 4 démarrée — {} entreprises à enrichir (parallèle ×{})",
        total, MAX_WORKERS,
    )

    enriched:       list[dict] = []
    failed          = 0
    completed       = 0
    warnings_lock   = threading.Lock()
    progress_lock   = threading.Lock()

    def _enrich_one(
        idx: int, company_db: Company
    ) -> tuple[bool, dict | None, str, str | None]:
        """Worker : enrichit une entreprise dans son propre thread."""
        # Décalage initial pour étaler les requêtes HTTP (0 s, 1 s, 2 s, 0 s, …)
        stagger = (idx % MAX_WORKERS) * 1.0
        if stagger:
            time.sleep(stagger)

        company_data: dict = company_db.phase2_data
        company_data["company_id"]   = company_db.company_id
        company_data["bce_number"]   = company_db.bce_number or ""
        company_data["phase3_score"] = company_db.phase3_score

        name = company_data.get("denomination", f"Entreprise {idx + 1}")

        with progress_lock:
            if progress_callback:
                progress_callback(name, completed, total, "running")

        try:
            dossier = enrich_company(company_data, profile)

            with _db_write_lock:
                _save_dossier(company_db.company_id, dossier)

            company_data["phase4_dossier"] = dossier
            return True, company_data, name, None

        except Exception as e:
            logger.warning("Phase 4 — erreur enrichissement {} : {}", name[:40], e)
            return False, None, name, str(e)

    # ── Lancement parallèle ────────────────────────────────────
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(_enrich_one, idx, company_db): idx
            for idx, company_db in enumerate(companies_db)
        }

        for future in as_completed(future_map):
            success, company_data, name, err = future.result()
            completed += 1

            if success:
                enriched.append(company_data)
                if progress_callback:
                    progress_callback(name, completed, total, "done")
            else:
                failed += 1
                with warnings_lock:
                    warnings.append(
                        f"Échec enrichissement de « {name[:60]} » : {err}"
                    )
                if progress_callback:
                    progress_callback(name, completed, total, "error")

    if failed > 0:
        warnings.append(f"{failed} entreprise(s) n'ont pas pu être enrichies.")

    logger.success(
        "Phase 4 terminée — {}/{} enrichies, {} échecs",
        len(enriched), total, failed,
    )

    return Phase4Result(
        session_id=session_id,
        total_companies=total,
        enriched_count=len(enriched),
        failed_count=failed,
        companies=enriched,
        warnings=warnings,
    )


def _save_dossier(company_id: str, dossier: dict) -> None:
    """Sauvegarde le dossier Phase 4 et les décideurs en base."""
    with get_session() as db:
        company_db = db.get(Company, company_id)
        if not company_db:
            return

        company_db.phase4_data = dossier

        # Supprimer les anciens décideurs
        old_dms = db.execute(
            select(DecisionMaker).where(DecisionMaker.company_id == company_id)
        ).scalars().all()
        for dm in old_dms:
            db.delete(dm)

        # Insérer les nouveaux décideurs
        for dm_data in dossier.get("bloc_decideurs", []):
            dm = DecisionMaker(
                company_id=company_id,
                full_name=dm_data.get("prenom_nom", "Inconnu"),
                title=dm_data.get("titre", ""),
                dm_type=dm_data.get("type", "AUTRE"),
                bio_short=dm_data.get("bio_courte", ""),
                linkedin_url=dm_data.get("linkedin_url", ""),
                email=dm_data.get("email", ""),
            )
            db.add(dm)

        db.commit()

    logger.debug("Phase 4 — dossier sauvegardé pour {}", company_id[:8])


# ============================================================
# Validation Phase 4
# ============================================================

def validate_phase4(session_id: str) -> None:
    """Marque Phase 4 comme validée dans la session DB."""
    with get_session() as db:
        session_db = db.get(DbSession, session_id)
        if session_db:
            session_db.p4_validated  = True
            session_db.current_phase = 5
            db.commit()
    logger.info("Phase 4 validée — session {}", session_id)


# ============================================================
# Chargement depuis la DB (rechargement après refresh)
# ============================================================

def load_phase4_results(session_id: str) -> list[dict]:
    """
    Recharge les dossiers Phase 4 depuis la DB.
    Retourne les entreprises avec dossier enrichi, triées par score.
    """
    with get_session() as db:
        stmt = (
            select(Company)
            .where(Company.session_id == session_id)
            .where(Company.is_phase3_selected.is_(True))
            .where(Company.phase4_data_json.isnot(None))
        )
        companies_db = list(db.execute(stmt).scalars().all())

    results = []
    for c in companies_db:
        data = c.phase2_data
        results.append({
            **data,
            "company_id":      c.company_id,
            "bce_number":      c.bce_number or "",
            "phase3_score":    c.phase3_score or 0.0,
            "phase4_dossier":  c.phase4_data,
            "operator_rating": c.operator_rating,
            "is_selected":     c.is_selected,
            "operator_notes":  c.operator_notes or "",
        })

    results.sort(key=lambda x: x["phase3_score"], reverse=True)
    return results


def update_company_selection(
    company_id: str,
    rating: int | None,
    is_selected: bool,
    notes: str = "",
) -> None:
    """Met à jour la notation et sélection d'une entreprise pour Phase 5."""
    with get_session() as db:
        company_db = db.get(Company, company_id)
        if company_db:
            company_db.operator_rating = rating
            company_db.is_selected     = is_selected
            company_db.operator_notes  = notes
            db.commit()
