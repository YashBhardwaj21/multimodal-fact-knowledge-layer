"""Unit and adversarial test suite for domain-agnostic semantic entity resolution."""

import pytest
import time
from typing import List, Dict, Any

from src.facts.entity_resolver import (
    EntityResolver,
    normalize_surface_form,
    extract_initialism,
    detect_contextual_entity_type,
    evaluate_type_compatibility
)
from src.facts.entity_models import MatchDecision, ResolutionStatus


# Normalization and primitive unit tests

def test_normalization_legal_suffixes():
    cases = [
        ("Acme Corp.", "acme"),
        ("ACME CORPORATION", "acme"),
        ("Acme Corporation", "acme"),
        ("Acme Inc.", "acme"),
        ("Acme Incorporated", "acme"),
        ("Acme Ltd.", "acme"),
        ("Acme Limited", "acme"),
        ("Acme LLC", "acme"),
        ("Acme Co.", "acme"),
    ]
    for raw, expected in cases:
        assert normalize_surface_form(raw) == expected, f"Failed for {raw}: got {normalize_surface_form(raw)}"


def test_normalization_punctuation_and_unicode():
    assert normalize_surface_form("U.S.A.") == "usa"
    assert normalize_surface_form("Apple's") == "apple"
    assert normalize_surface_form("L’Oréal") == "l oreal" or "loreal" in normalize_surface_form("L’Oréal")


def test_initialism_extraction():
    assert extract_initialism("International Business Machines") == "IBM"
    assert extract_initialism("Massachusetts Institute of Technology") == "MIT"
    assert extract_initialism("National Aeronautics and Space Administration") == "NASA"
    assert extract_initialism("United States") == "US"


def test_contextual_type_detection():
    t_comp, conf_comp = detect_contextual_entity_type(
        "Novartis",
        "Novartis, a multinational pharmaceutical company, announced clinical trials."
    )
    assert t_comp == "company"
    assert conf_comp >= 0.85

    t_inst, conf_inst = detect_contextual_entity_type(
        "Oxford",
        "Oxford is a collegiate research university in England."
    )
    assert t_inst == "institution"
    assert conf_inst >= 0.85

    t_mod, conf_mod = detect_contextual_entity_type(
        "GPT-4",
        "GPT-4 is a large multimodal language model developed by researchers."
    )
    assert t_mod == "model"


def test_type_compatibility_scoring():
    assert evaluate_type_compatibility("company", "company") == 1.0
    assert evaluate_type_compatibility("company", "organization") >= 0.8
    assert evaluate_type_compatibility("technology", "model") >= 0.8
    assert evaluate_type_compatibility("person", "company") <= 0.1
    assert evaluate_type_compatibility("location", "company") <= 0.1
    assert evaluate_type_compatibility("unknown", "company") >= 0.8


# Adversarial matching and false-merge safeguards

def test_acronym_positive_match():
    resolver = EntityResolver()
    e1, d1 = resolver.resolve_mention(
        "International Business Machines",
        context_sentence="International Business Machines is an enterprise technology provider."
    )
    e2, d2 = resolver.resolve_mention(
        "IBM",
        context_sentence="IBM published third quarter financial earnings."
    )
    assert e1.entity_id == e2.entity_id, "IBM should resolve to International Business Machines"
    assert d2.decision == MatchDecision.MATCH.value
    assert d2.confidence >= 0.80


def test_university_permutation_match():
    resolver = EntityResolver()
    e1, _ = resolver.resolve_mention(
        "Cambridge University",
        context_sentence="Cambridge University is an ancient collegiate research institution.",
        document_name="doc_a.pdf"
    )
    e2, d2 = resolver.resolve_mention(
        "University of Cambridge",
        context_sentence="University of Cambridge granted degrees in mathematics.",
        document_name="doc_b.pdf"
    )
    assert e1.entity_id == e2.entity_id, "Cambridge University must resolve to University of Cambridge"
    assert d2.decision == MatchDecision.MATCH.value


def test_apple_inc_vs_apple_records_false_merge_prevented():
    """Verify distinct entities with conflicting modifiers are not merged."""
    resolver = EntityResolver()
    e_tech, _ = resolver.resolve_mention(
        "Apple Inc.",
        context_sentence="Apple Inc. designs consumer electronics, software, and smartphones."
    )
    e_music, d_music = resolver.resolve_mention(
        "Apple Records",
        context_sentence="Apple Records is a record label founded by the Beatles in 1968."
    )
    assert e_tech.entity_id != e_music.entity_id, "Apple Inc. and Apple Records must NOT be merged!"


def test_amazon_vs_amazon_web_services_prevented():
    """Verify Amazon and Amazon Web Services remain distinct entities."""
    resolver = EntityResolver()
    e_amz, _ = resolver.resolve_mention(
        "Amazon",
        context_sentence="Amazon began as an online marketplace for books."
    )
    e_aws, d_aws = resolver.resolve_mention(
        "Amazon Web Services",
        context_sentence="Amazon Web Services provides on-demand cloud computing platforms."
    )
    assert e_amz.entity_id != e_aws.entity_id, "Amazon and Amazon Web Services must remain distinct!"


def test_coreference_resolution():
    resolver = EntityResolver()
    e1, _ = resolver.resolve_mention(
        "Tesla",
        context_sentence="Tesla manufactures electric vehicles and solar roof systems.",
        document_name="ev_report.pdf"
    )
    e_coref, d_coref = resolver.resolve_mention(
        "the company",
        context_sentence="the company delivered 400,000 vehicles in the fourth quarter.",
        document_name="ev_report.pdf"
    )
    assert e_coref.entity_id == e1.entity_id, "Generic 'the company' should corefer to the preceding company in the same document"
    assert d_coref.decision == MatchDecision.MATCH.value


def test_domain_agnosticity():
    """Verify resolver operates across unrelated domains without hardcoded rules."""
    resolver = EntityResolver()
    domains = [
        ("Pfizer Inc.", "Pfizer Inc. developed an mRNA vaccine for COVID-19.", "Pfizer", "Pfizer expanded drug manufacturing facilities."),
        ("James Webb Space Telescope", "The James Webb Space Telescope conducted deep infrared sky surveys.", "JWST", "JWST observed early galaxy formations."),
        ("European Central Bank", "The European Central Bank sets monetary policy for the euro zone.", "ECB", "ECB adjusted benchmark interest rates.")
    ]
    for long_name, ctx1, short_name, ctx2 in domains:
        e1, _ = resolver.resolve_mention(long_name, ctx1)
        e2, d2 = resolver.resolve_mention(short_name, ctx2)
        assert e1.entity_id == e2.entity_id, f"Failed domain-agnostic match for {short_name} <-> {long_name}"
        assert d2.decision == MatchDecision.MATCH.value


# Benchmark evaluation dataset

BENCHMARK_CASES = [
    # Positive Matches
    {
        "mention_a": "Microsoft Corporation",
        "context_a": "Microsoft Corporation develops cloud computing and productivity software.",
        "mention_b": "Microsoft",
        "context_b": "Microsoft published operating margins for the fiscal quarter.",
        "expected": "MATCH"
    },
    {
        "mention_a": "Massachusetts Institute of Technology",
        "context_a": "Massachusetts Institute of Technology researchers engineered a microfluidic device.",
        "mention_b": "MIT",
        "context_b": "MIT reported discoveries in quantum physics.",
        "expected": "MATCH"
    },
    {
        "mention_a": "Harvard University",
        "context_a": "Harvard University is a private Ivy League research university in Cambridge.",
        "mention_b": "President and Fellows of Harvard College",
        "context_b": "The President and Fellows of Harvard College oversee university endowment assets.",
        "expected": "POSSIBLE_MATCH"
    },
    {
        "mention_a": "United States of America",
        "context_a": "The United States of America signed a bilateral trade agreement.",
        "mention_b": "USA",
        "context_b": "USA delegates attended the global economic summit.",
        "expected": "MATCH"
    },
    {
        "mention_a": "World Health Organization",
        "context_a": "The World Health Organization issued international clinical guidance.",
        "mention_b": "WHO",
        "context_b": "WHO declared an end to the public health emergency.",
        "expected": "MATCH"
    },
    # Negative Matches (Adversarial False Merges to Reject)
    {
        "mention_a": "Apple Inc.",
        "context_a": "Apple Inc. produces the iPhone and iPad consumer hardware.",
        "mention_b": "Apple Records",
        "context_b": "Apple Records released remastered vinyl albums by the Beatles.",
        "expected": "DIFFERENT"
    },
    {
        "mention_a": "Amazon",
        "context_a": "Amazon operates retail fulfilment centers worldwide.",
        "mention_b": "Amazon Web Services",
        "context_b": "Amazon Web Services launched serverless cloud compute instances.",
        "expected": "DIFFERENT"
    },
    {
        "mention_a": "Tesla Motors",
        "context_a": "Tesla Motors produces electric sedans and batteries.",
        "mention_b": "Nikola Tesla",
        "context_b": "Nikola Tesla was a 19th century electrical engineer and inventor.",
        "expected": "DIFFERENT"
    },
    {
        "mention_a": "Columbia University",
        "context_a": "Columbia University is an academic institution in New York City.",
        "mention_b": "Columbia Sportswear",
        "context_b": "Columbia Sportswear manufactures outdoor jackets and boots.",
        "expected": "DIFFERENT"
    },
    {
        "mention_a": "Google LLC",
        "context_a": "Google LLC operates an internet search engine and Android OS.",
        "mention_b": "Meta Platforms",
        "context_b": "Meta Platforms builds social networks and virtual reality headsets.",
        "expected": "DIFFERENT"
    },
    # Ambiguous Cases (Abstention)
    {
        "mention_a": "Delta",
        "context_a": "Delta announced expanded flight routes between Atlanta and London.",
        "mention_b": "Delta",
        "context_b": "Delta variant transmissions increased rapidly across pediatric clinics.",
        "expected": "DIFFERENT"
    }
]


def test_benchmark_metrics_and_transparency_reporting():
    """Evaluate benchmark dataset, print scores, and verify accuracy metrics."""
    resolver = EntityResolver()
    tp, fp, tn, fn = 0, 0, 0, 0
    abstained = 0
    total = len(BENCHMARK_CASES)

    print("\n" + "=" * 90)
    print("ENTITY RESOLUTION TRANSPARENT SCORE REPORT")
    print("=" * 90)

    t_start = time.perf_counter()

    for idx, case in enumerate(BENCHMARK_CASES, start=1):
        resolver.clear()
        ent_a, dec_a = resolver.resolve_mention(case["mention_a"], case["context_a"], document_name="doc_a.pdf")
        ent_b, dec_b = resolver.resolve_mention(case["mention_b"], case["context_b"], document_name="doc_b.pdf")

        actual_match = (ent_a.entity_id == ent_b.entity_id)
        decision = dec_b.decision
        expected = case["expected"]

        scores = dec_b.scores
        print(f"\n[Case {idx}]")
        print(f"Mention A: '{case['mention_a']}' | Context: '{case['context_a'][:60]}...'")
        print(f"Candidate B: '{case['mention_b']}' | Context: '{case['context_b'][:60]}...'")
        print(f"Scores -> Lexical: {scores.get('lexical', 0.0):.2f} | Semantic: {scores.get('semantic', 0.0):.2f} | Type: {scores.get('type_compat', 0.0):.2f} | Acronym: {scores.get('acronym', 0.0):.2f} | Modifier Penalty: {scores.get('modifier_penalty', 0.0):.2f}")
        print(f"Final Score: {dec_b.score:.3f} | Confidence: {dec_b.confidence:.3f} | Decision: {decision} (Expected: {expected})")
        print(f"Reason: {dec_b.reason}")

        if decision in [MatchDecision.POSSIBLE_MATCH.value, MatchDecision.UNKNOWN.value]:
            abstained += 1

        if expected == "MATCH":
            if actual_match:
                tp += 1
            else:
                fn += 1
        elif expected == "DIFFERENT":
            if not actual_match:
                tn += 1
            else:
                fp += 1
        elif expected == "POSSIBLE_MATCH":
            if not actual_match:
                tn += 1
            else:
                tp += 1

    total_time = time.perf_counter() - t_start
    avg_latency_ms = (total_time / (total * 2)) * 1000

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    false_merge_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    false_split_rate = fn / (tp + fn) if (tp + fn) > 0 else 0.0
    abstention_rate = abstained / total

    print("\n" + "=" * 90)
    print("BENCHMARK EVALUATION METRICS")
    print("=" * 90)
    print(f"Total Benchmark Pairs: {total}")
    print(f"True Positives: {tp} | True Negatives: {tn}")
    print(f"False Merges (FP): {fp} | False Splits (FN): {fn}")
    print(f"Precision:         {precision * 100:.2f}%")
    print(f"Recall:            {recall * 100:.2f}%")
    print(f"F1 Score:          {f1 * 100:.2f}%")
    print(f"False Merge Rate:  {false_merge_rate * 100:.2f}%")
    print(f"False Split Rate:  {false_split_rate * 100:.2f}%")
    print(f"Abstention Rate:   {abstention_rate * 100:.2f}%")
    print(f"Average Latency:   {avg_latency_ms:.2f} ms per mention")
    print("=" * 90)

    assert false_merge_rate == 0.0, f"False merge rate must be 0%; got {false_merge_rate}"
    assert precision >= 0.90, f"Precision must be >= 90%; got {precision}"
    assert f1 >= 0.85, f"F1 score must be >= 85%; got {f1}"
