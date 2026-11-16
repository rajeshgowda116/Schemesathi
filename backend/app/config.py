import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory: root of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)

# Qdrant Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_URL = os.getenv("QDRANT_URL", None)  # e.g. "http://localhost:6333" or Cloud URL
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_STORAGE_PATH = os.getenv("QDRANT_STORAGE_PATH", str(BASE_DIR / "data" / "qdrant_storage"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "schemesathi_schemes")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", 384))  # 384 for all-MiniLM-L6-v2 / BGE-small
VECTOR_DISTANCE = os.getenv("VECTOR_DISTANCE", "Cosine")

# Embedding Configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "auto")  # auto, ollama, sentence_transformers, local
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", 32))

# Ollama LLM Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 45))

# Chunking Configuration
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", 500))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", 50))
TOP_K_RETRIEVAL = int(os.getenv("RAG_TOP_K", 4))
SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", 0.20))
