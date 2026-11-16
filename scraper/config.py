import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
SCRAPER_DIR = BASE_DIR / "scraper"
PDF_DIR = SCRAPER_DIR / "SCRAPED PDF"
DB_PATH = SCRAPER_DIR / "scraped_data.db"

# Ensure folders exist
PDF_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
ENV_FILE = BASE_DIR / ".env"
if not ENV_FILE.exists():
    ENV_FILE = BASE_DIR / "scheme_cleaner" / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)

# Default Target URLs
TARGET_URLS = [
    "https://sevasindhugs1.karnataka.gov.in/gl-sp/",
    "https://ssp.karnataka.gov.in/",
    "https://www.karnataka.gov.in/"
]

# Scraping settings
DEFAULT_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", 20))
MAX_DEPTH = int(os.getenv("SCRAPER_MAX_DEPTH", 5))  # Deep traversal: Home -> Scheme -> Application Form -> Redirects
MAX_PAGES_PER_DOMAIN = int(os.getenv("SCRAPER_MAX_PAGES", 500))  # Ample cap per domain to ensure all schemes/forms are captured

# Allowed trusted portal domains for following scheme application links and redirects
ALLOWED_PORTAL_DOMAINS = [
    "gov.in",
    "nic.in",
    "karnataka.gov.in",
    "serviceonline.gov.in",
    "scholarships.gov.in",
    "sakala.kar.nic.in"
]

# Keywords indicating schemes and services
SCHEME_KEYWORDS = [
    "scheme", "yojana", "service", "welfare", "benefit", "scholarship",
    "eligib", "dept", "department", "initiative", "mission", "seve", "yojane"
]

# Keywords indicating application forms and apply actions
APPLICATION_KEYWORDS = [
    "apply", "application", "form", "register", "registration", "login",
    "applyonline", "online-application", "new-account", "ca", "ssppre",
    "post_sa", "entry", "submission", "userlogin", "citizen-service"
]

# Keywords indicating downloadable guidelines/documents
DOCUMENT_KEYWORDS = [
    "guideline", "document", "instruction", "manual", "notification",
    "annexure", "format", "brochure", "faq", "circular"
]

# Database Configuration (MySQL with SQLite fallback)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "schemesathi_db")

MYSQL_DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
)
SQLITE_DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# Backwards compatibility URL
SQLALCHEMY_DATABASE_URL = SQLITE_DATABASE_URL
