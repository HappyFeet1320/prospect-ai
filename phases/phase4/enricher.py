"""
Phase 4 — Enrichissement d'une entreprise.

Pour chaque entreprise :
  0. CBE API → coordonnées officielles + date création + situation juridique + NACE
  1. Recherche site web (CBE en priorité, sinon DDG)
  2. Scraping multi-pages du site (À propos, Carrières)
  3. Recherches DDG en parallèle (ThreadPoolExecutor) :
       - Actualités / presse
       - Offres d'emploi
       - Dirigeants (web + LinkedIn DDG)
       - Données financières (NBB, presse économique)
  4. Appel LLM → synthèse complète structurée en 5 blocs
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlparse, unquote

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from utils.llm_client import call_with_json_tool
from phases.phase2.cbeapi_client import fetch_company_by_bce


# ============================================================
# Configuration d'enrichissement
# ============================================================

@dataclass
class EnrichConfig:
    """
    Contrôle les sources utilisées lors de l'enrichissement Phase 4.

    Presets :
        EnrichConfig.rapide()    → CBE API seule         (~2-5s/entreprise)
        EnrichConfig.standard()  → CBE + Web + DDG       (~30-45s/entreprise)
        EnrichConfig.complet()   → Tout activé           (~60-90s/entreprise)
    """
    use_cbe_api:      bool = True   # CBE API — coordonnées officielles
    use_web_scraping: bool = True   # Scraping du site web (About, Carrières)
    use_ddg_news:     bool = True   # DDG actualités / presse
    use_ddg_jobs:     bool = True   # DDG offres d'emploi
    use_ddg_managers: bool = True   # DDG dirigeants web
    use_linkedin:     bool = False  # DDG profils LinkedIn (plus lent)
    use_financial:    bool = False  # DDG données financières (NBB, presse éco)

    @classmethod
    def rapide(cls) -> "EnrichConfig":
        """CBE API uniquement — coordonnées officielles, pas de web."""
        return cls(
            use_cbe_api=True,
            use_web_scraping=False,
            use_ddg_news=False, use_ddg_jobs=False, use_ddg_managers=False,
            use_linkedin=False, use_financial=False,
        )

    @classmethod
    def standard(cls) -> "EnrichConfig":
        """CBE + site web + DDG (actualités, emplois, dirigeants) — mode recommandé."""
        return cls(
            use_cbe_api=True,
            use_web_scraping=True,
            use_ddg_news=True, use_ddg_jobs=True, use_ddg_managers=True,
            use_linkedin=False, use_financial=False,
        )

    @classmethod
    def complet(cls) -> "EnrichConfig":
        """Toutes sources activées — LinkedIn + données financières inclus."""
        return cls(
            use_cbe_api=True,
            use_web_scraping=True,
            use_ddg_news=True, use_ddg_jobs=True, use_ddg_managers=True,
            use_linkedin=True, use_financial=True,
        )

    @classmethod
    def web_seulement(cls) -> "EnrichConfig":
        """Web + DDG uniquement — sans CBE API (si clé non configurée)."""
        return cls(
            use_cbe_api=False,
            use_web_scraping=True,
            use_ddg_news=True, use_ddg_jobs=True, use_ddg_managers=True,
            use_linkedin=False, use_financial=False,
        )


# ============================================================
# Headers HTTP
# ============================================================

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-BE,fr;q=0.9,nl;q=0.8,en;q=0.7",
}

_TIMEOUT = 15


# ============================================================
# Point d'entrée principal
# ============================================================

def enrich_company(
    company: dict,
    profile: dict,
    config: EnrichConfig | None = None,
) -> dict:
    """
    Constitue le dossier complet Phase 4 pour une entreprise.

    Args:
        company : dict Phase 2/3 (bce_number, denomination, city, …)
        profile : dict profil opérateur Phase 1
        config  : EnrichConfig — contrôle les sources utilisées
                  (défaut : EnrichConfig.standard())

    Returns:
        dict dossier avec 5 blocs.
    """
    if config is None:
        config = EnrichConfig.rapide()

    name  = company.get("denomination", "")
    city  = company.get("city", "")
    bce   = company.get("bce_number", "")
    nace  = company.get("nace_searched", "")

    logger.info("Phase 4 enrichissement — {} ({})", name[:50], bce)

    dossier = {
        "enriched_at":      datetime.now().isoformat(),
        "bloc_identite":    _build_identite(company),
        "bloc_financier":   {},
        "bloc_commercial":  {},
        "bloc_decideurs":   [],
        "bloc_recrutement": {},
        "website_url":      "",
        "sources_used":     [],
    }

    # ── 0. CBE API — coordonnées + données officielles ───────
    cbe_contacts: dict | None = None
    if config.use_cbe_api:
        cbe_contacts = fetch_company_by_bce(bce)
        if cbe_contacts:
            dossier["bloc_identite"].update({
                "email_bce":           cbe_contacts.get("email", ""),
                "phone_bce":           cbe_contacts.get("phone", ""),
                "website_bce":         cbe_contacts.get("website", ""),
                "start_date_bce":      cbe_contacts.get("start_date", ""),
                "juridical_situation": cbe_contacts.get("juridical_situation", ""),
            })
            dossier["sources_used"].append("cbe_api")
            logger.debug("CBE API — {} : email={} tél={} web={}",
                         name[:40],
                         cbe_contacts.get("email") or "—",
                         cbe_contacts.get("phone") or "—",
                         cbe_contacts.get("website") or "—")

    if not cbe_contacts:
        dossier["bloc_identite"].update({
            "email_bce": "", "phone_bce": "", "website_bce": "",
            "start_date_bce": "", "juridical_situation": "",
        })

    # ── 1. URL du site web ────────────────────────────────────
    # Priorité : CBE API > rien (la recherche DDG se fait dans le pool)
    website_url: str = (cbe_contacts or {}).get("website", "")

    # ── 2. Recherches web (seulement si un mode web est activé) ─
    website_data: dict = {}
    news_snippets: list[str]      = []
    job_snippets: list[str]       = []
    manager_snippets: list[str]   = []
    linkedin_snippets: list[str]  = []
    financial_snippets: list[str] = []

    need_web = (
        config.use_web_scraping
        or config.use_ddg_news
        or config.use_ddg_jobs
        or config.use_ddg_managers
        or config.use_linkedin
        or config.use_financial
    )

    if need_web:
        # Trouver l'URL si pas fournie par CBE (obligatoire pour le scraping)
        if config.use_web_scraping and not website_url:
            website_url = _find_website(name, city)

        # Lancer les recherches DDG + scraping en parallèle
        tasks: dict = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            scrape_fut = None
            if config.use_web_scraping and website_url:
                scrape_fut = executor.submit(_deep_scrape_website, website_url)
            if config.use_ddg_news:
                tasks[executor.submit(_search_news, name, city)] = "news"
            if config.use_ddg_jobs:
                tasks[executor.submit(_search_jobs, name, city)] = "jobs"
            if config.use_ddg_managers:
                tasks[executor.submit(_search_managers, name, city)] = "managers"
            if config.use_linkedin:
                tasks[executor.submit(_search_linkedin_managers, name, city)] = "linkedin"
            if config.use_financial:
                tasks[executor.submit(_search_financial, name, city)] = "financial"

            for fut in as_completed(tasks):
                key = tasks[fut]
                try:
                    res = fut.result()
                except Exception:
                    res = []
                if key == "news":
                    news_snippets = res
                elif key == "jobs":
                    job_snippets = res
                elif key == "managers":
                    manager_snippets = res
                elif key == "linkedin":
                    linkedin_snippets = res
                elif key == "financial":
                    financial_snippets = res

            if scrape_fut:
                try:
                    website_data = scrape_fut.result() or {}
                    if website_data.get("text"):
                        dossier["sources_used"].append(f"site:{website_url}")
                except Exception:
                    website_data = {}

    dossier["website_url"] = website_url
    dossier["bloc_identite"]["website_url"] = website_url

    # Fusionner manager web + LinkedIn (dédoublonnage)
    all_manager_snippets = list(dict.fromkeys(manager_snippets + linkedin_snippets))[:8]

    # ── 3. Texte agrégé pour le LLM ──────────────────────────
    context = _build_llm_context(
        website_data, news_snippets, job_snippets,
        all_manager_snippets, financial_snippets, cbe_contacts,
    )

    # ── 5. Analyse LLM ───────────────────────────────────────
    llm = _llm_analyze(company, profile, context)

    # ── 6. Assembler le dossier ──────────────────────────────
    # Coordonnées : priorité CBE API (officiel) > scraping site web
    email_final = (cbe_contacts or {}).get("email") or website_data.get("email", "")
    phone_final = (cbe_contacts or {}).get("phone") or website_data.get("telephone", "")

    dossier["bloc_identite"].update({
        "description_ia":  llm.get("description", ""),
        "clients_types":   llm.get("clients_types", ""),
        "marches":         llm.get("marches", ""),
        "email_general":   email_final,
        "telephone":       phone_final,
        "reseaux_sociaux": website_data.get("social_links", []),
    })

    dossier["bloc_financier"] = {
        "tendance":          llm.get("tendance_financiere", "inconnu"),
        "signal_label":      llm.get("signal_label", "Données non disponibles"),
        "ca_estime":         llm.get("ca_estime", ""),
        "effectif_estime":   llm.get("effectif_estime", ""),
        "risque":            llm.get("risque_financier", "inconnu"),
        "evolution":         llm.get("evolution_ca", ""),
        "note":              "Estimations IA — sources : site web, presse, BCE",
    }

    dossier["bloc_commercial"] = {
        "clients_connus":    llm.get("clients_connus", []),
        "partenaires":       llm.get("partenaires", []),
        "offres_emploi":     _merge_job_offers(website_data, job_snippets),
        "marches":           llm.get("marches", ""),
        "type_clientele":    llm.get("clients_types", ""),
        "references":        website_data.get("references", []),
        "certifications":    website_data.get("certifications", []),
    }

    dossier["bloc_decideurs"] = llm.get("decideurs", [])

    dossier["bloc_recrutement"] = {
        "signaux_croissance": llm.get("signaux_croissance", []),
        "signaux_difficulte": llm.get("signaux_difficulte", []),
        "offres_actives":     _merge_job_offers(website_data, job_snippets),
        "derniere_mention":   llm.get("derniere_mention", ""),
        "contexte_rh":        llm.get("contexte_rh", ""),
    }

    logger.success("Phase 4 — {} — dossier constitué ({} sources)", name[:50], len(dossier["sources_used"]))
    return dossier


# ============================================================
# Bloc Identité depuis KBO
# ============================================================

def _build_identite(company: dict) -> dict:
    creation_year = company.get("creation_year") or company.get("start_year")
    try:
        age = (datetime.now().year - int(creation_year)) if creation_year else None
    except (ValueError, TypeError):
        age = None
    return {
        "bce_number":    company.get("bce_number", ""),
        "denomination":  company.get("denomination", ""),
        "legal_form":    company.get("legal_form", ""),
        "address":       company.get("address_raw", ""),
        "city":          company.get("city", ""),
        "postal_code":   company.get("postal_code", ""),
        "province":      company.get("province", ""),
        "creation_year": creation_year,
        "age_years":     age,
        "nace_searched": company.get("nace_searched", ""),
        "description_ia": "",
        "website_url":   "",
    }


# ============================================================
# Recherche DuckDuckGo
# ============================================================

def _ddg_search(query: str, max_results: int = 8) -> list[dict]:
    """Requête DuckDuckGo HTML → liste de {title, url, snippet}."""
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "be-fr"},
                headers=_HEADERS,
            )
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "lxml")
        results = []
        for el in soup.select(".result")[:max_results]:
            a = el.select_one(".result__title a")
            s = el.select_one(".result__snippet")
            if not a:
                continue
            href = a.get("href", "")
            m = re.search(r"uddg=([^&]+)", href)
            url = unquote(m.group(1)) if m else href
            results.append({
                "title":   a.get_text(strip=True),
                "url":     url,
                "snippet": s.get_text(strip=True) if s else "",
            })
        return results
    except Exception as e:
        logger.debug("DDG search '{}' erreur: {}", query[:50], e)
        return []


def _find_website(name: str, city: str) -> str:
    """Trouve l'URL du site officiel de l'entreprise."""
    EXCLUDE = (
        "facebook.com", "linkedin.com", "twitter.com", "instagram.com",
        "youtube.com", "kbopub.economie.fgov.be", "nbb.be", "belgique.be",
        "monster.", "indeed.", "jobat.", "references.be", "companyweb",
        "voka.be", "beci.be", "wikipedia", "pages-jaunes", "gouden-gids",
        "zlatestranky", "infobel", "kompass", "europages", "dnb.com",
        "google.", "bing.", "duckduckgo.", "yelp.", "tripadvisor.",
    )
    results = _ddg_search(f'"{name}" {city} Belgique site officiel')
    for r in results:
        url = r.get("url", "")
        if not url.startswith("http"):
            continue
        if any(ex in url.lower() for ex in EXCLUDE):
            continue
        return url
    return ""


def _search_news(name: str, city: str) -> list[str]:
    """Cherche les actualités récentes de l'entreprise."""
    results = _ddg_search(f'"{name}" {city} actualités 2024 2025 recrutement croissance')
    return [f"{r['title']} — {r['snippet']}" for r in results if r.get("snippet")][:6]


def _search_jobs(name: str, city: str) -> list[str]:
    """Cherche les offres d'emploi de l'entreprise."""
    results = _ddg_search(f'"{name}" offre emploi recrutement CDI CDD 2024 2025 indeed jobat linkedin')
    return [f"{r['title']} : {r['snippet']}" for r in results if r.get("snippet")][:6]


def _search_managers(name: str, city: str) -> list[str]:
    """Cherche les dirigeants et managers de l'entreprise."""
    results = _ddg_search(f'"{name}" {city} directeur CEO dirigeant DRH manager responsable')
    return [f"{r['title']} — {r['snippet']}" for r in results if r.get("snippet")][:6]


def _search_linkedin_managers(name: str, city: str) -> list[str]:
    """Cherche les profils LinkedIn des dirigeants de l'entreprise."""
    results = _ddg_search(
        f'site:linkedin.com/in "{name}" directeur OR CEO OR DRH OR founder OR manager OR responsable'
    )
    return [f"{r['title']} — {r['snippet']}" for r in results if r.get("snippet")][:5]


def _search_financial(name: str, city: str) -> list[str]:
    """Cherche les données financières publiées (NBB, presse économique)."""
    results = _ddg_search(
        f'"{name}" {city} chiffre affaires résultats bilan comptes annuels NBB croissance'
    )
    return [f"{r['title']} — {r['snippet']}" for r in results if r.get("snippet")][:5]


# ============================================================
# Scraping du site web
# ============================================================

_ABOUT_PATHS = [
    "/a-propos", "/about", "/qui-sommes-nous", "/over-ons",
    "/about-us", "/notre-entreprise", "/notre-societe", "/contact",
    "/equipe", "/team", "/management",
]

_JOB_PATHS = [
    "/emploi", "/jobs", "/carrieres", "/recrutement", "/vacatures",
    "/offres-emploi", "/work-with-us", "/join-us", "/rejoignez-nous",
]


def _deep_scrape_website(url: str) -> dict:
    """
    Scraping multi-pages du site web de l'entreprise.
    Retourne un dict avec: text, email, telephone, social_links,
    references, certifications, job_mentions.
    """
    result = {
        "text":           "",
        "email":          "",
        "telephone":      "",
        "social_links":   [],
        "references":     [],
        "certifications": [],
        "job_mentions":   [],
    }

    base = _base_url(url)
    pages_scraped = []

    # Page principale
    main_text, main_soup = _fetch_page_text(url)
    if main_text:
        result["text"] += main_text[:3000]
        pages_scraped.append(url)
        _extract_contacts(main_soup, result)
        _extract_socials(main_soup, url, result)
        _extract_references(main_soup, result)

    if not main_text:
        return result

    # Pages "À propos" et "Carrières"
    for path in _ABOUT_PATHS[:4]:
        about_url = urljoin(base, path)
        if about_url in pages_scraped:
            continue
        t, _ = _fetch_page_text(about_url)
        if t and len(t) > 200:
            result["text"] += "\n\n" + t[:1500]
            pages_scraped.append(about_url)
            break

    for path in _JOB_PATHS[:3]:
        job_url = urljoin(base, path)
        if job_url in pages_scraped:
            continue
        t, s = _fetch_page_text(job_url)
        if t and len(t) > 200:
            result["text"] += "\n\n[OFFRES EMPLOI] " + t[:1000]
            _extract_job_mentions(s, result)
            pages_scraped.append(job_url)
            break

    # Nettoyer
    result["text"] = re.sub(r"\s{3,}", "  ", result["text"])[:6000]
    return result


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _fetch_page_text(url: str) -> tuple[str, BeautifulSoup | None]:
    """Récupère et nettoie le texte d'une page web."""
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = client.get(url, headers=_HEADERS)
        if r.status_code != 200:
            return "", None
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s{3,}", "  ", text)
        return text, soup
    except Exception:
        return "", None


_SKIP_EMAIL_PREFIXES = frozenset({
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "webmaster", "postmaster", "mailer-daemon", "bounce",
    "newsletter", "unsubscribe",
})


def _extract_contacts(soup: BeautifulSoup | None, result: dict) -> None:
    if not soup:
        return
    text = soup.get_text(" ")
    # Emails : prendre le premier qui n'est pas une adresse technique
    emails = re.findall(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
    for email in emails:
        local = email.split("@")[0].lower().replace(".", "-")
        if local not in _SKIP_EMAIL_PREFIXES:
            result["email"] = email
            break
    if not result.get("email") and emails:
        result["email"] = emails[0]  # fallback : premier email trouvé
    # Téléphone belge
    m = re.search(r"(?:\+32|0)[\s.-]?\d[\d\s.-]{6,12}", text)
    if m:
        result["telephone"] = re.sub(r"\s+", " ", m.group(0)).strip()


def _extract_socials(soup: BeautifulSoup | None, base: str, result: dict) -> None:
    if not soup:
        return
    SOCIAL = ["linkedin.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com"]
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(base, href)
        for s in SOCIAL:
            if s in href and href not in seen:
                result["social_links"].append(href)
                seen.add(href)


def _extract_references(soup: BeautifulSoup | None, result: dict) -> None:
    if not soup:
        return
    text = soup.get_text(" ")
    # Chercher des mentions de clients/références
    patterns = [
        r"(?:nos clients|our clients|onze klanten)[^.]{0,200}",
        r"(?:références|références clients|client references)[^.]{0,200}",
        r"(?:ils nous font confiance|trusted by)[^.]{0,200}",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["references"].append(m.group(0).strip()[:200])
    # Certifications
    cert_patterns = [r"ISO \d{4,5}", r"GDPR compliant", r"certifi[eé]", r"label"]
    for pat in cert_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            ctx = text[max(0, m.start()-20):m.end()+60].strip()
            if ctx not in result["certifications"]:
                result["certifications"].append(ctx[:100])


def _extract_job_mentions(soup: BeautifulSoup | None, result: dict) -> None:
    if not soup:
        return
    text = soup.get_text(" ")
    for pat in [
        r"(?:CDI|CDD|temps plein|temps partiel|intérim)[^.]{10,80}",
        r"(?:cherche|recrute|poste ouvert)[^.]{10,80}",
    ]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            offer = m.group(0).strip()[:120]
            if offer not in result["job_mentions"] and len(offer) > 15:
                result["job_mentions"].append(offer)
        if len(result["job_mentions"]) >= 5:
            break


def _merge_job_offers(website_data: dict, job_snippets: list[str]) -> list[str]:
    """Fusionne les offres trouvées via scraping et recherche web."""
    offers = list(website_data.get("job_mentions", []))
    for s in job_snippets:
        if s not in offers and len(s) > 10:
            offers.append(s[:150])
    return list(dict.fromkeys(offers))[:6]


# ============================================================
# Contexte pour le LLM
# ============================================================

def _build_llm_context(
    website_data: dict,
    news_snippets: list[str],
    job_snippets:  list[str],
    manager_snippets:  list[str],
    financial_snippets: list[str] | None = None,
    cbe_contacts: dict | None = None,
) -> str:
    parts = []

    # Données officielles BCE (source la plus fiable)
    if cbe_contacts:
        cbe_lines = []
        if cbe_contacts.get("email"):
            cbe_lines.append(f"Email officiel : {cbe_contacts['email']}")
        if cbe_contacts.get("phone"):
            cbe_lines.append(f"Téléphone officiel : {cbe_contacts['phone']}")
        if cbe_contacts.get("website"):
            cbe_lines.append(f"Site web officiel : {cbe_contacts['website']}")
        if cbe_contacts.get("start_date"):
            cbe_lines.append(f"Date de création : {cbe_contacts['start_date']}")
        if cbe_contacts.get("juridical_situation"):
            cbe_lines.append(f"Situation juridique : {cbe_contacts['juridical_situation']}")
        if cbe_contacts.get("nace_descriptions"):
            nace_list = "\n".join(
                f"  • {n}" for n in cbe_contacts["nace_descriptions"][:8]
            )
            cbe_lines.append(f"Activités NACE déclarées :\n{nace_list}")
        if cbe_lines:
            parts.append("=== DONNÉES OFFICIELLES BCE ===\n" + "\n".join(cbe_lines))

    if website_data.get("text"):
        parts.append(f"=== CONTENU SITE WEB ===\n{website_data['text'][:3000]}")

    if not (cbe_contacts or {}).get("email") and website_data.get("email"):
        parts.append(f"Email trouvé (scraping) : {website_data['email']}")
    if not (cbe_contacts or {}).get("phone") and website_data.get("telephone"):
        parts.append(f"Téléphone trouvé (scraping) : {website_data['telephone']}")
    if website_data.get("references"):
        parts.append("Références/clients mentionnés :\n" + "\n".join(f"- {r}" for r in website_data["references"]))
    if website_data.get("certifications"):
        parts.append("Certifications :\n" + "\n".join(f"- {c}" for c in website_data["certifications"]))

    if news_snippets:
        parts.append("=== ACTUALITÉS / PRESSE ===\n" + "\n".join(f"- {s}" for s in news_snippets))

    if financial_snippets:
        parts.append("=== DONNÉES FINANCIÈRES ===\n" + "\n".join(f"- {s}" for s in financial_snippets))

    if job_snippets:
        parts.append("=== OFFRES D'EMPLOI DÉTECTÉES ===\n" + "\n".join(f"- {s}" for s in job_snippets))

    if manager_snippets:
        parts.append("=== DIRIGEANTS / MANAGERS (web + LinkedIn) ===\n" + "\n".join(f"- {s}" for s in manager_snippets))

    return "\n\n".join(parts) if parts else "Aucune information trouvée en ligne."


# ============================================================
# Analyse LLM
# ============================================================

_LLM_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "Description complète de l'entreprise en 5-8 phrases : activité principale, positionnement marché, points forts, culture d'entreprise si connue.",
        },
        "clients_types": {
            "type": "string",
            "description": "Type de clientèle : B2B, B2C, B2G ou mixte, avec précision si possible.",
        },
        "marches": {
            "type": "string",
            "description": "Marchés adressés : local, national, européen, international.",
        },
        "clients_connus": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Clients ou références connus mentionnés publiquement (max 8).",
        },
        "partenaires": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Partenaires technologiques ou commerciaux connus (max 5).",
        },
        "certifications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Certifications ou labels détectés (ISO, labels qualité, etc.).",
        },
        "tendance_financiere": {
            "type": "string",
            "enum": ["croissance", "stable", "déclin", "inconnu"],
        },
        "signal_label": {
            "type": "string",
            "description": "Phrase courte résumant le signal financier (ex: 'Croissance notable depuis 2022 — nouvelles offres détectées').",
        },
        "ca_estime": {
            "type": "string",
            "description": "Estimation du CA si des indices sont disponibles, sinon vide (ex: '2-5 M€').",
        },
        "effectif_estime": {
            "type": "string",
            "description": "Estimation de l'effectif depuis les indices disponibles (ex: '10-50 employés').",
        },
        "evolution_ca": {
            "type": "string",
            "description": "Description de l'évolution du CA si connue, sinon vide.",
        },
        "risque_financier": {
            "type": "string",
            "enum": ["faible", "modéré", "élevé", "inconnu"],
        },
        "decideurs": {
            "type": "array",
            "description": "Décideurs clés identifiés ou estimés (viser 3-5 personnes).",
            "items": {
                "type": "object",
                "properties": {
                    "prenom_nom": {"type": "string"},
                    "titre":      {"type": "string"},
                    "type":       {
                        "type": "string",
                        "enum": ["CEO", "DRH", "DEPT_HEAD", "OFFICE_MGR", "AUTRE"],
                    },
                    "bio_courte": {
                        "type": "string",
                        "description": "Biographie de 2-3 phrases sur son rôle et profil.",
                    },
                    "linkedin_url": {"type": "string", "description": "URL LinkedIn si trouvée."},
                    "email":        {"type": "string", "description": "Email si trouvé."},
                    "source":       {
                        "type": "string",
                        "enum": ["site_web", "recherche_web", "estimation_ia"],
                    },
                },
                "required": ["prenom_nom", "titre", "type", "bio_courte", "source"],
            },
        },
        "signaux_croissance": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Signaux positifs : nouveaux clients, expansion, recrutements, levées de fonds, récompenses…",
        },
        "signaux_difficulte": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Signaux négatifs : restructuration, départs de dirigeants, mauvaise presse, CA en baisse…",
        },
        "derniere_mention": {
            "type": "string",
            "description": "Dernière mention presse trouvée avec date si disponible.",
        },
        "contexte_rh": {
            "type": "string",
            "description": "Analyse RH : ambiance de recrutement, types de profils recherchés, politique RH visible.",
        },
    },
    "required": ["description", "clients_types", "tendance_financiere", "decideurs", "signaux_croissance"],
}


def _llm_analyze(company: dict, profile: dict, context: str) -> dict:
    """Appelle le LLM pour analyser et synthétiser toutes les infos trouvées."""
    name       = company.get("denomination", "")
    city       = company.get("city", "")
    legal_form = company.get("legal_form", "")
    nace       = company.get("nace_searched", "")
    creation   = company.get("creation_year", "")
    bce        = company.get("bce_number", "")
    try:
        age = (datetime.now().year - int(creation)) if creation else "?"
    except (ValueError, TypeError):
        age = "?"

    # Récupérer le titre depuis la première expérience (schéma profiler.py)
    exps = profile.get("experiences", [])
    operator_title = (exps[0].get("title", "") if exps and isinstance(exps[0], dict) else "") \
        or profile.get("current_title", "") or profile.get("job_title", "")
    # Clé correcte : must_have_skills (schéma profiler.py)
    operator_skills = ", ".join(str(s) for s in (profile.get("must_have_skills") or profile.get("skills") or [])[:10])
    operator_sector = ", ".join(
        n.get("label", "") if isinstance(n, dict) else str(n)
        for n in profile.get("nace_codes", [])[:3]
    )

    system = (
        "Tu es un analyste business senior spécialisé en intelligence économique sur les entreprises belges. "
        "Ton rôle : constituer des dossiers de prospection complets et précis pour aider un professionnel "
        "à identifier les meilleures opportunités et personnaliser son approche. "
        "Sois factuel, exhaustif et professionnel. Utilise toutes les données disponibles. "
        "Si une information est absente, propose une estimation raisonnée marquée comme telle. "
        "Pour les décideurs : identifie des personnes réelles si possible, sinon génère des profils plausibles "
        "pour les rôles clés (CEO, DRH, responsable technique) marqués 'estimation_ia'."
    )

    user = f"""Constitue un dossier de prospection complet pour cette entreprise belge.

## Données officielles BCE / KBO
- Numéro BCE : {bce}
- Dénomination officielle : {name}
- Forme juridique : {legal_form}
- Ville / Province : {city}
- Code NACE principal : {nace}
- Année de création : {creation} ({age} ans d'existence)

## Profil du professionnel en recherche
- Poste actuel / visé : {operator_title}
- Compétences clés : {operator_skills}
- Secteurs cibles : {operator_sector}

## Données collectées en ligne (site web + recherches)
{context}

## Instructions
1. Rédige une description complète et engageante de l'entreprise (5-8 phrases minimum).
2. Identifie les décideurs clés — cherche d'abord dans les données collectées, sinon génère les rôles probables.
3. Évalue la santé financière et les signaux de croissance/difficulté.
4. Analyse le contexte RH pour comprendre si l'entreprise recrute activement.
5. Identifie clients, partenaires et références si disponibles.
"""

    try:
        result, _ = call_with_json_tool(
            system=system,
            user=user,
            tool_name="constituer_dossier_entreprise",
            tool_description="Constitue un dossier complet de prospection pour une entreprise belge.",
            tool_schema=_LLM_TOOL_SCHEMA,
        )
        return result
    except Exception as e:
        logger.warning("LLM enrichissement {} — erreur: {}", name[:40], e)
        return {
            "description":          f"{name} est une entreprise belge basée à {city}, active depuis {creation}.",
            "clients_types":        "Inconnu",
            "tendance_financiere":  "inconnu",
            "signal_label":         "Analyse non disponible",
            "decideurs":            [],
            "signaux_croissance":   [],
            "signaux_difficulte":   [],
            "contexte_rh":          "",
        }
