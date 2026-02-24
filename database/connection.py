"""Connexion et initialisation de la base de données SQLite."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as OrmSession
from .models import Base
from config.settings import settings


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False},  # SQLite multithread
            echo=settings.DEBUG,
        )
    return _engine


def init_db():
    """Crée toutes les tables si elles n'existent pas encore."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_session() -> OrmSession:
    """Retourne une session SQLAlchemy. À utiliser dans un contexte with."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()
