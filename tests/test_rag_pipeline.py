import unittest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient

from scheme_cleaner.database import Base as SchemeBase, SchemeModel
from backend.app.models.sync_model import SchemeRAGSyncModel
from backend.app.ingestion.mysql_scheme_loader import MySQLSchemeLoader
from backend.app.ingestion.scheme_normalizer import SchemeNormalizer
from backend.app.ingestion.scheme_hash import SchemeHasher
from backend.app.ingestion.scheme_deduplicator import SchemeDeduplicator
from backend.app.ingestion.scheme_chunker import SchemeChunker
from backend.app.rag.embeddings import EmbeddingService
from backend.app.rag.qdrant_store import QdrantStore
from backend.app.ingestion.rag_sync import RAGSyncPipeline
from backend.app.rag.retriever import SchemeRetriever
from backend.app.rag.chain import RAGChain


class TestRAGPipeline(unittest.TestCase):
    """
    Comprehensive Test Suite for SchemeSathi SQL-to-RAG Pipeline.
    Tests all 12 operational and reliability requirements using isolated in-memory stores.
    """

    def setUp(self):
        # 1. Setup isolated In-Memory SQLite database
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        SchemeBase.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.session = self.Session()

        # 2. Setup isolated In-Memory Qdrant client
        self.qdrant_client = QdrantClient(":memory:")
        self.test_collection = "test_schemes"
        self.vector_store = QdrantStore(
            collection_name=self.test_collection,
            vector_size=384,
            client=self.qdrant_client
        )

        # 3. Setup core pipeline components
        self.embedder = EmbeddingService(dimension=384, provider="builtin")
        self.chunker = SchemeChunker(chunk_size=300, chunk_overlap=30)
        self.loader = MySQLSchemeLoader(db_session=self.session)

        self.pipeline = RAGSyncPipeline(
            loader=self.loader,
            chunker=self.chunker,
            embedder=self.embedder,
            vector_store=self.vector_store,
            db_session=self.session
        )

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _insert_test_scheme(self, **kwargs) -> SchemeModel:
        defaults = {
            "scheme_name": "Post-Matric Scholarship Scheme",
            "state": "Karnataka",
            "department": "Social Welfare Department",
            "description": "Financial scholarship support for post-matric students across Karnataka.",
            "benefits": ["Fee concession", "Monthly maintenance allowance"],
            "eligibility": ["Must be enrolled in recognized post-matric course", "Karnataka resident"],
            "age_min": 16,
            "age_max": 30,
            "income_min": 0,
            "income_max": 250000.0,
            "occupation": ["Student"],
            "category": ["SC", "ST", "OBC"],
            "documents_required": ["Aadhaar", "Income Certificate", "Caste Certificate"],
            "application_process": "Apply online at State Scholarship Portal (SSP).",
            "official_url": "https://ssp.karnataka.gov.in"
        }
        defaults.update(kwargs)
        scheme = SchemeModel(**defaults)
        self.session.add(scheme)
        self.session.commit()
        self.session.refresh(scheme)
        return scheme

    # -------------------------------------------------------------------------
    # TEST 1: New Scheme Insertion (Case A)
    # -------------------------------------------------------------------------
    def test_new_scheme_insertion(self):
        self._insert_test_scheme()
        res = self.pipeline.sync_all()

        self.assertEqual(res["new_indexed"], 1)
        self.assertEqual(res["updated"], 0)
        self.assertEqual(res["unchanged"], 0)
        self.assertGreater(self.vector_store.count_points(), 0)

        # Verify tracking row
        sync_row = self.session.query(SchemeRAGSyncModel).first()
        self.assertIsNotNone(sync_row)
        self.assertEqual(sync_row.indexing_status, "INDEXED")
        self.assertIsNotNone(sync_row.content_hash)
        self.assertIsNotNone(sync_row.last_indexed_at)

    # -------------------------------------------------------------------------
    # TEST 2: Duplicate Scheme Detection
    # -------------------------------------------------------------------------
    def test_duplicate_scheme_detection(self):
        # Two identical scheme definitions
        raw_list = [
            {"id": 1, "scheme_id": 1, "scheme_name": "Gruha Lakshmi", "department": "WCD", "state": "Karnataka", "official_url": "https://sevasindhu.karnataka.gov.in"},
            {"id": 2, "scheme_id": 2, "scheme_name": "Gruha Lakshmi", "department": "WCD", "state": "Karnataka", "official_url": "https://sevasindhu.karnataka.gov.in"},
            {"id": 3, "scheme_id": 3, "scheme_name": "Yuva Nidhi", "department": "Skill Dev", "state": "Karnataka", "official_url": "https://yovanidhi.karnataka.gov.in"}
        ]
        deduped = SchemeDeduplicator.deduplicate_batch(raw_list)
        # Duplicate Gruha Lakshmi must be detected and removed
        self.assertEqual(len(deduped), 2)
        names = [d["scheme_name"] for d in deduped]
        self.assertIn("Gruha Lakshmi", names)
        self.assertIn("Yuva Nidhi", names)

    # -------------------------------------------------------------------------
    # TEST 3: Unchanged Scheme Skipping (Case B)
    # -------------------------------------------------------------------------
    def test_unchanged_scheme_skipping(self):
        self._insert_test_scheme()
        # First sync: index
        res1 = self.pipeline.sync_all()
        self.assertEqual(res1["new_indexed"], 1)
        pts_before = self.vector_store.count_points()

        # Second sync without data modification: skip
        res2 = self.pipeline.sync_all()
        self.assertEqual(res2["new_indexed"], 0)
        self.assertEqual(res2["updated"], 0)
        self.assertEqual(res2["unchanged"], 1)
        pts_after = self.vector_store.count_points()

        # Vector count must remain strictly identical
        self.assertEqual(pts_before, pts_after)

    # -------------------------------------------------------------------------
    # TEST 4: Updated Scheme Re-indexing (Case C)
    # -------------------------------------------------------------------------
    def test_updated_scheme_reindexing(self):
        scheme = self._insert_test_scheme()
        self.pipeline.sync_all()

        sync_row_initial = self.session.query(SchemeRAGSyncModel).filter_by(scheme_id=scheme.id).first()
        initial_hash = sync_row_initial.content_hash

        # Modify scheme content
        scheme.description = "Updated description: Allowance increased to Rs 3000 per month."
        self.session.commit()

        # Run sync: should detect update
        res = self.pipeline.sync_all()
        self.assertEqual(res["updated"], 1)
        self.assertEqual(res["unchanged"], 0)

        # Hash must have changed
        self.session.refresh(sync_row_initial)
        self.assertNotEqual(sync_row_initial.content_hash, initial_hash)
        self.assertEqual(sync_row_initial.indexing_status, "UPDATED")

    # -------------------------------------------------------------------------
    # TEST 5: Old Vector Replacement
    # -------------------------------------------------------------------------
    def test_old_vector_replacement(self):
        scheme = self._insert_test_scheme()
        self.pipeline.sync_all()
        initial_pts = self.vector_store.count_points()

        # Shorten text so fewer chunks are produced
        scheme.description = "Short description."
        self.session.commit()

        self.pipeline.sync_all()
        updated_pts = self.vector_store.count_points()

        # Must not accumulate old chunks
        self.assertLessEqual(updated_pts, initial_pts)

    # -------------------------------------------------------------------------
    # TEST 6: Missing Source Information
    # -------------------------------------------------------------------------
    def test_missing_source_information(self):
        # Insert scheme with null URL, empty department, and no age/income limits
        scheme = self._insert_test_scheme(
            scheme_name="Bare Minimum Scheme",
            department=None,
            official_url=None,
            age_min=None,
            age_max=None,
            income_max=None,
            benefits=None,
            eligibility=None
        )
        res = self.pipeline.sync_all()
        self.assertEqual(res["new_indexed"], 1)

        # Full text generation must not fail or crash
        full_text = SchemeNormalizer.prepare_full_text({
            "scheme_name": scheme.scheme_name,
            "department": scheme.department,
            "official_url": scheme.official_url
        })
        self.assertIn("Not specified", full_text)

    # -------------------------------------------------------------------------
    # TEST 7: Empty Scheme Records & Junk Artifacts Filtering
    # -------------------------------------------------------------------------
    def test_empty_scheme_records(self):
        # Insert junk crawler artifact (.css file) and empty record
        self._insert_test_scheme(scheme_name="styles.css", description="body { color: red; }")
        self._insert_test_scheme(scheme_name="A", description="Too short")

        clean_schemes = self.loader.load_clean_schemes()
        # Junk records must be filtered out
        self.assertEqual(len(clean_schemes), 0)

    # -------------------------------------------------------------------------
    # TEST 8: Embedding Failures
    # -------------------------------------------------------------------------
    def test_embedding_failures(self):
        self._insert_test_scheme()

        # Mock embedding failure
        faulty_embedder = MagicMock()
        faulty_embedder.embed_documents.side_effect = RuntimeError("Embedding model GPU OOM")

        faulty_pipeline = RAGSyncPipeline(
            loader=self.loader,
            chunker=self.chunker,
            embedder=faulty_embedder,
            vector_store=self.vector_store,
            db_session=self.session
        )

        res = faulty_pipeline.sync_all()
        self.assertEqual(res["failed"], 1)
        self.assertEqual(res["new_indexed"], 0)

        # Verify tracking table records failure
        sync_row = self.session.query(SchemeRAGSyncModel).first()
        self.assertEqual(sync_row.indexing_status, "FAILED")
        self.assertIn("Embedding model GPU OOM", sync_row.error_message)

    # -------------------------------------------------------------------------
    # TEST 9: Qdrant Connection Failures
    # -------------------------------------------------------------------------
    def test_qdrant_connection_failures(self):
        self._insert_test_scheme()

        faulty_vector_store = MagicMock()
        faulty_vector_store.upsert_chunks.side_effect = ConnectionError("Qdrant server unreachable")

        faulty_pipeline = RAGSyncPipeline(
            loader=self.loader,
            chunker=self.chunker,
            embedder=self.embedder,
            vector_store=faulty_vector_store,
            db_session=self.session
        )

        res = faulty_pipeline.sync_all()
        self.assertEqual(res["failed"], 1)
        sync_row = self.session.query(SchemeRAGSyncModel).first()
        self.assertEqual(sync_row.indexing_status, "FAILED")

    # -------------------------------------------------------------------------
    # TEST 10: Retrieval and Source Citations
    # -------------------------------------------------------------------------
    def test_retrieval_and_source_citations(self):
        s1 = self._insert_test_scheme(scheme_name="SSP Scholarship for Students")
        s2 = self._insert_test_scheme(
            scheme_name="Kisan Tractor Subsidy",
            department="Agriculture Department",
            description="Subsidy for farmers purchasing tractors in Karnataka."
        )
        self.pipeline.sync_all()

        retriever = SchemeRetriever(embedder=self.embedder, vector_store=self.vector_store)
        hits = retriever.retrieve("scholarship for students studying college", top_k=2)

        self.assertGreater(len(hits), 0)
        top_hit = hits[0]["payload"]
        self.assertEqual(top_hit["scheme_id"], s1.id)
        self.assertEqual(top_hit["scheme_name"], "SSP Scholarship for Students")
        self.assertIn("https://ssp.karnataka.gov.in", top_hit["source_url"])

        # Test RAGChain generation and source citation structure
        chain = RAGChain(retriever=retriever)
        chat_res = chain.answer_question("scholarship for students studying college")
        self.assertGreater(chat_res["retrieved_chunks"], 0)
        self.assertGreater(len(chat_res["sources"]), 0)
        self.assertEqual(chat_res["sources"][0]["scheme_name"], "SSP Scholarship for Students")

    # -------------------------------------------------------------------------
    # TEST 11: Repeated Synchronization Without Duplicates
    # -------------------------------------------------------------------------
    def test_repeated_synchronization_without_duplicates(self):
        self._insert_test_scheme(scheme_name="Yuva Nidhi Scheme")
        self._insert_test_scheme(scheme_name="Gruha Lakshmi Scheme")

        # Run 1
        self.pipeline.sync_all()
        pts_run1 = self.vector_store.count_points()

        # Run 2
        self.pipeline.sync_all()
        pts_run2 = self.vector_store.count_points()

        # Run 3
        self.pipeline.sync_all()
        pts_run3 = self.vector_store.count_points()

        # Vector count must remain constant
        self.assertEqual(pts_run1, pts_run2)
        self.assertEqual(pts_run2, pts_run3)

    # -------------------------------------------------------------------------
    # TEST 12: Safe Handling of Missing or Removed Schemes (Case D)
    # -------------------------------------------------------------------------
    def test_safe_handling_of_missing_or_removed_schemes(self):
        s1 = self._insert_test_scheme(scheme_name="Permanent Scheme")
        s2 = self._insert_test_scheme(scheme_name="Temporary Scheme")
        self.pipeline.sync_all()

        pts_before = self.vector_store.count_points()

        # Simulate scheme s2 being removed from active SQL source
        self.session.delete(s2)
        self.session.commit()

        # Run sync again
        res = self.pipeline.sync_all()
        self.assertEqual(res["review_required"], 1)

        # Crucial check: Vectors in Qdrant must NOT be automatically deleted!
        pts_after = self.vector_store.count_points()
        self.assertEqual(pts_before, pts_after)

        # Tracking status must be REVIEW_REQUIRED
        s2_track = self.session.query(SchemeRAGSyncModel).filter_by(scheme_id=s2.id).first()
        self.assertEqual(s2_track.indexing_status, "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
