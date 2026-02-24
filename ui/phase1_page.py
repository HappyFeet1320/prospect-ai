"""
UI Streamlit — Phase 1 : Profiling Opérateur
Interface de saisie, analyse par Claude et validation du profil.
"""

import streamlit as st
from loguru import logger

from phases.phase1.profiler import (
    analyze_profile,
    is_profile_complete,
    get_profile_completeness_pct,
    format_profile_for_display,
)
from database.connection import get_session
from database.models import Session as DbSession


# --- Textes d'aide ---
PLACEHOLDER_TEXT = """Décrivez votre situation professionnelle en détail...

Exemples d'informations à inclure :
• Vos expériences : "J'ai travaillé 5 ans comme développeur Python chez Proximus à Bruxelles..."
• Vos compétences : "Je maîtrise Python, SQL, Docker, et j'ai une expérience en IA..."
• Votre localisation : "Je cherche un poste dans un rayon de 30 km autour de Liège..."
• Le type de contrat : "Je recherche un CDI ou une mission freelance..."
• Votre disponibilité : "Je suis disponible immédiatement / dans 1 mois..."
• Vos préférences : "Je préfère les PME, je peux faire du télétravail..."
"""

SENIORITY_LABELS = {
    "junior": "Junior (0-3 ans)",
    "medior": "Médior (3-7 ans)",
    "senior": "Senior (7+ ans)",
    "direction": "Direction / Management",
}

LANGUAGE_LABELS = {
    "fr": "🇫🇷 Français",
    "nl": "🇳🇱 Néerlandais",
    "de": "🇩🇪 Allemand",
    "en": "🇬🇧 Anglais",
    "es": "🇪🇸 Espagnol",
    "it": "🇮🇹 Italien",
    "pt": "🇵🇹 Portugais",
    "ar": "🇸🇦 Arabe",
    "zh": "🇨🇳 Chinois",
}


def render_phase1_page(session_id: str):
    """Rendu principal de la page Phase 1."""

    st.markdown("## Phase 1 — Profiling Opérateur")
    st.markdown(
        "Décrivez votre situation professionnelle en langage naturel. "
        "PROSPECT-AI analysera votre profil et déterminera les secteurs cibles "
        "et codes NACE belges pour la recherche d'entreprises."
    )

    # Initialisation de l'état Streamlit pour Phase 1
    if "p1_profile" not in st.session_state:
        st.session_state.p1_profile = None
    if "p1_raw_text" not in st.session_state:
        st.session_state.p1_raw_text = ""
    if "p1_step" not in st.session_state:
        st.session_state.p1_step = "input"  # input | analyzing | review | validated
    if "p1_follow_up_text" not in st.session_state:
        st.session_state.p1_follow_up_text = ""

    # ----------------------------------------------------------------
    # ÉTAPE 1 — Saisie initiale
    # ----------------------------------------------------------------
    if st.session_state.p1_step in ("input", "follow_up"):
        _render_input_step(session_id)

    # ----------------------------------------------------------------
    # ÉTAPE 2 — Revue du profil généré
    # ----------------------------------------------------------------
    elif st.session_state.p1_step == "review":
        _render_review_step(session_id)

    # ----------------------------------------------------------------
    # ÉTAPE 3 — Profil validé
    # ----------------------------------------------------------------
    elif st.session_state.p1_step == "validated":
        _render_validated_step(session_id)


# ============================================================
# Étape 1 — Saisie
# ============================================================

def _render_input_step(session_id: str):
    is_follow_up = st.session_state.p1_step == "follow_up"

    # --- Affichage des questions de relance si nécessaire ---
    if is_follow_up and st.session_state.p1_profile:
        profile = st.session_state.p1_profile
        questions = profile.get("follow_up_questions", [])
        missing = profile.get("missing_required_fields", [])

        if questions or missing:
            st.warning(
                "**Informations manquantes ou insuffisantes.** "
                "Répondez aux questions ci-dessous pour compléter votre profil."
            )

        if missing:
            st.markdown("**Champs obligatoires manquants :**")
            field_labels = {
                "experiences": "Expériences professionnelles",
                "localisation": "Localisation géographique souhaitée",
                "contract_types": "Type de contrat recherché",
                "availability": "Disponibilité",
                "skills": "Compétences techniques et sectorielles",
            }
            for f in missing:
                st.markdown(f"- {field_labels.get(f, f)}")

        if questions:
            st.markdown("**Questions de précision :**")
            for i, q in enumerate(questions, 1):
                st.markdown(f"**{i}.** {q}")

        st.markdown("---")

    # --- Zone de saisie principale ---
    if is_follow_up:
        label = "Vos réponses et précisions complémentaires :"
        help_text = "Répondez aux questions ci-dessus pour enrichir votre profil."
    else:
        label = "Décrivez votre situation professionnelle :"
        help_text = "Plus vous êtes précis, meilleure sera l'analyse. Minimum 100 caractères recommandé."

    text_input = st.text_area(
        label,
        value=st.session_state.p1_follow_up_text if is_follow_up else st.session_state.p1_raw_text,
        height=300,
        placeholder=PLACEHOLDER_TEXT,
        help=help_text,
        key="p1_text_area"
    )

    # --- Barre de progression si relance ---
    if is_follow_up and st.session_state.p1_profile:
        completeness = get_profile_completeness_pct(st.session_state.p1_profile)
        st.progress(completeness / 100, text=f"Complétude actuelle : {completeness}%")

    col1, col2 = st.columns([3, 1])

    with col1:
        char_count = len(text_input)
        if char_count < 100:
            st.caption(f"⚠️ {char_count}/100 caractères minimum recommandé")
        else:
            st.caption(f"✅ {char_count} caractères")

    with col2:
        btn_label = "Analyser mon profil" if not is_follow_up else "Mettre à jour le profil"
        analyze_clicked = st.button(
            btn_label,
            type="primary",
            disabled=char_count < 30,
            use_container_width=True
        )

    if is_follow_up:
        if st.button("← Revenir à la revue du profil", use_container_width=True):
            st.session_state.p1_step = "review"
            st.rerun()

    if analyze_clicked and text_input.strip():
        _run_analysis(text_input, session_id, is_follow_up)


# ============================================================
# Analyse via Claude
# ============================================================

def _run_analysis(text: str, session_id: str, is_follow_up: bool):
    """Lance l'appel Claude et stocke le résultat."""
    with st.spinner("Analyse de votre profil en cours... (10-30 secondes)"):
        try:
            previous_profile = st.session_state.p1_profile if is_follow_up else None
            raw_text = (
                st.session_state.p1_raw_text + "\n\n[COMPLÉMENT] " + text
                if is_follow_up else text
            )

            profile = analyze_profile(raw_text, previous_profile=previous_profile)
            st.session_state.p1_profile = profile
            st.session_state.p1_raw_text = raw_text
            st.session_state.p1_follow_up_text = ""
            st.session_state.p1_step = "review"
            st.success("Analyse terminée !")
            st.rerun()

        except ValueError as e:
            st.error(f"Configuration manquante : {e}")
        except Exception as e:
            logger.exception("Erreur lors de l'analyse du profil")
            st.error(f"Erreur lors de l'analyse : {e}")


# ============================================================
# Étape 2 — Revue du profil
# ============================================================

def _render_review_step(session_id: str):
    profile = st.session_state.p1_profile
    if not profile:
        st.session_state.p1_step = "input"
        st.rerun()
        return

    completeness = get_profile_completeness_pct(profile)
    missing = profile.get("missing_required_fields", [])
    questions = profile.get("follow_up_questions", [])

    # --- En-tête avec indicateur de complétude ---
    col_title, col_progress = st.columns([2, 1])
    with col_title:
        st.markdown("### Fiche Profil Générée")
    with col_progress:
        color = "green" if completeness >= 80 else "orange" if completeness >= 50 else "red"
        st.metric("Complétude", f"{completeness}%")

    st.progress(completeness / 100)

    if missing or questions:
        with st.expander("⚠️ Informations manquantes — cliquez pour voir les questions", expanded=True):
            if missing:
                st.markdown("**Champs obligatoires à compléter :**")
                field_labels = {
                    "experiences": "Expériences professionnelles détaillées",
                    "localisation": "Localisation géographique souhaitée",
                    "contract_types": "Type de contrat",
                    "availability": "Disponibilité",
                    "skills": "Compétences techniques",
                }
                for f in missing:
                    st.markdown(f"- {field_labels.get(f, f)}")
            if questions:
                st.markdown("**Questions pour affiner votre profil :**")
                for i, q in enumerate(questions, 1):
                    st.markdown(f"**{i}.** {q}")
            if st.button("Compléter ces informations", type="primary"):
                st.session_state.p1_step = "follow_up"
                st.rerun()

    st.markdown("---")

    # --- Résumé ---
    st.markdown("#### Résumé du Profil")
    summary = profile.get("profile_summary", "")
    if summary:
        st.info(summary)

    # --- Informations principales ---
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Informations Clés")
        seniority = profile.get("seniority_level", "")
        st.markdown(f"**Niveau :** {SENIORITY_LABELS.get(seniority, seniority.capitalize())}")

        availability = profile.get("availability", "Non précisée")
        st.markdown(f"**Disponibilité :** {availability}")

        contracts = profile.get("contract_types", [])
        if contracts:
            st.markdown(f"**Contrats :** {', '.join(contracts)}")

        locations = profile.get("target_locations", [])
        if locations:
            loc_str = ", ".join(
                f"{loc.get('city', '')} ({loc.get('postal_code', '')})"
                for loc in locations
            )
            st.markdown(f"**Localisation :** {loc_str}")

        radius = profile.get("search_radius_km", 30)
        st.markdown(f"**Rayon de recherche :** {radius} km")

        langs = profile.get("languages", [])
        if langs:
            lang_str = ", ".join(LANGUAGE_LABELS.get(l, l) for l in langs)
            st.markdown(f"**Langues :** {lang_str}")

        mobility = profile.get("mobility", {})
        mob_parts = []
        if mobility.get("remote"):
            mob_parts.append("Télétravail ✓")
        if mobility.get("travel_accepted"):
            mob_parts.append("Déplacements ✓")
        if mobility.get("international"):
            mob_parts.append("International ✓")
        if mob_parts:
            st.markdown(f"**Mobilité :** {' | '.join(mob_parts)}")

        company_sizes = profile.get("company_size_preference", [])
        if company_sizes:
            st.markdown(f"**Taille entreprise :** {', '.join(company_sizes)}")

        salary = profile.get("salary_expectation", "")
        if salary:
            st.markdown(f"**Prétentions :** {salary}")

    with col2:
        st.markdown("#### Compétences")
        must_have = profile.get("must_have_skills", [])
        if must_have:
            st.markdown("**Non-négociables :**")
            for skill in must_have:
                st.markdown(f"- {skill}")

        nice_to_have = profile.get("nice_to_have_skills", [])
        if nice_to_have:
            st.markdown("**Bonus :**")
            for skill in nice_to_have:
                st.markdown(f"- {skill}")

        exclusions = profile.get("exclusion_list", [])
        if exclusions:
            st.markdown("**À exclure :**")
            for excl in exclusions:
                st.markdown(f"- ~~{excl}~~")

    # --- Codes NACE ---
    st.markdown("---")
    st.markdown("#### Codes NACE Cibles")
    st.caption(
        "Ces codes NACE belges seront utilisés pour interroger la BCE "
        "et trouver les entreprises correspondantes à votre profil."
    )

    nace_codes = sorted(
        profile.get("nace_codes", []),
        key=lambda x: x.get("weight", 0),
        reverse=True
    )

    for nace in nace_codes:
        weight = nace.get("weight", 0)
        pct = int(weight * 100)
        code = nace.get("code", "")
        label = nace.get("label", "")
        justif = nace.get("justification", "")

        col_code, col_bar, col_pct = st.columns([1, 4, 1])
        with col_code:
            if weight >= 0.8:
                st.markdown(f"**{code}**")
            else:
                st.markdown(f"{code}")
        with col_bar:
            st.markdown(f"{label}")
            if justif:
                st.caption(justif)
        with col_pct:
            st.markdown(f"**{pct}%**")

        st.progress(weight)

    # --- Mode édition ---
    st.markdown("---")
    st.markdown("#### Corrections manuelles")
    st.caption("Vous pouvez modifier directement les champs sensibles avant validation.")

    with st.expander("Modifier le résumé", expanded=False):
        new_summary = st.text_area(
            "Résumé", value=profile.get("profile_summary", ""), height=100, key="edit_summary"
        )
        if st.button("Sauvegarder le résumé"):
            st.session_state.p1_profile["profile_summary"] = new_summary
            st.success("Résumé mis à jour")
            st.rerun()

    with st.expander("Modifier le rayon de recherche", expanded=False):
        new_radius = st.slider(
            "Rayon en km", min_value=5, max_value=200,
            value=profile.get("search_radius_km", 30), step=5, key="edit_radius"
        )
        if st.button("Sauvegarder le rayon"):
            st.session_state.p1_profile["search_radius_km"] = new_radius
            st.success("Rayon mis à jour")
            st.rerun()

    # --- Boutons d'action ---
    st.markdown("---")
    col_back, col_validate = st.columns(2)

    with col_back:
        if st.button("← Modifier ma description", use_container_width=True):
            st.session_state.p1_step = "follow_up"
            st.rerun()

    with col_validate:
        can_validate = completeness >= 60
        validate_help = (
            "Complétez d'abord les informations manquantes" if not can_validate else
            "Valider et passer à la Phase 2 — Recherche BCE"
        )
        if st.button(
            "Valider ce profil → Phase 2",
            type="primary",
            disabled=not can_validate,
            use_container_width=True,
            help=validate_help
        ):
            _save_and_validate_profile(session_id, profile)


# ============================================================
# Sauvegarde et validation
# ============================================================

def _save_and_validate_profile(session_id: str, profile: dict):
    """Sauvegarde le profil validé en base et passe à la Phase 2."""
    try:
        with get_session() as db:
            session_obj = db.get(DbSession, session_id)
            if session_obj:
                session_obj.operator_profile = profile
                session_obj.p1_validated = True
                session_obj.current_phase = 2
                db.commit()

        st.session_state.p1_step = "validated"
        st.session_state.current_phase = 2
        st.success("Profil validé et sauvegardé !")
        st.rerun()

    except Exception as e:
        logger.exception("Erreur lors de la sauvegarde du profil")
        st.error(f"Erreur lors de la sauvegarde : {e}")


# ============================================================
# Étape 3 — Profil validé
# ============================================================

def _render_validated_step(session_id: str):
    profile = st.session_state.p1_profile

    st.success("**Profil validé !** Vous pouvez maintenant passer à la Phase 2.")

    # Résumé compact du profil
    st.markdown("### Votre Profil Validé")

    col1, col2, col3 = st.columns(3)
    with col1:
        nace_count = len(profile.get("nace_codes", []))
        st.metric("Codes NACE", nace_count)
    with col2:
        radius = profile.get("search_radius_km", 30)
        st.metric("Rayon recherche", f"{radius} km")
    with col3:
        completeness = get_profile_completeness_pct(profile)
        st.metric("Complétude profil", f"{completeness}%")

    st.info(profile.get("profile_summary", ""))

    # Top codes NACE
    nace_codes = sorted(
        profile.get("nace_codes", []),
        key=lambda x: x.get("weight", 0),
        reverse=True
    )[:5]

    if nace_codes:
        st.markdown("**Top codes NACE sélectionnés :**")
        for n in nace_codes:
            st.markdown(
                f"- **{n.get('code')}** — {n.get('label')} "
                f"(priorité : {int(n.get('weight', 0) * 100)}%)"
            )

    st.markdown("---")

    col_edit, col_next = st.columns(2)
    with col_edit:
        if st.button("✏️ Modifier le profil", use_container_width=True):
            st.session_state.p1_step = "review"
            st.rerun()
    with col_next:
        if st.button(
            "Lancer la recherche BCE (Phase 2) →",
            type="primary",
            use_container_width=True
        ):
            st.session_state.current_page = "Phase 2 — Recherche BCE"
            st.rerun()
