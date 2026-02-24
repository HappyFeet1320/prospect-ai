"""
Phase 1 — Profiling Opérateur
Analyse du texte libre de l'opérateur via LLM (Groq ou Anthropic).
Extraction d'un profil normalisé avec codes NACE belges.
"""

import json
from loguru import logger
from config.settings import settings
from utils.llm_client import call_with_json_tool


# ============================================================
# Schéma JSON de l'outil d'extraction de profil
# ============================================================

PROFILE_TOOL_NAME = "extract_operator_profile"

PROFILE_TOOL_DESCRIPTION = (
    "Extrait et structure le profil professionnel d'un opérateur belge "
    "depuis une description en langage naturel. Génère les codes NACE "
    "belges pertinents et identifie les informations manquantes."
)

PROFILE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "profile_summary": {
            "type": "string",
            "description": "Résumé synthétique du profil en 3 à 5 phrases claires"
        },
        "experiences": {
            "type": "array",
            "description": "Liste des expériences professionnelles identifiées",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Intitulé du poste"},
                    "company": {"type": "string", "description": "Nom de l'entreprise"},
                    "duration_years": {"type": "number", "description": "Durée estimée en années"},
                    "key_responsibilities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Responsabilités et missions clés"
                    }
                },
                "required": ["title"]
            }
        },
        "nace_codes": {
            "type": "array",
            "description": "Entre 3 et 10 codes NACE belges pertinents (nomenclature NACE-BEL 2008). Minimum 3, maximum 10.",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Code NACE à 4 chiffres (ex: 6201)"},
                    "label": {"type": "string", "description": "Libellé du secteur en français"},
                    "weight": {
                        "type": "number",
                        "description": "Poids de pertinence entre 0.0 et 1.0 (1.0 = secteur principal)"
                    },
                    "justification": {
                        "type": "string",
                        "description": "Explication courte du lien avec le profil"
                    }
                },
                "required": ["code", "label", "weight", "justification"]
            }
        },
        "target_locations": {
            "type": "array",
            "description": "Zones géographiques cibles en Belgique",
            "items": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Nom de la ville ou commune"},
                    "postal_code": {"type": "string", "description": "Code postal belge (ex: 1000)"},
                    "province": {
                        "type": "string",
                        "description": "Province ou région belge",
                        "enum": [
                            "Bruxelles-Capitale",
                            "Brabant wallon", "Brabant flamand",
                            "Anvers", "Gand", "Flandre occidentale", "Flandre orientale",
                            "Liège", "Hainaut", "Namur", "Luxembourg", "Limbourg"
                        ]
                    }
                },
                "required": ["city"]
            }
        },
        "search_radius_km": {
            "type": "integer",
            "description": "Rayon de recherche en kilomètres depuis la localisation principale (défaut: 30)"
        },
        "contract_types": {
            "type": "array",
            "description": "Types de contrat acceptés",
            "items": {
                "type": "string",
                "enum": ["CDI", "CDD", "Freelance", "Intérim", "Alternance", "Job étudiant", "Stage", "Indépendant"]
            }
        },
        "seniority_level": {
            "type": "string",
            "description": "Niveau hiérarchique cible",
            "enum": ["junior", "medior", "senior", "direction"]
        },
        "must_have_skills": {
            "type": "array",
            "description": "Compétences non-négociables (maximum 8)",
            "items": {"type": "string"}
        },
        "nice_to_have_skills": {
            "type": "array",
            "description": "Compétences bonus (maximum 8)",
            "items": {"type": "string"}
        },
        "exclusion_list": {
            "type": "array",
            "description": "Secteurs, types d'entreprises ou situations à exclure",
            "items": {"type": "string"}
        },
        "languages": {
            "type": "array",
            "description": "Langues maîtrisées (codes ISO 639-1)",
            "items": {"type": "string", "enum": ["fr", "nl", "de", "en", "es", "it", "pt", "ar", "zh"]}
        },
        "salary_expectation": {
            "type": "string",
            "description": "Prétentions salariales ou taux journalier si mentionné"
        },
        "company_size_preference": {
            "type": "array",
            "description": "Taille d'entreprise préférée",
            "items": {
                "type": "string",
                "enum": ["Startup", "PME", "ETI", "Grande entreprise", "Administration publique"]
            }
        },
        "availability": {
            "type": "string",
            "description": "Disponibilité (ex: 'Immédiate', 'Préavis 1 mois', 'À partir du 01/03/2026')"
        },
        "mobility": {
            "type": "object",
            "description": "Préférences de mobilité",
            "properties": {
                "remote": {"type": "boolean", "description": "Télétravail accepté/souhaité"},
                "travel_accepted": {"type": "boolean", "description": "Déplacements professionnels acceptés"},
                "international": {"type": "boolean", "description": "Mobilité internationale"}
            }
        },
        "missing_required_fields": {
            "type": "array",
            "description": "Liste des champs obligatoires manquants ou insuffisamment précis dans la description de l'opérateur. Exemples : 'experiences', 'localisation', 'contract_types', 'availability', 'skills', 'salary_expectation'",
            "items": {"type": "string"}
        },
        "follow_up_questions": {
            "type": "array",
            "description": "Questions de relance pour compléter le profil (maximum 4)",
            "items": {"type": "string"}
        },
        "confidence_scores": {
            "type": "object",
            "description": "Score de confiance (0.0 à 1.0) pour chaque section clé du profil",
            "properties": {
                "experiences": {"type": "number"},
                "skills": {"type": "number"},
                "location": {"type": "number"},
                "nace_codes": {"type": "number"},
                "contract_types": {"type": "number"}
            }
        }
    },
    "required": [
        "profile_summary",
        "nace_codes",
        "contract_types",
        "seniority_level",
        "must_have_skills",
        "missing_required_fields",
        "follow_up_questions"
    ]
}


SYSTEM_PROMPT = """Tu es PROSPECT-AI, un assistant spécialisé dans l'analyse de profils professionnels belges.

Ton rôle est d'analyser la description qu'un opérateur (chercheur d'emploi, freelance, reconversion)
fait de lui-même et d'extraire un profil structuré pour l'aider à trouver des opportunités en Belgique.

Règles importantes :
- Utilise exclusivement les codes NACE-BEL 2008 (4 chiffres)
- Les codes NACE doivent refléter les SECTEURS CIBLES pour la recherche d'emploi, pas forcément le secteur de l'opérateur
- Pondère les codes NACE de 0.0 à 1.0 (1.0 = secteur prioritaire)
- Génère OBLIGATOIREMENT entre 3 et 10 codes NACE
- Pour la localisation, traduis les descriptions géographiques en communes belges réelles avec codes postaux
- Identifie PRÉCISÉMENT ce qui manque dans la description pour poser des questions ciblées
- Réponds en français

Contexte géographique : Belgique uniquement (Région wallonne, flamande, Bruxelles-Capitale)
"""


# ============================================================
# Fonction principale
# ============================================================

def analyze_profile(raw_text: str, previous_profile: dict | None = None) -> dict:
    """
    Analyse le texte libre de l'opérateur et retourne un profil structuré.
    Utilise le provider LLM configuré dans .env (Groq par défaut).

    Args:
        raw_text: Description libre de l'opérateur
        previous_profile: Profil existant à enrichir (mode relance)

    Returns:
        dict contenant le profil normalisé + métadonnées (model_used, tokens)
    """
    if previous_profile:
        user_content = (
            f"PROFIL EXISTANT (à enrichir / corriger) :\n"
            f"{json.dumps(previous_profile, ensure_ascii=False, indent=2)}\n\n"
            f"INFORMATIONS COMPLÉMENTAIRES FOURNIES PAR L'OPÉRATEUR :\n{raw_text}"
        )
    else:
        user_content = (
            f"Voici la description que l'opérateur a faite de sa situation professionnelle :\n\n"
            f"{raw_text}\n\n"
            f"Analyse ce texte et extrais le profil structuré."
        )

    logger.info(
        f"Analyse profil [{settings.provider_label}] — {len(raw_text)} caractères"
    )

    profile, usage = call_with_json_tool(
        system=SYSTEM_PROMPT,
        user=user_content,
        tool_name=PROFILE_TOOL_NAME,
        tool_description=PROFILE_TOOL_DESCRIPTION,
        tool_schema=PROFILE_TOOL_SCHEMA,
    )

    # Enrichissement avec métadonnées
    profile["raw_input"] = raw_text
    profile["model_used"] = usage["model"]
    profile["provider_used"] = usage["provider"]
    profile["input_tokens"] = usage["input_tokens"]
    profile["output_tokens"] = usage["output_tokens"]

    logger.success(
        f"Profil extrait — {len(profile.get('nace_codes', []))} codes NACE, "
        f"{len(profile.get('missing_required_fields', []))} champs manquants"
    )

    return profile


# ============================================================
# Utilitaires
# ============================================================

def is_profile_complete(profile: dict) -> bool:
    """Vérifie si le profil contient tous les champs obligatoires."""
    return len(profile.get("missing_required_fields", [])) == 0


def get_profile_completeness_pct(profile: dict) -> int:
    """Calcule un pourcentage de complétude du profil (0-100)."""
    required_keys = [
        "profile_summary", "nace_codes", "target_locations",
        "contract_types", "seniority_level", "must_have_skills",
        "availability"
    ]
    filled = sum(1 for k in required_keys if profile.get(k))
    return int((filled / len(required_keys)) * 100)


def format_profile_for_display(profile: dict) -> dict:
    """Prépare le profil pour l'affichage dans l'interface Streamlit."""
    nace_sorted = sorted(
        profile.get("nace_codes", []),
        key=lambda x: x.get("weight", 0),
        reverse=True
    )

    locations = profile.get("target_locations", [])
    loc_str = ", ".join(
        f"{loc.get('city', '')} ({loc.get('postal_code', '')})"
        for loc in locations
    ) or "Non précisée"

    return {
        "Résumé": profile.get("profile_summary", ""),
        "Niveau": profile.get("seniority_level", "").capitalize(),
        "Localisation": loc_str,
        "Rayon": f"{profile.get('search_radius_km', 30)} km",
        "Contrats": ", ".join(profile.get("contract_types", [])),
        "Disponibilité": profile.get("availability", "Non précisée"),
        "Compétences clés": profile.get("must_have_skills", []),
        "Compétences bonus": profile.get("nice_to_have_skills", []),
        "Codes NACE": nace_sorted,
        "Secteurs exclus": profile.get("exclusion_list", []),
        "Langues": profile.get("languages", []),
        "Mobilité": profile.get("mobility", {}),
        "Taille entreprise": profile.get("company_size_preference", []),
        "Complétude": f"{get_profile_completeness_pct(profile)}%",
        "Questions en attente": profile.get("follow_up_questions", []),
        "Provider": f"{profile.get('provider_used', '?')} / {profile.get('model_used', '?')}",
    }
