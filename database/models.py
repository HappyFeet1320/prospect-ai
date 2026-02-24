"""Modèles de données SQLAlchemy pour PROSPECT-AI."""

import uuid
import json
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session as OrmSession


class Base(DeclarativeBase):
    pass


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Session(Base):
    """Session opérateur — point d'entrée de chaque recherche."""
    __tablename__ = "sessions"

    session_id = Column(String(36), primary_key=True, default=_new_uuid)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    current_phase = Column(Integer, default=1)
    operator_name = Column(String(200), nullable=True)
    operator_profile_json = Column(Text, nullable=True)  # JSON fiche profil P1
    status = Column(String(20), default="active")  # active / completed / archived
    p1_validated = Column(Boolean, default=False)
    p2_validated = Column(Boolean, default=False)
    p3_validated = Column(Boolean, default=False)
    p4_validated = Column(Boolean, default=False)
    p5_validated = Column(Boolean, default=False)

    # Relations
    companies = relationship("Company", back_populates="session", cascade="all, delete-orphan")

    @property
    def operator_profile(self) -> dict:
        if self.operator_profile_json:
            return json.loads(self.operator_profile_json)
        return {}

    @operator_profile.setter
    def operator_profile(self, value: dict):
        self.operator_profile_json = json.dumps(value, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"<Session {self.session_id[:8]} phase={self.current_phase}>"


class Company(Base):
    """Entreprise identifiée et analysée au fil des phases."""
    __tablename__ = "companies"

    company_id = Column(String(36), primary_key=True, default=_new_uuid)
    session_id = Column(String(36), ForeignKey("sessions.session_id"), nullable=False)
    bce_number = Column(String(20), nullable=True, index=True)  # Numéro BCE unique
    created_at = Column(DateTime, default=datetime.utcnow)

    # --- Phase 2 — Données brutes BCE ---
    phase2_data_json = Column(Text, nullable=True)

    # --- Phase 3 — Scoring ---
    phase3_score = Column(Float, nullable=True)  # 0.0 à 1.0
    phase3_score_detail_json = Column(Text, nullable=True)  # détail par critère
    is_phase3_selected = Column(Boolean, default=False)

    # --- Phase 4 — Dossier complet ---
    phase4_data_json = Column(Text, nullable=True)

    # --- Notation opérateur ---
    operator_rating = Column(Integer, nullable=True)  # 1-5 étoiles
    is_selected = Column(Boolean, default=False)  # sélection finale P5
    operator_notes = Column(Text, nullable=True)

    # Relations
    session = relationship("Session", back_populates="companies")
    decision_makers = relationship("DecisionMaker", back_populates="company", cascade="all, delete-orphan")
    preparation_kit = relationship("PreparationKit", back_populates="company", uselist=False, cascade="all, delete-orphan")

    @property
    def phase2_data(self) -> dict:
        return json.loads(self.phase2_data_json) if self.phase2_data_json else {}

    @phase2_data.setter
    def phase2_data(self, value: dict):
        self.phase2_data_json = json.dumps(value, ensure_ascii=False)

    @property
    def phase3_score_detail(self) -> dict:
        return json.loads(self.phase3_score_detail_json) if self.phase3_score_detail_json else {}

    @phase3_score_detail.setter
    def phase3_score_detail(self, value: dict):
        self.phase3_score_detail_json = json.dumps(value, ensure_ascii=False)

    @property
    def phase4_data(self) -> dict:
        return json.loads(self.phase4_data_json) if self.phase4_data_json else {}

    @phase4_data.setter
    def phase4_data(self, value: dict):
        self.phase4_data_json = json.dumps(value, ensure_ascii=False)

    @property
    def name(self) -> str:
        return self.phase2_data.get("denomination", self.bce_number or "Inconnue")

    def __repr__(self) -> str:
        return f"<Company {self.bce_number} score={self.phase3_score}>"


class DecisionMaker(Base):
    """Décideur clé identifié dans une entreprise (Phase 4)."""
    __tablename__ = "decision_makers"

    dm_id = Column(String(36), primary_key=True, default=_new_uuid)
    company_id = Column(String(36), ForeignKey("companies.company_id"), nullable=False)
    full_name = Column(String(200))
    title = Column(String(200))
    email = Column(String(200), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    seniority_years = Column(Integer, nullable=True)
    bio_short = Column(Text, nullable=True)
    dm_type = Column(String(20))  # CEO / HR / DEPT_HEAD / OFFICE_MGR
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="decision_makers")

    def __repr__(self) -> str:
        return f"<DecisionMaker {self.full_name} ({self.dm_type})>"


class PreparationKit(Base):
    """Kit de préparation à l'entretien généré en Phase 5."""
    __tablename__ = "preparation_kits"

    kit_id = Column(String(36), primary_key=True, default=_new_uuid)
    company_id = Column(String(36), ForeignKey("companies.company_id"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    message_variants_json = Column(Text, nullable=True)   # 3 variantes message
    ambiguous_situations_json = Column(Text, nullable=True)  # 4-6 situations
    questions_to_ask_json = Column(Text, nullable=True)    # 5 questions
    risk_flags_json = Column(Text, nullable=True)          # points vigilance
    executive_summary = Column(Text, nullable=True)        # résumé 1 page

    company = relationship("Company", back_populates="preparation_kit")

    @property
    def message_variants(self) -> list:
        return json.loads(self.message_variants_json) if self.message_variants_json else []

    @message_variants.setter
    def message_variants(self, value: list):
        self.message_variants_json = json.dumps(value, ensure_ascii=False)

    @property
    def ambiguous_situations(self) -> list:
        return json.loads(self.ambiguous_situations_json) if self.ambiguous_situations_json else []

    @ambiguous_situations.setter
    def ambiguous_situations(self, value: list):
        self.ambiguous_situations_json = json.dumps(value, ensure_ascii=False)

    @property
    def questions_to_ask(self) -> list:
        return json.loads(self.questions_to_ask_json) if self.questions_to_ask_json else []

    @questions_to_ask.setter
    def questions_to_ask(self, value: list):
        self.questions_to_ask_json = json.dumps(value, ensure_ascii=False)

    @property
    def risk_flags(self) -> list:
        return json.loads(self.risk_flags_json) if self.risk_flags_json else []

    @risk_flags.setter
    def risk_flags(self, value: list):
        self.risk_flags_json = json.dumps(value, ensure_ascii=False)
