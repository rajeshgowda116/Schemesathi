import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from scheme_cleaner.database import SessionLocal
from backend.app.models.sync_model import SchemeRAGSyncModel, init_sync_table
from backend.app.ingestion.mysql_scheme_loader import MySQLSchemeLoader
from backend.app.ingestion.scheme_deduplicator import SchemeDeduplicator
from backend.app.ingestion.scheme_hash import SchemeHasher
from backend.app.ingestion.scheme_chunker import SchemeChunker
from backend.app.rag.embeddings import EmbeddingService
from backend.app.rag.qdrant_store import QdrantStore

logger = logging.getLogger("RAGSyncPipeline")


class RAGSyncPipeline:
    """
    Core SQL-to-RAG Ingestion and Synchronization Pipeline for SchemeSathi.
    Synchronizes cleaned MySQL scheme records into the Qdrant vector database.
    Implements:
    - Case A: New Scheme -> Insert & Index
    - Case B: Existing Unchanged -> Skip (Idempotent)
    - Case C: Existing Updated -> Replace vectors, Update hash & timestamp
    - Case D: Missing from Source -> Flag as REVIEW_REQUIRED (Never automatically wipe!)
    """

    def __init__(
        self,
        loader: Optional[MySQLSchemeLoader] = None,
        chunker: Optional[SchemeChunker] = None,
        embedder: Optional[EmbeddingService] = None,
        vector_store: Optional[QdrantStore] = None,
        db_session=None
    ):
        self.loader = loader or MySQLSchemeLoader(db_session=db_session)
        self.chunker = chunker or SchemeChunker()
        self.embedder = embedder or EmbeddingService()
        self.vector_store = vector_store or QdrantStore()
        self.external_session = db_session
        init_sync_table()

    def sync_all(self) -> Dict[str, Any]:
        """
        Executes complete synchronization between MySQL clean schemes and Qdrant.
        """
        session = self.external_session or SessionLocal()
        stats = {
            "total_sql_schemes": 0,
            "unique_schemes": 0,
            "new_indexed": 0,
            "updated": 0,
            "unchanged": 0,
            "failed": 0,
            "review_required": 0,
            "total_chunks_indexed": 0,
            "errors": []
        }

        try:
            # 1. Load clean validated schemes from MySQL
            raw_schemes = self.loader.load_clean_schemes()
            stats["total_sql_schemes"] = len(raw_schemes)

            # 2. Scheme Deduplication (ID -> Official ID -> URL -> Name+Dept+State)
            unique_schemes = SchemeDeduplicator.deduplicate_batch(raw_schemes)
            stats["unique_schemes"] = len(unique_schemes)

            active_scheme_ids = set()

            for scheme in unique_schemes:
                scheme_id = int(scheme.get("scheme_id") or scheme.get("id"))
                scheme_name = scheme.get("scheme_name") or "Unnamed Scheme"
                source_url = scheme.get("official_url") or ""
                active_scheme_ids.add(scheme_id)

                # Generate SHA-256 Content Hash across normalized RAG fields
                content_hash = SchemeHasher.compute_hash(scheme)

                # Query synchronization tracking record
                sync_record = session.query(SchemeRAGSyncModel).filter(
                    SchemeRAGSyncModel.scheme_id == scheme_id
                ).first()

                now = datetime.utcnow()

                # -------------------------------------------------------------
                # CASE B: Existing Scheme with UNCHANGED Content
                # -------------------------------------------------------------
                if sync_record and sync_record.content_hash == content_hash and sync_record.indexing_status in ("INDEXED", "UNCHANGED", "UPDATED"):
                    sync_record.last_checked_at = now
                    sync_record.indexing_status = "UNCHANGED"
                    session.commit()
                    stats["unchanged"] += 1
                    logger.debug(f"[UNCHANGED] Scheme {scheme_id} ('{scheme_name}') content matches hash. Skipped.")
                    continue

                # -------------------------------------------------------------
                # CASE C: Existing Scheme with UPDATED Content
                # -------------------------------------------------------------
                is_update = sync_record is not None and sync_record.content_hash != content_hash

                try:
                    # Generate section-aware chunks
                    chunks = self.chunker.chunk_scheme(scheme, content_hash)
                    if not chunks:
                        raise ValueError(f"No valid chunks generated for scheme {scheme_id}")

                    # Generate vector embeddings
                    chunk_texts = [c.chunk_text for c in chunks]
                    embeddings = self.embedder.embed_documents(chunk_texts)

                    if len(embeddings) != len(chunks):
                        raise ValueError(f"Embedding count mismatch: {len(embeddings)} vectors for {len(chunks)} chunks")

                    # If updating, delete existing obsolete vectors first
                    if is_update:
                        self.vector_store.delete_scheme_chunks(scheme_id)

                    # Insert chunks into Qdrant using deterministic UUIDv5 IDs
                    inserted_points = self.vector_store.upsert_chunks(chunks, embeddings)

                    # Update or Insert Sync Tracking Record
                    if sync_record:
                        sync_record.scheme_name = scheme_name
                        sync_record.content_hash = content_hash
                        sync_record.indexing_status = "UPDATED" if is_update else "INDEXED"
                        sync_record.chunks_count = inserted_points
                        sync_record.last_indexed_at = now
                        sync_record.last_checked_at = now
                        sync_record.error_message = None
                        sync_record.source_url = source_url
                    else:
                        sync_record = SchemeRAGSyncModel(
                            scheme_id=scheme_id,
                            scheme_name=scheme_name,
                            content_hash=content_hash,
                            indexing_status="INDEXED",
                            chunks_count=inserted_points,
                            last_indexed_at=now,
                            last_checked_at=now,
                            error_message=None,
                            source_url=source_url
                        )
                        session.add(sync_record)

                    session.commit()

                    if is_update:
                        stats["updated"] += 1
                        logger.info(f"[UPDATED] Scheme {scheme_id} ('{scheme_name}') re-indexed ({inserted_points} chunks).")
                    else:
                        stats["new_indexed"] += 1
                        logger.info(f"[INDEXED] New Scheme {scheme_id} ('{scheme_name}') indexed ({inserted_points} chunks).")

                    stats["total_chunks_indexed"] += inserted_points

                except Exception as scheme_err:
                    session.rollback()
                    err_msg = f"Failed to index scheme {scheme_id} ('{scheme_name}'): {str(scheme_err)}"
                    logger.error(err_msg)
                    stats["failed"] += 1
                    stats["errors"].append({"scheme_id": scheme_id, "error": str(scheme_err)})

                    # Record failure status in tracking table without claiming success
                    if sync_record:
                        sync_record.indexing_status = "FAILED"
                        sync_record.last_checked_at = now
                        sync_record.error_message = str(scheme_err)
                    else:
                        failed_rec = SchemeRAGSyncModel(
                            scheme_id=scheme_id,
                            scheme_name=scheme_name,
                            content_hash=content_hash,
                            indexing_status="FAILED",
                            chunks_count=0,
                            last_indexed_at=None,
                            last_checked_at=now,
                            error_message=str(scheme_err),
                            source_url=source_url
                        )
                        session.add(failed_rec)
                    session.commit()

            # -----------------------------------------------------------------
            # CASE D: Scheme missing from latest active source
            # -----------------------------------------------------------------
            # A failed crawler run must NEVER cause all previously indexed schemes
            # to be marked as deleted. Flag as REVIEW_REQUIRED instead.
            all_tracked_records = session.query(SchemeRAGSyncModel).all()
            for tracked in all_tracked_records:
                if tracked.scheme_id not in active_scheme_ids:
                    if tracked.indexing_status in ("INDEXED", "UNCHANGED", "UPDATED"):
                        tracked.indexing_status = "REVIEW_REQUIRED"
                        tracked.last_checked_at = datetime.utcnow()
                        tracked.error_message = "Scheme not present in latest active SQL source. Preserved pending confirmation."
                        stats["review_required"] += 1
                        logger.warning(
                            f"[REVIEW_REQUIRED] Tracked scheme {tracked.scheme_id} ('{tracked.scheme_name}') "
                            f"missing from source. Preserved in Qdrant pending review."
                        )

            session.commit()
            logger.info(f"RAG Synchronization completed: {stats}")
            return stats

        except Exception as global_err:
            session.rollback()
            logger.error(f"Global RAG Sync failure: {global_err}")
            raise global_err
        finally:
            if not self.external_session:
                session.close()

    def get_sync_status(self) -> Dict[str, Any]:
        """Returns summary statistics from the sync tracking table."""
        session = self.external_session or SessionLocal()
        try:
            total_sql = len(self.loader.load_clean_schemes())
            tracked = session.query(SchemeRAGSyncModel).all()

            status_counts = {
                "INDEXED": 0,
                "UNCHANGED": 0,
                "UPDATED": 0,
                "FAILED": 0,
                "PENDING": 0,
                "REVIEW_REQUIRED": 0
            }

            for t in tracked:
                status = t.indexing_status or "PENDING"
                status_counts[status] = status_counts.get(status, 0) + 1

            total_vectors = self.vector_store.count_points()

            return {
                "total_sql_schemes": total_sql,
                "total_tracked_schemes": len(tracked),
                "total_vectors_in_qdrant": total_vectors,
                "status_breakdown": status_counts,
                "last_sync_timestamp": max((t.last_checked_at for t in tracked), default=None).isoformat() if tracked else None
            }
        finally:
            if not self.external_session:
                session.close()

    def get_scheme_status(self, scheme_id: int) -> Optional[Dict[str, Any]]:
        """Returns synchronization status for a specific scheme."""
        session = self.external_session or SessionLocal()
        try:
            rec = session.query(SchemeRAGSyncModel).filter(
                SchemeRAGSyncModel.scheme_id == scheme_id
            ).first()
            if not rec:
                return None
            return {
                "scheme_id": rec.scheme_id,
                "scheme_name": rec.scheme_name,
                "content_hash": rec.content_hash,
                "indexing_status": rec.indexing_status,
                "chunks_count": rec.chunks_count,
                "last_indexed_at": rec.last_indexed_at.isoformat() if rec.last_indexed_at else None,
                "last_checked_at": rec.last_checked_at.isoformat() if rec.last_checked_at else None,
                "error_message": rec.error_message,
                "source_url": rec.source_url
            }
        finally:
            if not self.external_session:
                session.close()
