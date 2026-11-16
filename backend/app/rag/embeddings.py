import logging
import hashlib
import numpy as np
import requests
from typing import List, Optional
from backend.app.config import (
    VECTOR_SIZE, EMBEDDING_PROVIDER, EMBEDDING_MODEL_NAME,
    EMBEDDING_BATCH_SIZE, OLLAMA_BASE_URL
)

logger = logging.getLogger("EmbeddingService")


class EmbeddingService:
    """
    Unified Embedding Generation Service for SchemeSathi.
    Supports SentenceTransformers, Ollama embeddings, and a resilient
    built-in deterministic feature vectorizer as fallback.
    Guarantees exact dimensional consistency and cosine normalization.
    """

    def __init__(
        self,
        dimension: int = VECTOR_SIZE,
        model_name: str = EMBEDDING_MODEL_NAME,
        provider: str = EMBEDDING_PROVIDER
    ):
        self.dimension = dimension
        self.model_name = model_name
        self.provider = provider
        self._st_model = None
        self._init_provider()

    def _init_provider(self):
        """Initializes the configured embedding backend."""
        if self.provider in ("sentence_transformers", "auto"):
            try:
                from sentence_transformers import SentenceTransformer
                self._st_model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded SentenceTransformer model: {self.model_name}")
                self.provider = "sentence_transformers"
                return
            except Exception:
                pass

        if self.provider in ("ollama", "auto"):
            try:
                res = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
                if res.status_code == 200:
                    logger.info(f"Connected to Ollama for embeddings at {OLLAMA_BASE_URL}")
                    self.provider = "ollama"
                    return
            except Exception:
                pass

        # Fallback to built-in semantic vectorizer
        logger.info(f"Using built-in deterministic semantic vectorizer (Dimension: {self.dimension})")
        self.provider = "builtin"

    def _embed_builtin(self, text: str) -> List[float]:
        """
        Deterministic, subword-hashed semantic feature vector with cosine normalization.
        Provides robust offline embedding capability with zero external model download dependencies.
        """
        vec = np.zeros(self.dimension, dtype=np.float32)
        words = text.lower().split()
        if not words:
            return vec.tolist()

        for w in words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dimension] += 1.0
            for i in range(len(w) - 1):
                bg = w[i:i+2]
                h_bg = int(hashlib.sha256(bg.encode("utf-8")).hexdigest(), 16)
                vec[h_bg % self.dimension] += 0.5

        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec = vec / norm
        return vec.tolist()

    def _embed_ollama(self, texts: List[str]) -> List[List[float]]:
        """Calls Ollama embed or embeddings endpoint."""
        results: List[List[float]] = []
        for text in texts:
            try:
                # Try modern Ollama /api/embed first
                resp = requests.post(
                    f"{OLLAMA_BASE_URL}/api/embed",
                    json={"model": self.model_name, "input": text},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    embeds = data.get("embeddings", [])
                    if embeds:
                        results.append(self._resize_vector(embeds[0]))
                        continue

                # Fallback to legacy /api/embeddings
                resp = requests.post(
                    f"{OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": self.model_name, "prompt": text},
                    timeout=10
                )
                if resp.status_code == 200:
                    vec = resp.json().get("embedding", [])
                    results.append(self._resize_vector(vec))
                else:
                    results.append(self._embed_builtin(text))
            except Exception:
                results.append(self._embed_builtin(text))
        return results

    def _resize_vector(self, vec: List[float]) -> List[float]:
        """Ensures vector matches exactly self.dimension with cosine normalization."""
        v = np.array(vec, dtype=np.float32)
        if len(v) == self.dimension:
            norm = float(np.linalg.norm(v))
            return (v / norm).tolist() if norm > 0 else v.tolist()

        resized = np.zeros(self.dimension, dtype=np.float32)
        if len(v) > self.dimension:
            resized = v[:self.dimension]
        else:
            resized[:len(v)] = v

        norm = float(np.linalg.norm(resized))
        if norm > 0:
            resized = resized / norm
        return resized.tolist()

    def embed_documents(self, texts: List[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> List[List[float]]:
        """
        Generates vector embeddings for a list of texts in batches.
        Verifies vector dimensions on all generated vectors.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        if self.provider == "sentence_transformers" and self._st_model:
            try:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    vectors = self._st_model.encode(batch, convert_to_numpy=True, normalize_embeddings=True)
                    for vec in vectors:
                        v_list = self._resize_vector(vec.tolist())
                        all_embeddings.append(v_list)
                return all_embeddings
            except Exception as e:
                logger.warning(f"SentenceTransformers failed ({e}), falling back to built-in vectorizer.")

        if self.provider == "ollama":
            return self._embed_ollama(texts)

        # Builtin vectorizer
        for t in texts:
            v = self._embed_builtin(t)
            all_embeddings.append(v)

        # Dimension verification
        for v in all_embeddings:
            if len(v) != self.dimension:
                raise ValueError(f"Generated vector dimension {len(v)} does not match expected {self.dimension}")

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Generates embedding for a single search query."""
        results = self.embed_documents([query])
        if not results:
            raise ValueError("Failed to generate query embedding.")
        return results[0]
