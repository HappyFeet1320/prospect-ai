"""
Page Paramètres — Configuration et test des APIs externes.

Permet à l'utilisateur de :
- Configurer et tester le provider LLM (Groq / Anthropic)
- Configurer et tester la CBE API
- Voir l'état de toutes les connexions externes
- Enregistrer les clés dans le fichier .env
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from loguru import logger

from config.settings import settings

# Chemin vers le .env à la racine du projet
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


# ============================================================
# Helpers — lecture / écriture .env
# ============================================================

def _read_env() -> dict[str, str]:
    """Lit le fichier .env et retourne un dict clé→valeur."""
    env: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return env
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _write_env_key(key: str, value: str) -> None:
    """Met à jour (ou ajoute) une clé dans le fichier .env sans toucher aux autres lignes."""
    if not _ENV_PATH.exists():
        _ENV_PATH.write_text(f"{key}={value}\n", encoding="utf-8")
        return

    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped == f"{key}=":
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value}\n")

    _ENV_PATH.write_text("".join(new_lines), encoding="utf-8")


# ============================================================
# Tests de connexion
# ============================================================

def _test_groq(api_key: str, model: str) -> tuple[bool, str]:
    """Teste la connexion Groq avec la clé fournie."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Réponds juste: OK"}],
            max_tokens=10,
            temperature=0,
        )
        msg = resp.choices[0].message.content or "OK"
        tokens = resp.usage.completion_tokens if resp.usage else 0
        return True, f"Connexion réussie ✅ — modèle `{model}` — réponse : «{msg.strip()}» ({tokens} tokens)"
    except Exception as e:
        err = str(e)
        if "401" in err or "invalid_api_key" in err or "expired" in err:
            return False, f"Clé invalide ou expirée (401) — {err[:200]}"
        if "429" in err or "rate_limit" in err:
            return False, f"Rate limit atteint (429) — la clé est valide mais le quota est épuisé"
        if "model_not_found" in err.lower():
            return False, f"Modèle `{model}` introuvable — vérifiez le nom du modèle"
        return False, f"Erreur : {err[:300]}"


def _test_anthropic(api_key: str, model: str) -> tuple[bool, str]:
    """Teste la connexion Anthropic avec la clé fournie."""
    try:
        import anthropic as anthropic_sdk
        client = anthropic_sdk.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Réponds juste: OK"}],
        )
        msg = resp.content[0].text if resp.content else "OK"
        tokens = resp.usage.output_tokens if resp.usage else 0
        return True, f"Connexion réussie ✅ — modèle `{model}` — réponse : «{msg.strip()}» ({tokens} tokens)"
    except Exception as e:
        err = str(e)
        if "401" in err or "authentication" in err.lower():
            return False, f"Clé invalide (401) — {err[:200]}"
        if "credit" in err.lower() or "billing" in err.lower() or "balance" in err.lower():
            return False, f"Crédits insuffisants — la clé est valide mais le solde est épuisé. Rechargez sur console.anthropic.com"
        if "529" in err or "overloaded" in err.lower():
            return False, f"API surchargée (529) — réessayez dans quelques instants"
        return False, f"Erreur : {err[:300]}"


def _test_cbeapi(api_key: str) -> tuple[bool, str]:
    """Teste la connexion CBE API avec la clé fournie."""
    try:
        import requests
        url = "https://cbeapi.be/api/v1/company/0403.091.578"  # BCE de test connue (BNP Paribas Fortis)
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("denomination", "OK")
            return True, f"Connexion réussie ✅ — entreprise test : «{name[:60]}»"
        elif resp.status_code == 401:
            return False, "Clé invalide (401) — vérifiez votre CBEAPI_KEY sur https://cbeapi.be"
        elif resp.status_code == 403:
            return False, "Accès refusé (403) — votre clé n'a pas les droits nécessaires"
        elif resp.status_code == 429:
            return False, "Quota journalier atteint (429) — 2 500 req/jour sur tier gratuit"
        else:
            return False, f"Erreur HTTP {resp.status_code} — {resp.text[:200]}"
    except Exception as e:
        return False, f"Erreur réseau : {str(e)[:300]}"


# ============================================================
# Redémarrage Streamlit
# ============================================================

def _restart_streamlit() -> None:
    """Redémarre Streamlit : lance un nouveau processus puis quitte l'actuel."""
    import subprocess
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        cwd=str(app_path.parent),
    )
    os._exit(0)


# ============================================================
# Rendu des sections
# ============================================================

def _section_llm():
    """Section configuration LLM."""
    st.subheader("🤖 Provider LLM")

    env = _read_env()

    # Sélection provider
    current_provider = env.get("LLM_PROVIDER", settings.LLM_PROVIDER)
    provider = st.radio(
        "Provider actif",
        options=["groq", "anthropic"],
        index=0 if current_provider == "groq" else 1,
        format_func=lambda x: "Groq (llama-3.3-70b — gratuit)" if x == "groq" else "Anthropic / Claude (payant)",
        horizontal=True,
        key="settings_provider",
    )

    st.markdown("---")

    if provider == "groq":
        _subsection_groq(env)
    else:
        _subsection_anthropic(env)


def _subsection_groq(env: dict):
    """Sous-section Groq."""
    col_key, col_model = st.columns([3, 2])

    with col_key:
        current_key = env.get("GROQ_API_KEY", settings.GROQ_API_KEY or "")
        masked = f"{current_key[:8]}...{current_key[-4:]}" if len(current_key) > 12 else ("configurée" if current_key else "")
        st.markdown(f"**Clé actuelle :** `{masked or 'non configurée'}`")

        new_key = st.text_input(
            "Nouvelle clé Groq",
            type="password",
            placeholder="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            help="Obtenez votre clé sur https://console.groq.com/keys",
            key="settings_groq_key",
        )

    with col_model:
        current_model = env.get("GROQ_MODEL", settings.GROQ_MODEL)
        new_model = st.text_input(
            "Modèle Groq",
            value=current_model,
            help="Ex : llama-3.3-70b-versatile, mixtral-8x7b-32768",
            key="settings_groq_model",
        )

    col_save, col_test, col_status = st.columns([1, 1, 3])

    key_to_use = new_key or env.get("GROQ_API_KEY", settings.GROQ_API_KEY or "")
    model_to_use = new_model or current_model

    with col_save:
        if st.button("💾 Enregistrer", key="save_groq", use_container_width=True):
            if new_key:
                _write_env_key("GROQ_API_KEY", new_key)
            _write_env_key("GROQ_MODEL", model_to_use)
            _write_env_key("LLM_PROVIDER", "groq")
            st.success("Enregistré dans `.env` — redémarrez Streamlit pour appliquer.")
            logger.info("Paramètres Groq sauvegardés")

    with col_test:
        if st.button("🔌 Tester", key="test_groq", use_container_width=True):
            if not key_to_use:
                st.error("Entrez ou configurez une clé avant de tester.")
            else:
                with st.spinner("Test en cours…"):
                    ok, msg = _test_groq(key_to_use, model_to_use)
                st.session_state["groq_test_result"] = (ok, msg)

    with col_status:
        result = st.session_state.get("groq_test_result")
        if result:
            ok, msg = result
            if ok:
                st.success(msg)
            else:
                st.error(msg)
        else:
            # Statut courant depuis settings
            if settings.has_groq_key:
                st.info(f"Clé configurée — modèle : `{settings.GROQ_MODEL}`")
            else:
                st.warning("Clé Groq non configurée")


def _subsection_anthropic(env: dict):
    """Sous-section Anthropic / Claude."""
    col_key, col_model = st.columns([3, 2])

    with col_key:
        current_key = env.get("ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY or "")
        masked = f"{current_key[:12]}...{current_key[-4:]}" if len(current_key) > 16 else ("configurée" if current_key else "")
        st.markdown(f"**Clé actuelle :** `{masked or 'non configurée'}`")

        new_key = st.text_input(
            "Nouvelle clé Anthropic",
            type="password",
            placeholder="sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            help="Obtenez votre clé sur https://console.anthropic.com/",
            key="settings_anthropic_key",
        )

    with col_model:
        current_model = env.get("CLAUDE_MODEL", settings.CLAUDE_MODEL)
        new_model = st.text_input(
            "Modèle Claude",
            value=current_model,
            help="Ex : claude-sonnet-4-6, claude-haiku-4-5-20251001",
            key="settings_anthropic_model",
        )

    col_save, col_test, col_status = st.columns([1, 1, 3])

    key_to_use = new_key or env.get("ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY or "")
    model_to_use = new_model or current_model

    with col_save:
        if st.button("💾 Enregistrer", key="save_anthropic", use_container_width=True):
            if new_key:
                _write_env_key("ANTHROPIC_API_KEY", new_key)
            _write_env_key("CLAUDE_MODEL", model_to_use)
            _write_env_key("LLM_PROVIDER", "anthropic")
            st.success("Enregistré dans `.env` — redémarrez Streamlit pour appliquer.")
            logger.info("Paramètres Anthropic sauvegardés")

    with col_test:
        if st.button("🔌 Tester", key="test_anthropic", use_container_width=True):
            if not key_to_use:
                st.error("Entrez ou configurez une clé avant de tester.")
            else:
                with st.spinner("Test en cours…"):
                    ok, msg = _test_anthropic(key_to_use, model_to_use)
                st.session_state["anthropic_test_result"] = (ok, msg)

    with col_status:
        result = st.session_state.get("anthropic_test_result")
        if result:
            ok, msg = result
            if ok:
                st.success(msg)
            else:
                st.error(msg)
        else:
            if settings.has_anthropic_key:
                st.info(f"Clé configurée — modèle : `{settings.CLAUDE_MODEL}`")
            else:
                st.warning("Clé Anthropic non configurée")


def _section_cbeapi():
    """Section CBE API."""
    st.subheader("🏛 CBE API (cbeapi.be)")
    st.caption("Données entreprises belges en temps réel — email, téléphone, site web. Clé gratuite : 2 500 req/jour.")

    env = _read_env()
    current_key = env.get("CBEAPI_KEY", settings.CBEAPI_KEY or "")

    col_key, col_link = st.columns([3, 1])

    with col_key:
        masked = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 10 else ("configurée" if current_key else "")
        st.markdown(f"**Clé actuelle :** `{masked or 'non configurée'}`")

        new_key = st.text_input(
            "Nouvelle clé CBE API",
            type="password",
            placeholder="votre-clé-cbeapi",
            help="Créez un compte gratuit sur https://cbeapi.be pour obtenir une clé",
            key="settings_cbeapi_key",
        )

    with col_link:
        st.markdown("&nbsp;")
        st.link_button("Obtenir une clé", "https://cbeapi.be", use_container_width=True)

    col_save, col_test, col_status = st.columns([1, 1, 3])

    key_to_use = new_key or current_key

    with col_save:
        if st.button("💾 Enregistrer", key="save_cbeapi", use_container_width=True):
            if new_key:
                _write_env_key("CBEAPI_KEY", new_key)
                st.success("Clé CBE API enregistrée dans `.env` — redémarrez Streamlit pour appliquer.")
                logger.info("Clé CBE API sauvegardée")
            else:
                st.warning("Entrez une clé à enregistrer.")

    with col_test:
        if st.button("🔌 Tester", key="test_cbeapi", use_container_width=True):
            if not key_to_use:
                st.error("Entrez ou configurez une clé avant de tester.")
            else:
                with st.spinner("Test en cours…"):
                    ok, msg = _test_cbeapi(key_to_use)
                st.session_state["cbeapi_test_result"] = (ok, msg)

    with col_status:
        result = st.session_state.get("cbeapi_test_result")
        if result:
            ok, msg = result
            if ok:
                st.success(msg)
            else:
                st.error(msg)
        else:
            if settings.has_cbeapi_key:
                st.info("Clé configurée — Phase 4 (enrichissement) activée")
            else:
                st.warning("Non configurée — Phase 4 fonctionnera sans coordonnées officielles")


def _section_autres():
    """Section autres services (info seulement)."""
    st.subheader("🔧 Autres services")

    data = [
        ("DuckDuckGo", "✅ Gratuit", "Aucune clé requise — utilisé pour les recherches web en Phase 4", True),
        ("KBO Open Data", "✅ Gratuit", "Index local SQLite — pas de clé requise, téléchargement CSV depuis data.be", True),
        ("BNB (Banque Nationale)", "ℹ️ Optionnel", "Données financières détaillées — inscription gratuite sur nbb.be", bool(settings.BNB_API_KEY)),
        ("Hunter.io", "ℹ️ Optionnel", "Recherche d'emails professionnels — tier gratuit 25 req/mois", bool(settings.HUNTER_IO_API_KEY)),
        ("Apollo.io", "ℹ️ Optionnel", "Enrichissement contacts B2B — tier gratuit disponible", bool(settings.APOLLO_API_KEY)),
    ]

    for name, badge, desc, configured in data:
        col_name, col_badge, col_desc = st.columns([2, 1, 5])
        with col_name:
            st.markdown(f"**{name}**")
        with col_badge:
            if configured:
                st.markdown(f":green[{badge}]")
            else:
                st.markdown(f":orange[{badge}]")
        with col_desc:
            st.caption(desc)


def _section_statut_global():
    """Résumé de l'état global des connexions."""
    st.subheader("📊 État global")

    col1, col2, col3 = st.columns(3)

    with col1:
        if settings.has_llm_key:
            st.success(f"**LLM**\n{settings.provider_label}")
        else:
            provider = settings.LLM_PROVIDER
            key_var = "GROQ_API_KEY" if provider == "groq" else "ANTHROPIC_API_KEY"
            st.error(f"**LLM**\nClé manquante (`{key_var}`)")

    with col2:
        if settings.has_cbeapi_key:
            st.success("**CBE API**\nConfigurée")
        else:
            st.warning("**CBE API**\nNon configurée (optionnel)")

    with col3:
        st.info("**DuckDuckGo**\nDisponible (gratuit)")


# ============================================================
# Point d'entrée principal
# ============================================================

def render_settings_page():
    """Page principale des paramètres."""
    st.markdown("# ⚙️ Paramètres & Connexions")
    st.caption(
        "Configurez vos clés API et testez les connexions aux services externes. "
        "Les clés sont enregistrées dans le fichier `.env` à la racine du projet."
    )

    # Avertissement redémarrage + bouton
    col_info, col_btn = st.columns([5, 1])
    with col_info:
        st.info(
            "ℹ️ Après modification des clés, **redémarrez Streamlit** pour que les nouvelles valeurs "
            "soient prises en compte par l'application.",
            icon="ℹ️",
        )
    with col_btn:
        st.markdown("&nbsp;")
        if st.button("🔄 Redémarrer", key="btn_restart_streamlit", type="primary", use_container_width=True,
                     help="Redémarre le serveur Streamlit pour recharger le fichier .env"):
            st.toast("Redémarrage en cours…", icon="🔄")
            import time; time.sleep(0.8)
            _restart_streamlit()

    st.markdown("---")

    _section_statut_global()

    st.markdown("---")

    _section_llm()

    st.markdown("---")

    _section_cbeapi()

    st.markdown("---")

    _section_autres()

    st.markdown("---")

    # Chemin du fichier .env
    st.caption(f"Fichier de configuration : `{_ENV_PATH}`")
    if not _ENV_PATH.exists():
        st.warning(
            f"Fichier `.env` introuvable à `{_ENV_PATH}`. "
            "Copiez `.env.example` en `.env` pour commencer."
        )
