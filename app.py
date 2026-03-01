"""
PROSPECT-AI — Application principale Streamlit
Agent intelligent de recherche d'opportunités professionnelles en Belgique

Lancement : streamlit run app.py
"""

import uuid
import streamlit as st
from loguru import logger

from config.settings import settings
from database.connection import init_db, get_session
from database.models import Session as DbSession

# Pages UI
from ui.phase1_page import render_phase1_page
from ui.phase2_page import render_phase2_page
from ui.phase3_page import render_phase3_page
from ui.phase4_page import render_phase4_page
from ui.phase5_page import render_phase5_page
from ui.settings_page import render_settings_page


# ============================================================
# Configuration Streamlit
# ============================================================
st.set_page_config(
    page_title="PROSPECT-AI",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialisation base de données au démarrage
init_db()


# ============================================================
# Styles CSS personnalisés
# ============================================================
st.markdown("""
<style>
    /* Sidebar */
    .css-1d391kg { background-color: #1e1e2e; }

    /* Phases désactivées dans la sidebar */
    .phase-disabled { opacity: 0.4; cursor: not-allowed; }

    /* Badge de phase */
    .phase-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-done { background: #22c55e; color: white; }
    .badge-active { background: #3b82f6; color: white; }
    .badge-pending { background: #64748b; color: white; }

    /* Cartes de métriques */
    [data-testid="stMetricValue"] { font-size: 1.8rem; }

    /* Barre de progression NACE */
    .stProgress > div > div { background-color: #3b82f6; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Initialisation de la session utilisateur
# ============================================================
def init_session_state():
    """Initialise les variables d'état globales."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Accueil"
    if "current_phase" not in st.session_state:
        st.session_state.current_phase = 1


def create_new_session(operator_name: str = "") -> str:
    """Crée une nouvelle session en base et retourne son ID."""
    session_id = str(uuid.uuid4())
    try:
        with get_session() as db:
            session = DbSession(
                session_id=session_id,
                operator_name=operator_name or "Opérateur",
                current_phase=1,
                status="active"
            )
            db.add(session)
            db.commit()
        logger.info(f"Nouvelle session créée : {session_id[:8]}")
    except Exception as e:
        logger.error(f"Erreur création session : {e}")
    return session_id


def load_existing_sessions() -> list[dict]:
    """Charge la liste des sessions existantes depuis la base."""
    try:
        with get_session() as db:
            sessions = db.query(DbSession).filter(
                DbSession.status != "archived"
            ).order_by(DbSession.updated_at.desc()).limit(10).all()
            return [
                {
                    "id": s.session_id,
                    "name": s.operator_name or "Sans nom",
                    "phase": s.current_phase,
                    "updated": s.updated_at.strftime("%d/%m/%Y %H:%M") if s.updated_at else "",
                    "p1_ok": s.p1_validated,
                }
                for s in sessions
            ]
    except Exception:
        return []


# ============================================================
# Sidebar — Navigation
# ============================================================
def render_sidebar():
    """Rendu de la barre latérale de navigation."""
    with st.sidebar:
        # Logo / Titre
        st.markdown("# 🎯 PROSPECT-AI")
        st.markdown("*Agent intelligent — Belgique*")
        st.markdown("---")

        # Vérification clé API
        if not settings.has_anthropic_key:
            st.error("⚠️ Clé API Claude manquante\nAjoutez ANTHROPIC_API_KEY dans .env")

        # Session active
        session_id = st.session_state.get("session_id")
        if session_id:
            # Indicateurs de phases
            p1_done = st.session_state.get("p1_step") == "validated"
            current_phase = st.session_state.get("current_phase", 1)

            st.markdown("### Navigation")

            pages = [
                ("Phase 1 — Profiling", 1, True),
                ("Phase 2 — Recherche BCE", 2, p1_done),
                ("Phase 3 — Scoring", 3, current_phase >= 3),
                ("Phase 4 — Dossiers", 4, current_phase >= 4),
                ("Phase 5 — Préparation", 5, current_phase >= 5),
            ]

            for page_name, phase_num, enabled in pages:
                if enabled:
                    is_active = st.session_state.current_page == page_name
                    if st.button(
                        page_name,
                        key=f"nav_{phase_num}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True
                    ):
                        st.session_state.current_page = page_name
                        st.rerun()
                else:
                    st.button(
                        f"🔒 {page_name}",
                        key=f"nav_{phase_num}",
                        disabled=True,
                        use_container_width=True,
                        help="Complétez la phase précédente pour déverrouiller"
                    )

            st.markdown("---")

            # Info session
            st.markdown(f"**Session :** `{session_id[:8]}...`")
            if st.button("⊕ Nouvelle session", use_container_width=True):
                _reset_session()
                st.rerun()

        else:
            st.markdown("### Sessions récentes")
            sessions = load_existing_sessions()
            if sessions:
                for s in sessions[:5]:
                    phase_icon = "✅" if s["p1_ok"] else "▶️"
                    if st.button(
                        f"{phase_icon} {s['name']} — P{s['phase']} ({s['updated']})",
                        key=f"load_{s['id']}",
                        use_container_width=True,
                    ):
                        _load_session(s["id"])
                        st.rerun()
                st.markdown("---")

            if st.button("⊕ Démarrer une nouvelle session", type="primary", use_container_width=True):
                new_id = create_new_session()
                st.session_state.session_id = new_id
                st.session_state.current_page = "Phase 1 — Profiling"
                st.rerun()

        # Bouton Paramètres — toujours accessible
        st.markdown("---")
        is_settings = st.session_state.current_page == "Paramètres"
        if st.button(
            "⚙️ Paramètres",
            key="nav_settings",
            type="primary" if is_settings else "secondary",
            use_container_width=True,
        ):
            st.session_state.current_page = "Paramètres"
            st.rerun()

        # Pied de page
        st.markdown("---")
        st.caption(f"v{settings.APP_VERSION} | Belgique")
        st.caption(f"LLM : {settings.provider_label}")


def _reset_session():
    """Réinitialise complètement la session Streamlit."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.current_page = "Accueil"


def _load_session(session_id: str):
    """Charge une session existante depuis la base."""
    try:
        with get_session() as db:
            s = db.get(DbSession, session_id)
            if s:
                st.session_state.session_id = session_id
                st.session_state.current_phase = s.current_phase
                st.session_state.current_page = f"Phase {s.current_phase} — Profiling" if s.current_phase == 1 else f"Phase {s.current_phase}"

                if s.p1_validated and s.operator_profile:
                    st.session_state.p1_profile = s.operator_profile
                    st.session_state.p1_step = "validated"
                    st.session_state.current_page = "Phase 1 — Profiling"
    except Exception as e:
        st.error(f"Erreur chargement session : {e}")


# ============================================================
# Page d'Accueil
# ============================================================
def render_home():
    st.markdown("# 🎯 PROSPECT-AI")
    st.markdown("### Agent intelligent de recherche d'opportunités professionnelles en Belgique")

    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**🇧🇪 Sources officielles**\nBCE / KBO, BNB — données belges vérifiées")
    with col2:
        st.info(f"**LLM : {settings.provider_label}**\nAnalyse de profil, scoring, génération de contenu")
    with col3:
        st.info("**📋 5 phases automatisées**\nDe votre profil au kit d'entretien complet")

    st.markdown("---")
    st.markdown("## Comment ça marche ?")

    phases = [
        ("1", "Profiling Opérateur", "Décrivez votre situation. L'IA extrait votre profil et génère les codes NACE belges cibles.", "✅ Disponible"),
        ("2", "Recherche BCE / KBO", "Recherche dans la base officielle KBO (1,9M entreprises belges) via index local.", "✅ Disponible"),
        ("3", "Filtrage & Scoring", "Score de match (0-100) par entreprise sur 3 critères pondérés. Sélection des 100 meilleures.", "✅ Disponible"),
        ("4", "Dossiers Entreprises", "Fiche complète : finances, décideurs, actualités, offres d'emploi via DuckDuckGo + LLM.", "✅ Disponible"),
        ("5", "Kit de Préparation", "Messages d'accroche personnalisés, situations ambiguës, questions clés, résumé exportable.", "✅ Disponible"),
    ]

    for num, name, desc, status in phases:
        with st.expander(f"Phase {num} — {name} &nbsp;&nbsp; {status}", expanded=(num == "1")):
            st.markdown(desc)

    st.markdown("---")

    if not settings.has_llm_key:
        key_name = "GROQ_API_KEY" if settings.LLM_PROVIDER == "groq" else "ANTHROPIC_API_KEY"
        st.error(
            f"**Configuration requise :** Copiez `.env.example` en `.env` "
            f"et ajoutez votre clé `{key_name}`."
        )
    else:
        st.success(f"Provider configuré : {settings.provider_label}. Prêt à démarrer.")

    col_start, _ = st.columns([1, 2])
    with col_start:
        if st.button("🚀 Démarrer une nouvelle session", type="primary", use_container_width=True):
            new_id = create_new_session()
            st.session_state.session_id = new_id
            st.session_state.current_page = "Phase 1 — Profiling"
            st.rerun()


# ============================================================
# Point d'entrée principal
# ============================================================
def main():
    init_session_state()
    render_sidebar()

    session_id = st.session_state.get("session_id")
    current_page = st.session_state.get("current_page", "Accueil")

    # Routing
    if current_page == "Paramètres":
        render_settings_page()
    elif current_page == "Accueil" or not session_id:
        render_home()
    elif current_page == "Phase 1 — Profiling":
        render_phase1_page(session_id)
    elif current_page == "Phase 2 — Recherche BCE":
        render_phase2_page(session_id)
    elif current_page == "Phase 3 — Scoring":
        render_phase3_page(session_id)
    elif current_page == "Phase 4 — Dossiers":
        render_phase4_page(session_id)
    elif current_page == "Phase 5 — Préparation":
        render_phase5_page(session_id)
    else:
        render_home()


if __name__ == "__main__":
    main()
