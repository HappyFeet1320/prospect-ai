"""Configuration centralisée de PROSPECT-AI via variables d'environnement."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Charger le fichier .env depuis la racine du projet
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # Application
    APP_NAME: str = os.getenv("APP_NAME", "PROSPECT-AI")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # --- Sélection du provider LLM ---
    # Valeurs : "groq" | "anthropic"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")

    # Groq (provider actif par défaut)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Anthropic / Claude (provider alternatif)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    LLM_COST_ALERT_THRESHOLD: float = float(os.getenv("LLM_COST_ALERT_THRESHOLD", "5.0"))

    # Base de données
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/prospect_ai.db")

    # KBO Open Data — chemin vers le dossier des CSV officiels
    KBO_DATA_DIR: str = os.getenv(
        "KBO_DATA_DIR",
        str(BASE_DIR / "KboOpenData_0242_2026_01_15_Full"),
    )

    # API BCE
    BCE_API_BASE_URL: str = os.getenv("BCE_API_BASE_URL", "https://kbopub.economie.fgov.be/kbopub/trefwoordenSearchAction.do")
    BCE_OPEN_DATA_URL: str = os.getenv("BCE_OPEN_DATA_URL", "https://api.kbopub.be/v1")
    BCE_RATE_LIMIT_RPS: int = int(os.getenv("BCE_RATE_LIMIT_RPS", "10"))
    BCE_USE_MOCK: bool = os.getenv("BCE_USE_MOCK", "false").lower() == "true"

    # API CBE (https://cbeapi.be) — clé gratuite, données fraîches + coordonnées
    CBEAPI_KEY: str = os.getenv("CBEAPI_KEY", "")

    # API BNB
    BNB_API_KEY: str = os.getenv("BNB_API_KEY", "")
    BNB_API_BASE_URL: str = os.getenv("BNB_API_BASE_URL", "https://www.nbb.be/api/coa/v1")

    # APIs optionnelles
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")
    HUNTER_IO_API_KEY: str = os.getenv("HUNTER_IO_API_KEY", "")
    APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")
    DUCKDUCKGO_ENABLED: bool = os.getenv("DUCKDUCKGO_ENABLED", "true").lower() == "true"

    # Seuils Phase 3
    PHASE3_MIN_SCORE: float = float(os.getenv("PHASE3_MIN_SCORE", "0.45"))
    PHASE3_MIN_SCORE_FALLBACK: float = float(os.getenv("PHASE3_MIN_SCORE_FALLBACK", "0.35"))
    PHASE3_TARGET_COMPANIES: int = int(os.getenv("PHASE3_TARGET_COMPANIES", "100"))

    # Cache TTL (secondes)
    CACHE_BCE_TTL: int = int(os.getenv("CACHE_BCE_TTL", "86400"))
    CACHE_BNB_TTL: int = int(os.getenv("CACHE_BNB_TTL", "604800"))
    CACHE_SCRAPING_TTL: int = int(os.getenv("CACHE_SCRAPING_TTL", "43200"))

    # ----------------------------------------------------------------
    # Propriétés calculées
    # ----------------------------------------------------------------

    @property
    def active_model(self) -> str:
        """Retourne le nom du modèle du provider actif."""
        if self.LLM_PROVIDER == "groq":
            return self.GROQ_MODEL
        return self.CLAUDE_MODEL

    @property
    def has_llm_key(self) -> bool:
        """Vérifie que le provider actif a une clé configurée."""
        if self.LLM_PROVIDER == "groq":
            return bool(self.GROQ_API_KEY)
        return bool(self.ANTHROPIC_API_KEY and self.ANTHROPIC_API_KEY.startswith("sk-ant-"))

    @property
    def has_cbeapi_key(self) -> bool:
        return bool(self.CBEAPI_KEY)

    @property
    def has_groq_key(self) -> bool:
        return bool(self.GROQ_API_KEY)

    @property
    def has_anthropic_key(self) -> bool:
        """Rétrocompatibilité — vérifie la clé Anthropic."""
        return bool(self.ANTHROPIC_API_KEY and self.ANTHROPIC_API_KEY.startswith("sk-ant-"))

    @property
    def provider_label(self) -> str:
        """Label lisible du provider + modèle actif."""
        if self.LLM_PROVIDER == "groq":
            return f"Groq / {self.GROQ_MODEL}"
        return f"Anthropic / {self.CLAUDE_MODEL}"

    @property
    def data_dir(self) -> Path:
        d = BASE_DIR / "data"
        d.mkdir(exist_ok=True)
        return d


settings = Settings()
