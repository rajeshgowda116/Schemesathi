import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from scheme_cleaner.config import RAW_DATA_DIR, CLEANED_DATA_DIR
from scheme_cleaner.extractor import SchemeExtractor
from scheme_cleaner.validator import validate_scheme_dict
from scheme_cleaner.database import init_db, SessionLocal, insert_or_update_scheme

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SchemeCleanerPipeline")


class SchemeDataPipeline:
    """
    End-to-end Data Cleaning, Structuring, Validation, and MySQL Storage Pipeline.
    Reads raw scraped JSON files, cleans text, extracts & normalizes structured fields,
    validates with Pydantic, exports cleaned JSON, and persists records into MySQL.
    """

    def __init__(self, raw_dir: Path = RAW_DATA_DIR, cleaned_dir: Path = CLEANED_DATA_DIR):
        self.raw_dir = raw_dir
        self.cleaned_dir = cleaned_dir

    def run_pipeline(self) -> Dict[str, Any]:
        """
        Executes the data cleaning pipeline across all raw JSON files.
        """
        logger.info("=" * 65)
        logger.info("🚀 STARTING SCHEMESATHI DATA CLEANING & STRUCTURING PIPELINE")
        logger.info("=" * 65)

        # Initialize Database Tables
        init_db()
        db_session = SessionLocal()

        # Find raw JSON files
        json_files = list(self.raw_dir.glob("*.json"))
        if not json_files:
            logger.warning(f"No raw JSON files found in directory: {self.raw_dir}")
            return {
                "raw_records": 0,
                "cleaned_records": 0,
                "failed_records": 0,
                "duplicate_schemes": 0,
                "inserted_db_records": 0
            }

        logger.info(f"Found {len(json_files)} raw JSON file(s) to process.")

        # Pipeline Statistics
        total_raw_records = 0
        successfully_cleaned = 0
        failed_records = 0
        duplicate_schemes = 0
        inserted_db_records = 0

        cleaned_records_list: List[Dict[str, Any]] = []
        seen_scheme_keys = set()

        for json_file in json_files:
            logger.info(f"Reading raw file: {json_file.name}")
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    items = content if isinstance(content, list) else [content]
            except Exception as read_err:
                logger.error(f"Failed to read file {json_file.name}: {read_err}")
                continue

            for idx, raw_item in enumerate(items):
                total_raw_records += 1
                try:
                    # 1. Extraction & Cleaning
                    extracted_dict = SchemeExtractor.extract_scheme(raw_item)

                    # 2. Validation using Pydantic
                    validated_model = validate_scheme_dict(extracted_dict)
                    cleaned_dict = validated_model.model_dump()

                    # 3. Local In-Memory Duplicate Check
                    norm_name = cleaned_dict["scheme_name"].strip().lower()
                    norm_state = (cleaned_dict.get("state") or "Karnataka").strip().lower()
                    norm_dept = (cleaned_dict.get("department") or "").strip().lower()
                    unique_key = (norm_name, norm_state, norm_dept)

                    if unique_key in seen_scheme_keys:
                        duplicate_schemes += 1
                        logger.info(f"  [DUPLICATE DETECTED] Skipping duplicate scheme: {cleaned_dict['scheme_name']}")
                    else:
                        seen_scheme_keys.add(unique_key)

                    cleaned_records_list.append(cleaned_dict)
                    successfully_cleaned += 1

                    # 4. MySQL Database Persistence via SQLAlchemy
                    _, is_new = insert_or_update_scheme(db_session, cleaned_dict)
                    if is_new:
                        inserted_db_records += 1

                except Exception as item_err:
                    failed_records += 1
                    scheme_label = raw_item.get("scheme_name") or raw_item.get("title") or f"Item #{idx+1}"
                    logger.error(f"  ❌ FAILED processing '{scheme_label}': {item_err}")

        db_session.close()

        # 5. Export Cleaned Output JSON to data/cleaned/
        cleaned_output_file = self.cleaned_dir / "cleaned_schemes.json"
        try:
            with open(cleaned_output_file, "w", encoding="utf-8") as f:
                json.dump(cleaned_records_list, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved cleaned output JSON file ({len(cleaned_records_list)} items) to: {cleaned_output_file}")
        except Exception as export_err:
            logger.error(f"Failed saving cleaned JSON: {export_err}")

        # Summary Log Report
        summary = {
            "raw_records": total_raw_records,
            "cleaned_records": successfully_cleaned,
            "failed_records": failed_records,
            "duplicate_schemes": duplicate_schemes,
            "inserted_db_records": inserted_db_records
        }

        logger.info("=" * 65)
        logger.info("📊 SCHEMESATHI DATA CLEANING PIPELINE SUMMARY REPORT")
        logger.info("-" * 65)
        logger.info(f"  • Total Raw Records Processed  : {summary['raw_records']}")
        logger.info(f"  • Successfully Cleaned Records : {summary['cleaned_records']}")
        logger.info(f"  • Failed Records               : {summary['failed_records']}")
        logger.info(f"  • Duplicate Schemes Detected   : {summary['duplicate_schemes']}")
        logger.info(f"  • New Records Inserted into DB : {summary['inserted_db_records']}")
        logger.info("=" * 65)

        return summary


if __name__ == "__main__":
    pipeline = SchemeDataPipeline()
    pipeline.run_pipeline()
