"""Comprehensive regression test suite for arbitrary, unseen documents across multiple domains.

Tests:
- Test A: Technology & AI Architecture (accuracy %, latency ms, throughput req/s)
- Test B: Finance & Multi-year Filings (FY2025 vs FY2026 EUR revenue)
- Test C: Science & Chemistry (temperatures °C, sample counts, error rates %)
- Test D: Contradiction Detection across independent documents
- Test E: Contextual Scope Reconciliation (Standalone vs Consolidated)
- Test F: General Non-financial document (Theatre/Education text like Erth Dinosaur Zoo, ensuring zero false financial facts)
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from src.ingestion.pdf_loader import PDFPage
from src.facts.extractor import FactExtractor
from src.reconciliation.engine import ReconciliationEngine
from src.facts.models import RelationshipType


def test_suite_a_technology():
    """Test A: Technology metrics (accuracy %, latency ms, requests count)."""
    extractor = FactExtractor()
    doc_text = (
        "Distributed Neural Model Performance Report.\n"
        "A model achieved 94.6% accuracy across benchmark evaluations.\n"
        "Latency fell to 12.5 ms on edge accelerators.\n"
        "The system processed 2.3 million requests during the peak workload.\n"
    )
    page = PDFPage(
        document_name="Distributed_Neural_Model_Evaluation.pdf",
        page_number=1,
        text=doc_text
    )
    facts = extractor.extract_from_page(page)
    assert len(facts) >= 2, f"Expected at least 2 facts, got {len(facts)}"

    attrs = [f.attribute.lower() for f in facts]
    assert any("accuracy" in a for a in attrs), f"Should extract accuracy, got {attrs}"
    assert any("latency" in a for a in attrs), f"Should extract latency, got {attrs}"

    for f in facts:
        assert f.evidence.verbatim_quote in doc_text, "Evidence quote must be verbatim from doc text"


def test_suite_b_finance_temporal():
    """Test B: Finance multi-year filings (FY2025 vs FY2026 EUR revenue)."""
    extractor = FactExtractor()
    engine = ReconciliationEngine()

    p1 = PDFPage(
        document_name="European_Mobility_FY25.pdf",
        page_number=1,
        text="European Mobility Group Annual Filing. Revenue reached € 12.4 million in FY2025."
    )
    p2 = PDFPage(
        document_name="European_Mobility_FY26.pdf",
        page_number=1,
        text="European Mobility Group Annual Filing. Revenue was € 15.1 million in FY2026."
    )

    f1 = extractor.extract_from_page(p1)
    f2 = extractor.extract_from_page(p2)

    assert len(f1) >= 1
    assert len(f2) >= 1
    assert f1[0].unit == "EUR"
    assert f2[0].unit == "EUR"

    kl = engine.reconcile(f1 + f2)
    assert len(kl.comparisons) >= 1
    # Apparent difference should be reconciled by temporal period progression
    comp = kl.comparisons[0]
    assert comp.relationship_type == RelationshipType.RECONCILED
    assert "Period" in comp.title or "evolution" in comp.reconciliation_factor.lower()


def test_suite_c_science_and_chemistry():
    """Test C: Science metrics (temperature °C, sample count, error rate %)."""
    extractor = FactExtractor()
    doc_text = (
        "Thermodynamic Biomaterial Crystallization Experiment.\n"
        "The sample temperature was 37.2 °C throughout the synthesis stage.\n"
        "The experiment used 120 samples across three test batches.\n"
        "Observed error was 3.4% relative to theoretical models.\n"
    )
    page = PDFPage(
        document_name="Thermodynamic_Synthesis_Study.pdf",
        page_number=1,
        text=doc_text
    )
    facts = extractor.extract_from_page(page)
    assert len(facts) >= 2, f"Expected at least 2 facts, got {len(facts)}"

    units = [f.unit.lower() for f in facts if f.unit]
    attrs = [f.attribute.lower() for f in facts if f.attribute]

    assert any("temperature" in a or "°c" in u for a, u in zip(attrs, units))
    assert any("error" in a or "percentage" in u for a, u in zip(attrs, units))


def test_suite_d_genuine_contradiction():
    """Test D: Two independent documents state the same metric with materially conflicting values."""
    extractor = FactExtractor()
    engine = ReconciliationEngine(relative_tolerance=0.05)

    doc_a = PDFPage(
        document_name="Audit_Report_Alpha.pdf",
        page_number=1,
        text="CloudSys Infrastructure Audit FY26. Total data centers deployed was 450 units in FY26."
    )
    doc_b = PDFPage(
        document_name="Audit_Report_Beta.pdf",
        page_number=1,
        text="CloudSys Infrastructure Audit FY26. Total data centers deployed was 890 units in FY26."
    )

    f_a = extractor.extract_from_page(doc_a)
    f_b = extractor.extract_from_page(doc_b)

    assert len(f_a) >= 1
    assert len(f_b) >= 1

    kl = engine.reconcile(f_a + f_b)
    contradictions = [c for c in kl.comparisons if c.relationship_type == RelationshipType.CONTRADICTION]
    assert len(contradictions) >= 1, f"Expected contradiction between 450 and 890 units, got {kl.comparisons}"
    assert "Contradiction" in contradictions[0].title


def test_suite_e_contextual_scope_reconciliation():
    """Test E: Same metric reported for different scopes (Consolidated vs Standalone)."""
    extractor = FactExtractor()
    engine = ReconciliationEngine()

    p_consol = PDFPage(
        document_name="GlobalLogistics_Filing.pdf",
        page_number=1,
        text="Global Logistics Corporation FY24. In FY24, consolidated revenue stood at $ 850 million."
    )
    p_stand = PDFPage(
        document_name="GlobalLogistics_Filing.pdf",
        page_number=2,
        text="Global Logistics Corporation FY24. In FY24, standalone revenue stood at $ 420 million."
    )

    f_consol = extractor.extract_from_page(p_consol)
    f_stand = extractor.extract_from_page(p_stand)

    assert len(f_consol) >= 1
    assert len(f_stand) >= 1
    assert f_consol[0].context_scope == "Consolidated"
    assert f_stand[0].context_scope == "Standalone"

    kl = engine.reconcile(f_consol + f_stand)
    reconciled = [c for c in kl.comparisons if c.relationship_type == RelationshipType.RECONCILED]
    assert len(reconciled) >= 1, f"Expected scope reconciliation, got {kl.comparisons}"
    assert "Scope" in reconciled[0].title or "boundary" in reconciled[0].reconciliation_factor.lower()


def test_suite_f_non_financial_theatre_guide():
    """Test F: General arbitrary text (Erth Dinosaur Zoo Guide) MUST NOT emit spurious 'Financial Metric' facts."""
    extractor = FactExtractor()
    theatre_text = (
        "Erth Dinosaur Zoo - Resource Guide 2026.\n"
        "Employing sophisticated design and electronics, these giants are brought to life by skilled performers "
        "and puppeteers, made all the more real through the magic of theatre.\n"
        "Giant puppetry, stiltwalkers, inflatable environments, aerial and flying creatures: Erth is all these things, and more.\n"
        "INTRODUCTION TO THE TIME OF DINOSAURS 4.\n"
        "These two land masses also began to break up, and over millions of years they split into smaller continents each with.\n"
    )
    page = PDFPage(
        document_name="Erth Dinosaur Zoo Resource Guide2.pdf",
        page_number=3,
        text=theatre_text
    )
    facts = extractor.extract_from_page(page)

    # CRITICAL: Absolutely NO false "Financial Metric", "rs ,", or "RS 4" should be generated!
    for f in facts:
        assert f.attribute != "Financial Metric", f"Must NEVER default to 'Financial Metric', got: {f}"
        assert f.value.strip().lower() not in ["rs ,", "rs 4", "rs,"], f"Spurious 'rs' artifact detected: {f}"
        assert f.unit != "INR", f"Must not misinterpret normal English words as INR currency: {f}"
