"""Session-isolated vector store using ChromaDB."""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SessionVectorStore:
    """Manages isolated vector embeddings and retrieval for a single session."""

    def __init__(self, session_id: str, storage_base: str = "data/object_store"):
        self.session_id = session_id
        self.chroma_dir = Path(storage_base) / session_id / "chroma"
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.collection = None
        self.client = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(self.chroma_dir))
            self.client = client
            self.collection = client.get_or_create_collection(
                name=f"coll_{self.session_id[:16]}",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.warning(f"ChromaDB initialization fallback for session {self.session_id}: {e}")
            self.collection = None
            self.client = None

    def close(self):
        """Release Chroma client handles and open file locks."""
        self.collection = None
        if self.client:
            try:
                if hasattr(self.client, 'close'):
                    self.client.close()
                elif hasattr(self.client, '_system') and hasattr(self.client._system, 'stop'):
                    self.client._system.stop()
            except Exception:
                pass
            self.client = None

    def add_blocks(self, doc_name: str, blocks: List[Dict[str, Any]]):
        """Index text blocks into the session collection."""
        if not blocks:
            return

        documents = []
        metadatas = []
        ids = []

        for i, b in enumerate(blocks):
            text = b.get("text", "").strip()
            if len(text) < 15:
                continue

            b_id = b.get("id") or f"{doc_name}_p{b.get('page_number', 1)}_b{i}"
            documents.append(text)
            metadatas.append({
                "document_name": doc_name,
                "page_number": b.get("page_number", 1),
                "type": b.get("block_type", "paragraph"),
                "session_id": self.session_id
            })
            ids.append(b_id)

        self._upsert_batch(documents, metadatas, ids)

    def add_tables(self, doc_name: str, tables: List[Dict[str, Any]]):
        """Index structured Markdown tables into the session collection."""
        if not tables:
            return

        documents = []
        metadatas = []
        ids = []

        for i, t in enumerate(tables):
            md = t.get("markdown", "").strip()
            headers = ", ".join(t.get("headers", []))
            p_num = t.get("page_number", 1)
            t_id = t.get("id") or f"tab_p{p_num}_{i}"

            text = f"Structured Table on Page {p_num} (Columns: {headers}):\n{md}"
            if len(text) < 20:
                continue

            documents.append(text)
            metadatas.append({
                "document_name": doc_name,
                "page_number": p_num,
                "type": "table",
                "table_id": t_id,
                "headers": headers[:200],
                "session_id": self.session_id
            })
            ids.append(f"{doc_name}_table_{t_id}")

        self._upsert_batch(documents, metadatas, ids)

    def add_figures(self, doc_name: str, figures: List[Dict[str, Any]]):
        """Index visual figures and vector charts into the session collection."""
        if not figures:
            return

        documents = []
        metadatas = []
        ids = []

        for i, f in enumerate(figures):
            caption = f.get("caption", "").strip()
            fig_id = f.get("figure_id") or f"fig_{i}"
            p_num = f.get("page_number", 1)
            fig_type = f.get("figure_type", "chart")
            img_url = f.get("image_url", "")

            text = f"Visual Asset / {fig_type.title()} on Page {p_num}: {caption or fig_id}"
            documents.append(text)
            metadatas.append({
                "document_name": doc_name,
                "page_number": p_num,
                "type": "figure",
                "figure_id": fig_id,
                "figure_type": fig_type,
                "caption": caption[:200],
                "image_url": img_url,
                "session_id": self.session_id
            })
            ids.append(f"{doc_name}_fig_{fig_id}")

        self._upsert_batch(documents, metadatas, ids)

    def _upsert_batch(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        """Helper to batch upsert items into ChromaDB collection."""
        if self.collection and documents:
            try:
                batch_size = 64
                for idx in range(0, len(documents), batch_size):
                    end = idx + batch_size
                    self.collection.upsert(
                        documents=documents[idx:end],
                        metadatas=metadatas[idx:end],
                        ids=ids[idx:end]
                    )
            except Exception as e:
                logger.warning(f"Failed to upsert into ChromaDB: {e}")

    def search_hybrid(
        self,
        query: str,
        top_k: int = 5,
        doc_filter: Optional[str] = None,
        page_filter: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query the session index for relevant passages with optional document and page filtering."""
        results = []
        if not query.strip():
            return results

        if self.collection:
            try:
                where_clause = None
                conditions = []
                if doc_filter:
                    conditions.append({"document_name": doc_filter})
                if page_filter:
                    conditions.append({"page_number": page_filter})

                if len(conditions) == 1:
                    where_clause = conditions[0]
                elif len(conditions) > 1:
                    where_clause = {"$and": conditions}

                chroma_res = self.collection.query(
                    query_texts=[query],
                    n_results=top_k,
                    where=where_clause
                )
                if chroma_res and chroma_res.get("documents"):
                    docs = chroma_res["documents"][0]
                    metas = chroma_res["metadatas"][0] if chroma_res.get("metadatas") else [{}] * len(docs)
                    distances = chroma_res["distances"][0] if chroma_res.get("distances") else [0.0] * len(docs)

                    for d, m, dist in zip(docs, metas, distances):
                        res_item = {
                            "text": d,
                            "document_name": m.get("document_name", "Unknown"),
                            "page_number": m.get("page_number", 1),
                            "type": m.get("type", "paragraph"),
                            "score": round(1.0 - dist, 3) if dist is not None else 0.85
                        }
                        if m.get("figure_id"):
                            res_item["figure_id"] = m.get("figure_id")
                            res_item["image_url"] = m.get("image_url")
                            res_item["caption"] = m.get("caption")
                        if m.get("table_id"):
                            res_item["table_id"] = m.get("table_id")
                            res_item["headers"] = m.get("headers")
                        results.append(res_item)
            except Exception as e:
                logger.warning(f"Vector search failed in session {self.session_id}: {e}")

        # Fallback if filtered query yielded 0 results and a filter was used
        if not results and (doc_filter or page_filter):
            return self.search_hybrid(query, top_k=top_k, doc_filter=doc_filter, page_filter=None)

        return results

    def delete_document(self, doc_name: str):
        """Purge all vector embeddings and indexed blocks for a document."""
        if self.collection:
            try:
                self.collection.delete(where={"document_name": doc_name})
                logger.info(f"Purged vector index blocks for '{doc_name}' in session '{self.session_id}'")
            except Exception as e:
                logger.warning(f"Failed to delete vector blocks for '{doc_name}': {e}")
