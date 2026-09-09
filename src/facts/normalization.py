"""Generic normalization, scoping, and entity/predicate resolution utilities.

Completely domain-independent: operates without any hardcoded document, company, or schema assumptions.
"""

import re
from pathlib import Path
from typing import Optional, Tuple, Set


def derive_document_subject(doc_name: str) -> str:
    """Derive clean document subject from filename or title without hardcoded names."""
    stem = Path(doc_name).stem
    # Replace separators with spaces
    cleaned = re.sub(r'[-_.]+', ' ', stem)
    # Remove generic trailing version numbers or hashes
    cleaned = re.sub(r'\b(?:v\d+|rev\d+|\d{6,})\b', '', cleaned, flags=re.IGNORECASE)
    # Remove file extension artifacts
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned.title() or "Document"


def derive_page_subject(page_text: str, doc_name: str) -> str:
    """Infer prominent subject entity of a specific page or fallback to document subject."""
    if not page_text or len(page_text.strip()) < 10:
        return derive_document_subject(doc_name)

    # 1. Look for entity title right before FACT FILE / PROFILE / OVERVIEW / SPECIFICATIONS / SUMMARY
    m_ff = re.search(r'(?m)^([A-Z][a-zA-Z0-9\s\'-]{2,30})\s*\n\s*(?:FACT FILE|PROFILE|OVERVIEW|SPECIFICATIONS|SUMMARY)\b', page_text, re.IGNORECASE)
    if m_ff:
        subj = m_ff.group(1).strip()
        if len(subj) >= 3 and not any(w in subj.lower() for w in ["page", "chapter", "table"]):
            return subj.title()

    # 2. Look for dominant entity title in the first prominent heading lines
    first_lines = [l.strip() for l in page_text.split("\n")[:4] if len(l.strip()) >= 3]
    for line in first_lines:
        if len(line) <= 30 and not line.endswith((".", "?", "!", ",", ";", ":")):
            lower_l = line.lower()
            if not any(w in lower_l for w in ["page", "chapter", "section", "table of contents", "introduction", "study guide", "guide", "click here", "did you know"]):
                return line.title()

    # 3. Check for subject definition sentence at top: "X is a/an ..." or "X was a/an ..."
    m_def = re.search(r'^([A-Z][a-zA-Z\s\'-]{2,30}?)\s+(?:is|was|are|were)\s+(?:a|an|the)\b', page_text.strip())
    if m_def:
        subj = m_def.group(1).strip()
        if len(subj) >= 3 and not any(w in subj.lower() for w in ["this", "there", "these", "it", "they"]):
            return subj.title()

    return derive_document_subject(doc_name)


def normalize_currency(sym_or_code: str) -> str:
    """Convert currency symbol or code to standard ISO 4217 code."""
    if not sym_or_code:
        return ""
    s = sym_or_code.strip().upper().rstrip(".")
    mapping = {
        "$": "USD",
        "USD": "USD",
        "US$": "USD",
        "€": "EUR",
        "EUR": "EUR",
        "£": "GBP",
        "GBP": "GBP",
        "₹": "INR",
        "INR": "INR",
        "RS": "INR",
        "RUP": "INR",
        "¥": "JPY",
        "JPY": "JPY",
        "CNY": "CNY",
        "RMB": "CNY",
        "A$": "AUD",
        "AUD": "AUD",
        "C$": "CAD",
        "CAD": "CAD",
        "CHF": "CHF",
    }
    return mapping.get(s, s)


def parse_numeric_and_scale(val_str: str, scale_str: str = "") -> Tuple[Optional[float], bool]:
    """Parse numeric string with optional scale multiplier and approximation flag.
    
    Returns:
        (normalized_float, is_approximate)
    """
    if not val_str:
        return None, False

    raw = val_str.strip()
    is_approx = bool(re.search(r'\b(approx|approximately|nearly|over|under|around|about|estimated|at least|up to|>|<|~)\b', raw, re.IGNORECASE))
    
    # Handle accounting parenthetical negatives: (1,234.50) -> -1234.50
    is_negative = False
    if raw.startswith("(") and raw.endswith(")"):
        is_negative = True
        raw = raw[1:-1]
    elif raw.startswith("-"):
        is_negative = True
        raw = raw[1:]

    # Remove commas, currency symbols, and non-numeric fluff
    clean_num = re.sub(r'[^\d.]', '', raw)
    if not clean_num:
        return None, is_approx

    try:
        num = float(clean_num)
    except ValueError:
        return None, is_approx

    if is_negative:
        num = -num

    scale_lower = (scale_str or "").lower().strip()
    multipliers = {
        "trillion": 1_000_000_000_000,
        "t": 1_000_000_000_000,
        "billion": 1_000_000_000,
        "b": 1_000_000_000,
        "million": 1_000_000,
        "m": 1_000_000,
        "crore": 10_000_000,
        "cr": 10_000_000,
        "lakh": 100_000,
        "thousand": 1_000,
        "k": 1_000,
    }
    multiplier = multipliers.get(scale_lower, 1.0)
    num *= multiplier

    return num, is_approx


def extract_temporal_scope(text: str) -> Optional[str]:
    """Extract temporal scope (fiscal year, calendar year, quarter, date) from context."""
    # Fiscal years: FY24, FY 2024, FY2024-25, 2023-24
    m_fy = re.search(r'\b(?:FY|Fiscal\s+Year|FY-)\s*(\d{2,4}(?:-\d{2,4})?)\b', text, re.IGNORECASE)
    if m_fy:
        raw_yr = m_fy.group(1)
        return f"FY{raw_yr}" if not raw_yr.startswith("FY") else raw_yr

    # Quarters: Q1 FY24, Q3 2025, Q4
    m_q = re.search(r'\b(Q[1-4])\s*(?:FY)?\s*(\d{2,4})?\b', text, re.IGNORECASE)
    if m_q:
        q = m_q.group(1).upper()
        yr = f" {m_q.group(2)}" if m_q.group(2) else ""
        return f"{q}{yr}".strip()

    # Hyphenated years e.g. 2023-24 or 2024-2025
    m_range = re.search(r'\b(20\d{2}-\d{2,4})\b', text)
    if m_range:
        return m_range.group(1)

    # Standalone calendar year e.g. 2024, 2025
    m_yr = re.search(r'\b(20\d{2}|19\d{2})\b', text)
    if m_yr:
        return m_yr.group(1)

    # Explicit months + year: "March 31, 2024" or "as of June 2023"
    m_date = re.search(r'\b(?:as\s+of\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2},?\s+)?(20\d{2})\b', text, re.IGNORECASE)
    if m_date:
        return f"{m_date.group(1).title()} {m_date.group(3)}"

    # Relative temporal markers
    if re.search(r'\b(projected|forecast|budgeted|guidance|target)\b', text, re.IGNORECASE):
        return "Forecast / Target"
    if re.search(r'\b(historical|baseline|prior\s+year)\b', text, re.IGNORECASE):
        return "Historical"

    return None


def extract_context_scope(text: str) -> Optional[str]:
    """Extract reporting boundary, operational scope, or methodology context."""
    lower = text.lower()
    if "consolidated" in lower:
        return "Consolidated"
    if "standalone" in lower:
        return "Standalone"
    if "domestic" in lower and "international" not in lower:
        return "Domestic"
    if "international" in lower or "global" in lower:
        return "International"
    if "enterprise" in lower:
        return "Enterprise"
    if "retail" in lower:
        return "Retail"
    if "experimental" in lower or "laboratory" in lower:
        return "Experimental"
    if "production" in lower:
        return "Production"
    if "non-gaap" in lower:
        return "Non-GAAP"
    if "gaap" in lower:
        return "GAAP"
    if "audited" in lower:
        return "Audited"
    return None


def fuzzy_verify_evidence(quote: str, page_text: str) -> Tuple[bool, float]:
    """Verify whether evidence quote exists in page text via exact or whitespace-tolerant match.
    
    Returns:
        (is_verified, match_confidence)
    """
    if not quote or not page_text:
        return False, 0.0

    # 1. Exact verbatim match
    if quote in page_text:
        return True, 1.0

    # 2. Normalized whitespace & line breaks match
    norm_quote = re.sub(r'\s+', ' ', quote).strip().lower()
    norm_page = re.sub(r'\s+', ' ', page_text).strip().lower()
    if norm_quote in norm_page:
        return True, 0.95

    # 3. Soft substring match (e.g. OCR hyphenation dropped)
    clean_quote = re.sub(r'[^a-z0-9 ]', '', norm_quote)
    clean_page = re.sub(r'[^a-z0-9 ]', '', norm_page)
    if len(clean_quote) > 15 and clean_quote in clean_page:
        return True, 0.85

    # 4. Check for high token overlap
    quote_tokens = set(clean_quote.split())
    if len(quote_tokens) >= 5:
        page_tokens = set(clean_page.split())
        overlap = len(quote_tokens & page_tokens) / len(quote_tokens)
        if overlap >= 0.85:
            return True, 0.75

    return False, 0.0


def resolve_entity_alias(e1: str, e2: str) -> str:
    """Compare two entities without hardcoding specific dataset aliases.
    
    Returns:
        'MATCH' | 'ALIAS' | 'DIFFERENT' | 'UNKNOWN'
    """
    if not e1 or not e2:
        return "UNKNOWN"

    s1 = e1.strip().lower()
    s2 = e2.strip().lower()
    if s1 == s2:
        return "MATCH"

    # Strip generic organizational suffixes: Corp, Corporation, Inc, Ltd, Limited, Co, LLC, Company
    suffix_pattern = r'\b(?:corporation|corp|inc|incorporated|ltd|limited|company|co|llc|group|holdings|services)\b'
    base1 = re.sub(suffix_pattern, '', s1).strip()
    base2 = re.sub(suffix_pattern, '', s2).strip()
    if base1 and base2 and base1 == base2:
        return "ALIAS"

    # Check prefix / substring (e.g. "Acme" in "Acme Corporation")
    if len(base1) >= 4 and len(base2) >= 4:
        if base1 in base2 or base2 in base1:
            return "ALIAS"

    return "DIFFERENT"


def resolve_predicate_similarity(p1: str, p2: str) -> str:
    """Compare two predicates/attributes generically.
    
    Returns:
        'MATCH' | 'SIMILAR' | 'DIFFERENT'
    """
    if not p1 or not p2:
        return "DIFFERENT"

    a1 = p1.strip().lower()
    a2 = p2.strip().lower()
    if a1 == a2:
        return "MATCH"

    # Remove generic filler and scope words
    stop = r'\b(?:the|a|an|total|average|annual|quarterly|overall|gross|net|observed|measured|reported|level|rate|ratio|count|amount|value|consolidated|standalone|domestic|international)\b'
    stem1 = re.sub(stop, '', a1).strip()
    stem2 = re.sub(stop, '', a2).strip()
    if stem1 and stem2 and stem1 == stem2:
        return "SIMILAR"

    # Token set overlap
    t1 = set(stem1.split())
    t2 = set(stem2.split())
    if t1 and t2:
        jaccard = len(t1 & t2) / len(t1 | t2)
        if jaccard >= 0.6:
            return "SIMILAR"

    return "DIFFERENT"
