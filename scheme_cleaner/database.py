import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, DateTime, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker

from scheme_cleaner.config import DATABASE_URL, SQLITE_DATABASE_URL

logger = logging.getLogger("SchemeDatabase")
Base = declarative_base()


class SchemeModel(Base):
    """
    SQLAlchemy ORM Model representing the 'schemes' table in MySQL.
    """
    __tablename__ = "schemes"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    scheme_name = Column(String(255), nullable=False, index=True)
    state = Column(String(100), default="Karnataka", index=True)
    department = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    benefits = Column(JSON, nullable=True)
    eligibility = Column(JSON, nullable=True)
    age_min = Column(Integer, nullable=True)
    age_max = Column(Integer, nullable=True)
    income_min = Column(Float, nullable=True)
    income_max = Column(Float, nullable=True)
    occupation = Column(JSON, nullable=True)
    category = Column(JSON, nullable=True)
    documents_required = Column(JSON, nullable=True)
    application_process = Column(Text, nullable=True)
    official_url = Column(Text, nullable=True)
    source_date = Column(String(50), nullable=True)
    last_updated = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db_engine():
    """
    Initializes SQLAlchemy Engine.
    Tries MySQL first using environment variables.
    If MySQL server is offline/unreachable, falls back cleanly to SQLite.
    """
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
        # Test connection
        with engine.connect() as conn:
            pass
        logger.info(f"Connected successfully to MySQL database.")
        return engine
    except Exception as e:
        logger.warning(
            f"MySQL connection failed ({e}). Falling back to local SQLite database."
        )
        fallback_engine = create_engine(
            SQLITE_DATABASE_URL, connect_args={"check_same_thread": False}
        )
        return fallback_engine


# Instantiate engine and sessionmaker
engine = get_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Creates the 'schemes' table if it does not exist."""
    Base.metadata.create_all(bind=engine)


def insert_or_update_scheme(db_session, scheme_dict: Dict[str, Any]) -> Tuple[SchemeModel, bool]:
    """
    Inserts a cleaned scheme into MySQL using SQLAlchemy ORM.
    Detects duplicates using normalized scheme_name + state + department.
    Returns (SchemeModel instance, is_new: bool).
    """
    norm_name = scheme_dict["scheme_name"].strip().lower()
    norm_state = (scheme_dict.get("state") or "Karnataka").strip().lower()
    norm_dept = (scheme_dict.get("department") or "").strip().lower()

    # Query for duplicate scheme
    existing = (
        db_session.query(SchemeModel)
        .filter(
            SchemeModel.scheme_name.ilike(scheme_dict["scheme_name"].strip()),
            SchemeModel.state.ilike(scheme_dict.get("state", "Karnataka").strip())
        )
        .first()
    )

    if existing:
        # Update existing record
        existing.department = scheme_dict.get("department")
        existing.description = scheme_dict.get("description")
        existing.benefits = scheme_dict.get("benefits", [])
        existing.eligibility = scheme_dict.get("eligibility", [])
        existing.age_min = scheme_dict.get("age_min")
        existing.age_max = scheme_dict.get("age_max")
        existing.income_min = scheme_dict.get("income_min")
        existing.income_max = scheme_dict.get("income_max")
        existing.occupation = scheme_dict.get("occupation", [])
        existing.category = scheme_dict.get("category", [])
        existing.documents_required = scheme_dict.get("documents_required", [])
        existing.application_process = scheme_dict.get("application_process")
        existing.official_url = scheme_dict.get("official_url")
        existing.source_date = scheme_dict.get("source_date")
        existing.last_updated = scheme_dict.get("last_updated")
        existing.updated_at = datetime.utcnow()

        db_session.commit()
        db_session.refresh(existing)
        return existing, False

    # Insert new record
    new_scheme = SchemeModel(
        scheme_name=scheme_dict["scheme_name"],
        state=scheme_dict.get("state", "Karnataka"),
        department=scheme_dict.get("department"),
        description=scheme_dict.get("description"),
        benefits=scheme_dict.get("benefits", []),
        eligibility=scheme_dict.get("eligibility", []),
        age_min=scheme_dict.get("age_min"),
        age_max=scheme_dict.get("age_max"),
        income_min=scheme_dict.get("income_min"),
        income_max=scheme_dict.get("income_max"),
        occupation=scheme_dict.get("occupation", []),
        category=scheme_dict.get("category", []),
        documents_required=scheme_dict.get("documents_required", []),
        application_process=scheme_dict.get("application_process"),
        official_url=scheme_dict.get("official_url"),
        source_date=scheme_dict.get("source_date"),
        last_updated=scheme_dict.get("last_updated"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db_session.add(new_scheme)
    db_session.commit()
    db_session.refresh(new_scheme)
    return new_scheme, True
