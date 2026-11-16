import logging
from typing import List, Dict, Any, Optional
from scheme_cleaner.database import SessionLocal, SchemeModel
from scheme_cleaner.pipeline import SchemeDataPipeline

logger = logging.getLogger("MySQLSchemeLoader")


class MySQLSchemeLoader:
    """
    Connects to the existing MySQL / SQLite schemes database.
    Reads only validated, cleaned, and meaningful scheme records.
    Filters out non-scheme asset files, empty records, and unvalidated errors.
    """

    def __init__(self, db_session=None):
        self.external_session = db_session

    def load_clean_schemes(self) -> List[Dict[str, Any]]:
        """
        Queries and returns only clean, valid scheme records from the 'schemes' table.
        """
        session = self.external_session or SessionLocal()
        try:
            records = session.query(SchemeModel).order_by(SchemeModel.id.asc()).all()
            valid_schemes: List[Dict[str, Any]] = []

            for r in records:
                scheme_dict = {
                    "scheme_id": int(r.id),
                    "id": int(r.id),
                    "scheme_name": r.scheme_name,
                    "state": r.state or "Karnataka",
                    "department": r.department or "Government of Karnataka",
                    "description": r.description or "",
                    "benefits": r.benefits or [],
                    "eligibility": r.eligibility or [],
                    "age_min": r.age_min,
                    "age_max": r.age_max,
                    "income_min": r.income_min,
                    "income_max": r.income_max,
                    "occupation": r.occupation or [],
                    "category": r.category or [],
                    "documents_required": r.documents_required or [],
                    "application_process": r.application_process or "",
                    "official_url": r.official_url or "",
                    "source_date": r.source_date or "",
                    "last_updated": r.last_updated or "",
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None
                }

                # Validate that the record is meaningful and not a crawler artifact
                if not SchemeDataPipeline.is_meaningful_scheme(r.scheme_name, r.description or ""):
                    logger.debug(f"Skipping non-scheme artifact record [ID {r.id}]: {r.scheme_name}")
                    continue

                valid_schemes.append(scheme_dict)

            logger.info(f"Loaded {len(valid_schemes)} valid cleaned schemes from database (out of {len(records)} total records).")
            return valid_schemes

        except Exception as e:
            logger.error(f"Error loading clean schemes from database: {e}")
            raise e
        finally:
            if not self.external_session:
                session.close()

    def get_scheme_by_id(self, scheme_id: int) -> Optional[Dict[str, Any]]:
        """Loads a single scheme record by ID."""
        session = self.external_session or SessionLocal()
        try:
            r = session.query(SchemeModel).filter(SchemeModel.id == scheme_id).first()
            if not r:
                return None
            return {
                "scheme_id": int(r.id),
                "id": int(r.id),
                "scheme_name": r.scheme_name,
                "state": r.state or "Karnataka",
                "department": r.department or "Government of Karnataka",
                "description": r.description or "",
                "benefits": r.benefits or [],
                "eligibility": r.eligibility or [],
                "age_min": r.age_min,
                "age_max": r.age_max,
                "income_min": r.income_min,
                "income_max": r.income_max,
                "occupation": r.occupation or [],
                "category": r.category or [],
                "documents_required": r.documents_required or [],
                "application_process": r.application_process or "",
                "official_url": r.official_url or "",
                "source_date": r.source_date or "",
                "last_updated": r.last_updated or "",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None
            }
        finally:
            if not self.external_session:
                session.close()
