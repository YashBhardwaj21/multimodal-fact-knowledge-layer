"""Session and workspace manager with normalized SQLite database storage and separated Object Storage."""

import os
import json
import uuid
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from src.storage.object_store import ObjectStore, default_object_store
from src.facts.models import KnowledgeLayer, Fact, Evidence, FactComparison, RelationshipType
from src.facts.entity_models import CanonicalEntity, EntityMention

logger = logging.getLogger(__name__)


class ChatMessage:
    """Represents a conversational message with citations."""

    def __init__(
        self,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        msg_id: Optional[str] = None,
        timestamp: Optional[str] = None
    ):
        self.id = msg_id or f"msg_{uuid.uuid4().hex[:8]}"
        self.role = role
        self.content = content
        self.citations = citations or []
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "citations": self.citations,
            "timestamp": self.timestamp
        }


class WorkspaceSession:
    """Isolated chat workspace holding documents, facts, and conversation history."""

    def __init__(
        self,
        session_id: str,
        title: str,
        description: str = "",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None
    ):
        self.id = session_id
        self.title = title
        self.description = description
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or self.created_at
        self.documents: List[Dict[str, Any]] = []
        self.messages: List[ChatMessage] = []
        self.knowledge_layer: KnowledgeLayer = KnowledgeLayer()

    def to_dict(self, include_knowledge: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_documents": len(self.documents),
            "documents": self.documents,
            "message_count": len(self.messages),
            "recent_messages": [m.to_dict() for m in self.messages[-5:]],
            "stats": {
                "total_facts": len(self.knowledge_layer.facts),
                "total_comparisons": len(self.knowledge_layer.comparisons),
                "corroborations": self.knowledge_layer.statistics.get("corroborations", 0),
                "contradictions": self.knowledge_layer.statistics.get("contradictions", 0),
                "reconciled": self.knowledge_layer.statistics.get("reconciled", 0),
                "failures_handled": self.knowledge_layer.statistics.get("extraction_failures_handled", 0),
            }
        }
        if include_knowledge:
            data["knowledge_layer"] = self.knowledge_layer.to_dict()
        return data


def _fact_from_dict(d: Dict[str, Any]) -> Fact:
    ev_data = d.get("evidence")
    ev = Evidence(**ev_data) if ev_data else None
    return Fact(
        id=d.get("id", f"fact_{uuid.uuid4().hex[:8]}"),
        subject=d.get("subject", ""),
        attribute=d.get("attribute", d.get("predicate", "")),
        value=d.get("value", ""),
        normalized_value=d.get("normalized_value"),
        unit=d.get("unit", ""),
        temporal_scope=d.get("temporal_scope", d.get("time")),
        context_scope=d.get("context_scope", d.get("scope")),
        evidence=ev,
        confidence=d.get("confidence", 1.0),
        surface_subject=d.get("surface_subject", d.get("subject", "")),
        entity_id=d.get("entity_id"),
        canonical_subject=d.get("canonical_subject", d.get("subject", "")),
        entity_resolution_confidence=d.get("entity_resolution_confidence", 1.0),
        entity_type=d.get("entity_type", "unknown"),
        entity_resolution_status=d.get("entity_resolution_status", "resolved" if d.get("entity_id") else "unresolved")
    )


def _comparison_from_dict(d: Dict[str, Any]) -> FactComparison:
    rel_str = d.get("relationship_type", d.get("relationship", "corroboration"))
    try:
        rel_type = RelationshipType(rel_str)
    except ValueError:
        rel_type = RelationshipType.CORROBORATION

    f_a = _fact_from_dict(d["fact_a"]) if d.get("fact_a") else None
    f_b = _fact_from_dict(d["fact_b"]) if d.get("fact_b") else None

    return FactComparison(
        id=d.get("id", f"rel_{uuid.uuid4().hex[:8]}"),
        relationship_type=rel_type,
        title=d.get("title", ""),
        fact_a=f_a,
        fact_b=f_b,
        explanation=d.get("explanation", d.get("reasoning", "")),
        reconciliation_factor=d.get("reconciliation_factor")
    )


class SessionManager:
    """Registry and controller for isolated chat workspaces backed by a relational SQLite database."""

    def __init__(
        self,
        object_store: Optional[ObjectStore] = None,
        db_path: Optional[str] = None
    ):
        self.object_store = object_store or default_object_store

        if db_path:
            self.db_path = str(db_path)
        else:
            self.db_path = str(Path("data/database/document_intelligence.db"))

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self.sessions: Dict[str, WorkspaceSession] = {}
        self._init_db()
        self._load_from_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS workspaces (
                            id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            description TEXT DEFAULT '',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS documents (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            filename TEXT NOT NULL,
                            file_size INTEGER NOT NULL,
                            file_hash TEXT NOT NULL,
                            storage_path TEXT NOT NULL,
                            page_count INTEGER NOT NULL,
                            uploaded_at TEXT NOT NULL,
                            status TEXT DEFAULT 'Processed',
                            summary TEXT DEFAULT '',
                            tags TEXT DEFAULT '[]',
                            blocks_count INTEGER DEFAULT 0,
                            tables_count INTEGER DEFAULT 0,
                            figures_count INTEGER DEFAULT 0,
                            processed_time TEXT DEFAULT 'Just now',
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS document_pages (
                            id TEXT PRIMARY KEY,
                            document_id TEXT NOT NULL,
                            workspace_id TEXT NOT NULL,
                            page_number INTEGER NOT NULL,
                            text TEXT NOT NULL,
                            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS facts (
                            id TEXT PRIMARY KEY,
                            document_id TEXT NOT NULL,
                            workspace_id TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            predicate TEXT NOT NULL,
                            value TEXT NOT NULL,
                            normalized_value REAL,
                            unit TEXT DEFAULT '',
                            time TEXT DEFAULT '',
                            scope TEXT DEFAULT '',
                            confidence REAL DEFAULT 1.0,
                            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS evidence (
                            id TEXT PRIMARY KEY,
                            fact_id TEXT NOT NULL,
                            document_name TEXT NOT NULL,
                            page_number INTEGER NOT NULL,
                            quote TEXT NOT NULL,
                            table_citation TEXT,
                            image_citation TEXT,
                            FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS fact_relationships (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            fact_a_id TEXT,
                            fact_b_id TEXT,
                            relationship TEXT NOT NULL,
                            title TEXT NOT NULL,
                            reasoning TEXT NOT NULL,
                            reconciliation_factor TEXT,
                            confidence REAL DEFAULT 1.0,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
                            FOREIGN KEY (fact_a_id) REFERENCES facts(id) ON DELETE SET NULL,
                            FOREIGN KEY (fact_b_id) REFERENCES facts(id) ON DELETE SET NULL
                        );

                        CREATE TABLE IF NOT EXISTS messages (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            role TEXT NOT NULL,
                            content TEXT NOT NULL,
                            citations TEXT DEFAULT '[]',
                            timestamp TEXT NOT NULL,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS entities (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            canonical_name TEXT NOT NULL,
                            entity_type TEXT DEFAULT 'unknown',
                            aliases TEXT DEFAULT '[]',
                            description TEXT DEFAULT '',
                            confidence REAL DEFAULT 1.0,
                            resolution_status TEXT DEFAULT 'resolved',
                            source_documents TEXT DEFAULT '[]',
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS entity_mentions (
                            id TEXT PRIMARY KEY,
                            entity_id TEXT,
                            workspace_id TEXT NOT NULL,
                            surface_form TEXT NOT NULL,
                            normalized_form TEXT NOT NULL,
                            entity_type TEXT DEFAULT 'unknown',
                            document_name TEXT NOT NULL,
                            page_number INTEGER NOT NULL,
                            context_sentence TEXT DEFAULT '',
                            confidence REAL DEFAULT 1.0,
                            resolution_method TEXT DEFAULT 'deterministic',
                            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                        );
                    """)

                    # Column migrations for facts table
                    for col, col_type in [
                        ("surface_subject", "TEXT DEFAULT ''"),
                        ("entity_id", "TEXT DEFAULT ''"),
                        ("canonical_subject", "TEXT DEFAULT ''"),
                        ("entity_resolution_confidence", "REAL DEFAULT 1.0"),
                        ("entity_type", "TEXT DEFAULT ''"),
                        ("entity_resolution_status", "TEXT DEFAULT ''"),
                    ]:
                        try:
                            conn.execute(f"ALTER TABLE facts ADD COLUMN {col} {col_type};")
                        except sqlite3.OperationalError:
                            pass
            finally:
                conn.close()

    def _load_from_db(self):
        with self._lock:
            self.sessions.clear()
            conn = self._get_conn()
            try:
                # 1. Load workspaces
                ws_cursor = conn.execute("SELECT id, title, description, created_at, updated_at FROM workspaces ORDER BY created_at ASC")
                for row in ws_cursor.fetchall():
                    session = WorkspaceSession(
                        session_id=row["id"],
                        title=row["title"],
                        description=row["description"] or "",
                        created_at=row["created_at"],
                        updated_at=row["updated_at"]
                    )

                    # 2. Load documents
                    doc_cursor = conn.execute(
                        "SELECT id, filename, file_size, file_hash, storage_path, page_count, uploaded_at, status, summary, tags, blocks_count, tables_count, figures_count, processed_time FROM documents WHERE workspace_id = ? ORDER BY uploaded_at ASC",
                        (row["id"],)
                    )
                    for d in doc_cursor.fetchall():
                        try:
                            tags = json.loads(d["tags"])
                        except Exception:
                            tags = []
                        session.documents.append({
                            "doc_id": d["id"],
                            "id": d["id"],
                            "filename": d["filename"],
                            "title": d["filename"].replace(".pdf", "").replace("-", " ").replace("_", " ").title(),
                            "pages_count": d["page_count"],
                            "blocks_count": d["blocks_count"],
                            "tables_count": d["tables_count"],
                            "figures_count": d["figures_count"],
                            "summary": d["summary"] or "",
                            "tags": tags,
                            "status": d["status"] or "Processed",
                            "processed_time": d["processed_time"] or "Just now",
                            "size_bytes": d["file_size"] or 0,
                            "storage_path": d["storage_path"]
                        })

                    # 3. Load facts with evidence
                    facts_cursor = conn.execute("""
                        SELECT f.id, f.document_id, f.subject, f.predicate, f.value, f.normalized_value, f.unit, f.time, f.scope, f.confidence,
                               f.surface_subject, f.entity_id, f.canonical_subject, f.entity_resolution_confidence, f.entity_type, f.entity_resolution_status,
                               e.document_name, e.page_number, e.quote, e.table_citation, e.image_citation
                        FROM facts f
                        LEFT JOIN evidence e ON f.id = e.fact_id
                        WHERE f.workspace_id = ?
                    """, (row["id"],))

                    facts_map: Dict[str, Fact] = {}
                    for f_row in facts_cursor.fetchall():
                        ev = None
                        if f_row["document_name"]:
                            ev = Evidence(
                                document_name=f_row["document_name"],
                                page_number=f_row["page_number"],
                                verbatim_quote=f_row["quote"],
                                table_citation=f_row["table_citation"],
                                image_citation=f_row["image_citation"]
                            )
                        fact = Fact(
                            id=f_row["id"],
                            subject=f_row["subject"],
                            attribute=f_row["predicate"],
                            value=f_row["value"],
                            normalized_value=f_row["normalized_value"],
                            unit=f_row["unit"] or "",
                            temporal_scope=f_row["time"],
                            context_scope=f_row["scope"],
                            evidence=ev,
                            confidence=f_row["confidence"] or 1.0,
                            surface_subject=f_row["surface_subject"] or f_row["subject"],
                            entity_id=f_row["entity_id"] or None,
                            canonical_subject=f_row["canonical_subject"] or f_row["subject"],
                            entity_resolution_confidence=float(f_row["entity_resolution_confidence"] or 1.0),
                            entity_type=f_row["entity_type"] or "unknown",
                            entity_resolution_status=f_row["entity_resolution_status"] or None
                        )
                        facts_map[fact.id] = fact

                    session.knowledge_layer.facts = list(facts_map.values())
                    session.knowledge_layer.documents = sorted(list(set(d["filename"] for d in session.documents)))

                    # 4. Load fact relationships
                    rel_cursor = conn.execute(
                        "SELECT id, fact_a_id, fact_b_id, relationship, title, reasoning, reconciliation_factor, confidence FROM fact_relationships WHERE workspace_id = ?",
                        (row["id"],)
                    )
                    comparisons = []
                    for r_row in rel_cursor.fetchall():
                        try:
                            rel_type = RelationshipType(r_row["relationship"].lower())
                        except Exception:
                            rel_type = RelationshipType.CORROBORATION
                        comparisons.append(FactComparison(
                            id=r_row["id"],
                            relationship_type=rel_type,
                            title=r_row["title"],
                            fact_a=facts_map.get(r_row["fact_a_id"]),
                            fact_b=facts_map.get(r_row["fact_b_id"]),
                            explanation=r_row["reasoning"],
                            reconciliation_factor=r_row["reconciliation_factor"]
                        ))
                    session.knowledge_layer.comparisons = comparisons

                    # 5. Load canonical entities and mentions
                    ent_cursor = conn.execute(
                        "SELECT id, canonical_name, entity_type, aliases, description, confidence, resolution_status, source_documents FROM entities WHERE workspace_id = ?",
                        (row["id"],)
                    )
                    entities_map: Dict[str, CanonicalEntity] = {}
                    for e_row in ent_cursor.fetchall():
                        try:
                            aliases = json.loads(e_row["aliases"])
                        except Exception:
                            aliases = []
                        try:
                            sdocs = json.loads(e_row["source_documents"])
                        except Exception:
                            sdocs = []
                        entities_map[e_row["id"]] = CanonicalEntity(
                            entity_id=e_row["id"],
                            canonical_name=e_row["canonical_name"],
                            entity_type=e_row["entity_type"] or "unknown",
                            aliases=aliases,
                            description=e_row["description"] or "",
                            confidence=float(e_row["confidence"] or 1.0),
                            resolution_status=e_row["resolution_status"] or "resolved",
                            source_documents=sdocs
                        )

                    men_cursor = conn.execute(
                        "SELECT id, entity_id, surface_form, normalized_form, entity_type, document_name, page_number, context_sentence, confidence, resolution_method FROM entity_mentions WHERE workspace_id = ?",
                        (row["id"],)
                    )
                    for m_row in men_cursor.fetchall():
                        men_obj = EntityMention(
                            mention_id=m_row["id"],
                            surface_form=m_row["surface_form"],
                            normalized_form=m_row["normalized_form"],
                            entity_type=m_row["entity_type"] or "unknown",
                            document_name=m_row["document_name"] or "",
                            page_number=m_row["page_number"] or 1,
                            context_sentence=m_row["context_sentence"] or "",
                            resolved_entity_id=m_row["entity_id"],
                            confidence=float(m_row["confidence"] or 1.0),
                            resolution_method=m_row["resolution_method"] or "deterministic"
                        )
                        if m_row["entity_id"] in entities_map:
                            entities_map[m_row["entity_id"]].source_mentions.append(men_obj)

                    session.knowledge_layer.entities = entities_map

                    # 5. Load messages
                    msg_cursor = conn.execute(
                        "SELECT id, role, content, citations, timestamp FROM messages WHERE workspace_id = ? ORDER BY timestamp ASC",
                        (row["id"],)
                    )
                    for m in msg_cursor.fetchall():
                        try:
                            citations = json.loads(m["citations"])
                        except Exception:
                            citations = []
                        session.messages.append(ChatMessage(
                            role=m["role"],
                            content=m["content"],
                            citations=citations,
                            msg_id=m["id"],
                            timestamp=m["timestamp"]
                        ))

                    self.sessions[session.id] = session

                if len(self.sessions) == 0:
                    default_id = f"workspace_{uuid.uuid4().hex[:8]}"
                    now_str = datetime.now().isoformat()
                    with conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO workspaces (id, title, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (default_id, "Workspace 1", "Interactive document intelligence workspace.", now_str, now_str)
                        )
                    self.sessions[default_id] = WorkspaceSession(
                        session_id=default_id,
                        title="Workspace 1",
                        description="Interactive document intelligence workspace.",
                        created_at=now_str,
                        updated_at=now_str
                    )
            finally:
                conn.close()

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.sessions.values()]

    def get_session(self, session_id: str, include_knowledge: bool = False) -> Optional[WorkspaceSession]:
        return self.sessions.get(session_id)

    def create_session(self, title: str, description: str = "") -> WorkspaceSession:
        new_id = f"workspace_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        session = WorkspaceSession(
            session_id=new_id,
            title=title.strip() or "Untitled Workspace",
            description=description,
            created_at=now,
            updated_at=now
        )

        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO workspaces (id, title, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (session.id, session.title, session.description, session.created_at, session.updated_at)
                    )
                self.sessions[new_id] = session
            finally:
                conn.close()

        logger.info(f"Created and persisted workspace '{session.title}' ({new_id})")
        return session

    def rename_session(self, session_id: str, new_title: str) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False

        clean_title = new_title.strip()
        now = datetime.now().isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.execute(
                        "UPDATE workspaces SET title = ?, updated_at = ? WHERE id = ?",
                        (clean_title, now, session_id)
                    )
                session.title = clean_title
                session.updated_at = now
            finally:
                conn.close()

        logger.info(f"Renamed workspace {session_id} to '{clean_title}'")
        return True

    def delete_session(self, session_id: str) -> bool:
        """Permanently delete a workspace and all its data from SQLite and Object Storage."""
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.execute("DELETE FROM workspaces WHERE id = ?", (session_id,))
                if session_id in self.sessions:
                    del self.sessions[session_id]
                try:
                    self.object_store.delete_session_storage(session_id)
                except Exception as e:
                    logger.warning(f"Storage purge warning for workspace {session_id}: {e}")
            finally:
                conn.close()

        logger.info(f"Completely purged workspace {session_id} from database and storage")
        return True

    def add_document(
        self,
        session_id: str,
        doc_entry: Dict[str, Any],
        pages: Optional[List[Any]] = None,
        facts: Optional[List[Fact]] = None,
        comparisons: Optional[List[FactComparison]] = None
    ) -> bool:
        """Persist document metadata, pages, facts, and evidence in normalized tables."""
        session = self.get_session(session_id)
        if not session:
            return False

        now = datetime.now().isoformat()
        doc_id = doc_entry.get("doc_id") or doc_entry.get("id") or f"doc_{uuid.uuid4().hex[:8]}"
        filename = doc_entry.get("filename", "")
        file_size = doc_entry.get("size_bytes", doc_entry.get("file_size", 0))
        file_hash = doc_entry.get("sha256", doc_entry.get("file_hash", doc_id))
        storage_path = doc_entry.get("storage_path", f"{session_id}/documents/{filename}")
        page_count = doc_entry.get("pages_count", doc_entry.get("page_count", len(pages) if pages else 1))
        summary = doc_entry.get("summary", "")
        tags_json = json.dumps(doc_entry.get("tags", []))
        blocks_count = doc_entry.get("blocks_count", 0)
        tables_count = doc_entry.get("tables_count", 0)
        figures_count = doc_entry.get("figures_count", 0)
        processed_time = doc_entry.get("processed_time", "Just now")

        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    # 0. Guarantee workspace exists in workspaces table to satisfy foreign key
                    ws_row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (session_id,)).fetchone()
                    if not ws_row:
                        ws_title = session.title if session else "Active Workspace"
                        ws_desc = session.description if session else ""
                        conn.execute(
                            "INSERT OR REPLACE INTO workspaces (id, title, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (session_id, ws_title, ws_desc, now, now)
                        )

                    # 1. Insert or replace document record
                    conn.execute("""
                        INSERT OR REPLACE INTO documents (
                            id, workspace_id, filename, file_size, file_hash, storage_path,
                            page_count, uploaded_at, status, summary, tags, blocks_count,
                            tables_count, figures_count, processed_time
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        doc_id, session_id, filename, file_size, file_hash, storage_path,
                        page_count, now, "Processed", summary, tags_json, blocks_count,
                        tables_count, figures_count, processed_time
                    ))

                    # 2. Insert pages text
                    if pages:
                        for p in pages:
                            p_num = getattr(p, "page_number", p.get("page_number", 1) if isinstance(p, dict) else 1)
                            p_text = getattr(p, "text", p.get("text", "") if isinstance(p, dict) else "")
                            p_id = f"{doc_id}_p{p_num}"
                            conn.execute("""
                                INSERT OR REPLACE INTO document_pages (id, document_id, workspace_id, page_number, text)
                                VALUES (?, ?, ?, ?, ?)
                            """, (p_id, doc_id, session_id, p_num, p_text))

                    # 3. Insert facts and evidence
                    if facts:
                        for f in facts:
                            conn.execute("""
                                INSERT OR REPLACE INTO facts (
                                    id, document_id, workspace_id, subject, predicate, value,
                                    normalized_value, unit, time, scope, confidence,
                                    surface_subject, entity_id, canonical_subject,
                                    entity_resolution_confidence, entity_type, entity_resolution_status
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                f.id, doc_id, session_id, f.subject, f.attribute, f.value,
                                f.normalized_value, f.unit, f.temporal_scope or "", f.context_scope or "", f.confidence,
                                f.surface_subject or f.subject, f.entity_id or "", f.canonical_subject or f.subject,
                                float(f.entity_resolution_confidence if f.entity_resolution_confidence is not None else 1.0),
                                f.entity_type or "unknown", f.entity_resolution_status or ""
                            ))
                            if f.evidence:
                                ev_id = f"ev_{f.id}"
                                conn.execute("""
                                    INSERT OR REPLACE INTO evidence (
                                        id, fact_id, document_name, page_number, quote, table_citation, image_citation
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    ev_id, f.id, f.evidence.document_name, f.evidence.page_number,
                                    f.evidence.verbatim_quote, f.evidence.table_citation, f.evidence.image_citation
                                ))

                    # 4. Insert fact relationships (guarantee facts exist to satisfy foreign key)
                    if comparisons:
                        valid_fact_ids = set(r[0] for r in conn.execute("SELECT id FROM facts WHERE workspace_id = ?", (session_id,)).fetchall())
                        for c in comparisons:
                            fa_id = c.fact_a.id if (c.fact_a and c.fact_a.id in valid_fact_ids) else None
                            fb_id = c.fact_b.id if (c.fact_b and c.fact_b.id in valid_fact_ids) else None
                            conn.execute("""
                                INSERT OR REPLACE INTO fact_relationships (
                                    id, workspace_id, fact_a_id, fact_b_id, relationship, title,
                                    reasoning, reconciliation_factor, confidence
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                c.id, session_id,
                                fa_id, fb_id,
                                c.relationship_type.value, c.title, c.explanation,
                                c.reconciliation_factor, 1.0
                            ))

                    conn.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (now, session_id))

                # Update in-memory session cache
                existing_idx = next((i for i, d in enumerate(session.documents) if d.get("id") == doc_id or d.get("filename") == filename), None)
                norm_doc_entry = {
                    "doc_id": doc_id,
                    "id": doc_id,
                    "filename": filename,
                    "title": doc_entry.get("title", filename.replace(".pdf", "").replace("-", " ").replace("_", " ").title()),
                    "pages_count": page_count,
                    "blocks_count": blocks_count,
                    "tables_count": tables_count,
                    "figures_count": figures_count,
                    "summary": summary,
                    "tags": doc_entry.get("tags", []),
                    "status": "Processed",
                    "processed_time": processed_time,
                    "size_bytes": file_size,
                    "storage_path": storage_path
                }
                if existing_idx is not None:
                    session.documents[existing_idx] = norm_doc_entry
                else:
                    session.documents.append(norm_doc_entry)

                if facts:
                    # Append new facts without duplicate IDs
                    existing_fids = set(f.id for f in session.knowledge_layer.facts)
                    for f in facts:
                        if f.id not in existing_fids:
                            session.knowledge_layer.facts.append(f)

                if comparisons:
                    session.knowledge_layer.comparisons = comparisons

                session.knowledge_layer.documents = sorted(list(set(d["filename"] for d in session.documents)))
                session.updated_at = now
            finally:
                conn.close()

        return True

    def delete_document(self, session_id: str, doc_identifier: str) -> bool:
        """Purge document, its pages, facts, evidence, and object storage files."""
        session = self.get_session(session_id)
        if not session:
            return False

        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                # Find document record
                cursor = conn.execute(
                    "SELECT id, filename FROM documents WHERE workspace_id = ? AND (id = ? OR filename = ?)",
                    (session_id, doc_identifier, doc_identifier)
                )
                row = cursor.fetchone()
                if not row:
                    return False

                doc_id = row["id"]
                filename = row["filename"]

                with conn:
                    # Cascade deletion takes care of document_pages, facts, evidence, etc.
                    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                    # Clean up orphan comparisons that referenced facts from this document
                    conn.execute("""
                        DELETE FROM fact_relationships
                        WHERE workspace_id = ? AND (fact_a_id IS NULL AND fact_b_id IS NULL)
                    """, (session_id,))
                    conn.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (now, session_id))

                # Delete object storage files (PDF, thumbnails, figures)
                self.object_store.delete_document_files(session_id, filename)

                # Update in-memory session cache
                session.documents = [d for d in session.documents if d.get("id") != doc_id and d.get("filename") != filename]
                session.knowledge_layer.facts = [
                    f for f in session.knowledge_layer.facts
                    if not f.evidence or f.evidence.document_name != filename
                ]
                session.knowledge_layer.documents = sorted(list(set(d["filename"] for d in session.documents)))
                session.updated_at = now
            finally:
                conn.close()

        logger.info(f"Permanently purged document '{doc_identifier}' from workspace '{session_id}' across DB & Object Storage")
        return True

    def persist_message(self, session_id: str, msg: ChatMessage):
        """Save a ChatMessage instance directly into the SQLite database."""
        citations_json = json.dumps(msg.citations)
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    ws_row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (session_id,)).fetchone()
                    if not ws_row:
                        now_ts = datetime.now().isoformat()
                        session = self.get_session(session_id)
                        ws_title = session.title if session else "Active Workspace"
                        conn.execute(
                            "INSERT OR REPLACE INTO workspaces (id, title, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (session_id, ws_title, "", now_ts, now_ts)
                        )
                    conn.execute(
                        "INSERT OR REPLACE INTO messages (id, workspace_id, role, content, citations, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                        (msg.id, session_id, msg.role, msg.content, citations_json, msg.timestamp)
                    )
                    conn.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (msg.timestamp, session_id))
            finally:
                conn.close()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[ChatMessage]:
        session = self.get_session(session_id)
        if not session:
            return None

        msg = ChatMessage(role=role, content=content, citations=citations)
        self.persist_message(session_id, msg)
        if not any(m.id == msg.id for m in session.messages):
            session.messages.append(msg)
        session.updated_at = msg.timestamp
        return msg

    def save_knowledge_layer(self, session_id: str, knowledge_layer: KnowledgeLayer):
        """Update facts and relationships for a session."""
        session = self.get_session(session_id)
        if not session:
            return

        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    # 0. Guarantee workspace exists
                    ws_row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (session_id,)).fetchone()
                    if not ws_row:
                        now_ts = datetime.now().isoformat()
                        session = self.get_session(session_id)
                        ws_title = session.title if session else "Active Workspace"
                        conn.execute(
                            "INSERT OR REPLACE INTO workspaces (id, title, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (session_id, ws_title, "", now_ts, now_ts)
                        )

                    # Map valid document IDs for this workspace
                    doc_rows = conn.execute("SELECT id, filename FROM documents WHERE workspace_id = ?", (session_id,)).fetchall()
                    valid_doc_map = {r["filename"]: r["id"] for r in doc_rows}

                    # Collect all facts including those embedded in comparisons
                    all_facts_to_save = list(knowledge_layer.facts)
                    saved_fact_ids = set()

                    for c in knowledge_layer.comparisons:
                        if c.fact_a and c.fact_a not in all_facts_to_save:
                            all_facts_to_save.append(c.fact_a)
                        if c.fact_b and c.fact_b not in all_facts_to_save:
                            all_facts_to_save.append(c.fact_b)

                    for f in all_facts_to_save:
                        fname = f.evidence.document_name if f.evidence else "unknown.pdf"
                        doc_id = valid_doc_map.get(fname)
                        if not doc_id:
                            # Register document properly to satisfy foreign key
                            doc_id = f"doc_{hashlib.md5((session_id + fname).encode()).hexdigest()[:12]}"
                            now_ts = datetime.now().isoformat()
                            conn.execute("""
                                INSERT OR IGNORE INTO documents (
                                    id, workspace_id, filename, file_size, file_hash, storage_path,
                                    page_count, uploaded_at, status, summary, tags, blocks_count,
                                    tables_count, figures_count, processed_time
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                doc_id, session_id, fname, 0, doc_id, "", 1, now_ts, "Processed", "", "[]", 0, 0, 0, "Just now"
                            ))
                            valid_doc_map[fname] = doc_id

                        conn.execute("""
                            INSERT OR REPLACE INTO facts (
                                id, document_id, workspace_id, subject, predicate, value,
                                normalized_value, unit, time, scope, confidence,
                                surface_subject, entity_id, canonical_subject,
                                entity_resolution_confidence, entity_type, entity_resolution_status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            f.id, doc_id, session_id, f.subject, f.attribute, f.value,
                            f.normalized_value, f.unit, f.temporal_scope or "", f.context_scope or "", f.confidence,
                            f.surface_subject or f.subject, f.entity_id or "", f.canonical_subject or f.subject,
                            float(f.entity_resolution_confidence if f.entity_resolution_confidence is not None else 1.0),
                            f.entity_type or "unknown", f.entity_resolution_status or ""
                        ))
                        saved_fact_ids.add(f.id)

                        if f.evidence:
                            conn.execute("""
                                INSERT OR REPLACE INTO evidence (
                                    id, fact_id, document_name, page_number, quote, table_citation, image_citation
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                f"ev_{f.id}", f.id, f.evidence.document_name, f.evidence.page_number,
                                f.evidence.verbatim_quote, f.evidence.table_citation, f.evidence.image_citation
                            ))

                    for c in knowledge_layer.comparisons:
                        fa_id = c.fact_a.id if (c.fact_a and c.fact_a.id in saved_fact_ids) else None
                        fb_id = c.fact_b.id if (c.fact_b and c.fact_b.id in saved_fact_ids) else None
                        conn.execute("""
                            INSERT OR REPLACE INTO fact_relationships (
                                id, workspace_id, fact_a_id, fact_b_id, relationship, title,
                                reasoning, reconciliation_factor, confidence
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            c.id, session_id,
                            fa_id, fb_id,
                            c.relationship_type.value, c.title, c.explanation,
                            c.reconciliation_factor, 1.0
                        ))

                    # Persist canonical entities and mentions if present
                    if knowledge_layer.entities:
                        ent_list = list(knowledge_layer.entities.values()) if isinstance(knowledge_layer.entities, dict) else list(knowledge_layer.entities)
                        for ent in ent_list:
                            eid = getattr(ent, "entity_id", ent.get("entity_id") if isinstance(ent, dict) else str(uuid.uuid4()))
                            cname = getattr(ent, "canonical_name", ent.get("canonical_name") if isinstance(ent, dict) else "")
                            etype = getattr(ent, "entity_type", ent.get("entity_type", "unknown") if isinstance(ent, dict) else "unknown")
                            aliases = getattr(ent, "aliases", ent.get("aliases", []) if isinstance(ent, dict) else [])
                            desc = getattr(ent, "description", ent.get("description", "") if isinstance(ent, dict) else "")
                            conf = getattr(ent, "confidence", ent.get("confidence", 1.0) if isinstance(ent, dict) else 1.0)
                            status = getattr(ent, "resolution_status", ent.get("resolution_status", "resolved") if isinstance(ent, dict) else "resolved")
                            sdocs = getattr(ent, "source_documents", ent.get("source_documents", []) if isinstance(ent, dict) else [])

                            conn.execute("""
                                INSERT OR REPLACE INTO entities (
                                    id, workspace_id, canonical_name, entity_type, aliases, description,
                                    confidence, resolution_status, source_documents
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                eid, session_id, cname, etype, json.dumps(aliases), desc,
                                float(conf), str(status), json.dumps(sdocs)
                            ))

                            mentions = getattr(ent, "source_mentions", ent.get("source_mentions", []) if isinstance(ent, dict) else [])
                            for m in mentions:
                                mid = getattr(m, "mention_id", m.get("mention_id") if isinstance(m, dict) else str(uuid.uuid4()))
                                sform = getattr(m, "surface_form", m.get("surface_form", "") if isinstance(m, dict) else "")
                                nform = getattr(m, "normalized_form", m.get("normalized_form", "") if isinstance(m, dict) else "")
                                m_etype = getattr(m, "entity_type", m.get("entity_type", "unknown") if isinstance(m, dict) else "unknown")
                                dname = getattr(m, "document_name", m.get("document_name", "") if isinstance(m, dict) else "")
                                pnum = getattr(m, "page_number", m.get("page_number", 1) if isinstance(m, dict) else 1)
                                ctx = getattr(m, "context_sentence", m.get("context_sentence", "") if isinstance(m, dict) else "")
                                mconf = getattr(m, "confidence", m.get("confidence", 1.0) if isinstance(m, dict) else 1.0)
                                method = getattr(m, "resolution_method", m.get("resolution_method", "deterministic") if isinstance(m, dict) else "deterministic")

                                conn.execute("""
                                    INSERT OR REPLACE INTO entity_mentions (
                                        id, entity_id, workspace_id, surface_form, normalized_form,
                                        entity_type, document_name, page_number, context_sentence,
                                        confidence, resolution_method
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    mid, eid, session_id, sform, nform,
                                    m_etype, dname, pnum, ctx,
                                    float(mconf), str(method)
                                ))

                    conn.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (datetime.now().isoformat(), session_id))

                session.knowledge_layer = knowledge_layer
            finally:
                conn.close()

    def save_entities(self, session_id: str, entities: List[Any]):
        """Persist canonical entities and mentions into SQLite."""
        if not entities:
            return
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    for ent in entities:
                        eid = getattr(ent, "entity_id", ent.get("entity_id") if isinstance(ent, dict) else str(uuid.uuid4()))
                        cname = getattr(ent, "canonical_name", ent.get("canonical_name") if isinstance(ent, dict) else "")
                        etype = getattr(ent, "entity_type", ent.get("entity_type", "unknown") if isinstance(ent, dict) else "unknown")
                        aliases = getattr(ent, "aliases", ent.get("aliases", []) if isinstance(ent, dict) else [])
                        desc = getattr(ent, "description", ent.get("description", "") if isinstance(ent, dict) else "")
                        conf = getattr(ent, "confidence", ent.get("confidence", 1.0) if isinstance(ent, dict) else 1.0)
                        status = getattr(ent, "resolution_status", ent.get("resolution_status", "resolved") if isinstance(ent, dict) else "resolved")
                        sdocs = getattr(ent, "source_documents", ent.get("source_documents", []) if isinstance(ent, dict) else [])

                        conn.execute("""
                            INSERT OR REPLACE INTO entities (
                                id, workspace_id, canonical_name, entity_type, aliases, description,
                                confidence, resolution_status, source_documents
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            eid, session_id, cname, etype, json.dumps(aliases), desc,
                            float(conf), str(status), json.dumps(sdocs)
                        ))

                        mentions = getattr(ent, "source_mentions", ent.get("source_mentions", []) if isinstance(ent, dict) else [])
                        for m in mentions:
                            mid = getattr(m, "mention_id", m.get("mention_id") if isinstance(m, dict) else str(uuid.uuid4()))
                            sform = getattr(m, "surface_form", m.get("surface_form", "") if isinstance(m, dict) else "")
                            nform = getattr(m, "normalized_form", m.get("normalized_form", "") if isinstance(m, dict) else "")
                            m_etype = getattr(m, "entity_type", m.get("entity_type", "unknown") if isinstance(m, dict) else "unknown")
                            dname = getattr(m, "document_name", m.get("document_name", "") if isinstance(m, dict) else "")
                            pnum = getattr(m, "page_number", m.get("page_number", 1) if isinstance(m, dict) else 1)
                            ctx = getattr(m, "context_sentence", m.get("context_sentence", "") if isinstance(m, dict) else "")
                            mconf = getattr(m, "confidence", m.get("confidence", 1.0) if isinstance(m, dict) else 1.0)
                            method = getattr(m, "resolution_method", m.get("resolution_method", "deterministic") if isinstance(m, dict) else "deterministic")

                            conn.execute("""
                                INSERT OR REPLACE INTO entity_mentions (
                                    id, entity_id, workspace_id, surface_form, normalized_form,
                                    entity_type, document_name, page_number, context_sentence,
                                    confidence, resolution_method
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                mid, eid, session_id, sform, nform,
                                m_etype, dname, pnum, ctx,
                                float(mconf), str(method)
                            ))
            finally:
                conn.close()

    def update_document_figures_count(self, session_id: str, filename: str, figures_count: int) -> None:
        """Update the figures count for a document in SQLite and in-memory cache."""
        session = self.get_session(session_id)
        if session:
            for d in session.documents:
                if d.get("filename") == filename:
                    d["figures_count"] = figures_count
                    break

        conn = self._get_conn()
        try:
            with conn:
                conn.execute(
                    "UPDATE documents SET figures_count = ? WHERE workspace_id = ? AND filename = ?",
                    (figures_count, session_id, filename)
                )
        finally:
            conn.close()


default_session_manager = SessionManager()
