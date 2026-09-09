"""Entity models for domain-agnostic semantic entity resolution."""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class MatchDecision(str, Enum):
    MATCH = "MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    DIFFERENT = "DIFFERENT"
    UNKNOWN = "UNKNOWN"


@dataclass
class EntityMention:
    """A raw or extracted entity mention occurring in source text."""
    mention_id: str = field(default_factory=lambda: f"men_{uuid.uuid4().hex[:8]}")
    surface_form: str = ""
    normalized_form: str = ""
    entity_type: str = "unknown"
    type_confidence: float = 1.0
    document_name: str = ""
    page_number: int = 1
    context_sentence: str = ""
    heading_context: Optional[str] = None
    char_offset: Optional[int] = None
    resolved_entity_id: Optional[str] = None
    resolution_method: str = "unresolved"
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalEntity:
    """A canonical real-world entity with accumulated aliases, mentions, and context."""
    entity_id: str = field(default_factory=lambda: f"ent_{uuid.uuid4().hex[:8]}")
    canonical_name: str = ""
    entity_type: str = "unknown"
    aliases: List[str] = field(default_factory=list)
    source_mentions: List[EntityMention] = field(default_factory=list)
    description: str = ""
    descriptions: List[str] = field(default_factory=list)
    contexts: List[str] = field(default_factory=list)
    source_documents: List[str] = field(default_factory=list)
    confidence: float = 1.0
    resolution_status: str = ResolutionStatus.RESOLVED.value
    embedding: Optional[List[float]] = None

    def add_alias(self, alias: str) -> None:
        if alias and alias not in self.aliases and alias.strip().lower() != self.canonical_name.strip().lower():
            self.aliases.append(alias.strip())

    def add_mention(self, mention: EntityMention) -> None:
        self.source_mentions.append(mention)
        if mention.document_name and mention.document_name not in self.source_documents:
            self.source_documents.append(mention.document_name)
        if mention.context_sentence and mention.context_sentence not in self.contexts:
            self.contexts.append(mention.context_sentence)
            if len(self.contexts) > 10:
                self.contexts.pop(0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "aliases": list(set(self.aliases)),
            "source_mentions": [m.to_dict() for m in self.source_mentions],
            "description": self.description,
            "descriptions": self.descriptions,
            "contexts": self.contexts,
            "source_documents": self.source_documents,
            "confidence": round(self.confidence, 4),
            "resolution_status": self.resolution_status,
        }


@dataclass
class ResolutionDecision:
    """Outcome of scoring a mention against a candidate canonical entity."""
    decision: str = MatchDecision.UNKNOWN.value
    confidence: float = 0.0
    score: float = 0.0
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    scores: Dict[str, float] = field(default_factory=dict)
    reason: str = ""
    method: str = "deterministic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": round(self.confidence, 4),
            "score": round(self.score, 4),
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "reason": self.reason,
            "method": self.method
        }
