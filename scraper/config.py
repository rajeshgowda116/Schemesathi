import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
SCRAPER_DIR = BASE_DIR / "scraper"
PDF_DIR = SCRAPER_DIR / "SCRAPED PDF"
DB_PATH = SCRAPER_DIR / "scraped_data.db"

# Ensure folders exist
PDF_DIR.mkdir(parents=True, exist_ok=True)

# Default Target URLs provided by user
TARGET_URLS = [
    "https://sevasindhugs1.karnataka.gov.in/gl-sp/",
    "https://ssp.karnataka.gov.in/",
    "https://www.karnataka.gov.in/"
]

# Scraping settings
DEFAULT_TIMEOUT = 15
MAX_DEPTH = 2  # Follow internal links up to depth 2
MAX_PAGES_PER_DOMAIN = 30  # Safety cap per domain to avoid infinite loops

# Database URL for SQLAlchemy
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"
