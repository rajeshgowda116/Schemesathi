import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory of scheme_cleaner
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file inside scheme_cleaner directory
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)

# Directory Paths
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
CLEANED_DATA_DIR = BASE_DIR / "data" / "cleaned"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database Environment Variables
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "schemesathi_db")

# Constructed MySQL SQLAlchemy connection string
DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
)

# SQLite Fallback URL if MySQL is offline during local test execution
SQLITE_FALLBACK_DB = BASE_DIR / "data" / "schemesathi_fallback.db"
SQLITE_DATABASE_URL = f"sqlite:///{SQLITE_FALLBACK_DB.as_posix()}"
