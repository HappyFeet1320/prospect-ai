"""
UI Streamlit — Phase 2 : Recherche BCE / KBO
Interface de configuration, suivi en temps réel et validation des résultats.
"""

import time
import pandas as pd
import streamlit as st
from loguru import logger

from config.settings import settings
from phases.phase2.runner import run_phase2, validate_phase2, Phase2Result
from phases.phase2.bce_client import test_bce_connection
from phases.phase2.kbo_reader import is_index_built, build_index, get_index_stats


# ============================================================
# Point d'entrée principal
# ============================================================

def render_phase2_page(session_id: str):
    """Rendu principal de la page Phase 2."""
    st.markdown("## Phase 2 — Recherche BCE / KBO")
    st.markdown(
        "Interrogation automatique de la Banque-Carrefour des Entreprises belge "
        "pour chaque code NACE de votre profil."
    )

    # Vérification Phase 1 complète
    profile = st.session_state.get("p1_profile")
    if not profile or st.session_state.get("p1_step") not in ("review", "validated"):
        st.warning("Vous devez d'abord valider votre profil (Phase 1).")
        if st.button("← Retour Phase 1", key="p2_back_p1"):
            st.session_state.current_page = "Phase 1 — Profiling"
            st.rerun()
        return

    # Initialisation état Phase 2
    if "p2_step" not in st.session_state:
        st.session_state.p2_step = "config"
    if "p2_result" not in st.session_state:
        st.session_state.p2_result = None
    if "p2_source" not in st.session_state:
        st.session_state.p2_source = "kbo"  # "kbo" | "mock"

    step = st.session_state.p2_step

    if step == "config":
        _render_config(session_id, profile)
    elif step == "searching":
        _render_searching(session_id, profile)
    elif step == "results":
        _render_results(session_id, profile)
    elif step == "validated":
        _render_validated(session_id)


# ============================================================
# Étape 1 — Configuration
# ============================================================

def _render_config(session_id: str, profile: dict):
    """Écran de configuration avant le lancement de la recherche."""

    nace_codes: list[dict] = profile.get("nace_codes", [])
    target_locations: list[dict] = profile.get("target_locations", [])
    radius_km: int = profile.get("search_radius_km", 30)

    # Initialisation de la liste NACE modifiable (indépendante du profil Phase 1)
    if "p2_nace_override" not in st.session_state:
        st.session_state.p2_nace_override = [dict(n) for n in nace_codes]

    nace_override: list[dict] = st.session_state.p2_nace_override

    # --- Résumé du profil ---
    st.markdown("### Paramètres de recherche")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Codes NACE", len(nace_override))
    with col2:
        loc_str = ", ".join(loc.get("city", "") for loc in target_locations) or "Non définie"
        st.metric("Zone cible", loc_str[:25])
    with col3:
        st.metric("Rayon", f"{radius_km} km")

    # --- Tableau des codes NACE (modifiable) ---
    st.markdown("#### Codes NACE à rechercher")
    st.caption("Ces codes proviennent de votre profil. Vous pouvez en ajouter ou en supprimer avant de lancer la recherche.")

    # Tri par poids décroissant (en place pour que les indices restent cohérents)
    nace_override.sort(key=lambda x: x.get("weight", 0), reverse=True)

    to_delete = None
    for i, nace in enumerate(nace_override):
        weight = nace.get("weight", 0)
        col_code, col_label, col_weight, col_del = st.columns([1, 4, 1, 0.6])
        with col_code:
            st.markdown(f"**{nace.get('code')}**")
        with col_label:
            st.markdown(nace.get("label", ""))
            if nace.get("justification"):
                st.caption(nace.get("justification", ""))
        with col_weight:
            st.markdown(f"**{int(weight * 100)}%**")
        with col_del:
            if st.button("✕", key=f"p2_del_nace_{i}", help="Supprimer ce code NACE"):
                to_delete = i
        st.progress(weight)

    if to_delete is not None:
        nace_override.pop(to_delete)
        st.rerun()

    # --- Ajout manuel d'un code NACE ---
    with st.expander("➕ Ajouter un code NACE manuellement"):
        col_c, col_l = st.columns([1, 3])
        with col_c:
            new_code = st.text_input("Code NACE (4 chiffres)", key="p2_new_code", max_chars=5,
                                     placeholder="ex: 6201")
        with col_l:
            new_label = st.text_input("Libellé", key="p2_new_label",
                                      placeholder="ex: Développement de logiciels")
        new_weight = st.slider("Priorité (%)", 10, 100, 50, 5, key="p2_new_weight")
        col_add, col_reset = st.columns([1, 1])
        with col_add:
            if st.button("Ajouter ce code NACE", key="p2_btn_add_nace", use_container_width=True):
                code_clean = (new_code or "").strip()
                if code_clean.isdigit() and 2 <= len(code_clean) <= 5:
                    # Vérifier que le code n'existe pas déjà
                    existing_codes = [n.get("code", "") for n in nace_override]
                    if code_clean in existing_codes:
                        st.warning(f"Le code NACE {code_clean} est déjà dans la liste.")
                    else:
                        nace_override.append({
                            "code":          code_clean,
                            "label":         new_label or f"NACE {code_clean}",
                            "weight":        new_weight / 100,
                            "justification": "Ajouté manuellement",
                        })
                        st.rerun()
                else:
                    st.error("Code NACE invalide — saisissez 2 à 5 chiffres.")
        with col_reset:
            if st.button("↺ Réinitialiser depuis le profil", key="p2_btn_reset_nace", use_container_width=True):
                st.session_state.p2_nace_override = [dict(n) for n in nace_codes]
                st.rerun()

    st.markdown("---")

    # --- Source des données ---
    st.markdown("### Source des données")
    _render_source_selector()

    st.markdown("---")

    # --- Bouton de lancement ---
    source = st.session_state.get("p2_source", "kbo")
    col_back, col_launch = st.columns([1, 2])
    with col_back:
        if st.button("← Modifier le profil", key="p2_cfg_back", use_container_width=True):
            st.session_state.current_page = "Phase 1 — Profiling"
            st.rerun()
    with col_launch:
        labels = {
            "kbo":     "Lancer la recherche KBO Open Data",
            "cbe_api": "Lancer la recherche CBE API (en ligne)",
            "mock":    "Lancer avec données fictives (test)",
        }
        can_launch = _can_launch(source)
        if st.button(
            labels.get(source, "Lancer la recherche"),
            key="p2_cfg_launch",
            type="primary",
            use_container_width=True,
            disabled=not can_launch,
        ):
            st.session_state.p2_step = "searching"
            st.rerun()


# ============================================================
# Étape 2 — Recherche en cours (progression temps réel)
# ============================================================

def _render_source_selector():
    """Widget de sélection de la source Phase 2 : KBO Open Data ou Mode test."""
    source   = st.session_state.get("p2_source", "kbo")
    index_ok = is_index_built()

    col_kbo, col_mock = st.columns(2)

    with col_kbo:
        st.markdown("#### KBO Open Data (recommandé)")
        if index_ok:
            stats = get_index_stats()
            st.success(
                f"Index prêt — {stats['nb_enterprises']:,} entreprises "
                f"({stats['size_mb']} MB)"
            )
        else:
            st.warning("Index non construit")
            if st.button("🔨 Construire l'index (unique, ~5 min)", key="p2_btn_build_idx", use_container_width=True):
                _build_kbo_index_ui()
                st.rerun()
        st.caption(
            "1,94 M entreprises actives · Recherche instantanée par NACE · "
            "Pas de clé requise · Les coordonnées sont ajoutées en Phase 4 via CBE API."
        )
        col_sel, col_chk = st.columns([2, 1])
        with col_sel:
            if st.button(
                "✓ Utiliser KBO" if source != "kbo" else "✅ KBO sélectionné",
                key="p2_src_kbo",
                use_container_width=True,
                disabled=not index_ok or source == "kbo",
                type="primary" if source == "kbo" else "secondary",
            ):
                st.session_state.p2_source = "kbo"
                st.rerun()
        with col_chk:
            if st.button("🔌", key="p2_chk_kbo", help="Vérifier l'index"):
                ok, msg = test_bce_connection()
                st.toast(msg, icon="✅" if ok else "❌")

    with col_mock:
        st.markdown("#### Mode test (fictif)")
        st.error("Entreprises **inventées** — tests uniquement")
        st.caption(
            "N'utilise aucune vraie donnée. "
            "Pour tester l'interface sans index KBO ni connexion réseau."
        )
        if st.button(
            "✓ Utiliser Mock" if source != "mock" else "✅ Mock sélectionné",
            key="p2_src_mock",
            use_container_width=True,
            type="primary" if source == "mock" else "secondary",
        ):
            st.session_state.p2_source = "mock"
            st.rerun()


def _can_launch(source: str) -> bool:
    """Vérifie si la source sélectionnée est disponible pour le lancement."""
    if source == "kbo":
        return is_index_built()
    return True  # mock toujours disponible


def _render_searching(session_id: str, profile: dict):
    """Écran de progression pendant la recherche BCE."""

    # Utiliser les codes NACE potentiellement modifiés par l'opérateur
    nace_codes: list[dict] = st.session_state.get("p2_nace_override", profile.get("nace_codes", []))
    source: str = st.session_state.get("p2_source", "kbo")
    use_mock: bool = source == "mock"

    source_labels = {
        "kbo":     f"KBO Open Data — requête batch sur {len(nace_codes)} codes NACE simultanément",
        "cbe_api": "CBE API (en ligne) — recherche par code postal + filtre NACE",
        "mock":    "Données fictives (test)",
    }

    st.markdown("### Recherche BCE en cours...")
    st.caption(f"Mode : **{source_labels.get(source, source)}**")

    total_counter = st.empty()
    global_bar    = st.progress(0.0, text="Initialisation...")
    st.markdown("---")

    nace_containers: dict[str, dict] = {}
    batch_status = None  # défini seulement en mode réel

    if use_mock:
        # Mode mock : un bloc par code NACE pour voir la progression individuelle
        for nace in sorted(nace_codes, key=lambda x: x.get("weight", 0), reverse=True):
            code  = nace.get("code", "")
            label = nace.get("label", "")[:50]
            col_label, col_status, col_count = st.columns([3, 2, 1])
            with col_label:
                st.markdown(f"**{code}** — {label}")
            nace_containers[code] = {
                "status_col": col_status.empty(),
                "count_col":  col_count.empty(),
            }
            nace_containers[code]["status_col"].markdown("⏳ En attente")
            nace_containers[code]["count_col"].markdown("—")
    else:
        # Mode réel (KBO ou CBE API) : requête batch — afficher les codes interrogés
        if source == "cbe_api":
            target_locations = profile.get("target_locations", [])
            postals = [loc.get("postal_code", "") for loc in target_locations if loc.get("postal_code")]
            st.markdown(
                f"🔍 **CBE API** — codes postaux interrogés : **{', '.join(postals) or 'aucun'}** "
                f"· filtre NACE local sur {len(nace_codes)} codes"
            )
        else:
            st.markdown(
                "🔍 **Requête batch KBO** — les entreprises suivantes seront retournées en une seule passe :"
            )
            codes_str = "  ·  ".join(
                f"**{n.get('code')}** ({int(n.get('weight', 0)*100)}%)"
                for n in sorted(nace_codes, key=lambda x: x.get("weight", 0), reverse=True)
            )
            st.markdown(codes_str)
        batch_status = st.empty()
        batch_status.info(
            "Interrogation de la CBE API en cours…" if source == "cbe_api"
            else "Interrogation de l'index KBO en cours…"
        )

    st.markdown("---")

    _found_total = [0]
    _done_nace   = [0]

    def on_nace_progress(nace_code: str, found: int, total: int, pct: float, status: str):
        """Callback de progression — adapté au mode batch (réel) ou par code (mock)."""
        if nace_code == "__batch__":
            if status == "running":
                global_bar.progress(0.4, text="Requête KBO en cours…")
            elif status == "done":
                global_bar.progress(1.0, text="Recherche terminée !")
                _found_total[0] = found
                total_counter.metric("Entreprises uniques trouvées", found)
                if batch_status:
                    batch_status.success(f"✅ {found} entreprises uniques trouvées.")
            elif status == "error":
                global_bar.progress(1.0, text="Erreur")
                if batch_status:
                    batch_status.error("❌ Erreur lors de la recherche KBO.")
            return

        # Mode mock : mise à jour par code NACE
        container = nace_containers.get(nace_code, {})
        if status == "running":
            container.get("status_col", st.empty()).markdown("🔍 Recherche…")
            container.get("count_col",  st.empty()).markdown(f"**{found}**")
        elif status == "done":
            container.get("status_col", st.empty()).markdown("✅ Terminé")
            container.get("count_col",  st.empty()).markdown(f"**{found}**")
            _found_total[0] += found
            _done_nace[0]   += 1
            pct_global = _done_nace[0] / max(len(nace_codes), 1)
            global_bar.progress(
                pct_global,
                text=f"Progression : {_done_nace[0]}/{len(nace_codes)} codes NACE",
            )
        elif status == "error":
            container.get("status_col", st.empty()).markdown("❌ Erreur")
            _done_nace[0] += 1
        total_counter.metric("Entreprises trouvées (total)", _found_total[0])

    # Lancement de la recherche (avec les codes NACE éventuellement modifiés)
    search_profile = {**profile, "nace_codes": nace_codes}
    try:
        result = run_phase2(
            session_id=session_id,
            profile=search_profile,
            source=source,
            cbeapi_max_pages=st.session_state.get("p2_cbeapi_pages", 5),
            nace_progress_callback=on_nace_progress,
        )

        global_bar.progress(1.0, text="Recherche terminée !")
        st.session_state.p2_result = result
        st.session_state.p2_step = "results"
        time.sleep(0.5)
        st.rerun()

    except Exception as e:
        logger.exception("Erreur Phase 2")
        st.error(f"Erreur lors de la recherche BCE : {e}")
        if st.button("← Retour à la configuration", key="p2_search_err_back"):
            st.session_state.p2_step = "config"
            st.rerun()


# ============================================================
# Étape 3 — Résultats
# ============================================================

def _render_results(session_id: str, profile: dict):
    """Affiche les résultats de la recherche BCE avec tableau et stats."""

    result: Phase2Result = st.session_state.get("p2_result")
    if not result:
        st.session_state.p2_step = "config"
        st.rerun()
        return

    source = st.session_state.get("p2_source", "kbo")

    # --- En-tête et métriques ---
    if source == "mock":
        st.error(
            "⚠️ **CES DONNÉES SONT FICTIVES** — Ces entreprises sont inventées et n'existent pas. "
            "Relancez la recherche en **mode réel** pour obtenir de vraies entreprises de la BCE."
        )
    elif source == "cbe_api":
        st.success(
            f"CBE API — **{result.total_companies}** entreprises réelles trouvées "
            "(données fraîches, coordonnées incluses)."
        )
    else:
        st.success(f"KBO Open Data — **{result.total_companies}** entreprises réelles trouvées.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Entreprises uniques", result.total_companies)
    with col2:
        nace_with_results = sum(
            1 for v in result.companies_by_nace.values() if v.get("found", 0) > 0
        )
        st.metric("Codes NACE avec résultats", f"{nace_with_results}/{len(result.companies_by_nace)}")
    with col3:
        top_province = max(result.companies_by_province, key=result.companies_by_province.get, default="—")
        st.metric("Province principale", top_province)
    with col4:
        st.metric("Prêt pour Phase 3", "✓" if result.total_companies >= 5 else "⚠️")

    # --- Avertissements ---
    for warning in result.warnings:
        st.warning(warning)

    st.markdown("---")

    # --- Résultats par code NACE ---
    st.markdown("#### Résultats par code NACE")
    nace_rows = []
    for code, stats in result.companies_by_nace.items():
        nace_rows.append({
            "Code NACE": code,
            "Secteur": stats.get("label", "")[:60],
            "Priorité": f"{int(stats.get('weight', 0) * 100)}%",
            "Trouvées": stats.get("found", 0),
            "Nouvelles uniques": stats.get("new_unique", 0),
        })
    if nace_rows:
        st.dataframe(
            pd.DataFrame(nace_rows),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")

    # --- Répartition géographique ---
    st.markdown("#### Répartition géographique")
    if result.companies_by_province:
        geo_df = pd.DataFrame([
            {"Province / Ville": k, "Entreprises": v}
            for k, v in sorted(result.companies_by_province.items(), key=lambda x: x[1], reverse=True)
        ])
        st.bar_chart(geo_df.set_index("Province / Ville"))

    st.markdown("---")

    # --- Tableau des entreprises ---
    st.markdown("#### Liste des entreprises (aperçu)")

    companies = result.unique_companies
    if companies:
        # Filtres
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            search_filter = st.text_input(
                "Filtrer par nom ou BCE", placeholder="Ex: TechSolutions"
            )
        with col_f2:
            available_provinces = sorted(set(
                c.get("province") or c.get("city") or "Inconnue"
                for c in companies
            ))
            province_filter = st.selectbox(
                "Filtrer par province / ville",
                ["Toutes"] + available_provinces,
            )

        # Application des filtres
        filtered = companies
        if search_filter:
            search_lower = search_filter.lower()
            filtered = [
                c for c in filtered
                if search_lower in c.get("denomination", "").lower()
                or search_lower in c.get("bce_number", "").lower()
            ]
        if province_filter != "Toutes":
            filtered = [
                c for c in filtered
                if (c.get("province") or c.get("city") or "") == province_filter
            ]

        st.caption(f"{len(filtered)} entreprises affichées sur {len(companies)}")

        show_contacts = source == "cbe_api"
        table_data = []
        for c in filtered[:200]:  # Limiter à 200 lignes pour les performances
            src = c.get("source", "")
            source_label = (
                "⚠️ FICTIF" if src == "mock_data"
                else "CBE API ✓" if src == "cbe_api"
                else "KBO ✓" if src.startswith("bce") or src == "kbo"
                else src
            )
            matched_codes = c.get("matched_nace_codes", [c.get("nace_searched", "")])
            match_count   = len(matched_codes)
            match_label   = (
                f"★ {match_count} codes ({', '.join(matched_codes)})"
                if match_count > 1
                else (matched_codes[0] if matched_codes else "")
            )
            row = {
                "Numéro BCE": c.get("bce_number", ""),
                "Dénomination": c.get("denomination", "")[:60],
                "Forme juridique": c.get("legal_form", ""),
                "Ville": c.get("city", ""),
                "Code postal": c.get("postal_code", ""),
                "Province": c.get("province", ""),
                "NACE correspondants": match_label,
                "Source": source_label,
            }
            if show_contacts:
                row["Email"]    = c.get("email", "")
                row["Téléphone"] = c.get("phone", "")
                row["Site web"]  = c.get("website", "")
            table_data.append(row)

        st.dataframe(
            pd.DataFrame(table_data),
            use_container_width=True,
            hide_index=True,
            height=400,
        )

    st.markdown("---")

    # --- Actions ---
    col_back, col_redo, col_validate = st.columns(3)

    with col_back:
        if st.button("← Modifier le profil", key="p2_res_back", use_container_width=True):
            st.session_state.current_page = "Phase 1 — Profiling"
            st.rerun()

    with col_redo:
        if st.button("Relancer la recherche", key="p2_res_redo", use_container_width=True):
            st.session_state.p2_step = "config"
            st.session_state.p2_result = None
            st.rerun()

    with col_validate:
        can_validate = result.total_companies >= 5
        if st.button(
            "Valider et passer au Scoring (Phase 3) →",
            key="p2_res_validate",
            type="primary",
            disabled=not can_validate,
            use_container_width=True,
            help="Minimum 5 entreprises requises pour passer en Phase 3."
            if not can_validate else "Lancer le scoring et filtrage des entreprises.",
        ):
            _validate(session_id)


def _build_kbo_index_ui():
    """Lance la construction de l'index KBO avec barre de progression Streamlit."""
    st.markdown("### Construction de l'index KBO en cours…")
    st.caption("Cette opération est unique et prend environ 3 à 6 minutes.")

    steps = {
        "entreprises":      ("1/5 — Entreprises actives",    0.10),
        "dénominations":    ("2/5 — Noms des entreprises",   0.35),
        "adresses":         ("3/5 — Adresses",               0.55),
        "activités NACE":   ("4/5 — Codes NACE (long...)",   0.75),
        "index SQL":        ("5/5 — Index SQL",              0.95),
    }
    bar     = st.progress(0.0, text="Initialisation…")
    status  = st.empty()

    def on_progress(step: str, current: int, total: int):
        label, pct = steps.get(step, (step, 0.5))
        bar.progress(pct, text=label)
        if current and total:
            status.caption(f"{current:,} / {total:,}")

    try:
        stats = build_index(progress_callback=on_progress)
        bar.progress(1.0, text="Index KBO construit !")
        st.success(
            f"Index KBO prêt — {stats['nb_enterprises']:,} entreprises, "
            f"{stats['nb_nace']:,} activités NACE indexées."
        )
    except Exception as e:
        logger.exception("Erreur construction index KBO")
        st.error(f"Erreur lors de la construction : {e}")


def _validate(session_id: str):
    """Valide Phase 2 et passe à Phase 3."""
    try:
        validate_phase2(session_id)
        st.session_state.p2_step = "validated"
        st.session_state.current_phase = 3
        st.success("Phase 2 validée !")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur lors de la validation : {e}")


# ============================================================
# Étape 4 — Phase 2 validée
# ============================================================

def _render_validated(session_id: str):
    """Écran affiché après validation de Phase 2."""
    result: Phase2Result = st.session_state.get("p2_result")

    st.success("**Phase 2 validée !**")

    if result:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Entreprises collectées", result.total_companies)
        with col2:
            nace_count = len([v for v in result.companies_by_nace.values() if v.get("found", 0) > 0])
            st.metric("Codes NACE actifs", nace_count)
        with col3:
            st.metric("Prochaine étape", "Phase 3 — Scoring")

    st.markdown("---")
    col_edit, col_next = st.columns(2)
    with col_edit:
        if st.button("← Voir les résultats", key="p2_val_back", use_container_width=True):
            st.session_state.p2_step = "results"
            st.rerun()
    with col_next:
        if st.button(
            "Lancer le Scoring (Phase 3) →",
            key="p2_val_goto_p3",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.current_page = "Phase 3 — Scoring"
            st.rerun()
