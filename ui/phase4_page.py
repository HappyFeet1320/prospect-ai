"""
UI Streamlit — Phase 4 : Recherche Approfondie par Entreprise.

Architecture UI sans st.tabs() dans st.expander() (bug Streamlit connu).
Approche : sélecteur d'entreprise + dossier complet affiché en dessous.
"""

import streamlit as st
from loguru import logger

from phases.phase4.runner import (
    run_phase4, validate_phase4, load_phase4_results,
    update_company_selection,
)
from phases.phase4.enricher import EnrichConfig


# ============================================================
# Point d'entrée
# ============================================================

def render_phase4_page(session_id: str):
    st.markdown("## Phase 4 — Recherche Approfondie par Entreprise")
    st.markdown(
        "Constitution d'un dossier complet pour chaque entreprise sélectionnée : "
        "identité, finances, commercial, décideurs et signaux de recrutement."
    )

    profile = st.session_state.get("p1_profile", {})

    if "p4_step" not in st.session_state:
        st.session_state.p4_step = "config"
    if "p4_result" not in st.session_state:
        st.session_state.p4_result = None
    if "p4_selected_idx" not in st.session_state:
        st.session_state.p4_selected_idx = 0
    if "p4_enrich_mode" not in st.session_state:
        st.session_state.p4_enrich_mode = "Rapide"

    step = st.session_state.p4_step

    if step == "config":
        _render_config(session_id, profile)
    elif step == "enriching":
        _render_enriching(session_id, profile)
    elif step == "review":
        _render_review(session_id)
    elif step == "validated":
        _render_validated(session_id)


# ============================================================
# Étape 1 — Configuration
# ============================================================

_MODE_LABELS = ["Rapide", "Standard (bêta)", "Complet (bêta)", "Web seulement (bêta)"]
_MODE_DETAILS = {
    "Rapide": {
        "icon": "⚡",
        "desc": "CBE API uniquement — coordonnées officielles (email, tél, site web)",
        "time": "~2-5s / entreprise",
        "sources": ["🏛 CBE API"],
        "stable": True,
    },
    "Standard (bêta)": {
        "icon": "⚖️",
        "desc": "CBE API + scraping site web + DDG (actualités, emplois, dirigeants)",
        "time": "~30-45s / entreprise",
        "sources": ["🏛 CBE API", "🌐 Site web", "📰 Actualités", "💼 Emplois", "👤 Dirigeants"],
        "stable": False,
    },
    "Complet (bêta)": {
        "icon": "🔬",
        "desc": "Tout activé — LinkedIn et données financières NBB en plus",
        "time": "~60-90s / entreprise",
        "sources": ["🏛 CBE API", "🌐 Site web", "📰 Actualités", "💼 Emplois",
                    "👤 Dirigeants", "🔗 LinkedIn", "💰 Financier"],
        "stable": False,
    },
    "Web seulement (bêta)": {
        "icon": "🌐",
        "desc": "Scraping + DDG sans CBE API — utile si clé non configurée",
        "time": "~30-45s / entreprise",
        "sources": ["🌐 Site web", "📰 Actualités", "💼 Emplois", "👤 Dirigeants"],
        "stable": False,
    },
}


def _mode_to_config(mode: str) -> EnrichConfig:
    """Convertit le label de mode en EnrichConfig."""
    if mode == "Rapide":
        return EnrichConfig.rapide()
    if mode.startswith("Complet"):
        return EnrichConfig.complet()
    if mode.startswith("Web seulement"):
        return EnrichConfig.web_seulement()
    if mode.startswith("Standard"):
        return EnrichConfig.standard()
    return EnrichConfig.rapide()  # défaut sécurisé


def _render_config(session_id: str, profile: dict):
    from config.settings import settings
    existing     = load_phase4_results(session_id)
    has_existing = bool(existing)
    cbeapi_active = settings.has_cbeapi_key

    if has_existing:
        st.info(f"Dossiers Phase 4 existants : **{len(existing)}** entreprise(s).")

    # ── Tableau des blocs produits ────────────────────────────
    if not has_existing:
        st.markdown("""
L'agent va enrichir chaque entreprise sélectionnée (Phase 3) avec :

| Bloc | Contenu |
|------|---------|
| **Identité** | Description IA, site web, email, téléphone, ancienneté |
| **Financier** | Tendance, CA estimé, effectif, signal risque |
| **Commercial** | Clients, partenaires, marchés, certifications |
| **Décideurs** | CEO, DRH, responsables identifiés via web |
| **Recrutement** | Offres actives, signaux croissance/difficulté |
        """)

    # ── Sélecteur de mode ─────────────────────────────────────
    st.markdown("#### Mode d'enrichissement")

    # Masquer "Web seulement" si CBE API est active (peu utile)
    available_modes = _MODE_LABELS if not cbeapi_active else _MODE_LABELS[:-1]

    current_mode = st.session_state.p4_enrich_mode
    if current_mode not in available_modes:
        current_mode = "Standard"

    selected_mode = st.radio(
        "Source des données",
        options=available_modes,
        index=available_modes.index(current_mode),
        horizontal=True,
        key="p4_mode_radio",
        label_visibility="collapsed",
    )
    st.session_state.p4_enrich_mode = selected_mode

    detail = _MODE_DETAILS.get(selected_mode, _MODE_DETAILS["Rapide"])
    col_d, col_t = st.columns([3, 1])
    with col_d:
        st.markdown(f"{detail['icon']} {detail['desc']}")
        st.caption("Sources : " + "  ·  ".join(detail["sources"]))
    with col_t:
        st.metric("Durée estimée", detail["time"])

    # Alerte si mode bêta sélectionné
    if not detail.get("stable", True):
        st.warning(
            "⚠️ **Module en développement** — Ce mode utilise la recherche web (DuckDuckGo + scraping). "
            "Il peut être instable selon la disponibilité des sites. "
            "Préférez le mode **Rapide** pour un enrichissement fiable."
        )

    # Alerte CBE API
    cfg_preview = _mode_to_config(selected_mode)
    if cfg_preview.use_cbe_api and not cbeapi_active:
        st.warning(
            "⚠️ CBE API sélectionnée mais `CBEAPI_KEY` absent du `.env`. "
            "Les coordonnées officielles ne seront pas récupérées."
        )
    elif cbeapi_active and not cfg_preview.use_cbe_api:
        st.info("ℹ️ CBE API disponible mais non utilisée dans ce mode.")
    elif cbeapi_active and cfg_preview.use_cbe_api:
        st.success("🏛 **CBE API activée** — coordonnées officielles incluses.")

    st.markdown("")

    # ── 3 boutons TOUJOURS présents — structure DOM stable ───
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← Phase 3", key="p4_cfg_back", use_container_width=True):
            st.session_state.current_page = "Phase 3 — Scoring"
            st.rerun()

    with col2:
        if st.button(
            "Consulter les dossiers",
            key="p4_cfg_consult",
            type="primary" if has_existing else "secondary",
            use_container_width=True,
            disabled=not has_existing,
            help="Consultez les dossiers existants." if has_existing else "Aucun dossier disponible.",
        ):
            st.session_state.p4_result = existing
            st.session_state.p4_step   = "review"
            st.rerun()

    with col3:
        launch_label = "Relancer l'enrichissement" if has_existing else "Lancer →"
        if st.button(
            launch_label,
            key="p4_cfg_launch",
            type="secondary" if has_existing else "primary",
            use_container_width=True,
        ):
            st.session_state.p4_step = "enriching"
            st.rerun()


# ============================================================
# Étape 2 — Enrichissement en cours
# ============================================================

def _render_enriching(session_id: str, profile: dict):
    mode          = st.session_state.get("p4_enrich_mode", "Standard")
    enrich_config = _mode_to_config(mode)
    detail        = _MODE_DETAILS.get(mode, _MODE_DETAILS["Rapide"])

    st.markdown(f"### {detail['icon']} Enrichissement {mode} en cours…")
    st.caption(f"{detail['desc']} — {detail['time']}. Veuillez patienter.")

    global_bar = st.progress(0.0, text="Initialisation…")
    log_area   = st.empty()
    logs: list[str] = []

    def on_progress(name: str, current: int, total: int, status: str):
        pct  = current / max(total, 1)
        icon = {"running": "🔍", "done": "✅", "error": "❌"}.get(status, "⏳")
        global_bar.progress(pct, text=f"{icon} {name[:55]} ({current}/{total})")
        if status in ("done", "error"):
            logs.append(f"{icon} {name[:55]}")
            log_area.markdown("\n".join(logs))

    try:
        from phases.phase4.runner import run_phase4, Phase4Result
        result: Phase4Result = run_phase4(
            session_id=session_id,
            profile=profile,
            enrich_config=enrich_config,
            progress_callback=on_progress,
        )
        global_bar.progress(1.0, text="Recherche terminée !")
        for w in result.warnings:
            st.warning(w)
        st.session_state.p4_result      = result.companies
        st.session_state.p4_step        = "review"
        st.session_state.p4_selected_idx = 0
        st.rerun()

    except Exception as e:
        logger.exception("Erreur Phase 4")
        st.error(f"Erreur : {e}")
        if st.button("← Retour", key="p4_enrich_err_back"):
            st.session_state.p4_step = "config"
            st.rerun()


# ============================================================
# Étape 3 — Consultation des dossiers
# ============================================================

def _render_review(session_id: str):
    companies = st.session_state.get("p4_result") or load_phase4_results(session_id)

    if not companies:
        st.warning("Aucun dossier disponible.")
        if st.button("← Retour", key="p4_review_no_data_back"):
            st.session_state.p4_step = "config"
            st.rerun()
        return

    # ── Métriques ────────────────────────────────────────────
    selected_count = sum(1 for c in companies if c.get("is_selected", False))
    enriched_count = len(companies)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Dossiers enrichis", enriched_count)
    col2.metric("Favoris sélectionnés", selected_count)
    col3.metric("Notés", sum(1 for c in companies if c.get("operator_rating")))
    col4.metric("Prêt Phase 5", "✓" if enriched_count >= 1 else "⚠️")

    st.markdown("---")

    # ── Sélecteur d'entreprise ────────────────────────────────
    names = []
    for c in companies:
        r    = c.get("operator_rating") or 0
        sel  = "✅ " if c.get("is_selected") else ""
        star = "★" * r + "☆" * (5 - r)
        sc   = int(c.get("phase3_score", 0) * 100)
        names.append(f"{sel}{c.get('denomination','?')[:45]}  [{sc}% — {star}]")

    idx = st.selectbox(
        "Choisir une entreprise à consulter",
        options=range(len(names)),
        format_func=lambda i: names[i],
        index=min(st.session_state.p4_selected_idx, len(names) - 1),
        key="p4_company_selectbox",
    )
    st.session_state.p4_selected_idx = idx

    company = companies[idx]
    st.markdown("---")

    # ── Dossier de l'entreprise sélectionnée ─────────────────
    _render_dossier(company, idx)

    st.markdown("---")

    # ── Actions globales ─────────────────────────────────────
    col_back, col_redo, col_validate = st.columns(3)
    with col_back:
        if st.button("← Phase 3", key="p4_review_back", use_container_width=True):
            st.session_state.current_page = "Phase 3 — Scoring"
            st.rerun()
    with col_redo:
        if st.button("Relancer l'enrichissement", key="p4_review_redo", use_container_width=True):
            st.session_state.p4_step = "enriching"
            st.rerun()
    with col_validate:
        if st.button(
            "Valider → Phase 5",
            key="p4_review_validate",
            type="primary",
            disabled=(enriched_count < 1),
            use_container_width=True,
            help="Enrichissez au moins 1 entreprise (Phase 4) pour continuer." if enriched_count < 1 else "",
        ):
            _validate(session_id)


# ============================================================
# Dossier complet d'une entreprise
# ============================================================

def _render_dossier(company: dict, idx: int):
    """Affiche le dossier complet — pas de tabs ni d'expanders imbriqués."""
    dossier  = company.get("phase4_dossier", {})
    name     = company.get("denomination", "")
    cid      = company.get("company_id", f"c{idx}")
    score    = company.get("phase3_score", 0.0)
    rating   = company.get("operator_rating") or 0
    is_sel   = company.get("is_selected", False)
    identite = dossier.get("bloc_identite", {})

    # ── En-tête ──────────────────────────────────────────────
    col_h, col_r = st.columns([3, 1])
    with col_h:
        st.markdown(f"### {name}")
        st.caption(
            f"BCE : {company.get('bce_number','')}  |  "
            f"{identite.get('legal_form','')}  |  "
            f"{identite.get('city','')}  |  "
            f"Créée en {identite.get('creation_year','?')}  |  "
            f"Score Phase 3 : {int(score*100)}%"
        )
        # Description IA
        desc = identite.get("description_ia", "")
        if desc:
            st.info(desc)
        # Liens
        website = dossier.get("website_url", "") or identite.get("website_url", "")
        bce_url = (
            "https://kbopub.economie.fgov.be/kbopub/zoeknummerAction.do"
            f"?nummer={company.get('bce_number','')}"
        )
        links = [f"[📋 Fiche BCE]({bce_url})"]
        if website:
            links.insert(0, f"[🌐 Site web]({website})")
        st.markdown("  |  ".join(links))

    with col_r:
        st.markdown("**Votre notation**")
        new_rating = st.slider(
            "Étoiles",
            min_value=1, max_value=5,
            value=max(1, rating),
            key=f"p4_rating_{idx}",
        )
        st.markdown(
            f"<div style='text-align:center;font-size:1.5em'>"
            f"{'★'*new_rating}{'☆'*(5-new_rating)}"
            f"</div>",
            unsafe_allow_html=True,
        )
        new_sel = st.checkbox(
            "Sélectionner pour Phase 5",
            value=is_sel,
            key=f"p4_sel_{idx}",
        )
        new_notes = st.text_area(
            "Notes",
            value=company.get("operator_notes", ""),
            height=80,
            key=f"p4_notes_{idx}",
            placeholder="Observations, points d'attention…",
        )
        if st.button("💾 Enregistrer", key=f"p4_save_{idx}", use_container_width=True):
            update_company_selection(
                company_id=cid,
                rating=new_rating,
                is_selected=new_sel,
                notes=new_notes,
            )
            company["operator_rating"] = new_rating
            company["is_selected"]     = new_sel
            company["operator_notes"]  = new_notes
            st.success("Enregistré !")

    st.markdown("---")

    # ── 5 sections (sans tabs ni expanders imbriqués) ────────
    _section_identite(identite, dossier)
    st.markdown("---")
    _section_financier(dossier.get("bloc_financier", {}))
    st.markdown("---")
    _section_commercial(dossier.get("bloc_commercial", {}))
    st.markdown("---")
    _section_decideurs(dossier.get("bloc_decideurs", []), company)
    st.markdown("---")
    _section_recrutement(dossier.get("bloc_recrutement", {}))


# ── Sections ─────────────────────────────────────────────────

def _section_identite(ident: dict, dossier: dict):
    st.markdown("#### 🏢 Identité")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**BCE** : {ident.get('bce_number','—')}")
        st.markdown(f"**Forme juridique** : {ident.get('legal_form','—')}")
        # Date précise si disponible via CBE API, sinon année KBO
        start_date = ident.get("start_date_bce") or ident.get("creation_year") or "—"
        age_suffix = f" ({ident['age_years']} ans)" if ident.get("age_years") else ""
        st.markdown(f"**Création** : {start_date}{age_suffix}")
        if ident.get("juridical_situation"):
            st.markdown(f"**Situation** : {ident['juridical_situation']}")
    with col2:
        st.markdown(f"**Ville** : {ident.get('city','—')}")
        st.markdown(f"**Province** : {ident.get('province','—')}")
        st.markdown(f"**Code postal** : {ident.get('postal_code','—')}")
    with col3:
        _render_contacts(ident)
    if ident.get("address"):
        st.caption(f"Adresse : {ident['address']}")


def _section_financier(fin: dict):
    st.markdown("#### 💰 Financier")
    if not fin or fin.get("tendance") == "inconnu":
        st.caption("Données financières non disponibles publiquement.")
        if fin.get("signal_label"):
            st.markdown(fin["signal_label"])
        return

    tendance = fin.get("tendance", "inconnu")
    icon = {"croissance": "📈", "stable": "➡️", "déclin": "📉"}.get(tendance, "❓")
    st.markdown(f"{icon} **{fin.get('signal_label', '')}**")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tendance", tendance.capitalize())
    col2.metric("CA estimé", fin.get("ca_estime") or "N/D")
    col3.metric("Effectif estimé", fin.get("effectif_estime") or "N/D")
    col4.metric("Risque", fin.get("risque","—").capitalize())

    if fin.get("evolution"):
        st.caption(f"Évolution : {fin['evolution']}")
    if fin.get("note"):
        st.caption(f"ℹ️ {fin['note']}")


def _section_commercial(com: dict):
    st.markdown("#### 📈 Commercial")
    if not com:
        st.caption("Données commerciales non disponibles.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Type de clientèle** : {com.get('type_clientele') or '—'}")
        st.markdown(f"**Marchés** : {com.get('marches') or '—'}")
        clients = com.get("clients_connus", [])
        if clients:
            st.markdown("**Clients connus :**")
            for c in clients[:8]:
                st.markdown(f"  - {c}")
        refs = com.get("references", [])
        if refs:
            st.markdown("**Références :**")
            for r in refs[:3]:
                st.caption(r)
    with col2:
        partners = com.get("partenaires", [])
        if partners:
            st.markdown("**Partenaires :**")
            for p in partners[:5]:
                st.markdown(f"  - {p}")
        certs = com.get("certifications", [])
        if certs:
            st.markdown("**Certifications / Labels :**")
            for c in certs[:4]:
                st.markdown(f"  - {c}")
        offers = com.get("offres_emploi", [])
        if offers:
            st.markdown("**Offres d'emploi détectées :**")
            for o in offers[:4]:
                st.markdown(f"  🔵 {o}")


def _section_decideurs(decideurs: list, company: dict):
    st.markdown("#### 👤 Décideurs Clés")
    if not decideurs:
        name = company.get("denomination", "")
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={name.replace(' ', '%20')}"
        st.caption(f"Aucun décideur identifié automatiquement. [Rechercher sur LinkedIn]({search_url})")
        return

    cols = st.columns(min(len(decideurs), 3))
    for i, dm in enumerate(decideurs[:6]):
        col = cols[i % len(cols)]
        with col:
            dm_type = dm.get("type", "AUTRE")
            icon = {"CEO": "👔", "DRH": "👥", "DEPT_HEAD": "🏗️", "OFFICE_MGR": "🗂️"}.get(dm_type, "👤")
            source = dm.get("source", "")
            src_icon = {"site_web": "🌐", "recherche_web": "🔍", "estimation_ia": "🤖"}.get(source, "")

            st.markdown(f"**{icon} {dm.get('prenom_nom','—')}** {src_icon}")
            st.caption(dm.get("titre", ""))
            if dm.get("bio_courte"):
                st.markdown(f"_{dm['bio_courte']}_")
            links_parts = []
            if dm.get("linkedin_url"):
                links_parts.append(f"[LinkedIn]({dm['linkedin_url']})")
            if dm.get("email"):
                links_parts.append(f"`{dm['email']}`")
            if links_parts:
                st.markdown(" | ".join(links_parts))
            st.markdown("")


def _section_recrutement(rec: dict):
    st.markdown("#### 🔍 Contexte Recrutement")
    if not rec:
        st.caption("Données non disponibles.")
        return

    if rec.get("contexte_rh"):
        st.markdown(rec["contexte_rh"])

    col1, col2 = st.columns(2)
    with col1:
        pos = rec.get("signaux_croissance", [])
        st.markdown("**Signaux positifs** 📈")
        if pos:
            for s in pos:
                st.markdown(f"  ✅ {s}")
        else:
            st.caption("Aucun signal positif détecté.")
    with col2:
        neg = rec.get("signaux_difficulte", [])
        st.markdown("**Signaux de difficulté** ⚠️")
        if neg:
            for s in neg:
                st.markdown(f"  🔴 {s}")
        else:
            st.caption("Aucun signal négatif détecté.")

    offres = rec.get("offres_actives", [])
    if offres:
        st.markdown("**Offres d'emploi actives :**")
        for o in offres[:5]:
            st.markdown(f"  🔵 {o}")

    if rec.get("derniere_mention"):
        st.caption(f"Dernière mention presse : {rec['derniere_mention']}")


# ============================================================
# Helpers
# ============================================================

def _render_contacts(ident: dict):
    """Affiche les coordonnées de contact avec badge de source (BCE / scraping)."""
    email_bce   = ident.get("email_bce", "")
    phone_bce   = ident.get("phone_bce", "")
    website_bce = ident.get("website_bce", "")
    email_gen   = ident.get("email_general", "")
    telephone   = ident.get("telephone", "")
    website_url = ident.get("website_url", "")

    # Email
    if email_bce:
        st.markdown(f"**Email** : {email_bce} `🏛 BCE`")
    elif email_gen:
        st.markdown(f"**Email** : {email_gen} `🔍 web`")

    # Téléphone
    if phone_bce:
        st.markdown(f"**Tél** : {phone_bce} `🏛 BCE`")
    elif telephone:
        st.markdown(f"**Tél** : {telephone} `🔍 web`")

    # Site web
    if website_bce:
        st.markdown(f"**Site** : [{website_bce}]({website_bce}) `🏛 BCE`")
    elif website_url:
        st.markdown(f"**Site** : [{website_url}]({website_url}) `🔍 web`")

    if not any([email_bce, email_gen, phone_bce, telephone, website_bce, website_url]):
        st.caption("Aucun contact disponible")

    # Réseaux sociaux
    if ident.get("reseaux_sociaux"):
        socials = ident["reseaux_sociaux"]
        links = " | ".join(f"[{_social_name(s)}]({s})" for s in socials[:4])
        st.markdown(f"**Réseaux** : {links}")


def _social_name(url: str) -> str:
    if "linkedin" in url:
        return "LinkedIn"
    if "facebook" in url:
        return "Facebook"
    if "twitter" in url or "x.com" in url:
        return "Twitter/X"
    if "instagram" in url:
        return "Instagram"
    if "youtube" in url:
        return "YouTube"
    return "Réseau social"


# ============================================================
# Validation
# ============================================================

def _validate(session_id: str):
    try:
        validate_phase4(session_id)
        st.session_state.p4_step = "validated"
        st.session_state.current_phase = 5
        st.success("Phase 4 validée !")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur : {e}")


# ============================================================
# Étape 4 — Validée
# ============================================================

def _render_validated(session_id: str):
    companies = load_phase4_results(session_id)
    selected  = [c for c in companies if c.get("is_selected")]

    st.success("**Phase 4 validée !**")
    col1, col2, col3 = st.columns(3)
    col1.metric("Dossiers constitués", len(companies))
    col2.metric("Favoris sélectionnés", len(selected))
    col3.metric("Prochaine étape", "Phase 5 — Kit entretien")

    if companies:
        st.markdown("---")
        st.markdown("**Entreprises prêtes pour Phase 5 (kits générés pour toutes) :**")
        for c in companies:
            r   = c.get("operator_rating", 0) or 0
            sel = " ✅" if c.get("is_selected") else ""
            st.markdown(
                f"- **{c.get('denomination','—')}** ({c.get('city','—')}) "
                f"— {'★'*r if r else '—'} — {int(c.get('phase3_score',0)*100)}%{sel}"
            )

    st.markdown("---")
    col_edit, col_next = st.columns(2)
    with col_edit:
        if st.button("← Voir les dossiers", key="p4_val_back", use_container_width=True):
            st.session_state.p4_step = "review"
            st.rerun()
    with col_next:
        if st.button("Lancer la Préparation (Phase 5) →", key="p4_val_goto_p5", type="primary", use_container_width=True):
            st.session_state.current_page = "Phase 5 — Préparation"
            st.rerun()
