import logging
from typing import List, Dict, Any, Optional

from backend.app.config import TOP_K_RETRIEVAL, SCORE_THRESHOLD
from backend.app.rag.embeddings import EmbeddingService
from backend.app.rag.qdrant_store import QdrantStore
from backend.app.ingestion.scheme_normalizer import SchemeNormalizer

logger = logging.getLogger("RAGRetriever")


class SchemeRetriever:
    """
    Semantic Retriever for SchemeSathi.
    Embeds user queries, searches Qdrant, applies metadata filters,
    and returns relevant scheme chunks with source citations.
    """

    def __init__(
        self,
        embedder: Optional[EmbeddingService] = None,
        vector_store: Optional[QdrantStore] = None,
        top_k: int = TOP_K_RETRIEVAL,
        score_threshold: float = SCORE_THRESHOLD
    ):
        self.embedder = embedder or EmbeddingService()
        self.vector_store = vector_store or QdrantStore()
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic retrieval for a user question.
        """
        norm_query = SchemeNormalizer.normalize_string(query)
        if not norm_query:
            return []

        k = top_k if top_k is not None else self.top_k
        thresh = score_threshold if score_threshold is not None else self.score_threshold

        try:
            query_vector = self.embedder.embed_query(norm_query)
            hits = self.vector_store.search(
                query_vector=query_vector,
                top_k=k,
                score_threshold=thresh,
                filters=filters
            )
            logger.info(f"Retrieved {len(hits)} scheme chunks for query: '{norm_query}' (threshold={thresh})")
            return hits
        except Exception as e:
            logger.error(f"Error during retrieval: {e}")
            return []
