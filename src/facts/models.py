"""
Data Models for the Fact Knowledge Layer.

Defines schemas for grounded facts, source evidence, and cross-document relationships.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
import uuid


class RelationshipType(str, Enum):
    CORROBORATION = "corroboration"
    CONTRADICTION = "contradiction"
    RECONCILED = "reconciled"
    EXTRACTION_FAILURE = "extraction_failure"


@dataclass
class Evidence:
    """Grounding metadata pointing to exact source location."""
    document_name: str
    page_number: int
    verbatim_quote: str
    context_snippet: Optional[str] = None
    char_offset: Optional[int] = None
    table_citation: Optional[str] = None
    image_citation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Fact:
    """Represents an extracted semantic or numerical fact with source grounding."""
    id: str = field(default_factory=lambda: f"fact_{uuid.uuid4().hex[:8]}")
    subject: str = ""
    attribute: str = ""
    value: str = ""
    normalized_value: Optional[float] = None
    unit: str = ""
    temporal_scope: Optional[str] = None
    context_scope: Optional[str] = None
    evidence: Optional[Evidence] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.evidence:
            data["evidence"] = self.evidence.to_dict()
        return data


@dataclass
class FactComparison:
    """Represents a relationship between facts across or within documents."""
    id: str = field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:8]}")
    relationship_type: RelationshipType = RelationshipType.CORROBORATION
    title: str = ""
    fact_a: Optional[Fact] = None
    fact_b: Optional[Fact] = None
    explanation: str = ""
    reconciliation_factor: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "relationship_type": self.relationship_type.value,
            "title": self.title,
            "fact_a": self.fact_a.to_dict() if self.fact_a else None,
            "fact_b": self.fact_b.to_dict() if self.fact_b else None,
            "explanation": self.explanation,
            "reconciliation_factor": self.reconciliation_factor
        }


@dataclass
class KnowledgeLayer:
    """The aggregate knowledge graph/store of facts and cross-document reconciliations."""
    documents: List[str] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    comparisons: List[FactComparison] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "documents": self.documents,
            "total_facts": len(self.facts),
            "facts": [f.to_dict() for f in self.facts],
            "total_comparisons": len(self.comparisons),
            "comparisons": [c.to_dict() for c in self.comparisons],
            "statistics": self.statistics
        }
