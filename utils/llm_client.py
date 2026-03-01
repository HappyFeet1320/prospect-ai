"""
Couche d'abstraction LLM pour PROSPECT-AI.
Supporte Groq (défaut) et Anthropic (Claude) via la variable LLM_PROVIDER dans .env.

Usage:
    from utils.llm_client import call_with_json_tool
    result, usage = call_with_json_tool(system, user, tool_name, tool_desc, tool_schema)

Pour basculer de provider : changer LLM_PROVIDER=groq|anthropic dans .env
"""

import json
import copy
from loguru import logger
from config.settings import settings


def call_with_json_tool(
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    tool_schema: dict,
    max_tokens: int = 4096,
) -> tuple[dict, dict]:
    """
    Appel LLM unifié avec extraction JSON garantie via function/tool calling.

    Args:
        system: Prompt système
        user: Message utilisateur
        tool_name: Nom de la fonction/outil
        tool_description: Description de la fonction/outil
        tool_schema: Schéma JSON des paramètres (format JSON Schema)

    Returns:
        (result_dict, usage_dict)
        - result_dict : JSON extrait par le modèle
        - usage_dict  : {"input_tokens", "output_tokens", "model", "provider"}

    Raises:
        ValueError: Si la clé API du provider actif est manquante
        RuntimeError: Si le modèle ne retourne pas de résultat structuré
    """
    provider = settings.LLM_PROVIDER

    if not settings.has_llm_key:
        raise ValueError(
            f"Clé API manquante pour le provider '{provider}'. "
            f"Ajoutez {'GROQ_API_KEY' if provider == 'groq' else 'ANTHROPIC_API_KEY'} dans votre .env"
        )

    logger.info(f"Appel LLM [{provider}] modele={settings.active_model} outil={tool_name}")

    if provider == "groq":
        return _call_groq(system, user, tool_name, tool_description, tool_schema, max_tokens)
    elif provider == "anthropic":
        return _call_anthropic(system, user, tool_name, tool_description, tool_schema, max_tokens)
    else:
        raise ValueError(
            f"LLM_PROVIDER='{provider}' inconnu. Valeurs acceptées : groq, anthropic"
        )


# ============================================================
# Provider : Groq (llama-3.3-70b-versatile par défaut)
# ============================================================

def _clean_schema_for_groq(schema: dict) -> dict:
    """
    Nettoie le schéma JSON pour compatibilité Groq/OpenAI.
    Supprime minItems / maxItems (non supportés par certains modèles).
    """
    UNSUPPORTED_KEYS = {"minItems", "maxItems"}
    if not isinstance(schema, dict):
        return schema

    cleaned = {}
    for k, v in schema.items():
        if k in UNSUPPORTED_KEYS:
            continue
        if isinstance(v, dict):
            cleaned[k] = _clean_schema_for_groq(v)
        elif isinstance(v, list):
            cleaned[k] = [
                _clean_schema_for_groq(i) if isinstance(i, dict) else i
                for i in v
            ]
        else:
            cleaned[k] = v
    return cleaned


def _call_groq(
    system: str, user: str,
    tool_name: str, tool_description: str, tool_schema: dict,
    max_tokens: int = 4096,
) -> tuple[dict, dict]:
    """Appel via SDK Groq avec retry automatique sur rate limit."""
    import time as _time
    from groq import Groq

    client = Groq(api_key=settings.GROQ_API_KEY)

    groq_tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_description,
            "parameters": _clean_schema_for_groq(copy.deepcopy(tool_schema)),
        }
    }

    # Retry avec backoff exponentiel (rate limit Groq = 6 000 tokens/min sur tier gratuit)
    max_retries = 4
    wait_times  = [10, 30, 60, 120]  # secondes

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=[groq_tool],
                tool_choice={"type": "function", "function": {"name": tool_name}},
                temperature=0.2,
                max_tokens=max_tokens,
            )

            message = response.choices[0].message
            if not message.tool_calls:
                raise RuntimeError(
                    f"Groq n'a pas retourné d'appel de fonction pour '{tool_name}'"
                )

            raw_args = message.tool_calls[0].function.arguments
            try:
                result = json.loads(raw_args)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Groq JSON invalide : {e}\n{raw_args[:300]}")

            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "model": settings.GROQ_MODEL,
                "provider": "groq",
            }
            logger.success(
                "Groq OK (tentative {}/{}) — {} in / {} out tokens",
                attempt + 1, max_retries,
                usage["input_tokens"], usage["output_tokens"],
            )
            return result, usage

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # Retry uniquement sur rate limit (429) ou erreurs réseau transitoires
            if "429" in str(e) or "rate_limit" in err_str or "rate limit" in err_str:
                wait = wait_times[min(attempt, len(wait_times) - 1)]
                logger.warning(
                    "Groq rate limit (tentative {}/{}) — attente {}s : {}",
                    attempt + 1, max_retries, wait, str(e)[:120],
                )
                _time.sleep(wait)
            else:
                # Erreur non-transitoire → pas de retry
                logger.error("Groq erreur non-transitoire : {}", str(e)[:200])
                raise

    raise RuntimeError(
        f"Groq — {max_retries} tentatives échouées (rate limit persistant). "
        f"Dernière erreur : {last_error}"
    )


# ============================================================
# Provider : Anthropic (Claude)
# ============================================================

def _call_anthropic(
    system: str, user: str,
    tool_name: str, tool_description: str, tool_schema: dict,
    max_tokens: int = 4096,
) -> tuple[dict, dict]:
    """Appel via SDK Anthropic avec tool_use forcé."""
    import anthropic as anthropic_sdk

    client = anthropic_sdk.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    anthropic_tool = {
        "name": tool_name,
        "description": tool_description,
        "input_schema": tool_schema,
    }

    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        tools=[anthropic_tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )

    result = None
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            result = block.input
            break

    if result is None:
        raise RuntimeError(f"Claude n'a pas retourné de résultat pour '{tool_name}'")

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": settings.CLAUDE_MODEL,
        "provider": "anthropic",
    }

    logger.success(
        f"Claude OK — {usage['input_tokens']} tokens in / {usage['output_tokens']} tokens out"
    )
    return result, usage
