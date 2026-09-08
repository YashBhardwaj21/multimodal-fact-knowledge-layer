"""Demonstration script for cross-document fact extraction and reconciliation."""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion.pdf_loader import PDFLoader
from src.facts.extractor import FactExtractor
from src.reconciliation.engine import ReconciliationEngine
from src.facts.models import RelationshipType

sys.stdout.reconfigure(encoding='utf-8')


def run_demo(data_dir: str = "data/raw/delhivery"):
    print("=" * 80)
    print("FACT KNOWLEDGE LAYER DEMONSTRATION")
    print(f"Target Directory: {data_dir}")
    print("=" * 80)

    loader = PDFLoader()
    docs_pages = loader.load_directory(data_dir)
    total_pages = sum(len(pages) for pages in docs_pages.values())
    print(f"Ingested {len(docs_pages)} documents ({total_pages} total pages)")
    for doc_name, pages in docs_pages.items():
        print(f"  {doc_name}: {len(pages)} pages")

    extractor = FactExtractor()
    all_facts = []
    for doc_name, pages in docs_pages.items():
        doc_facts = extractor.extract_from_pages(pages)
        all_facts.extend(doc_facts)
        print(f"  {doc_name}: {len(doc_facts)} grounded facts extracted")

    print(f"Total facts in Knowledge Layer: {len(all_facts)}")

    reconciler = ReconciliationEngine()
    knowledge_layer = reconciler.reconcile(all_facts, list(docs_pages.keys()))
    stats = knowledge_layer.statistics

    print("Reconciliation complete:")
    print(f"  Corroborations: {stats.get('corroborations', 0)}")
    print(f"  Contradictions: {stats.get('contradictions', 0)}")
    print(f"  Reconciled by context: {stats.get('reconciled', 0)}")
    print(f"  Extraction failures handled: {stats.get('extraction_failures_handled', 0)}")

    categories = [
        (RelationshipType.CORROBORATION, "CORROBORATION ACROSS DOCUMENTS"),
        (RelationshipType.CONTRADICTION, "GENUINE CONTRADICTION"),
        (RelationshipType.RECONCILED, "APPARENT CONTRADICTION RECONCILED BY CONTEXT"),
        (RelationshipType.EXTRACTION_FAILURE, "EXTRACTION / REASONING FAILURE HANDLED")
    ]

    for rel_type, header in categories:
        print(f"\n--- {header} ---")
        matches = [c for c in knowledge_layer.comparisons if c.relationship_type == rel_type]
        if not matches:
            print("  (None found)")
            continue

        for i, comp in enumerate(matches, 1):
            print(f"\n[{i}] {comp.title}")
            print(f"Explanation: {comp.explanation}")
            if comp.reconciliation_factor:
                print(f"Resolution Factor: {comp.reconciliation_factor}")

            if comp.fact_a and comp.fact_a.evidence:
                ea = comp.fact_a.evidence
                print(f"  [Evidence A] {ea.document_name} (Page {ea.page_number}):")
                print(f"    Value: {comp.fact_a.value} | Scope: {comp.fact_a.context_scope} | Period: {comp.fact_a.temporal_scope}")
                print(f"    Quote: \"{ea.verbatim_quote}\"")

            if comp.fact_b and comp.fact_b.evidence:
                eb = comp.fact_b.evidence
                print(f"  [Evidence B] {eb.document_name} (Page {eb.page_number}):")
                print(f"    Value: {comp.fact_b.value} | Scope: {comp.fact_b.context_scope} | Period: {comp.fact_b.temporal_scope}")
                print(f"    Quote: \"{eb.verbatim_quote}\"")

    output_path = Path("outputs/knowledge_layer.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(knowledge_layer.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"\nSaved structured knowledge layer to: {output_path}")

    return knowledge_layer


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/raw/delhivery"
    run_demo(target)
