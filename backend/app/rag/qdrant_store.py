import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import (
    VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue
)

from backend.app.config import (
    QDRANT_URL, QDRANT_HOST, QDRANT_PORT, QDRANT_API_KEY,
    QDRANT_STORAGE_PATH, QDRANT_COLLECTION, VECTOR_SIZE, VECTOR_DISTANCE
)
from backend.app.ingestion.scheme_chunker import SchemeChunk

logger = logging.getLogger("QdrantStore")

# Fixed namespace for deterministic UUIDv5 generation
SCHEME_NAMESPACE_UUID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_singleton_client: Optional[QdrantClient] = None


class QdrantStore:
    """
    Qdrant Vector Database Integration for SchemeSathi.
    Provides collection initialization, idempotent point upserts,
    deterministic UUIDv5 point IDs, scheme chunk deletion, and filtered retrieval.
    """

    def __init__(
        self,
        collection_name: str = QDRANT_COLLECTION,
        vector_size: int = VECTOR_SIZE,
        client: Optional[QdrantClient] = None
    ):
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.client = client or self._get_or_create_client()
        self.init_collection()

    @classmethod
    def _get_or_create_client(cls) -> QdrantClient:
        """
        Returns or creates a shared singleton QdrantClient instance.
        Prevents multiple file-lock collisions on local persistent storage.
        """
        global _singleton_client
        if _singleton_client is not None:
            return _singleton_client

        # 1. Try explicit QDRANT_URL
        if QDRANT_URL:
            try:
                c = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=3.0)
                c.get_collections()
                logger.info(f"Connected to remote Qdrant at {QDRANT_URL}")
                _singleton_client = c
                return c
            except Exception as e:
                logger.warning(f"Remote Qdrant at {QDRANT_URL} unreachable ({e}). Falling back to local storage.")

        # 2. Try QDRANT_HOST:QDRANT_PORT
        if QDRANT_HOST and QDRANT_HOST != "localhost":
            try:
                c = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY, timeout=3.0)
                c.get_collections()
                logger.info(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
                _singleton_client = c
                return c
            except Exception as e:
                logger.warning(f"Qdrant at {QDRANT_HOST}:{QDRANT_PORT} unreachable ({e}). Falling back to local storage.")

        # 3. Fallback to Local Persistent File Storage
        try:
            storage_path = Path(QDRANT_STORAGE_PATH)
            storage_path.mkdir(parents=True, exist_ok=True)
            c = QdrantClient(path=str(storage_path))
            logger.info(f"Using local persistent Qdrant storage at {storage_path}")
            _singleton_client = c
            return c
        except Exception as e:
            logger.warning(f"Local Qdrant file storage failed ({e}). Falling back to in-memory Qdrant.")
            c = QdrantClient(":memory:")
            _singleton_client = c
            return c

    def init_collection(self):
        """
        Ensures the target Qdrant collection exists and validates vector dimensions.
        """
        try:
            collections = self.client.get_collections().collections
            exists = any(col.name == self.collection_name for col in collections)

            dist = Distance.COSINE if VECTOR_DISTANCE.lower() == "cosine" else Distance.EUCLID

            if not exists:
                logger.info(f"Creating Qdrant collection '{self.collection_name}' (dim: {self.vector_size})...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance=dist)
                )
            else:
                info = self.client.get_collection(self.collection_name)
                # Verify vector size matches
                configured_size = getattr(info.config.params.vectors, "size", self.vector_size)
                if configured_size != self.vector_size:
                    logger.warning(
                        f"Collection '{self.collection_name}' vector size is {configured_size}, "
                        f"expected {self.vector_size}."
                    )
        except Exception as e:
            logger.error(f"Error initializing Qdrant collection '{self.collection_name}': {e}")
            raise e

    @staticmethod
    def generate_point_id(scheme_id: int, chunk_index: int) -> str:
        """
        Generates a deterministic UUIDv5 for a scheme chunk.
        Ensures idempotent insertion and prevents duplicate points in Qdrant.
        """
        seed = f"scheme_{scheme_id}_chunk_{chunk_index}"
        return str(uuid.uuid5(SCHEME_NAMESPACE_UUID, seed))

    def upsert_chunks(self, chunks: List[SchemeChunk], embeddings: List[List[float]]) -> int:
        """
        Upserts a batch of scheme chunks into Qdrant using deterministic IDs.
        """
        if not chunks or not embeddings or len(chunks) != len(embeddings):
            return 0

        points: List[PointStruct] = []
        for chunk, vector in zip(chunks, embeddings):
            pt_id = self.generate_point_id(chunk.scheme_id, chunk.chunk_index)
            payload = chunk.to_dict()

            points.append(
                PointStruct(
                    id=pt_id,
                    vector=vector,
                    payload=payload
                )
            )

        batch_size = 64
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True
            )

        logger.info(f"Upserted {len(points)} chunks into Qdrant collection '{self.collection_name}'.")
        return len(points)

    def delete_scheme_chunks(self, scheme_id: int) -> int:
        """
        Deletes all existing Qdrant vector chunks for a specific scheme_id.
        Used during Case C (content update) to remove obsolete chunks.
        """
        try:
            flt = Filter(
                must=[
                    FieldCondition(
                        key="scheme_id",
                        match=MatchValue(value=scheme_id)
                    )
                ]
            )
            res = self.client.delete(
                collection_name=self.collection_name,
                points_selector=flt,
                wait=True
            )
            logger.info(f"Deleted existing Qdrant vector chunks for scheme_id={scheme_id}.")
            return 1
        except Exception as e:
            logger.error(f"Error deleting chunks for scheme_id={scheme_id}: {e}")
            return 0

    def search(
        self,
        query_vector: List[float],
        top_k: int = 4,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic vector similarity search with optional payload filters.
        """
        query_filter = None
        if filters:
            conditions = []
            for k, v in filters.items():
                if v is not None and str(v).strip():
                    conditions.append(
                        FieldCondition(key=k, match=MatchValue(value=v))
                    )
            if conditions:
                query_filter = Filter(must=conditions)

        hits = []
        if hasattr(self.client, "query_points"):
            res = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold
            )
            hits = getattr(res, "points", []) or []
        elif hasattr(self.client, "search"):
            hits = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold
            )

        results = []
        for hit in hits:
            results.append({
                "score": float(hit.score),
                "point_id": str(hit.id),
                "payload": hit.payload or {}
            })
        return results

    def count_points(self) -> int:
        """Returns total vector count in collection."""
        try:
            info = self.client.get_collection(self.collection_name)
            return info.points_count or 0
        except Exception:
            return 0
