"""Session-isolated vector store using ChromaDB."""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SessionVectorStore:
    """Manages isolated vector embeddings and retrieval for a single session."""

    def __init__(self, session_id: str, storage_base: str = "storage/buckets"):
        self.session_id = session_id
        self.chroma_dir = Path(storage_base) / session_id / "chroma"
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.collection = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(self.chroma_dir))
            self.collection = client.get_or_create_collection(
                name=f"coll_{self.session_id[:16]}",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.warning(f"ChromaDB initialization fallback for session {self.session_id}: {e}")
            self.collection = None

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
                        results.append({
                            "text": d,
                            "document_name": m.get("document_name", "Unknown"),
                            "page_number": m.get("page_number", 1),
                            "score": round(1.0 - dist, 3) if dist is not None else 0.85
                        })
            except Exception as e:
                logger.warning(f"Vector search failed in session {self.session_id}: {e}")

        # Fallback if filtered query yielded 0 results and a filter was used
        if not results and (doc_filter or page_filter):
            return self.search_hybrid(query, top_k=top_k, doc_filter=doc_filter, page_filter=None)

        return results
