"""
Phase 5 — Génération du kit de préparation à l'entretien.

Pour chaque entreprise sélectionnée, appelle le LLM pour générer :
- 3 variantes de message d'accroche (email, LinkedIn, téléphone)
- 4-6 situations ambiguës avec réponses suggérées
- 5 questions clés à poser lors de l'entretien
- Points de vigilance (risques)
- Résumé exécutif 1 page
"""

from __future__ import annotations

import json
from loguru import logger

from utils.llm_client import call_with_json_tool


# ============================================================
# Schéma JSON du kit
# ============================================================

_KIT_SCHEMA = {
    "type": "object",
    "properties": {
        "message_variants": {
            "type": "array",
            "description": "3 variantes de message d'accroche",
            "items": {
                "type": "object",
                "properties": {
                    "canal":   {"type": "string", "enum": ["Email", "LinkedIn", "Téléphone"]},
                    "angle":   {"type": "string", "description": "Angle stratégique (Valeur / Contexte / Réseau)"},
                    "objet":   {"type": "string", "description": "Objet du message (email) ou accroche (LinkedIn/téléphone)"},
                    "corps":   {"type": "string", "description": "Corps complet du message, personnalisé et prêt à envoyer"},
                },
                "required": ["canal", "angle", "objet", "corps"],
            },
        },
        "ambiguous_situations": {
            "type": "array",
            "description": "4 à 6 situations délicates spécifiques à cette entreprise/secteur",
            "items": {
                "type": "object",
                "properties": {
                    "situation":       {"type": "string", "description": "Question ou situation difficile potentielle"},
                    "reponse_suggeree": {"type": "string", "description": "Stratégie de réponse conseillée, détaillée"},
                },
                "required": ["situation", "reponse_suggeree"],
            },
        },
        "questions_to_ask": {
            "type": "array",
            "description": "5 questions pertinentes que l'opérateur peut poser lors de l'entretien",
            "items": {
                "type": "object",
                "properties": {
                    "question":  {"type": "string", "description": "La question à poser"},
                    "rationale": {"type": "string", "description": "Pourquoi poser cette question et ce qu'elle démontre"},
                },
                "required": ["question", "rationale"],
            },
        },
        "risk_flags": {
            "type": "array",
            "description": "Points de vigilance et risques identifiés",
            "items": {
                "type": "object",
                "properties": {
                    "type":        {"type": "string", "description": "Catégorie du risque (Financier / RH / Commercial / Culturel / Autre)"},
                    "description": {"type": "string", "description": "Description précise du risque identifié"},
                    "severite":    {"type": "string", "enum": ["Faible", "Modérée", "Élevée"]},
                },
                "required": ["type", "description", "severite"],
            },
        },
        "executive_summary": {
            "type": "string",
            "description": (
                "Résumé exécutif 1 page : présentation de l'entreprise, pourquoi elle correspond "
                "au profil, le décideur à contacter, les 3 points forts à valoriser, "
                "et la stratégie d'approche recommandée."
            ),
        },
    },
    "required": [
        "message_variants",
        "ambiguous_situations",
        "questions_to_ask",
        "risk_flags",
        "executive_summary",
    ],
}


# ============================================================
# Fonction principale
# ============================================================

def generate_kit(company: dict, profile: dict) -> dict:
    """
    Génère le kit de préparation pour une entreprise.

    Args:
        company: Données enrichies de l'entreprise (phase2_data + phase4_dossier)
        profile: Profil opérateur (Phase 1)

    Returns:
        Dict avec les 5 composantes du kit.
    """
    context = _build_context(company, profile)
    system  = _build_system_prompt(profile)

    result, usage = call_with_json_tool(
        system=system,
        user=context,
        tool_name="generate_preparation_kit",
        tool_description=(
            "Génère un kit de préparation complet et personnalisé pour un entretien professionnel "
            "avec une entreprise cible, incluant messages d'accroche, situations ambiguës, "
            "questions, points de vigilance et résumé exécutif. "
            "Si certaines informations sont manquantes, génère quand même un kit utile "
            "en t'appuyant sur le secteur d'activité, le nom et la localisation de l'entreprise."
        ),
        tool_schema=_KIT_SCHEMA,
        max_tokens=4000,  # Groq tier gratuit : 6 000 tokens/min → rester sous 4 000
    )

    logger.info(
        "Kit généré pour {} — {} tokens",
        company.get("denomination", "?")[:40],
        usage.get("output_tokens", 0),
    )

    return result


# ============================================================
# Helpers de construction du contexte
# ============================================================

def _build_system_prompt(profile: dict) -> str:
    # Calculer l'expérience totale depuis la liste des expériences
    experiences_list = profile.get("experiences", [])
    experience_total = sum(
        float(e.get("duration_years", 0) or 0)
        for e in experiences_list
        if isinstance(e, dict)
    )
    experience = str(int(experience_total)) if experience_total > 0 else "?"

    # Clés correctes issues du schéma profiler.py
    nom           = "l'opérateur"
    competences   = ", ".join(
        str(s) for s in (profile.get("must_have_skills") or [])[:8] if s
    )
    secteurs      = ", ".join(
        n.get("label", "") if isinstance(n, dict) else str(n)
        for n in (profile.get("nace_codes") or [])[:5]
    )
    disponibilite = profile.get("availability", "")
    objectif      = profile.get("profile_summary", "")

    return f"""Tu es un coach de recherche d'emploi expert en Belgique.
Tu dois générer un kit de préparation ULTRA-PERSONNALISÉ pour {nom}, qui a {experience} ans d'expérience.

PROFIL OPÉRATEUR :
- Compétences clés : {competences}
- Secteurs cibles : {secteurs}
- Disponibilité : {disponibilite}
- Objectif : {objectif}

RÈGLES DE GÉNÉRATION :
1. Génère TOUJOURS un kit complet, même si les données de l'entreprise sont partielles.
2. Si une information est absente, appuie-toi sur le secteur d'activité, la forme juridique et la localisation.
3. Les messages doivent être naturels, professionnels et adaptés au secteur.
4. Indique [À COMPLÉTER] uniquement pour les champs qui nécessitent une info personnelle (ex : prénom du contact).
5. Les situations ambiguës doivent être réalistes pour ce type d'entreprise/secteur.
6. Le résumé exécutif doit être court (5-8 lignes) et actionnable.
7. Toujours rédiger en français professionnel belge.
8. Longueur des messages : email ~150 mots, LinkedIn ~100 mots, téléphone = script ~60 mots."""


def _build_context(company: dict, profile: dict) -> str:
    """Construit le contexte complet pour le LLM."""
    dossier = company.get("phase4_dossier", {})

    # Bloc identité
    nom     = company.get("denomination", "Entreprise inconnue")
    adresse = company.get("adresse_complete", company.get("municipality", ""))
    nace    = company.get("nace_label", company.get("nace_code", ""))
    forme_j = company.get("forme_juridique", "")
    bce     = company.get("bce_number", "")

    # Blocs Phase 4
    identite    = dossier.get("bloc_identite", {})
    financier   = dossier.get("bloc_financier", {})
    commercial  = dossier.get("bloc_commercial", {})
    decideurs   = dossier.get("bloc_decideurs", [])
    recrutement = dossier.get("bloc_recrutement", {})

    # ── Décideur principal ─────────────────────────────────────
    decideur_str = "Non identifié"
    if decideurs:
        d = decideurs[0]
        decideur_str = (
            f"{d.get('prenom_nom', '?')} — {d.get('titre', '?')} "
            f"({d.get('type', '?')})"
        )
        if d.get("bio_courte"):
            decideur_str += f"\n  Bio : {d['bio_courte']}"

    # ── Description ────────────────────────────────────────────
    description = identite.get("description_ia", "")

    # ── Coordonnées — clés correctes Phase 4 ──────────────────
    # Site web : CBE en priorité, sinon web
    site_web = (
        identite.get("website_bce", "")
        or identite.get("website_url", "")
        or dossier.get("website_url", "")
    )
    # Email : CBE en priorité, sinon scraping
    email = (
        identite.get("email_bce", "")
        or identite.get("email_general", "")
    )
    # Téléphone : CBE en priorité, sinon scraping
    telephone = (
        identite.get("phone_bce", "")
        or identite.get("telephone", "")
    )

    # ── Données financières — clés correctes Phase 4 ──────────
    ca_str   = financier.get("ca_estime", "")      # Phase 4 utilise "ca_estime"
    tendance = financier.get("tendance", "")
    effectif = financier.get("effectif_estime", "")
    signal   = financier.get("signal_label", "")

    # ── Commercial — clés correctes Phase 4 (listes) ──────────
    clients_list = commercial.get("clients_connus", [])
    clients = ", ".join(str(c) for c in clients_list[:6]) if clients_list else ""

    certifs_list = commercial.get("certifications", [])
    certifs = ", ".join(str(c) for c in certifs_list[:4]) if certifs_list else ""

    marches = commercial.get("marches", "") or commercial.get("type_clientele", "")

    # ── Recrutement — clés correctes Phase 4 (listes) ─────────
    offres_list = recrutement.get("offres_actives", [])  # Phase 4 utilise "offres_actives"
    offres = "\n".join(f"  - {o}" for o in offres_list[:4]) if offres_list else ""

    signaux_list = recrutement.get("signaux_croissance", [])
    signaux_rh = "\n".join(f"  + {s}" for s in signaux_list[:4]) if signaux_list else ""

    contexte_rh = recrutement.get("contexte_rh", "")

    # ── Profil opérateur ───────────────────────────────────────
    competences = ", ".join(
        str(s) for s in (profile.get("must_have_skills") or [])[:8] if s
    )
    zones = ", ".join(
        loc.get("city", "") if isinstance(loc, dict) else str(loc)
        for loc in (profile.get("target_locations") or [])[:4]
    )
    score  = company.get("phase3_score", 0.0)
    rating = company.get("operator_rating", "")
    notes  = company.get("operator_notes", "")

    ctx = f"""=== DOSSIER ENTREPRISE ===

IDENTITÉ
- Nom : {nom}
- BCE : {bce}
- Forme juridique : {forme_j}
- Activité NACE : {nace}
- Adresse : {adresse}
- Site web : {site_web or "Non disponible"}
- Email : {email or "Non disponible"}
- Téléphone : {telephone or "Non disponible"}
- Score Phase 3 : {score:.0%}

DESCRIPTION
{description or "Non disponible"}

DONNÉES FINANCIÈRES
- CA estimé : {ca_str or "Non disponible"}
- Effectif estimé : {effectif or "Non disponible"}
- Tendance : {tendance or "Non disponible"}
- Signal : {signal or "Non disponible"}

COMMERCIAL
- Marchés / Clientèle : {marches or "Non disponible"}
- Clients/Références : {clients or "Non disponible"}
- Certifications : {certifs or "Non disponible"}

DÉCIDEUR PRINCIPAL À CONTACTER
{decideur_str}

RECRUTEMENT
- Offres d'emploi actuelles :
{offres or "  Aucune trouvée"}
- Signaux de croissance :
{signaux_rh or "  Non identifiés"}
- Contexte RH : {contexte_rh or "Non disponible"}

=== PROFIL OPÉRATEUR ===
- Compétences : {competences}
- Zones ciblées : {zones}
- Note opérateur sur l'entreprise : {rating or "non renseignée"}/5
- Notes personnelles : {notes or "aucune"}

=== MISSION ===
Génère un kit de préparation complet et personnalisé pour que l'opérateur approche
cette entreprise avec confiance et pertinence. Adapte chaque élément aux spécificités
du dossier ci-dessus. Si des données sont manquantes, base-toi sur le secteur d'activité."""

    return ctx
