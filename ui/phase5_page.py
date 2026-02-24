"""
UI Streamlit — Phase 5 : Préparation à l'Entretien.

RÈGLE DOM : chaque widget est TOUJOURS rendu (jamais conditionnel).
Utiliser disabled=True au lieu d'if/else sur st.button.
Pas de st.tabs() ni st.expander() imbriqués.
"""

import html as html_lib
import time
import streamlit as st
from loguru import logger

from phases.phase5.runner import (
    run_phase5,
    validate_phase5,
    load_phase5_results,
    Phase5Result,
)


# ============================================================
# Point d'entrée principal
# ============================================================

def render_phase5_page(session_id: str):
    """Rendu principal de la page Phase 5."""
    st.markdown("## Phase 5 — Préparation à l'Entretien")
    st.markdown(
        "Génération d'un kit de préparation personnalisé pour chaque entreprise sélectionnée : "
        "messages d'accroche, situations ambiguës, questions clés et résumé exécutif."
    )

    profile = st.session_state.get("p1_profile")
    if not profile:
        st.warning("Vous devez d'abord valider votre profil (Phase 1).")
        return

    # Vérification Phase 4 validée
    current_phase = st.session_state.get("current_phase", 1)
    p4_step       = st.session_state.get("p4_step", "")
    if current_phase < 5 and p4_step != "validated":
        st.warning("Vous devez d'abord valider la Phase 4 (Recherche Approfondie).")
        if st.button("← Retour Phase 4", key="p5_back_p4"):
            st.session_state.current_page = "Phase 4 — Dossiers"
            st.rerun()
        return

    # Initialisation état
    if "p5_step" not in st.session_state:
        st.session_state.p5_step = "config"

    step = st.session_state.p5_step

    if step == "config":
        _render_config(session_id, profile)
    elif step == "generating":
        _render_generating(session_id, profile)
    elif step == "review":
        _render_review(session_id, profile)
    elif step == "validated":
        _render_validated(session_id)


# ============================================================
# Étape 1 — Configuration
# ============================================================

def _render_config(session_id: str, profile: dict):
    """Affiche les entreprises éligibles — structure DOM stable."""

    companies   = load_phase5_results(session_id)
    with_kit    = [c for c in companies if c.get("phase5_kit")]
    without_kit = [c for c in companies if not c.get("phase5_kit")]
    has_any     = len(companies) > 0
    all_done    = has_any and len(without_kit) == 0

    # Info globale
    if has_any:
        st.info(
            f"**{len(companies)} entreprise(s) éligible(s)** pour la génération de kit "
            f"(notation ≥ 3 étoiles ou sélectionnées en Phase 4). "
            f"{len(with_kit)} kit(s) déjà généré(s)."
        )
        for c in companies:
            rating = c.get("operator_rating") or 0
            stars  = "⭐" * rating if rating else "—"
            kit_ok = "✅ Kit prêt" if c.get("phase5_kit") else "⏳ À générer"
            nom    = c.get("denomination", c.get("bce_number", "?"))
            st.markdown(f"- {nom} — {stars} — {kit_ok}")
    else:
        st.warning(
            "Aucune entreprise éligible. "
            "Retournez en Phase 4 pour noter au moins une entreprise avec ≥ 3 étoiles."
        )

    st.markdown("---")

    col1, col2 = st.columns(2)

    # Bouton 1 : générer — toujours rendu, disabled si rien à faire
    gen_label   = "Générer les kits manquants →" if (has_any and not all_done) else "Générer tous les kits →"
    gen_help    = "Génère les kits pour les entreprises sans kit." if without_kit else "Tous les kits sont déjà générés."
    gen_disable = not has_any or all_done

    with col1:
        if st.button(
            gen_label,
            key="p5_btn_generate",
            type="primary",
            use_container_width=True,
            disabled=gen_disable,
            help=gen_help,
        ):
            st.session_state.p5_step = "generating"
            st.rerun()

    # Bouton 2 : consulter — toujours rendu, disabled si aucun kit
    with col2:
        if st.button(
            "Consulter les kits →",
            key="p5_btn_review",
            use_container_width=True,
            disabled=not with_kit,
            help="Consultez les kits déjà générés." if with_kit else "Aucun kit disponible.",
        ):
            st.session_state.p5_step = "review"
            st.rerun()

    # Message si tout est prêt
    if all_done:
        st.success("Tous les kits sont générés. Cliquez sur **Consulter les kits** pour les voir.")


# ============================================================
# Étape 2 — Génération avec progression
# ============================================================

def _render_generating(session_id: str, profile: dict):
    """Lance la génération et affiche la progression."""
    st.markdown("### Génération des kits en cours...")

    status_area  = st.empty()
    progress_bar = st.progress(0.0)
    log_area     = st.empty()

    logs: list[str] = []

    def progress_callback(name: str, current: int, total: int, status: str):
        pct = current / total if total > 0 else 0
        progress_bar.progress(pct)

        icons = {"running": "⏳", "done": "✅", "error": "❌"}
        icon  = icons.get(status, "")
        logs.append(f"{icon} {name[:50]}")
        log_area.markdown("\n".join(logs[-8:]))

        msgs = {
            "running": f"Génération du kit pour **{name[:40]}**...",
            "done":    f"Kit généré pour **{name[:40]}**",
            "error":   f"Erreur pour **{name[:40]}**",
        }
        status_area.info(msgs.get(status, ""))

    try:
        result: Phase5Result = run_phase5(session_id, profile, progress_callback)
        progress_bar.progress(1.0)

        for w in result.warnings:
            st.warning(w)

        st.success(
            f"Génération terminée — **{result.generated_count}/{result.total_companies}** kits créés."
        )
        st.session_state.p5_step = "review"
        time.sleep(0.6)
        st.rerun()

    except Exception as e:
        logger.error("Phase 5 — erreur génération : {}", e)
        st.error(f"Erreur lors de la génération : {e}")
        if st.button("Réessayer", key="p5_btn_retry"):
            st.rerun()


# ============================================================
# Étape 3 — Consultation des kits
# ============================================================

def _render_review(session_id: str, profile: dict):
    """Affiche le kit de l'entreprise sélectionnée — DOM stable."""

    companies_all = load_phase5_results(session_id)
    companies_kit = [c for c in companies_all if c.get("phase5_kit")]

    if not companies_kit:
        st.warning("Aucun kit disponible. Lancez d'abord la génération.")
        if st.button("← Retour", key="p5_btn_no_kit_back"):
            st.session_state.p5_step = "config"
            st.rerun()
        return

    # ── Sélecteur d'entreprise ────────────────────────────────
    noms = [
        c.get("denomination", c.get("bce_number", f"Entreprise {i+1}"))
        for i, c in enumerate(companies_kit)
    ]

    col_sel, col_star = st.columns([4, 1])
    with col_sel:
        idx = st.selectbox(
            "Sélectionnez une entreprise",
            range(len(noms)),
            format_func=lambda i: noms[i],
            key="p5_company_select",
        )
    with col_star:
        st.markdown("<br>", unsafe_allow_html=True)
        rating = companies_kit[idx].get("operator_rating") or 0
        st.markdown("⭐" * rating if rating else "—")

    company = companies_kit[idx]
    kit     = company.get("phase5_kit", {})

    st.markdown("---")

    # ── Sections du kit ──────────────────────────────────────
    _section_messages(kit.get("message_variants", []))
    _section_situations(kit.get("ambiguous_situations", []))
    _section_questions(kit.get("questions_to_ask", []))
    _section_risks(kit.get("risk_flags", []))
    _section_summary(company, kit.get("executive_summary", ""))

    st.markdown("---")

    # ── Boutons d'action — TOUJOURS les 3 rendus ─────────────
    all_ready = len(companies_kit) == len(companies_all)

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← Retour config", key="p5_btn_back_cfg", use_container_width=True):
            st.session_state.p5_step = "config"
            st.rerun()

    with col2:
        if st.button(
            "Regénérer ce kit",
            key="p5_btn_regen",
            use_container_width=True,
            help="Relance la génération pour cette entreprise uniquement.",
        ):
            _regenerate_single(company, profile)

    with col3:
        if st.button(
            "Valider et terminer ✓",
            key="p5_btn_validate",
            type="primary",
            use_container_width=True,
            disabled=not all_ready,
            help="Valide Phase 5 et clôture la session." if all_ready
                 else "Générez d'abord tous les kits.",
        ):
            validate_phase5(session_id)
            st.session_state.p5_step = "validated"
            st.rerun()


def _regenerate_single(company: dict, profile: dict):
    """Regénère le kit pour une seule entreprise sans changer la page."""
    from phases.phase5.runner import _save_kit
    from phases.phase5.generator import generate_kit

    cid  = company["company_id"]
    name = company.get("denomination", cid[:8])

    with st.spinner(f"Régénération pour {name[:40]}..."):
        try:
            kit = generate_kit(company, profile)
            _save_kit(cid, kit)
            st.success("Kit régénéré.")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")


# ============================================================
# Sections d'affichage — toujours une structure identique
# ============================================================

def _section_messages(variants: list):
    st.markdown("### Messages d'Accroche")

    if not variants:
        st.info("Aucun message généré.")
        return

    canal_icons = {"Email": "Email", "LinkedIn": "LinkedIn", "Téléphone": "Téléphone"}

    for i, v in enumerate(variants):
        canal = v.get("canal", f"Canal {i+1}")
        angle = v.get("angle", "")
        objet = v.get("objet", "")
        corps = v.get("corps", "")

        st.markdown(f"**{canal} — Angle {angle}**")
        if objet:
            st.markdown(f"*{objet}*")
        # text_area toujours rendu, clé stable via index i
        st.text_area(
            label=canal,
            value=corps,
            height=150,
            key=f"p5_msg_{i}",
            label_visibility="collapsed",
        )
        st.markdown("")


def _section_situations(situations: list):
    st.markdown("### Situations Ambiguës — Préparation")

    if not situations:
        st.info("Aucune situation générée.")
        return

    for i, s in enumerate(situations):
        situation = s.get("situation", f"Situation {i+1}")
        reponse   = s.get("reponse_suggeree", "")

        st.markdown(f"**{i+1}. {situation}**")
        if reponse:
            st.markdown(
                f'<div style="background:#f0f8ff;padding:10px 12px;border-left:3px solid #1f77b4;'
                f'border-radius:4px;margin-bottom:10px;">{html_lib.escape(reponse)}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("")


def _section_questions(questions: list):
    st.markdown("### Questions Clés à Poser")

    if not questions:
        st.info("Aucune question générée.")
        return

    for i, q in enumerate(questions):
        question  = q.get("question", f"Question {i+1}")
        rationale = q.get("rationale", "")

        st.markdown(f"**{i+1}. {question}**")
        if rationale:
            st.caption(f"→ {rationale}")
        st.markdown("")


def _section_risks(flags: list):
    st.markdown("### Points de Vigilance")

    if not flags:
        st.success("Aucun risque majeur identifié.")
        return

    severity_icon = {"Faible": "🟢", "Modérée": "🟡", "Élevée": "🔴"}

    for f in flags:
        type_    = f.get("type", "Autre")
        desc     = f.get("description", "")
        severite = f.get("severite", "Faible")
        icon     = severity_icon.get(severite, "🟡")
        st.markdown(f"{icon} **{type_}** ({severite}) — {desc}")


def _section_summary(company: dict, summary: str):
    st.markdown("### Résumé Exécutif")

    nom    = company.get("denomination", "Entreprise")
    score  = company.get("phase3_score", 0.0)
    rating = company.get("operator_rating") or 0
    bce    = company.get("bce_number", "")

    st.markdown(
        f"**{nom}** | BCE : {bce} | Score : {score:.0%} | Note : {'⭐' * rating if rating else '—'}"
    )

    if summary:
        st.markdown(
            f'<div style="background:#fafafa;padding:16px;border:1px solid #e0e0e0;'
            f'border-radius:6px;white-space:pre-wrap;font-size:0.92em;">{html_lib.escape(summary)}</div>',
            unsafe_allow_html=True,
        )
        # Export texte — download_button est toujours rendu si summary non vide
        full_text = _build_export_text(company)
        st.download_button(
            label="Télécharger le résumé complet (.txt)",
            data=full_text,
            file_name=f"kit_{nom[:30].replace(' ', '_')}.txt",
            mime="text/plain",
            key=f"p5_dl_{company.get('company_id', 'x')[:8]}",
        )
    else:
        st.info("Résumé non disponible.")


def _build_export_text(company: dict) -> str:
    """Construit le texte exportable complet du kit."""
    nom   = company.get("denomination", "Entreprise")
    bce   = company.get("bce_number", "")
    score = company.get("phase3_score", 0.0)
    kit   = company.get("phase5_kit", {})

    msgs  = kit.get("message_variants", [])
    qs    = kit.get("questions_to_ask", [])
    sits  = kit.get("ambiguous_situations", [])
    risks = kit.get("risk_flags", [])
    summ  = kit.get("executive_summary", "")

    lines = [
        f"KIT DE PRÉPARATION — {nom.upper()}",
        f"BCE : {bce} | Score PROSPECT-AI : {score:.0%}",
        "=" * 60,
        "",
        "RÉSUMÉ EXÉCUTIF",
        "-" * 40,
        summ,
        "",
        "MESSAGES D'ACCROCHE",
        "-" * 40,
    ]
    for v in msgs:
        lines += [
            f"\n[{v.get('canal')} — Angle {v.get('angle')}]",
            f"Objet : {v.get('objet', '')}",
            v.get("corps", ""),
        ]

    lines += ["", "SITUATIONS AMBIGUËS", "-" * 40]
    for i, s in enumerate(sits, 1):
        lines += [f"\n{i}. {s.get('situation', '')}", f"   → {s.get('reponse_suggeree', '')}"]

    lines += ["", "QUESTIONS À POSER", "-" * 40]
    for i, q in enumerate(qs, 1):
        lines += [f"{i}. {q.get('question', '')}"]

    lines += ["", "POINTS DE VIGILANCE", "-" * 40]
    for r in risks:
        lines += [f"[{r.get('severite')}] {r.get('type')} — {r.get('description', '')}"]

    lines += ["", "=" * 60, "Généré par PROSPECT-AI"]
    return "\n".join(lines)


# ============================================================
# Étape 4 — Validée / Terminée
# ============================================================

def _render_validated(session_id: str):
    """Écran de fin de session."""
    st.success("### Phase 5 validée — Session terminée !")

    st.markdown("""
**Félicitations !** Vous avez complété les 5 phases de PROSPECT-AI.

**Prochaines étapes recommandées :**
1. Envoyez vos messages d'accroche en commençant par les entreprises les mieux notées
2. Préparez-vous aux situations ambiguës avant chaque contact
3. Posez vos questions lors des entretiens pour démontrer votre connaissance de l'entreprise
    """)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Retour aux kits", key="p5_btn_val_back", use_container_width=True):
            st.session_state.p5_step = "review"
            st.rerun()
    with col2:
        if st.button("Nouvelle session →", key="p5_btn_new_session", type="primary", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
