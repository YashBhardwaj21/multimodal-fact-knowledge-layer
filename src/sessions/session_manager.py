"""Session and workspace manager with zero-knowledge multi-tenant isolation."""

import os
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from src.storage.object_store import ObjectStore, default_object_store
from src.facts.models import KnowledgeLayer, Fact, FactComparison, RelationshipType

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
        created_at: Optional[str] = None
    ):
        self.id = session_id
        self.title = title
        self.description = description
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = self.created_at
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


class SessionManager:
    """Registry and controller for isolated chat workspaces."""

    def __init__(self, object_store: Optional[ObjectStore] = None):
        self.object_store = object_store or default_object_store
        self.sessions: Dict[str, WorkspaceSession] = {}
        self._init_default_sessions()

    def _init_default_sessions(self):
        delhivery_session = WorkspaceSession(
            session_id="delhivery_financial_intel",
            title="Delhivery Financial & Operational Intelligence",
            description="Multi-document analysis across FY24 Annual Report, Prospectus, and Q4 Earnings Presentation."
        )
        delhivery_session.documents = [
            {
                "doc_id": "doc_delhivery_ar_fy24",
                "filename": "02-delhivery-annual-report-fy24-excerpt.pdf",
                "title": "Delhivery Annual Report FY24",
                "pages_count": 22,
                "blocks_count": 184,
                "tables_count": 8,
                "figures_count": 14,
                "summary": "Audited standalone and consolidated statutory financial statements and logistics network disclosures.",
                "tags": ["Annual Report", "Financials", "Consolidated"],
                "status": "Processed",
                "processed_time": "2 hours ago"
            },
            {
                "doc_id": "doc_delhivery_presentation_q4",
                "filename": "03-delhivery-q4-fy24-earnings-presentation.pdf",
                "title": "Delhivery Q4 FY24 Earnings Presentation",
                "pages_count": 24,
                "blocks_count": 142,
                "tables_count": 12,
                "figures_count": 28,
                "summary": "Q4 & Full Year FY24 investor deck summarizing service revenues, EBITDA margins, and volume highlights.",
                "tags": ["Investor Deck", "Q4 FY24", "EBITDA"],
                "status": "Processed",
                "processed_time": "1 hour ago"
            },
            {
                "doc_id": "doc_delhivery_prospectus_2022",
                "filename": "01-delhivery-prospectus-2022-excerpt.pdf",
                "title": "Delhivery Initial Public Offering Prospectus",
                "pages_count": 44,
                "blocks_count": 280,
                "tables_count": 15,
                "figures_count": 12,
                "summary": "Statutory IPO red herring prospectus detailing historic express parcel network expansion.",
                "tags": ["Prospectus", "Network", "SEBI"],
                "status": "Processed",
                "processed_time": "3 hours ago"
            }
        ]
        self.sessions[delhivery_session.id] = delhivery_session

        ai_session = WorkspaceSession(
            session_id="transformer_research_workspace",
            title="Transformer Architecture & Foundational Models",
            description="Comparative analysis of foundational NLP architectures, tokenization, and self-attention."
        )
        ai_session.documents = [
            {
                "doc_id": "doc_attention_paper",
                "filename": "Attention-Is-All-You-Need.pdf",
                "title": "Attention Is All You Need",
                "pages_count": 15,
                "blocks_count": 506,
                "tables_count": 6,
                "figures_count": 76,
                "summary": "The original Transformer paper introducing multi-head self-attention mechanism.",
                "tags": ["NLP", "Transformers", "Attention"],
                "status": "Processed",
                "processed_time": "Just now"
            }
        ]
        self.sessions[ai_session.id] = ai_session

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.sessions.values()]

    def get_session(self, session_id: str, include_knowledge: bool = False) -> Optional[WorkspaceSession]:
        return self.sessions.get(session_id)

    def create_session(self, title: str, description: str = "") -> WorkspaceSession:
        new_id = f"workspace_{uuid.uuid4().hex[:8]}"
        session = WorkspaceSession(session_id=new_id, title=title, description=description)
        self.sessions[new_id] = session
        return session

    def rename_session(self, session_id: str, new_title: str) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.title = new_title.strip()
        session.updated_at = datetime.now().isoformat()
        return True

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.object_store.delete_session_storage(session_id)
            return True
        return False

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
        session.messages.append(msg)
        session.updated_at = datetime.now().isoformat()
        return msg


default_session_manager = SessionManager()
