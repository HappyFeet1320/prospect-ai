"""
Client CBE API — https://cbeapi.be/
Recherche d'entreprises belges actives via l'API REST officielle.

Avantages vs KBO Open Data :
  - Aucun index local à construire
  - Données fraîches (temps réel)
  - Coordonnées incluses (email, téléphone, site web)

Stratégie de recherche :
  La CBE API n'offre pas de recherche par NACE.
  On interroge par code postal (zones cibles du profil), on récupère toutes
  les entreprises actives (jusqu'à max_pages_per_postal pages par code postal),
  et on laisse le scoring Phase 3 filtrer par pertinence NACE.

  Avec 10 pages par code postal (= 250 entreprises), la recherche prend ~3s
  par code postal, soit 15-30s au total pour 5 à 10 codes postaux.

  Les codes NACE déclarés sont inclus dans les données (plusieurs versions NACE
  peuvent coexister : 2003, 2008, 2025). Phase 3 calcule le score sectoriel.

Limites :
  - 2 500 requêtes/jour (tier gratuit)
  - Clé API gratuite sur https://cbeapi.be
"""

import time
import requests
from loguru import logger

from config.settings import settings

_BASE_URL           = "https://cbeapi.be/api/v1"
_PER_PAGE           = 25    # l'API retourne 25 résultats par page (valeur fixe)
_MIN_DELAY          = 0.25  # secondes entre requêtes (respect rate limit)
_MAX_PAGES_DEFAULT  = 5     # pages max par code postal (= 125 entreprises, ~30s/postal)


# ============================================================
# Test de disponibilité
# ============================================================

def test_cbeapi_connection() -> tuple[bool, str]:
    """
    Vérifie que la clé CBE API est configurée et fonctionnelle.
    Retourne (ok: bool, message: str).
    """
    if not settings.CBEAPI_KEY:
        return False, (
            "Clé CBE API non configurée. "
            "Obtenez-en une gratuitement sur https://cbeapi.be, "
            "puis ajoutez CBEAPI_KEY=... dans votre fichier .env"
        )
    try:
        data = _get("/company/search", params={"post_code": "1000"})
        total = data.get("meta", {}).get("total", "?")
        total_str = f"{total:,}" if isinstance(total, int) else str(total)
        return True, f"CBE API connectée — {total_str} entreprises actives dans la base"
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            return False, "Clé CBE API invalide (401 Unauthorized). Vérifiez CBEAPI_KEY dans .env"
        return False, f"Erreur HTTP CBE API : {e}"
    except Exception as e:
        return False, f"Erreur CBE API : {e}"


# ============================================================
# Recherche principale : par codes postaux (sans filtre NACE)
# ============================================================

def search_by_postal_codes(
    postal_codes: list[str],
    nace_codes: list[str] | None = None,
    max_results: int = 2000,
    max_pages_per_postal: int = _MAX_PAGES_DEFAULT,
    progress_callback=None,
) -> list[dict]:
    """
    Recherche les entreprises actives dans les codes postaux cibles.

    La CBE API ne propose pas de recherche directe par NACE.
    Toutes les entreprises actives des codes postaux sont retournées
    (jusqu'à max_pages_per_postal pages par code postal = 250 entreprises/postal).
    Phase 3 applique ensuite le scoring sectoriel pour filtrer par NACE.

    Si nace_codes est fourni, matched_nace_codes est calculé pour affichage
    (intersect entre les codes déclarés de l'entreprise et les codes recherchés).

    Args:
        postal_codes:          Liste de codes postaux belges (4 chiffres).
        nace_codes:            Codes NACE 4 chiffres du profil (pour matched_nace_codes).
        max_results:           Nombre maximum d'entreprises à retourner.
        max_pages_per_postal:  Pages max par code postal (défaut : 10 = 250 entreprises).
        progress_callback:     fn(found, max_results) appelée après chaque page.

    Returns:
        Liste normalisée d'entreprises (format compatible avec kbo_reader).
    """
    if not settings.CBEAPI_KEY:
        raise RuntimeError(
            "Clé CBE API manquante. Ajoutez CBEAPI_KEY dans .env "
            "ou obtenez-en une gratuitement sur https://cbeapi.be"
        )

    # Normaliser les codes NACE : 4 chiffres, pour calculer matched_nace_codes
    nace_set = {c.strip()[:4] for c in (nace_codes or []) if c.strip()}

    all_companies: dict[str, dict] = {}  # bce_number → company

    for postal in postal_codes:
        if len(all_companies) >= max_results:
            break

        logger.info("CBE API — recherche code postal {} (max {} pages)", postal, max_pages_per_postal)
        page = 1

        while page <= max_pages_per_postal:
            if len(all_companies) >= max_results:
                break

            try:
                data = _get("/company/search", params={
                    "post_code": postal,
                    "page":      page,
                })
            except Exception as e:
                logger.warning("CBE API — erreur postal={} page={}: {}", postal, page, e)
                break

            companies_raw = data.get("data", [])
            if not companies_raw:
                break

            for raw in companies_raw:
                if len(all_companies) >= max_results:
                    break

                normalized = _normalize(raw, nace_set)
                if not normalized:
                    continue

                bce = normalized.get("bce_number", "")
                if bce and bce not in all_companies:
                    all_companies[bce] = normalized

            if progress_callback:
                progress_callback(len(all_companies), max_results)

            # Pagination : arrêt si dernière page atteinte
            meta      = data.get("meta", {})
            last_page = meta.get("last_page", 1)
            if page >= last_page:
                break
            page += 1
            time.sleep(_MIN_DELAY)

    result = list(all_companies.values())
    logger.info("CBE API — {} entreprises trouvées dans {} codes postaux", len(result), len(postal_codes))
    return result




# ============================================================
# Enrichissement Phase 4 : GET /company/{bceNumber}
# ============================================================

def fetch_company_by_bce(bce_number: str) -> dict | None:
    """
    Récupère les coordonnées officielles d'une entreprise via son numéro BCE.
    Utilisé en Phase 4 pour enrichir les données de contact (email, tél, site).

    Args:
        bce_number: Numéro BCE (avec ou sans points : "0773.453.366" ou "0773453366").

    Returns:
        Dict avec les champs : email, phone, website, denomination, juridical_form.
        Retourne None si la clé API manque, si l'entreprise n'est pas trouvée,
        ou en cas d'erreur réseau.
    """
    if not settings.CBEAPI_KEY:
        return None

    # Normaliser : supprimer les points (API attend "0773453366")
    bce_clean = bce_number.replace(".", "").strip()
    if not bce_clean:
        return None

    try:
        data = _get(f"/company/{bce_clean}", params={})
        company = data.get("data") or data  # la réponse est {"data": {...}}

        contacts = company.get("contact_infos") or {}

        # Codes NACE avec descriptions (toutes versions)
        nace_descriptions = []
        for act in (company.get("nace_activities") or []):
            code = str(act.get("code", "")).strip()
            desc = act.get("description", "")
            version = act.get("nace_version", "")
            if code and desc:
                nace_descriptions.append(f"{code} — {desc} ({version})")

        return {
            "email":              contacts.get("email") or "",
            "phone":              contacts.get("phone") or "",
            "website":            contacts.get("web") or "",
            "denomination":       company.get("denomination", ""),
            "legal_form":         company.get("juridical_form", ""),
            "start_date":         company.get("start_date", ""),
            "juridical_situation": company.get("juridical_situation", ""),
            "nace_descriptions":  nace_descriptions,
        }
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.debug("CBE API — entreprise {} non trouvée (404)", bce_clean)
        else:
            logger.warning("CBE API fetch_company_by_bce({}) — HTTP {}", bce_clean, e)
        return None
    except Exception as e:
        logger.warning("CBE API fetch_company_by_bce({}) — erreur: {}", bce_clean, e)
        return None


# ============================================================
# Internals
# ============================================================

def _get(path: str, params: dict) -> dict:
    """Appel GET authentifié sur l'API CBE."""
    url     = _BASE_URL + path
    headers = {
        "Authorization": f"Bearer {settings.CBEAPI_KEY}",
        "Accept":        "application/json",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _normalize(raw: dict, nace_set: set[str] | None = None) -> dict | None:
    """
    Convertit un objet entreprise CBE API au format interne de PROSPECT-AI
    (identique à celui produit par kbo_reader.py).

    Retourne None si l'entreprise est inactive ou si le numéro BCE est absent.

    Note NACE : l'API peut retourner des codes de plusieurs versions (2003, 2008, 2025).
    On conserve les 4 premiers chiffres de chaque code. Phase 3 gère le scoring sectoriel.
    """
    bce = raw.get("cbe_number", "")
    if not bce:
        return None

    # Filtrer les entreprises non actives
    status = (raw.get("status") or "").lower()
    if status and status not in ("actif", "active"):
        return None

    addr     = raw.get("address") or {}
    contacts = raw.get("contact_infos") or {}

    # Codes NACE déclarés (toutes versions, tronqués à 4 chiffres)
    nace_codes: list[str] = []
    seen_nace: set[str] = set()
    for act in (raw.get("nace_activities") or []):
        code = str(act.get("code", "")).strip()
        if code:
            code4 = code[:4]
            if code4 not in seen_nace:
                nace_codes.append(code4)
                seen_nace.add(code4)

    # Intersection avec les codes NACE recherchés (pour affichage dans les résultats)
    matched: list[str] = []
    if nace_set:
        matched = sorted(seen_nace & nace_set)

    postal  = str(addr.get("post_code", "")).strip()
    city    = str(addr.get("city", "")).strip()
    street  = str(addr.get("street", "")).strip()
    num     = str(addr.get("street_number", "")).strip()
    box     = str(addr.get("box", "")).strip()
    num_box = f"{num}{' bte ' + box if box else ''}".strip()
    address_raw = ", ".join(p for p in [num_box, street, f"{postal} {city}".strip()] if p)

    return {
        "bce_number":          bce,
        "denomination":        raw.get("denomination", ""),
        "legal_form":          raw.get("juridical_form", ""),
        "postal_code":         postal,
        "city":                city,
        "province":            "",   # non fourni par la CBE API
        "address_raw":         address_raw,
        "creation_year":       None,
        "nace_codes_declared": nace_codes,
        "matched_nace_codes":  matched,
        "matched_nace_count":  len(matched),
        "status":              "active",
        "source":              "cbe_api",
        # Coordonnées — bonus absent du KBO Open Data
        "email":               contacts.get("email") or "",
        "phone":               contacts.get("phone") or "",
        "website":             contacts.get("web") or "",
    }
