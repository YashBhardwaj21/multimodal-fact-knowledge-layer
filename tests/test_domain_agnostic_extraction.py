import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from src.ingestion.pdf_loader import PDFPage
from src.facts.extractor import FactExtractor
from src.reconciliation.engine import ReconciliationEngine
from src.facts.models import Fact, RelationshipType

def test_tech_document_extraction():
    extractor = FactExtractor()
    doc_text = (
        "CloudAI Distributed Architecture Whitepaper 2026.\n"
        "In FY26, the cluster achieved an uptime of 99.99% and sustained 45,000 active nodes.\n"
        "Total infrastructure expenditure reached $14.2 million.\n"
        "Mean inference latency was measured at 12.5 ms per transaction.\n"
        "Network throughput reached 450 req/s across global regions.\n"
    )
    
    page = PDFPage(
        document_name="CloudAI Architecture Benchmark.pdf",
        page_number=1,
        text=doc_text
    )
    facts = extractor.extract_from_page(page)
    
    assert len(facts) >= 3, f"Expected at least 3 facts, got {len(facts)}"
    
    # Check attributes and units
    units = [f.unit.lower() for f in facts if f.unit]
    attrs = [f.attribute.lower() for f in facts if f.attribute]
    
    # Check that we extracted currencies, percentages, and unit metrics
    has_cost = any("expenditure" in a or "$" in f.value or "usd" in f.unit.lower() for a, f in zip(attrs, facts))
    has_pct = any("percent" in u or "%" in u for u in units)
    
    assert has_cost, f"Should dynamically extract expenditure fact, got attrs: {attrs}"
    assert has_pct, f"Should dynamically extract percentage metric, got units: {units}"
    
    # Verify exact quotes are verbatim extracts from the document
    for f in facts:
        assert f.evidence.verbatim_quote in doc_text, f"Quote '{f.evidence.verbatim_quote}' must be verbatim from doc"
        assert f.subject.lower() == "cloudai architecture benchmark"

def test_medical_document_extraction():
    extractor = FactExtractor()
    doc_text = (
        "Clinical Trial Summary Report: Phase III Oncology.\n"
        "In 2025, overall patient response rate was 78.4% across 1,200 subjects.\n"
        "Median progression-free survival improved to 14.8 months.\n"
        "Treatment group experienced adverse events in 4.2% of cases.\n"
    )
    
    page = PDFPage(
        document_name="Oncology_Phase3_Trial_Summary.pdf",
        page_number=2,
        text=doc_text
    )
    facts = extractor.extract_from_page(page)
    
    assert len(facts) >= 2, f"Expected at least 2 facts, got {len(facts)}"
    units = [f.unit.lower() for f in facts if f.unit]
    assert any("percent" in u or "month" in u for u in units), f"Should extract percentage or months units, got {units}"

def test_dynamic_reconciliation_temporal_and_scope():
    extractor = FactExtractor()
    engine = ReconciliationEngine()
    
    p1 = PDFPage(
        document_name="Logistics_FY23.pdf",
        page_number=1,
        text="Global Logistics Annual Filing. In FY23, total consolidated revenue was $500 million."
    )
    p2 = PDFPage(
        document_name="Logistics_FY24.pdf",
        page_number=1,
        text="Global Logistics Annual Filing. In FY24, total consolidated revenue was $650 million. In FY24, standalone revenue was $400 million."
    )
    
    f1 = extractor.extract_from_page(p1)
    f2 = extractor.extract_from_page(p2)
    
    all_facts = f1 + f2
    kl = engine.reconcile(all_facts)
    
    # Check that reconciliation ran dynamically without errors
    assert len(kl.facts) >= 3
    assert len(kl.comparisons) >= 1
    rel_types = [c.relationship_type for c in kl.comparisons]
    assert RelationshipType.RECONCILED in rel_types or RelationshipType.CORROBORATION in rel_types
