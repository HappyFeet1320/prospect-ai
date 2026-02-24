"""
UI Streamlit — Phase 3 : Scoring & Notation
Tableau trié par score, notation étoiles 1-5, sélection manuelle, validation.
"""

from __future__ import annotations

import time
import pandas as pd
import streamlit as st
from loguru import logger

from phases.phase3.runner import (
    run_phase3,
    update_operator_rating,
    validate_phase3,
    load_phase3_results,
    Phase3Result,
)


# ============================================================
# Point d'entrée principal
# ============================================================

def render_phase3_page(session_id: str):
    """Rendu principal de la page Phase 3."""
    st.markdown("## Phase 3 — Scoring & Notation")
    st.markdown(
        "Chaque entreprise est évaluée sur 3 critères : "
        "**alignement sectoriel** (40%), **proximité géographique** (30%), "
        "et **potentiel structurel** (30%)."
    )

    # Vérification Phase 2 validée
    if st.session_state.get("p2_step") not in ("validated",) and not st.session_state.get("p2_result"):
        st.warning("Vous devez d'abord compléter la Phase 2 (Recherche BCE).")
        if st.button("← Retour Phase 2", key="p3_back_p2"):
            st.session_state.current_page = "Phase 2 — Recherche BCE"
            st.rerun()
        return

    # Initialisation état Phase 3
    if "p3_step" not in st.session_state:
        st.session_state.p3_step = "scoring"
    if "p3_result" not in st.session_state:
        st.session_state.p3_result = None

    step = st.session_state.p3_step

    if step == "scoring":
        _render_scoring(session_id)
    elif step == "review":
        _render_review(session_id)
    elif step == "validated":
        _render_validated(session_id)


# ============================================================
# Étape 1 — Scoring automatique
# ============================================================

def _render_scoring(session_id: str):
    """Lance le scoring automatique avec barre de progression."""
    profile = st.session_state.get("p1_profile", {})

    st.markdown("### Lancement du scoring")

    n_companies = 0
    p2_result = st.session_state.get("p2_result")
    if p2_result:
        n_companies = p2_result.total_companies

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Entreprises à scorer", n_companies)
    with col2:
        st.metric("Critères", "3")
    with col3:
        st.metric("Cible sélection", "100 meilleures")

    st.markdown("---")

    progress_bar   = st.progress(0.0, text="Prêt à scorer...")
    status_text    = st.empty()
    counter_metric = st.empty()

    def on_progress(current: int, total: int):
        pct = current / max(total, 1)
        progress_bar.progress(pct, text=f"Scoring entreprise {current}/{total}...")
        counter_metric.metric("Scorées", current)

    if st.button("🚀 Lancer le scoring", key="p3_btn_launch", type="primary", use_container_width=True):
        try:
            status_text.info("Calcul des scores en cours...")
            result: Phase3Result = run_phase3(
                session_id=session_id,
                profile=profile,
                progress_callback=on_progress,
            )

            progress_bar.progress(1.0, text="Scoring terminé !")
            st.session_state.p3_result = result
            st.session_state.p3_step   = "review"
            time.sleep(0.4)
            st.rerun()

        except Exception as e:
            logger.exception("Erreur Phase 3 scoring")
            st.error(f"Erreur lors du scoring : {e}")


# ============================================================
# Étape 2 — Revue & notation
# ============================================================

def _render_review(session_id: str):
    """
    Tableau trié par score avec :
    - Barres de progression par critère
    - Notation étoiles 1-5 par opérateur
    - Inclusion / exclusion manuelle
    """
    result: Phase3Result | None = st.session_state.get("p3_result")

    # Si rechargement de page, on tente de recharger depuis la DB
    companies = result.companies if result else load_phase3_results(session_id)

    if not companies:
        st.warning("Aucun résultat de scoring. Relancez le scoring.")
        if st.button("← Relancer le scoring", key="p3_btn_relaunch_empty"):
            st.session_state.p3_step = "scoring"
            st.rerun()
        return

    # --------------------------------------------------------
    # En-tête & métriques globales
    # --------------------------------------------------------
    selected_count = sum(1 for c in companies if c.get("is_phase3_selected", False))
    threshold_pct  = int((result.threshold_used if result else 0.45) * 100)

    st.success(
        f"Scoring terminé — **{len(companies)}** entreprises évaluées, "
        f"**{selected_count}** sélectionnées automatiquement (seuil {threshold_pct}%)."
    )

    if result:
        for w in result.warnings:
            st.warning(w)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Scorées", len(companies))
    with col2:
        st.metric("Sélection auto", selected_count)
    with col3:
        rated = sum(1 for c in companies if c.get("operator_rating"))
        st.metric("Notées par vous", rated)
    with col4:
        top_score = companies[0]["phase3_score"] if companies else 0
        st.metric("Meilleur score", f"{top_score:.0%}")

    st.markdown("---")

    # --------------------------------------------------------
    # Légende scores
    # --------------------------------------------------------
    with st.expander("📊 Comprendre les scores", expanded=False):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**Alignement sectoriel (40%)**")
            st.caption(
                "Correspondance entre les codes NACE de l'entreprise et votre profil. "
                "Plus votre secteur est central, plus le score est élevé."
            )
        with col_b:
            st.markdown("**Proximité géographique (30%)**")
            st.caption(
                "Distance entre le siège et vos zones cibles. "
                "Zone cœur (<25% du rayon) → 100%, hors rayon → 0%."
            )
        with col_c:
            st.markdown("**Potentiel structurel (30%)**")
            st.caption(
                "Ancienneté ≥ 5 ans, forme juridique SA/SRL, "
                "nombre d'activités NACE, effectif, statut actif."
            )

    # --------------------------------------------------------
    # Filtres
    # --------------------------------------------------------
    st.markdown("### Filtres")
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)

    with col_f1:
        search_filter = st.text_input("Nom ou BCE", placeholder="Ex: TechSolutions")

    with col_f2:
        show_filter = st.selectbox(
            "Afficher",
            ["Toutes", "Sélectionnées uniquement", "Non sélectionnées", "Notées (★)"],
        )

    with col_f3:
        available_provinces = sorted(set(
            c.get("province") or c.get("city") or "Inconnue"
            for c in companies
        ))
        province_filter = st.selectbox("Province", ["Toutes"] + available_provinces)

    with col_f4:
        min_score = st.slider("Score minimum", 0, 100, 0, step=5, format="%d%%")

    # Application des filtres
    filtered = companies[:]

    if search_filter:
        s = search_filter.lower()
        filtered = [
            c for c in filtered
            if s in c.get("denomination", "").lower()
            or s in c.get("bce_number", "").lower()
        ]

    if show_filter == "Sélectionnées uniquement":
        filtered = [c for c in filtered if c.get("is_phase3_selected")]
    elif show_filter == "Non sélectionnées":
        filtered = [c for c in filtered if not c.get("is_phase3_selected")]
    elif show_filter == "Notées (★)":
        filtered = [c for c in filtered if c.get("operator_rating")]

    if province_filter != "Toutes":
        filtered = [
            c for c in filtered
            if (c.get("province") or c.get("city") or "") == province_filter
        ]

    filtered = [c for c in filtered if c["phase3_score"] >= min_score / 100]

    st.caption(f"**{len(filtered)}** entreprises affichées sur {len(companies)}")

    st.markdown("---")

    # --------------------------------------------------------
    # Tableau de notation interactif
    # --------------------------------------------------------
    st.markdown("### Notation des entreprises")
    st.caption(
        "Modifiez la colonne **Note** (1-5) et **Inclure** directement dans le tableau. "
        "Cliquez **Sauvegarder** pour persister vos choix."
    )

    # ── Construction du DataFrame éditable ───────────────────
    # Une seule liste de company_ids parallèle au DataFrame
    company_ids_ordered: list[str] = []
    editor_rows = []

    for c in filtered:
        detail     = c.get("phase3_score_detail") or {}
        cid        = c["company_id"]
        auto_stars = detail.get("stars", 3)

        # Valeur courante : modif en session > DB
        saved = st.session_state.get("p3_ratings", {}).get(cid, {})
        cur_rating   = saved.get("rating")   or c.get("operator_rating") or auto_stars
        cur_selected = saved.get("selected", c.get("is_phase3_selected", False))

        company_ids_ordered.append(cid)
        editor_rows.append({
            "Entreprise":   c.get("denomination", "—")[:50],
            "Ville":        c.get("city", "") or c.get("municipality", ""),
            "Score %":      int(round(c["phase3_score"] * 100)),
            "Sectoriel %":  int(round(detail.get("sectoral_score", 0) * 100)),
            "Geo %":        int(round(detail.get("geo_score", 0) * 100)),
            "Struct %":     int(round(detail.get("structural_score", 0) * 100)),
            "Note (1-5)":   int(cur_rating),
            "Inclure":      bool(cur_selected),
        })

    df_editor = pd.DataFrame(editor_rows)

    # ── Affichage data_editor (1 seul widget, stable) ────────
    edited_df = st.data_editor(
        df_editor,
        key="p3_data_editor",
        column_config={
            "Entreprise":   st.column_config.TextColumn("Entreprise", disabled=True, width="large"),
            "Ville":        st.column_config.TextColumn("Ville", disabled=True),
            "Score %":      st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d%%"),
            "Sectoriel %":  st.column_config.ProgressColumn("Sect.", min_value=0, max_value=100, format="%d%%"),
            "Geo %":        st.column_config.ProgressColumn("Géo", min_value=0, max_value=100, format="%d%%"),
            "Struct %":     st.column_config.ProgressColumn("Struct.", min_value=0, max_value=100, format="%d%%"),
            "Note (1-5)":   st.column_config.NumberColumn("Note ★", min_value=1, max_value=5, step=1),
            "Inclure":      st.column_config.CheckboxColumn("Inclure"),
        },
        disabled=["Entreprise", "Ville", "Score %", "Sectoriel %", "Geo %", "Struct %"],
        hide_index=True,
        use_container_width=True,
        height=min(620, len(editor_rows) * 36 + 42),
    )

    # Synchroniser le data_editor vers p3_ratings en session
    if "p3_ratings" not in st.session_state:
        st.session_state.p3_ratings = {}
    for pos, row in edited_df.iterrows():
        cid = company_ids_ordered[pos]
        st.session_state.p3_ratings[cid] = {
            "rating":   int(row["Note (1-5)"]),
            "selected": bool(row["Inclure"]),
        }

    # ── Actions ──────────────────────────────────────────────
    st.markdown("---")
    col_save, col_reset, col_validate = st.columns(3)

    with col_save:
        if st.button("Sauvegarder les notations", key="p3_btn_save", use_container_width=True):
            _save_ratings(st.session_state.p3_ratings)
            st.success("Notations sauvegardées !")
            st.rerun()

    with col_reset:
        if st.button("Relancer le scoring", key="p3_btn_reset", use_container_width=True):
            st.session_state.p3_step   = "scoring"
            st.session_state.p3_result = None
            st.rerun()

    with col_validate:
        total_selected = sum(
            1 for c in companies
            if st.session_state.p3_ratings.get(c["company_id"], {}).get(
                "selected", c.get("is_phase3_selected", False)
            )
        )
        can_validate = total_selected >= 3
        if st.button(
            f"Valider et passer à Phase 4 ({total_selected} sélectionnées)",
            key="p3_btn_validate",
            type="primary",
            disabled=not can_validate,
            use_container_width=True,
            help=(
                "Minimum 3 entreprises sélectionnées requises."
                if not can_validate
                else "Lancer la recherche approfondie (Phase 4)."
            ),
        ):
            _save_ratings(st.session_state.p3_ratings)
            validate_phase3(session_id)
            st.session_state.p3_step    = "validated"
            st.session_state.p3_ratings = {}
            st.rerun()

    # ── Export CSV ───────────────────────────────────────────
    st.markdown("---")
    export_rows = []
    for c in companies:
        detail = c.get("phase3_score_detail") or {}
        r = st.session_state.p3_ratings.get(c["company_id"], {})
        export_rows.append({
            "BCE":          c.get("bce_number", ""),
            "Dénomination": c.get("denomination", "")[:60],
            "Ville":        c.get("city", ""),
            "Province":     c.get("province", ""),
            "Score":        f"{c['phase3_score']:.0%}",
            "Sectoriel":    f"{detail.get('sectoral_score', 0):.0%}",
            "Géographie":   f"{detail.get('geo_score', 0):.0%}",
            "Structurel":   f"{detail.get('structural_score', 0):.0%}",
            "Note":         r.get("rating", c.get("operator_rating", "")),
            "Sélectionnée": "✓" if r.get("selected", c.get("is_phase3_selected")) else "",
        })
    csv = pd.DataFrame(export_rows).to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Télécharger CSV complet",
        data=csv,
        file_name=f"phase3_scoring_{session_id[:8]}.csv",
        mime="text/csv",
        key="p3_btn_dl_csv",
    )


# ============================================================
# Helpers
# ============================================================

def _save_ratings(ratings: dict) -> None:
    """Persiste les notations et sélections en base."""
    for company_id, data in ratings.items():
        update_operator_rating(
            company_id=company_id,
            rating=data.get("rating"),
            selected=data.get("selected", False),
        )
    logger.info("Phase 3 : {} notations sauvegardées", len(ratings))


# ============================================================
# Étape 3 — Phase 3 validée
# ============================================================

def _render_validated(session_id: str):
    """Écran affiché après validation Phase 3."""
    companies = load_phase3_results(session_id)
    selected  = [c for c in companies if c.get("is_phase3_selected")]

    st.success("**Phase 3 validée !**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Entreprises scorées",      len(companies))
    with col2:
        st.metric("Entreprises sélectionnées", len(selected))
    with col3:
        top = companies[0]["phase3_score"] if companies else 0
        st.metric("Meilleur score",            f"{top:.0%}")

    st.markdown("---")

    if selected:
        st.markdown("#### Top entreprises sélectionnées")
        for i, c in enumerate(selected[:5], 1):
            detail = c.get("phase3_score_detail") or {}
            rating = c.get("operator_rating") or detail.get("stars", 0)
            stars  = ("★" * rating + "☆" * (5 - rating)) if isinstance(rating, int) else "—"
            st.markdown(
                f"**{i}. {c.get('denomination', '—')}** — "
                f"{c['phase3_score']:.0%} {stars} · {c.get('city', '')}"
            )

    st.markdown("---")
    col_edit, col_next = st.columns(2)
    with col_edit:
        if st.button("← Voir les résultats", key="p3_btn_back_review", use_container_width=True):
            st.session_state.p3_step = "review"
            st.rerun()
    with col_next:
        if st.button(
            "Lancer Phase 4 — Recherche approfondie →",
            key="p3_btn_goto_p4",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.current_page = "Phase 4 — Dossiers"
            st.rerun()
