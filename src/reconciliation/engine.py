"""Domain-agnostic fact reconciliation and comparability engine.

"""

import re
import uuid
import logging
from typing import List, Dict, Optional, Set, Tuple, Any
from collections import defaultdict
from src.facts.models import Fact, FactComparison, RelationshipType, KnowledgeLayer
from src.facts.normalization import resolve_entity_alias, resolve_predicate_similarity

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """Evaluates comparability and resolves relationships between extracted facts."""

    def __init__(self, relative_tolerance: float = 0.05):
        self.tolerance = relative_tolerance

    def reconcile(
        self,
        facts: List[Fact],
        documents: Optional[List[str]] = None,
        entities: Optional[Dict[str, Any]] = None
    ) -> KnowledgeLayer:
        """Reconcile facts dynamically across documents."""
        docs = documents or sorted(list(set(f.evidence.document_name for f in facts if f.evidence)))
        pairs = self._generate_candidate_pairs(facts)
        comparisons: List[FactComparison] = []

        for f_a, f_b in pairs:
            comp = self._evaluate_pairwise_comparability(f_a, f_b)
            if comp:
                comparisons.append(comp)

        # Deduplicate comparisons with matching fact pairs and relationship
        seen_keys: Set[tuple] = set()
        deduped: List[FactComparison] = []
        for c in comparisons:
            pair_key = (
                c.relationship_type,
                c.fact_a.id if c.fact_a else "",
                c.fact_b.id if c.fact_b else "",
                c.title
            )
            if pair_key not in seen_keys:
                seen_keys.add(pair_key)
                deduped.append(c)

        ent_dict = entities or {}
        stats = {
            "total_facts": len(facts),
            "total_documents": len(docs),
            "total_entities": len(ent_dict),
            "corroborations": sum(1 for c in deduped if c.relationship_type == RelationshipType.CORROBORATION),
            "contradictions": sum(1 for c in deduped if c.relationship_type == RelationshipType.CONTRADICTION),
            "reconciled": sum(1 for c in deduped if c.relationship_type == RelationshipType.RECONCILED),
            "extraction_failures_handled": sum(1 for c in deduped if c.relationship_type == RelationshipType.EXTRACTION_FAILURE),
        }

        return KnowledgeLayer(
            documents=docs,
            facts=facts,
            comparisons=deduped,
            entities=ent_dict,
            statistics=stats
        )

    def _generate_candidate_pairs(self, facts: List[Fact]) -> List[Tuple[Fact, Fact]]:
        """Identify candidate pairs sharing canonical entity identity, predicate, or semantic affinity."""
        pairs = []
        n = len(facts)
        if n < 2:
            return pairs

        if n <= 50:
            for i in range(n):
                for j in range(i + 1, n):
                    pairs.append((facts[i], facts[j]))
            return pairs

        clusters = defaultdict(list)
        pred_stop = {
            "consolidated", "standalone", "domestic", "international", "total", "overall",
            "annual", "quarterly", "fiscal", "monthly", "weekly", "yearly", "reported",
            "gross", "net", "adjusted", "core"
        }
        for f in facts:
            if f.entity_id:
                clusters[f"entity_{f.entity_id}"].append(f)

            stem = f.attribute.lower()
            words = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', stem) if w not in pred_stop]
            cluster_key = words[0] if words else stem[:10]
            clusters[f"pred_{cluster_key}"].append(f)

        seen_pairs: Set[tuple] = set()

        for key, cluster_facts in clusters.items():
            k_len = len(cluster_facts)
            for i in range(min(k_len, 25)):
                for j in range(i + 1, min(k_len, 25)):
                    f1 = cluster_facts[i]
                    f2 = cluster_facts[j]
                    pair_id = tuple(sorted([f1.id, f2.id]))
                    if pair_id not in seen_pairs:
                        seen_pairs.add(pair_id)
                        pairs.append((f1, f2))

        return pairs

    def _evaluate_pairwise_comparability(self, f_a: Fact, f_b: Fact) -> Optional[FactComparison]:
        """Construct explicit multi-dimensional comparability decision matrix."""
        # Entity comparability
        if f_a.entity_id and f_b.entity_id:
            if f_a.entity_id == f_b.entity_id:
                if (
                    f_a.entity_resolution_status == "ambiguous"
                    or f_b.entity_resolution_status == "ambiguous"
                    or f_a.entity_resolution_confidence < 0.75
                    or f_b.entity_resolution_confidence < 0.75
                ):
                    entity_match = "POSSIBLE_MATCH"
                else:
                    entity_match = "MATCH"
            else:
                entity_match = "DIFFERENT"
        else:
            entity_match = resolve_entity_alias(f_a.subject, f_b.subject)

        if entity_match == "DIFFERENT":
            return None

        # Predicate comparability
        pred_match = resolve_predicate_similarity(f_a.attribute, f_b.attribute)
        if pred_match == "DIFFERENT":
            return None

        # Unit compatibility
        unit_a = (f_a.unit or "").strip().upper()
        unit_b = (f_b.unit or "").strip().upper()
        if not unit_a or not unit_b:
            unit_match = "UNKNOWN"
        elif unit_a == unit_b:
            unit_match = "COMPATIBLE"
        else:
            unit_match = "INCOMPATIBLE"

        # Temporal compatibility
        time_a = f_a.temporal_scope
        time_b = f_b.temporal_scope
        if not time_a or not time_b:
            time_match = "UNKNOWN"
        elif time_a.strip().upper() == time_b.strip().upper():
            time_match = "SAME"
        else:
            time_match = "DIFFERENT"

        # Contextual scope compatibility
        scope_a = f_a.context_scope
        scope_b = f_b.context_scope
        if not scope_a or not scope_b:
            scope_match = "UNKNOWN"
        elif scope_a.strip().upper() == scope_b.strip().upper():
            scope_match = "SAME"
        else:
            scope_match = "DIFFERENT"

        # Numeric value comparison
        val_a = f_a.normalized_value
        val_b = f_b.normalized_value

        if val_a is None or val_b is None:
            if unit_match == "INCOMPATIBLE":
                return FactComparison(
                    id=f"comp_{uuid.uuid4().hex[:8]}",
                    relationship_type=RelationshipType.EXTRACTION_FAILURE,
                    title=f"Uncertain Comparison: {f_a.attribute} (Incompatible Units)",
                    fact_a=f_a,
                    fact_b=f_b,
                    explanation=(
                        f"Comparability Matrix:\n"
                        f"Entity: {entity_match} | Predicate: {pred_match} | Unit: {unit_match}\n"
                        f"Cannot evaluate numerical equivalence between '{f_a.value}' and '{f_b.value}' "
                        f"due to incompatible unit definitions ('{f_a.unit}' vs '{f_b.unit}')."
                    ),
                    reconciliation_factor="Uncertain: incompatible unit metrics"
                )
            return None

        denom = max(abs(val_a), abs(val_b))
        rel_diff = abs(val_a - val_b) / denom if denom > 0 else 0.0

        if rel_diff <= self.tolerance:
            val_relation = "WITHIN_TOLERANCE"
        else:
            val_relation = "DIVERGENT"

        doc_a = f_a.evidence.document_name if f_a.evidence else "Doc A"
        doc_b = f_b.evidence.document_name if f_b.evidence else "Doc B"
        page_a = f_a.evidence.page_number if f_a.evidence else 0
        page_b = f_b.evidence.page_number if f_b.evidence else 0

        # Skip intra-page identical duplicate citations
        if doc_a == doc_b and page_a == page_b and f_a.value == f_b.value:
            return None

        def _format_entity_label(f: Fact) -> str:
            if f.surface_subject and f.canonical_subject and f.surface_subject != f.canonical_subject:
                return f"'{f.surface_subject}' (canonical: '{f.canonical_subject}')"
            return f"'{f.subject}'"

        ent_desc_a = _format_entity_label(f_a)
        ent_desc_b = _format_entity_label(f_b)

        matrix_repr = (
            f"Comparability Decision Matrix:\n"
            f"- Entity: {entity_match} ({ent_desc_a} vs {ent_desc_b})\n"
            f"- Predicate: {pred_match} ('{f_a.attribute}' vs '{f_b.attribute}')\n"
            f"- Unit: {unit_match} ('{unit_a}' vs '{unit_b}')\n"
            f"- Temporal Scope: {time_match} ('{time_a}' vs '{time_b}')\n"
            f"- Context Scope: {scope_match} ('{scope_a}' vs '{scope_b}')\n"
            f"- Value Relation: {val_relation} (delta = {rel_diff * 100:.2f}%)"
        )

        # Corroboration
        if val_relation == "WITHIN_TOLERANCE" and unit_match in ["COMPATIBLE", "UNKNOWN"]:
            time_str = f" ({time_a})" if time_a else ""
            is_cross = (doc_a != doc_b)
            prefix = "Cross-Document Corroboration" if is_cross else "Consistency Confirmation"
            if entity_match == "POSSIBLE_MATCH":
                prefix = f"Possible {prefix}"
            return FactComparison(
                id=f"comp_{uuid.uuid4().hex[:8]}",
                relationship_type=RelationshipType.CORROBORATION,
                title=f"{prefix}: {f_a.attribute}{time_str}",
                fact_a=f_a,
                fact_b=f_b,
                explanation=(
                    f"Sources independently corroborate '{f_a.attribute}'.\n"
                    f"Source A ({doc_a}, p.{page_a}): '{f_a.value}' (Entity: {ent_desc_a})\n"
                    f"Source B ({doc_b}, p.{page_b}): '{f_b.value}' (Entity: {ent_desc_b})\n"
                    f"Delta is {rel_diff * 100:.2f}%, within tolerance threshold ({self.tolerance * 100:.1f}%).\n\n"
                    f"{matrix_repr}"
                ),
                reconciliation_factor=(
                    "Numerical agreement within configured tolerance across verified source citations."
                    if entity_match == "MATCH"
                    else "Possible agreement subject to uncertain entity identity match."
                )
            )

        # Reconciled by temporal evolution
        if time_match == "DIFFERENT":
            return FactComparison(
                id=f"comp_{uuid.uuid4().hex[:8]}",
                relationship_type=RelationshipType.RECONCILED,
                title=f"Reconciled by Period: {f_a.attribute} ({time_a} vs {time_b})",
                fact_a=f_a,
                fact_b=f_b,
                explanation=(
                    f"Apparent divergence in '{f_a.attribute}' ('{f_a.value}' vs '{f_b.value}') "
                    f"is resolved by progression across temporal periods: '{time_a}' vs '{time_b}'.\n\n"
                    f"{matrix_repr}"
                ),
                reconciliation_factor=f"Temporal period evolution: '{time_a}' -> '{time_b}'"
            )

        # Reconciled by reporting scope
        if scope_match == "DIFFERENT":
            return FactComparison(
                id=f"comp_{uuid.uuid4().hex[:8]}",
                relationship_type=RelationshipType.RECONCILED,
                title=f"Reconciled by Scope: {f_a.attribute} ({scope_a} vs {scope_b})",
                fact_a=f_a,
                fact_b=f_b,
                explanation=(
                    f"Discrepancy in '{f_a.attribute}' between '{f_a.value}' and '{f_b.value}' "
                    f"is explained by differing reporting boundaries: '{scope_a}' vs '{scope_b}'.\n\n"
                    f"{matrix_repr}"
                ),
                reconciliation_factor=f"Context boundary differentiation: '{scope_a}' vs '{scope_b}'"
            )

        # Contradiction
        if (time_match in ["SAME", "UNKNOWN"]) and (scope_match in ["SAME", "UNKNOWN"]) and val_relation == "DIVERGENT":
            if unit_match in ["COMPATIBLE", "UNKNOWN"]:
                is_cross = (doc_a != doc_b)
                prefix = "Cross-Document Contradiction" if is_cross else "Internal Discrepancy"
                if entity_match == "POSSIBLE_MATCH":
                    prefix = f"Potential {prefix}"
                return FactComparison(
                    id=f"comp_{uuid.uuid4().hex[:8]}",
                    relationship_type=RelationshipType.CONTRADICTION,
                    title=f"{prefix}: {f_a.attribute}",
                    fact_a=f_a,
                    fact_b=f_b,
                    explanation=(
                        f"Direct contradiction detected for '{f_a.attribute}'.\n"
                        f"Source A ({doc_a}, p.{page_a}) claims '{f_a.value}' (Entity: {ent_desc_a}), whereas "
                        f"Source B ({doc_b}, p.{page_b}) claims '{f_b.value}' (Entity: {ent_desc_b}).\n"
                        f"Both claims share the same temporal scope ('{time_a or 'unspecified'}') "
                        f"and context scope ('{scope_a or 'unspecified'}'), yielding an irreconcilable difference "
                        f"of {rel_diff * 100:.2f}%.\n\n"
                        f"{matrix_repr}"
                    ),
                    reconciliation_factor=(
                        "Unreconciled contradiction: competing values reported for identical scope and period."
                        if entity_match == "MATCH"
                        else "Potential contradiction subject to uncertain entity identity match."
                    )
                )

        # Extraction failure or uncertain comparison
        return FactComparison(
            id=f"comp_{uuid.uuid4().hex[:8]}",
            relationship_type=RelationshipType.EXTRACTION_FAILURE,
            title=f"Uncertain Comparison: {f_a.attribute}",
            fact_a=f_a,
            fact_b=f_b,
            explanation=(
                f"The system detected related candidate facts but cannot determine a conclusive relationship "
                f"due to unaligned scopes or missing unit definitions.\n\n"
                f"{matrix_repr}"
            ),
            reconciliation_factor="Uncertain relationship: indeterminate scope or unit alignment"
        )
