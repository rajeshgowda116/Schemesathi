import logging
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Index
)
from scheme_cleaner.database import Base, engine

logger = logging.getLogger("SchemeRAGSyncModel")


class SchemeRAGSyncModel(Base):
    """
    SQLAlchemy ORM Model representing the 'scheme_rag_sync' table.
    Tracks SHA-256 content hashes, vector indexing status, and timestamps.
    """
    __tablename__ = "scheme_rag_sync"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    scheme_id = Column(Integer, unique=True, index=True, nullable=False)
    scheme_name = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    indexing_status = Column(String(50), default="PENDING", index=True)  # PENDING, INDEXED, UNCHANGED, UPDATED, FAILED, REVIEW_REQUIRED
    chunks_count = Column(Integer, default=0)
    last_indexed_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_sync_scheme_hash", "scheme_id", "content_hash"),
    )


def init_sync_table():
    """Initializes the scheme_rag_sync table in the database."""
    Base.metadata.create_all(bind=engine)
