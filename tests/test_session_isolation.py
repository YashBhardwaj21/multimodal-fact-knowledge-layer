"""Unit tests for multi-tenant session isolation."""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.storage.object_store import ObjectStore
from src.sessions.session_manager import SessionManager
from src.rag.vector_store import SessionVectorStore
from src.rag.chat_engine import ChatEngine


class TestSessionIsolation(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_isolation_")
        self.storage_base = Path(self.test_dir) / "buckets"
        self.storage_base.mkdir(parents=True, exist_ok=True)
        self.object_store = ObjectStore(base_dir=str(self.storage_base))
        self.session_manager = SessionManager(object_store=self.object_store)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_session_metadata_isolation(self):
        """Test document metadata isolation between workspaces."""
        session_a = self.session_manager.create_session("Finance Alpha", "Alpha internal docs")
        session_b = self.session_manager.create_session("Legal Beta", "Beta legal reviews")

        doc_a = {
            "doc_id": "doc_alpha_secret",
            "filename": "alpha_q3_confidential.pdf",
            "title": "Alpha Q3 Confidential Results",
            "pages_count": 10,
            "blocks_count": 50,
            "tables_count": 2,
            "figures_count": 1,
            "summary": "Confidential EBITDA growth of 42% for Alpha Corporation.",
            "tags": ["Confidential", "Finance"]
        }
        session_a.documents.append(doc_a)

        self.assertEqual(len(session_a.documents), 1)
        self.assertEqual(session_a.documents[0]["doc_id"], "doc_alpha_secret")

        self.assertEqual(len(session_b.documents), 0)
        b_doc_ids = [d["doc_id"] for d in session_b.documents]
        self.assertNotIn("doc_alpha_secret", b_doc_ids)

    def test_object_store_bucket_isolation(self):
        """Test binary file blob isolation between session buckets."""
        session_a = self.session_manager.create_session("Tenant A")
        session_b = self.session_manager.create_session("Tenant B")

        payload_a = b"SECRET_ALPHA_TOKEN_9918237192"
        res_a = self.object_store.save_document(session_a.id, "confidential.pdf", payload_a)
        saved_path = res_a["file_path"]
        self.assertTrue(Path(saved_path).exists())

        self.assertIn(session_a.id, str(saved_path))
        self.assertNotIn(session_b.id, str(saved_path))

        files_a = self.object_store.list_session_documents(session_a.id)
        files_b = self.object_store.list_session_documents(session_b.id)

        self.assertIn("confidential.pdf", files_a)
        self.assertNotIn("confidential.pdf", files_b)
        self.assertEqual(len(files_b), 0)

    def test_vector_store_zero_knowledge_isolation(self):
        """Test vector embedding search isolation between sessions."""
        session_a_id = "workspace_isolated_a"
        session_b_id = "workspace_isolated_b"

        vec_a = SessionVectorStore(session_id=session_a_id, storage_base=str(self.storage_base))
        vec_b = SessionVectorStore(session_id=session_b_id, storage_base=str(self.storage_base))

        vec_a.add_blocks(
            doc_name="QuantumAlgorithm.pdf",
            blocks=[
                {
                    "id": "blk_q_01",
                    "text": "Project Zephyr achieved 99.8% quantum gate fidelity using cryogenic silicon qubits.",
                    "page_number": 4,
                    "block_type": "paragraph"
                }
            ]
        )

        vec_b.add_blocks(
            doc_name="CulinaryGuide.pdf",
            blocks=[
                {
                    "id": "blk_c_01",
                    "text": "To make the perfect sourdough, maintain starter hydration at precisely 80 percent.",
                    "page_number": 1,
                    "block_type": "recipe"
                }
            ]
        )

        results_a = vec_a.search_hybrid("quantum gate fidelity silicon", top_k=3)
        self.assertGreater(len(results_a), 0)
        self.assertEqual(results_a[0]["document_name"], "QuantumAlgorithm.pdf")

        results_b = vec_b.search_hybrid("quantum gate fidelity silicon", top_k=3)
        for res in results_b:
            self.assertNotEqual(res.get("document_name"), "QuantumAlgorithm.pdf")
            self.assertNotIn("Zephyr", res.get("text", ""))

    def test_chat_engine_cross_talk_isolation(self):
        """Test conversational query isolation between sessions."""
        session_a = self.session_manager.create_session("Pharma Trials")
        session_b = self.session_manager.create_session("Auto Mechanics")

        engine_a = ChatEngine(session=session_a, storage_base=str(self.storage_base))
        engine_b = ChatEngine(session=session_b, storage_base=str(self.storage_base))

        engine_a.vector_store.add_blocks(
            doc_name="VaccinePhase3.pdf",
            blocks=[
                {
                    "id": "vac_01",
                    "text": "The efficacy rate of compound VX-809 was observed to be 94.6% in clinical cohort beta.",
                    "page_number": 12,
                    "block_type": "paragraph"
                }
            ]
        )

        res_a = engine_a.chat("What was the efficacy rate of compound VX-809?")
        self.assertTrue("94" in res_a["reply"] and "efficacy" in res_a["reply"].lower())
        self.assertGreater(len(res_a["citations"]), 0)
        self.assertEqual(res_a["citations"][0]["document_name"], "VaccinePhase3.pdf")

        res_b = engine_b.chat("What was the efficacy rate of compound VX-809?")
        citations_b_docs = [c.get("document_name") for c in res_b["citations"]]
        self.assertNotIn("VaccinePhase3.pdf", citations_b_docs)
        self.assertEqual(len(res_b["citations"]), 0)
        self.assertIn("no verified information", res_b["reply"].lower())


if __name__ == "__main__":
    unittest.main()
