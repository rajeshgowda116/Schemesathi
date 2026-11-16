import logging
from typing import Dict, Any, Optional

from backend.app.ingestion.rag_sync import RAGSyncPipeline
from backend.app.rag.chain import RAGChain

logger = logging.getLogger("SchemeSyncService")


class SchemeSyncService:
    """
    High-level Application Service managing SchemeSathi RAG synchronization,
    system health metrics, and citizen query answering.
    """

    def __init__(
        self,
        sync_pipeline: Optional[RAGSyncPipeline] = None,
        rag_chain: Optional[RAGChain] = None,
        vector_store: Optional[Any] = None,
        embedder: Optional[Any] = None
    ):
        v_store = vector_store
        emb = embedder
        if sync_pipeline is None:
            from backend.app.rag.qdrant_store import QdrantStore
            from backend.app.rag.embeddings import EmbeddingService
            from backend.app.rag.retriever import SchemeRetriever
            v_store = v_store or QdrantStore()
            emb = emb or EmbeddingService()
            self.sync_pipeline = RAGSyncPipeline(vector_store=v_store, embedder=emb)
            retriever = SchemeRetriever(vector_store=v_store, embedder=emb)
            self.rag_chain = rag_chain or RAGChain(retriever=retriever)
        else:
            self.sync_pipeline = sync_pipeline
            self.rag_chain = rag_chain or RAGChain()

    def run_synchronization(self) -> Dict[str, Any]:
        """Runs the SQL-to-RAG synchronization pipeline."""
        logger.info("Triggering RAG Synchronization Service...")
        return self.sync_pipeline.sync_all()

    def get_sync_status(self) -> Dict[str, Any]:
        """Fetches synchronization status and metrics."""
        return self.sync_pipeline.get_sync_status()

    def get_scheme_detail(self, scheme_id: int) -> Optional[Dict[str, Any]]:
        """Fetches indexing and source information for a specific scheme."""
        return self.sync_pipeline.get_scheme_status(scheme_id)

    def ask(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Queries the RAG pipeline for citizen questions."""
        return self.rag_chain.answer_question(
            query=query,
            user_profile=user_profile,
            filters=filters
        )
