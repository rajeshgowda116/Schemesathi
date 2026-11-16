import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from scheme_cleaner.config import RAW_DATA_DIR, CLEANED_DATA_DIR
from scheme_cleaner.extractor import SchemeExtractor
from scheme_cleaner.validator import validate_scheme_dict
from scheme_cleaner.database import init_db, SessionLocal, insert_or_update_scheme, get_all_schemes

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SchemeCleanerPipeline")


class SchemeDataPipeline:
    """
    End-to-end Data Cleaning, Structuring, Validation, and Database Storage Pipeline.
    Reads raw scraped pages from SQL and/or JSON files, cleans text, extracts & normalizes
    structured fields, validates with Pydantic, exports cleaned JSON, and persists records
    into MySQL (or local SQLite fallback).
    """

    def __init__(self, raw_dir: Path = RAW_DATA_DIR, cleaned_dir: Path = CLEANED_DATA_DIR):
        self.raw_dir = raw_dir
        self.cleaned_dir = cleaned_dir

    @staticmethod
    def infer_department(domain: str, title: str) -> str:
        d_lower = (domain or "").lower()
        t_lower = (title or "").lower()
        if "ssp" in d_lower or "scholarship" in t_lower:
            return "Social Welfare Department / State Scholarship Portal"
        if "sevasindhu" in d_lower or "seva sindhu" in t_lower:
            return "Department of e-Governance / Seva Sindhu"
        if "karnataka" in d_lower:
            return "Government of Karnataka"
        return "Government of Karnataka"

    @staticmethod
    def is_meaningful_scheme(title: str, content: str) -> bool:
        """Filters out non-scheme asset files, scripts, images, and empty pages."""
        if not title or len(title.strip()) < 3:
            return False
        junk_indicators = ['.css', '.png', '.jpg', '.jpeg', '.gif', '.js', '.ico', '.svg', 'error 404', 'not found', 'forbidden']
        t_low = title.lower()
        if any(j in t_low for j in junk_indicators):
            return False
        if not content or len(content.strip()) < 40:
            return False
        return True

    def export_cleaned_schemes_json(self) -> int:
        """
        Exports all schemes currently stored in MySQL/SQLite database
        to cleaned_schemes.json for the frontend UI.
        """
        db_session = SessionLocal()
        try:
            all_records = get_all_schemes(db_session)
            cleaned_output_file = self.cleaned_dir / "cleaned_schemes.json"
            with open(cleaned_output_file, "w", encoding="utf-8") as f:
                json.dump(all_records, f, indent=2, ensure_ascii=False)
            logger.info(f"Exported {len(all_records)} cleaned schemes to {cleaned_output_file}")
            return len(all_records)
        except Exception as e:
            logger.error(f"Error exporting cleaned schemes JSON: {e}")
            return 0
        finally:
            db_session.close()

    def clean_and_save_item(self, raw_item: Dict[str, Any], db_session=None) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Cleans a single raw item, validates with Pydantic, and saves to database.
        Returns (cleaned_dict, is_new_record: bool).
        """
        close_session = False
        if db_session is None:
            init_db()
            db_session = SessionLocal()
            close_session = True

        try:
            # 1. Extraction & Cleaning
            extracted_dict = SchemeExtractor.extract_scheme(raw_item)

            # Ensure scheme is meaningful
            name = extracted_dict.get("scheme_name", "")
            desc = extracted_dict.get("description", "")
            if not self.is_meaningful_scheme(name, desc):
                return None, False

            # 2. Validation using Pydantic
            validated_model = validate_scheme_dict(extracted_dict)
            cleaned_dict = validated_model.model_dump()

            # 3. Persistence into MySQL / SQLite
            _, is_new = insert_or_update_scheme(db_session, cleaned_dict)
            return cleaned_dict, is_new
        except Exception as e:
            logger.error(f"Error cleaning item '{raw_item.get('title') or raw_item.get('scheme_name')}': {e}")
            return None, False
        finally:
            if close_session:
                db_session.close()

    def process_scraped_pages(self, pages: List[Any]) -> Dict[str, int]:
        """
        Takes a list of ScrapedPage ORM records or dicts, cleans each,
        saves to MySQL/Database, and updates cleaned_schemes.json.
        """
        init_db()
        db_session = SessionLocal()
        cleaned_count = 0
        new_count = 0

        for page in pages:
            url = getattr(page, 'url', None) or page.get('url', '')
            title = getattr(page, 'title', None) or page.get('title', '')
            domain = getattr(page, 'domain', None) or page.get('domain', '')
            content_text = getattr(page, 'content_text', None) or page.get('content_text', '')
            raw_html = getattr(page, 'raw_html', None) or page.get('raw_html', '')
            scraped_at = getattr(page, 'scraped_at', None) or page.get('scraped_at', '')
            source_date = scraped_at.strftime("%Y-%m-%d") if hasattr(scraped_at, 'strftime') else str(scraped_at)[:10]

            if not self.is_meaningful_scheme(title, content_text):
                continue

            raw_item = {
                "scheme_name": title,
                "title": title,
                "state": "Karnataka",
                "department": self.infer_department(domain, title),
                "official_url": url,
                "content_text": content_text,
                "raw_html": raw_html,
                "source_date": source_date
            }

            cleaned_dict, is_new = self.clean_and_save_item(raw_item, db_session=db_session)
            if cleaned_dict:
                cleaned_count += 1
                if is_new:
                    new_count += 1

        db_session.close()

        if cleaned_count > 0:
            self.export_cleaned_schemes_json()

        return {"cleaned_records": cleaned_count, "inserted_db_records": new_count}

    def process_scraped_data_db(self) -> Dict[str, Any]:
        """
        Reads all raw pages from the scraper's database (scraped_data.db / ScrapedPage),
        cleans them, persists to MySQL/Cleaned DB, and updates cleaned_schemes.json.
        """
        from scraper.database import SessionLocal as ScraperSession, ScrapedPage
        scraper_db = ScraperSession()
        try:
            pages = scraper_db.query(ScrapedPage).filter(ScrapedPage.status == "SUCCESS").all()
            logger.info(f"Processing {len(pages)} pages from scraper database...")
            stats = self.process_scraped_pages(pages)
            return stats
        finally:
            scraper_db.close()

    def run_pipeline(self) -> Dict[str, Any]:
        """
        Executes the data cleaning pipeline across all raw JSON files and raw scraper data.
        """
        logger.info("=" * 65)
        logger.info("🚀 STARTING SCHEMESATHI DATA CLEANING & STRUCTURING PIPELINE")
        logger.info("=" * 65)

        # Initialize Database Tables
        init_db()
        db_session = SessionLocal()

        # Find raw JSON files
        json_files = list(self.raw_dir.glob("*.json"))
        total_raw_records = 0
        successfully_cleaned = 0
        failed_records = 0
        duplicate_schemes = 0
        inserted_db_records = 0

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
                    cleaned_dict, is_new = self.clean_and_save_item(raw_item, db_session=db_session)
                    if cleaned_dict:
                        successfully_cleaned += 1
                        if is_new:
                            inserted_db_records += 1
                    else:
                        failed_records += 1
                except Exception as item_err:
                    failed_records += 1
                    scheme_label = raw_item.get("scheme_name") or raw_item.get("title") or f"Item #{idx+1}"
                    logger.error(f"  ❌ FAILED processing '{scheme_label}': {item_err}")

        # Also process raw pages from scraper database
        try:
            from scraper.database import SessionLocal as ScraperSession, ScrapedPage
            scraper_db = ScraperSession()
            raw_pages = scraper_db.query(ScrapedPage).filter(ScrapedPage.status == "SUCCESS").all()
            for p in raw_pages:
                total_raw_records += 1
                if not self.is_meaningful_scheme(p.title, p.content_text):
                    continue
                raw_item = {
                    "scheme_name": p.title,
                    "title": p.title,
                    "state": "Karnataka",
                    "department": self.infer_department(p.domain, p.title),
                    "official_url": p.url,
                    "content_text": p.content_text,
                    "raw_html": p.raw_html,
                    "source_date": p.scraped_at.strftime("%Y-%m-%d") if p.scraped_at else datetime.utcnow().strftime("%Y-%m-%d")
                }
                cleaned_dict, is_new = self.clean_and_save_item(raw_item, db_session=db_session)
                if cleaned_dict:
                    successfully_cleaned += 1
                    if is_new:
                        inserted_db_records += 1
            scraper_db.close()
        except Exception as db_err:
            logger.warning(f"Could not read directly from scraper DB during pipeline run: {db_err}")

        db_session.close()

        # Synchronize cleaned output JSON
        exported_total = self.export_cleaned_schemes_json()

        # Summary Log Report
        summary = {
            "raw_records": total_raw_records,
            "cleaned_records": successfully_cleaned,
            "failed_records": failed_records,
            "inserted_db_records": inserted_db_records,
            "total_schemes_exported": exported_total
        }

        logger.info("=" * 65)
        logger.info("📊 SCHEMESATHI DATA CLEANING PIPELINE SUMMARY REPORT")
        logger.info("-" * 65)
        logger.info(f"  • Total Raw Records Processed  : {summary['raw_records']}")
        logger.info(f"  • Successfully Cleaned Records : {summary['cleaned_records']}")
        logger.info(f"  • New Records Inserted into DB : {summary['inserted_db_records']}")
        logger.info(f"  • Total Schemes in Cleaned JSON: {summary['total_schemes_exported']}")
        logger.info("=" * 65)

        return summary


if __name__ == "__main__":
    pipeline = SchemeDataPipeline()
    pipeline.run_pipeline()
