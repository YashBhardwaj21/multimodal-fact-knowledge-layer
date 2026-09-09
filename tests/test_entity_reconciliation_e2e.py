"""End-to-end integration tests for cross-document entity reconciliation."""

import pytest
from src.facts.models import Fact, Evidence, RelationshipType
from src.facts.entity_resolver import EntityResolver
from src.reconciliation.engine import ReconciliationEngine


def test_cross_document_acronym_reconciliation():
    """Verify acronym entity resolution enables cross-document numerical corroboration."""
    resolver = EntityResolver()
    reconciler = ReconciliationEngine(relative_tolerance=0.05)

    ent_a, dec_a = resolver.resolve_mention(
        surface_form="International Business Machines",
        context_sentence="International Business Machines reported total annual revenue of $60.5 billion.",
        document_name="Doc_A_Annual_Report.pdf",
        page_number=4
    )
    fact_a = Fact(
        id="fact_ibm_long",
        subject=ent_a.canonical_name,
        surface_subject="International Business Machines",
        entity_id=ent_a.entity_id,
        canonical_subject=ent_a.canonical_name,
        entity_resolution_confidence=dec_a.confidence,
        entity_type=ent_a.entity_type,
        attribute="Annual Revenue",
        value="$60.5 billion",
        normalized_value=60_500_000_000.0,
        unit="USD",
        temporal_scope="FY2023",
        evidence=Evidence(
            document_name="Doc_A_Annual_Report.pdf",
            page_number=4,
            verbatim_quote="International Business Machines reported total annual revenue of $60.5 billion."
        )
    )

    ent_b, dec_b = resolver.resolve_mention(
        surface_form="IBM",
        context_sentence="IBM confirmed consolidated full-year revenue stood at $60.5B.",
        document_name="Doc_B_Press_Release.pdf",
        page_number=1
    )
    fact_b = Fact(
        id="fact_ibm_short",
        subject=ent_b.canonical_name,
        surface_subject="IBM",
        entity_id=ent_b.entity_id,
        canonical_subject=ent_b.canonical_name,
        entity_resolution_confidence=dec_b.confidence,
        entity_type=ent_b.entity_type,
        attribute="Revenue",
        value="$60.5B",
        normalized_value=60_500_000_000.0,
        unit="USD",
        temporal_scope="FY2023",
        evidence=Evidence(
            document_name="Doc_B_Press_Release.pdf",
            page_number=1,
            verbatim_quote="IBM confirmed consolidated full-year revenue stood at $60.5B."
        )
    )

    assert ent_a.entity_id == ent_b.entity_id, "Both mentions must link to the same canonical entity ID"
    assert fact_a.entity_id == fact_b.entity_id

    kl = reconciler.reconcile(
        facts=[fact_a, fact_b],
        documents=["Doc_A_Annual_Report.pdf", "Doc_B_Press_Release.pdf"],
        entities=resolver.entities
    )

    assert len(kl.comparisons) == 1, "Should generate exactly 1 cross-document comparison"
    comp = kl.comparisons[0]
    assert comp.relationship_type == RelationshipType.CORROBORATION
    assert "Cross-Document Corroboration" in comp.title
    assert "International Business Machines" in comp.explanation
    assert "IBM" in comp.explanation


def test_adversarial_distinct_entities_not_reconciled():
    """Verify distinct entities with conflicting modifiers are not reconciled across documents."""
    resolver = EntityResolver()
    reconciler = ReconciliationEngine(relative_tolerance=0.05)

    ent_tech, _ = resolver.resolve_mention(
        surface_form="Apple Inc.",
        context_sentence="Apple Inc. reported quarterly revenue of $90 billion from iPhone sales.",
        document_name="Apple_10Q.pdf",
        page_number=2
    )
    fact_tech = Fact(
        id="fact_apple_tech",
        subject=ent_tech.canonical_name,
        surface_subject="Apple Inc.",
        entity_id=ent_tech.entity_id,
        canonical_subject=ent_tech.canonical_name,
        attribute="Revenue",
        value="$90 billion",
        normalized_value=90_000_000_000.0,
        unit="USD",
        temporal_scope="Q3 2024",
        evidence=Evidence(
            document_name="Apple_10Q.pdf",
            page_number=2,
            verbatim_quote="Apple Inc. reported quarterly revenue of $90 billion from iPhone sales."
        )
    )

    ent_records, _ = resolver.resolve_mention(
        surface_form="Apple Records",
        context_sentence="Apple Records reported royalty revenue of $90 million for the year.",
        document_name="Beatles_Music_Report.pdf",
        page_number=1
    )
    fact_records = Fact(
        id="fact_apple_records",
        subject=ent_records.canonical_name,
        surface_subject="Apple Records",
        entity_id=ent_records.entity_id,
        canonical_subject=ent_records.canonical_name,
        attribute="Revenue",
        value="$90 million",
        normalized_value=90_000_000.0,
        unit="USD",
        temporal_scope="Q3 2024",
        evidence=Evidence(
            document_name="Beatles_Music_Report.pdf",
            page_number=1,
            verbatim_quote="Apple Records reported royalty revenue of $90 million for the year."
        )
    )

    assert ent_tech.entity_id != ent_records.entity_id, "Apple Inc. and Apple Records must have different entity IDs"
    assert fact_tech.entity_id != fact_records.entity_id

    kl = reconciler.reconcile(
        facts=[fact_tech, fact_records],
        documents=["Apple_10Q.pdf", "Beatles_Music_Report.pdf"],
        entities=resolver.entities
    )

    assert len(kl.comparisons) == 0, "Facts with different entity IDs must not be reconciled"
