"""Main CLI pipeline for fact extraction and cross-document reconciliation."""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion.pdf_loader import PDFLoader
from src.facts.extractor import FactExtractor
from src.facts.llm_provider import LLMProvider
from src.reconciliation.engine import ReconciliationEngine
from src.facts.models import RelationshipType

sys.stdout.reconfigure(encoding='utf-8')


def run_pipeline(
    input_path: str,
    output_dir: str = "outputs",
    max_pages: int = None,
    llm_backend: str = "auto"
) -> dict:
    target = Path(input_path)
    if not target.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    print("=" * 80)
    print("FACT KNOWLEDGE LAYER PIPELINE")
    print(f"Target: {input_path}")
    print(f"LLM Backend: {llm_backend}")
    if max_pages:
        print(f"Max pages per document: {max_pages}")
    print("=" * 80)

    loader = PDFLoader(max_pages_per_doc=max_pages)
    if target.is_dir():
        docs_dict = loader.load_directory(str(target))
    else:
        docs_dict = {target.name: loader.load_pdf(str(target))}

    total_pages = sum(len(p) for p in docs_dict.values())
    print(f"Loaded {len(docs_dict)} document(s) with {total_pages} total pages")

    llm = LLMProvider(provider_type=llm_backend)
    extractor = FactExtractor(llm_provider=llm)

    all_facts = []
    for doc_name, pages in docs_dict.items():
        doc_facts = extractor.extract_from_pages(pages)
        all_facts.extend(doc_facts)
        print(f"  {doc_name}: {len(doc_facts)} grounded facts")

    print(f"Total facts extracted: {len(all_facts)}")

    reconciler = ReconciliationEngine()
    knowledge_layer = reconciler.reconcile(all_facts, list(docs_dict.keys()))
    stats = knowledge_layer.statistics

    print(f"Discovered {len(knowledge_layer.comparisons)} cross-document relationships:")
    print(f"  Corroborations:            {stats.get('corroborations', 0)}")
    print(f"  Contradictions:            {stats.get('contradictions', 0)}")
    print(f"  Reconciled by context:     {stats.get('reconciled', 0)}")
    print(f"  Failures flagged/handled:  {stats.get('extraction_failures_handled', 0)}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / "knowledge_layer.json"
    summary_path = out_dir / "knowledge_summary.txt"

    kl_data = knowledge_layer.to_dict()
    kl_data["timestamp"] = timestamp
    kl_data["source_path"] = str(input_path)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(kl_data, f, indent=2, ensure_ascii=False)

    print(f"Structured Knowledge Layer: {json_path}")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("FACT KNOWLEDGE LAYER SUMMARY REPORT\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Source: {input_path}\n")
        f.write("=" * 80 + "\n\n")

        f.write("STATISTICS:\n")
        for k, v in stats.items():
            f.write(f"  {k}: {v}\n")
        f.write("\n" + "-" * 80 + "\n")
        f.write("KEY CROSS-DOCUMENT RECONCILIATIONS:\n")
        f.write("-" * 80 + "\n\n")

        for i, c in enumerate(knowledge_layer.comparisons, 1):
            f.write(f"[{i}] {c.title} ({c.relationship_type.value.upper()})\n")
            f.write(f"    Explanation: {c.explanation}\n")
            if c.reconciliation_factor:
                f.write(f"    Resolution:  {c.reconciliation_factor}\n")
            if c.fact_a and c.fact_a.evidence:
                f.write(f"    Source A:    {c.fact_a.evidence.document_name} p.{c.fact_a.evidence.page_number} | \"{c.fact_a.evidence.verbatim_quote}\"\n")
            if c.fact_b and c.fact_b.evidence:
                f.write(f"    Source B:    {c.fact_b.evidence.document_name} p.{c.fact_b.evidence.page_number} | \"{c.fact_b.evidence.verbatim_quote}\"\n")
            f.write("\n")

    print(f"Summary report: {summary_path}")
    return kl_data


def main():
    parser = argparse.ArgumentParser(
        description="Fact Knowledge Layer CLI"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to PDF file or directory"
    )
    parser.add_argument(
        "--output", "-o",
        default="outputs",
        help="Output directory"
    )
    parser.add_argument(
        "--max-pages", "-m",
        type=int,
        default=None,
        help="Maximum pages to process per document"
    )
    parser.add_argument(
        "--llm",
        default="auto",
        choices=["auto", "gemini", "openai", "ollama", "builtin"],
        help="LLM backend"
    )

    args = parser.parse_args()

    input_target = args.input
    if not input_target:
        if Path("data/raw/delhivery").exists():
            input_target = "data/raw/delhivery"
        elif Path("data/raw").exists():
            input_target = "data/raw"
        else:
            parser.print_help()
            sys.exit(1)

    run_pipeline(
        input_path=input_target,
        output_dir=args.output,
        max_pages=args.max_pages,
        llm_backend=args.llm
    )


if __name__ == "__main__":
    main()
