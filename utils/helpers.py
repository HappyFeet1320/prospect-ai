"""Fonctions utilitaires partagées entre les phases."""

import uuid
from datetime import datetime


def new_uuid() -> str:
    return str(uuid.uuid4())


def now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def truncate(text: str, max_len: int = 100) -> str:
    """Tronque un texte avec ellipsis."""
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


def format_bce_number(raw: str) -> str:
    """Formate un numéro BCE brut en format standard 0XXX.XXX.XXX."""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return f"{digits[:4]}.{digits[4:7]}.{digits[7:]}"
    return raw
