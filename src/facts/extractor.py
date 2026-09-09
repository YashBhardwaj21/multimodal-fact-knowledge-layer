"""Extracts structured, verified facts from arbitrary PDF documents across all domains.

Purely document-agnostic:
- Extracts generic candidate primitives (currencies, percentages, operational units, counts, dates, table cells).
- Discovers semantic facts via LLM with structured JSON output and strict evidence verification.
- Employs rich deterministic syntactic and profile grounding when running offline or as fallback.
- Never defaults to domain-specific assumptions (e.g., never assumes domain predicates or hardcoded companies).
- Derives page subjects dynamically (e.g. dinosaur names, model names, company entities).
- Verifies every fact against verbatim document text before acceptance.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional, Set
from src.facts.models import Fact, Evidence
from src.ingestion.pdf_loader import PDFPage
from src.facts.llm_provider import LLMProvider
from src.facts.normalization import (
    derive_document_subject,
    derive_page_subject,
    normalize_currency,
    parse_numeric_and_scale,
    extract_temporal_scope,
    extract_context_scope,
    fuzzy_verify_evidence,
)

logger = logging.getLogger(__name__)

class FactExtractor:
    """Extracts grounded facts from arbitrary PDF documents without domain-specific assumptions."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm = llm_provider or LLMProvider()
        self._llm_consecutive_failures = 0

    def extract_from_pages(self, pages: List[PDFPage]) -> List[Fact]:
        """Extract facts across a collection of pages."""
        self._llm_consecutive_failures = 0
        all_facts: List[Fact] = []
        for page in pages:
            facts = self.extract_from_page(page)
            all_facts.extend(facts)
        return all_facts

    def extract_from_page(self, page: PDFPage) -> List[Fact]:
        """Extract facts from a single page with strict grounding and verification."""
        text = page.text
        if not text or len(text.strip()) < 10:
            return []

        doc_name = page.document_name
        p_num = page.page_number
        page_subject = derive_page_subject(text, doc_name)
        facts: List[Fact] = []

        # 1. LLM Semantic Fact Extraction (if LLM backend is active and not circuit-broken)
        llm_facts_extracted = False
        if self.llm.is_active() and self._llm_consecutive_failures < 2 and len(text) > 80:
            try:
                llm_facts = self._extract_with_llm(page, page_subject)
                if llm_facts:
                    facts.extend(llm_facts)
                    llm_facts_extracted = True
                self._llm_consecutive_failures = 0
            except Exception as e:
                self._llm_consecutive_failures += 1
                if self._llm_consecutive_failures >= 2:
                    logger.info(f"LLM backend timed out or unavailable ({e}); proceeding with fast deterministic extraction.")
                else:
                    logger.warning(f"LLM fact extraction skipped on {doc_name} p.{p_num}: {e}")

        # 2. Contextual Syntactic & Profile Fact Extraction (runs deterministic semantic discovery)
        deterministic_facts = self._extract_contextual_facts(page, page_subject)
        facts.extend(deterministic_facts)

        # 3. Deduplicate facts on the same page sharing identical attribute & normalized value
        seen: Set[tuple] = set()
        unique_facts: List[Fact] = []
        for f in facts:
            attr_key = re.sub(r'[^a-z0-9]', '', f.attribute.lower())[:24]
            val_key = str(f.normalized_value) if f.normalized_value is not None else f.value.strip().lower()
            subj_key = f.subject.strip().lower()[:20]
            key = (subj_key, attr_key, val_key, f.temporal_scope or "", f.context_scope or "")
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)

        return unique_facts

    def _extract_with_llm(self, page: PDFPage, page_subject: str) -> List[Fact]:
        """Extract semantic facts using structured LLM output with rigorous evidence validation."""
        system_prompt = (
            "You are a strict, domain-agnostic fact extraction system. "
            "Extract verified factual claims (metrics, operational capacities, dates, percentages, measurements, key characteristics) "
            "from the supplied text excerpt.\n"
            "RULES:\n"
            "1. Facts must come ONLY from the supplied text. Do NOT invent numbers, entities, or dates.\n"
            "2. 'evidence_quote' MUST be an exact verbatim substring copied directly from the text.\n"
            "3. If an entity/subject is not explicitly named, use the page or document subject.\n"
            "4. Unknown scopes must be null.\n"
            "5. Distinguish historical actuals, projections, and targets.\n"
            "Return JSON adhering to this schema:\n"
            "{\n"
            '  "facts": [\n'
            '    {\n'
            '      "subject": "string",\n'
            '      "attribute": "string",\n'
            '      "value": "string",\n'
            '      "unit": "string",\n'
            '      "temporal_scope": "string or null",\n'
            '      "context_scope": "string or null",\n'
            '      "evidence_quote": "exact verbatim quote from text",\n'
            '      "confidence": 0.95\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        user_prompt = (
            f"Document: {page.document_name}, Page: {page.page_number}\n"
            f"Text Excerpt:\n{page.text[:3000]}\n\n"
            "Extract up to 6 high-importance, grounded facts with exact verbatim evidence quotes."
        )

        response_text = self.llm.generate(user_prompt, system_prompt=system_prompt, as_json=True)
        if not response_text:
            return []

        try:
            data = json.loads(response_text)
        except Exception:
            m = re.search(r'\{.*\}', response_text, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
            else:
                return []

        verified_facts: List[Fact] = []
        raw_items = data.get("facts", [])
        for item in raw_items:
            quote = (item.get("evidence_quote") or "").strip()
            val = (item.get("value") or "").strip()
            raw_attr = (item.get("attribute") or "").strip()
            if not quote or not val or not raw_attr:
                continue

            # EVIDENCE VERIFICATION STAGE
            is_verified, match_score = fuzzy_verify_evidence(quote, page.text)
            if not is_verified:
                continue

            clean_val = re.sub(r'[^\d.]', '', val)
            if clean_val and clean_val not in re.sub(r'[^\d.]', '', quote):
                continue

            norm_val, is_approx = parse_numeric_and_scale(val)
            unit_str = (item.get("unit") or "").strip()
            temp_scope = item.get("temporal_scope") or extract_temporal_scope(quote)
            ctx_scope = item.get("context_scope") or extract_context_scope(quote)
            subj = item.get("subject") or page_subject

            attr = self._clean_attribute_name(raw_attr)
            if len(attr) < 2:
                continue

            char_pos = page.text.find(quote)
            verified_facts.append(Fact(
                subject=subj,
                attribute=attr,
                value=val,
                normalized_value=norm_val,
                unit=unit_str or ("Count" if norm_val is not None else "Text"),
                temporal_scope=temp_scope,
                context_scope=ctx_scope,
                evidence=Evidence(
                    document_name=page.document_name,
                    page_number=page.page_number,
                    verbatim_quote=quote,
                    char_offset=max(0, char_pos)
                ),
                confidence=min(0.96, match_score * float(item.get("confidence", 0.90)))
            ))

        return verified_facts

    def _extract_contextual_facts(self, page: PDFPage, page_subject: str) -> List[Fact]:
        """Extract facts using deterministic syntactic and profile grounding."""
        facts: List[Fact] = []
        text = page.text
        doc = page.document_name
        p_num = page.page_number

        # --- A. Structured & Unstructured Key-Value Profile Items ---
        # Matches both single-line ('Height: 16 feet') and multi-line ('Height:\n16 feet')
        # Handles dimensional measurements, dates, and qualitative attributes
        kv_pattern = r'(?m)^([A-Za-z0-9][a-zA-Z0-9\s/&-]{1,32}?):\s*(?:\n\s*)?([^\n\r]{1,90})'
        for m in re.finditer(kv_pattern, text):
            raw_key = re.sub(r'^(?:FACT FILE|PROFILE|OVERVIEW|SPECIFICATIONS|SUMMARY)\s*', '', m.group(1), flags=re.IGNORECASE).strip()
            raw_val = m.group(2).strip()

            if len(raw_key) < 2 or any(w in raw_key.lower() for w in ["http", "www", "page", "chapter", "section", "table of contents", "did you know", "click here", "contents"]):
                continue
            if not raw_val or len(raw_val) < 1 or "..." in raw_val:
                continue

            attr = self._clean_attribute_name(raw_key)
            if len(attr) < 2:
                continue

            # Detect measurement units in value e.g. "16 feet", "6 tons", "33 lbs", "1 lb 1.67 oz", "94.6%"
            m_unit = re.search(r'([\d,]+\.?\d*)\s*(feet|foot|ft|inches|inch|in|meters|metres|m|cm|mm|miles|km|tons|tonnes|ton|lbs|lb|pounds|pound|ounces|oz|kg|mg|g|mya|million years|years ago|mph|km/h|req/s|rps|nodes|ms|%)\b', raw_val, re.IGNORECASE)
            if m_unit:
                norm_val, _ = parse_numeric_and_scale(m_unit.group(1))
                unit_str = m_unit.group(2).title()
            else:
                m_num = re.search(r'(-?[\d,]+\.?\d*)', raw_val)
                if m_num and len(raw_val) <= 25:
                    norm_val, _ = parse_numeric_and_scale(m_num.group(1))
                    unit_str = "Count" if "year" not in attr.lower() else "Year"
                else:
                    norm_val = None
                    unit_str = "Text"

            match_text = m.group(0).strip()
            char_pos = text.find(match_text)

            facts.append(Fact(
                subject=page_subject,
                attribute=attr,
                value=raw_val,
                normalized_value=norm_val,
                unit=unit_str,
                temporal_scope=extract_temporal_scope(raw_val) or extract_temporal_scope(match_text),
                context_scope=extract_context_scope(raw_val) or extract_context_scope(match_text),
                evidence=Evidence(
                    document_name=doc,
                    page_number=p_num,
                    verbatim_quote=match_text,
                    char_offset=max(0, char_pos)
                ),
                confidence=0.95
            ))

        # --- B. Sentence-Level Clause Analysis ---
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.replace("\r", " ")) if len(s.strip()) > 15]

        for sentence in sentences:
            temporal_scope = extract_temporal_scope(sentence)
            context_scope = extract_context_scope(sentence)

            # --- Pattern Family 1: Currencies with Explicit Symbols & Scales ---
            # Strictly requires explicit currency symbol/code AND at least one digit
            curr_matches = re.finditer(
                r'([A-Za-z][a-zA-Z\s/&]{2,45}?)\s*(?:was|is|reached|stood at|amounted to|totaled|totalled|of|at)\s+(?:\$|€|£|¥|₹|\bUSD\b|\bEUR\b|\bINR\b|\bGBP\b|\bJPY\b|\bRs\.\s*|\bRs\s+)\s*([\d,]+\.?\d*)\s*(trillion|billion|million|crore|cr|lakh|thousand|[kKmMbB])?\b',
                sentence, re.IGNORECASE
            )
            for m in curr_matches:
                raw_attr = m.group(1)
                val_num = m.group(2)
                scale_str = m.group(3) or ""

                attr = self._clean_attribute_name(raw_attr)
                if len(attr) < 3 or any(w in attr.lower() for w in ["page", "chapter", "section", "table", "figure", "http"]):
                    continue

                norm_val, _ = parse_numeric_and_scale(val_num, scale_str)
                sym_match = re.search(r'(\$|€|£|¥|₹|\bUSD\b|\bEUR\b|\bINR\b|\bGBP\b|\bJPY\b|\bRs\.?)', m.group(0), re.IGNORECASE)
                sym = sym_match.group(1) if sym_match else "USD"
                val_repr = f"{sym} {val_num} {scale_str}".strip()

                char_pos = text.find(sentence)
                facts.append(Fact(
                    subject=page_subject,
                    attribute=attr,
                    value=val_repr,
                    normalized_value=norm_val,
                    unit=normalize_currency(sym),
                    temporal_scope=temporal_scope,
                    context_scope=context_scope,
                    evidence=Evidence(
                        document_name=doc,
                        page_number=p_num,
                        verbatim_quote=sentence,
                        char_offset=max(0, char_pos)
                    ),
                    confidence=0.96
                ))

            # --- Pattern Family 2: Percentages & Rates with Grounded Subject ---
            pct_matches = re.finditer(
                r'([A-Za-z][a-zA-Z\s/&]{2,45}?)\s*(?:of|is|was|were|reached|at|in|by|achieved|moderated to|grew by|expanded by|declined by|decreased to|increased to|stood at|averaged)\s+(-?[\d\.]+)\s*(?:%|per\s*cent)(?:\s+([A-Za-z]{2,20}))?',
                sentence, re.IGNORECASE
            )
            for m in pct_matches:
                raw_attr = m.group(1)
                val_str = m.group(2)
                post_noun = (m.group(3) or "").strip()

                if post_noun and post_noun.lower() not in ["across", "during", "in", "for", "on", "of", "and", "the", "with"]:
                    attr = self._clean_attribute_name(post_noun)
                else:
                    attr = self._clean_attribute_name(raw_attr)

                if len(attr) < 3 or any(w in attr.lower() for w in ["page", "chapter", "section", "table", "figure"]):
                    continue

                try:
                    norm_val = float(val_str)
                except ValueError:
                    norm_val = None

                char_pos = text.find(sentence)
                facts.append(Fact(
                    subject=page_subject,
                    attribute=attr,
                    value=f"{val_str}%",
                    normalized_value=norm_val,
                    unit="Percentage",
                    temporal_scope=temporal_scope,
                    context_scope=context_scope,
                    evidence=Evidence(
                        document_name=doc,
                        page_number=p_num,
                        verbatim_quote=sentence,
                        char_offset=max(0, char_pos)
                    ),
                    confidence=0.95
                ))

            # --- Pattern Family 3: Physical, Technical, and Dimensional Units ---
            # e.g., "latency fell to 12.5 ms", "wingspan over 2 feet", "sample temperature was 37.2 °C"
            # e.g., "processed 2.3 million requests", "sustained 45,000 nodes"
            unit_matches = re.finditer(
                r'([A-Za-z][a-zA-Z\s/&]{2,45}?)\s*(?:of|is|was|were|at|in|by|has|had|stood at|reached|deployed|handled|processed|sustained|used|recorded at|measured at|decreased to|increased to|improved to|fell to|rose to|dropped to|capacity of|with a wingspan of|wingspan over)\s+(?:over\s+|nearly\s+)?([\d,]+\.?\d*)\s*(million|billion|crore|cr|lakh|thousand|[kKmMbB])?\s*(feet|foot|ft|inches|inch|in|meters|metres|m|cm|mm|miles|km|yards|tons|tonnes|ton|lbs|lb|pounds|pound|ounces|oz|kg|mg|g|mcg|ml|l|mya|million years|years ago|mph|km/h|kph|m/s|°c|°f|celsius|fahrenheit|hz|khz|mhz|ghz|kb|mb|gb|tb|ms|milliseconds|seconds|minutes|hours|days|weeks|months|years|nodes|parameters|tokens|requests|req/s|rps|users|customers|clients|shipments|units|stores|branches|facilities|subjects|patients|cases|participants|samples|trials|events)\b',
                sentence, re.IGNORECASE
            )
            for m in unit_matches:
                raw_attr = m.group(1)
                val_str = m.group(2)
                scale_str = m.group(3) or ""
                unit_str = m.group(4)

                cleaned_raw = self._clean_attribute_name(raw_attr)
                if cleaned_raw.lower() in ["system", "platform", "model", "we", "firm", "company", "experiment", "study"]:
                    attr = f"{unit_str.title()} Processed"
                else:
                    attr = cleaned_raw

                if len(attr) < 3 or any(w in attr.lower() for w in ["page", "chapter", "section", "table", "figure"]):
                    continue

                norm_val, _ = parse_numeric_and_scale(val_str, scale_str)
                full_val = f"{val_str} {scale_str} {unit_str}".replace("  ", " ").strip()

                char_pos = text.find(sentence)
                facts.append(Fact(
                    subject=page_subject,
                    attribute=attr,
                    value=full_val,
                    normalized_value=norm_val,
                    unit=unit_str.title(),
                    temporal_scope=temporal_scope,
                    context_scope=context_scope,
                    evidence=Evidence(
                        document_name=doc,
                        page_number=p_num,
                        verbatim_quote=sentence,
                        char_offset=max(0, char_pos)
                    ),
                    confidence=0.94
                ))

            # --- Pattern Family 4: Historical, Discovery, and Founding Milestones ---
            # e.g., "T-rex was first discovered by Barnum Brown in 1902", "founded in 1990", "coined in 1842"
            disc_match = re.search(
                r'([A-Z][a-zA-Z\s\'-]{2,30}?)\s+(?:was\s+first\s+discovered|was\s+discovered|was\s+first\s+described|was\s+first\s+coined|was\s+coined|was\s+founded|was\s+established|since\s+its\s+beginnings\s+in)\s+(?:by\s+[A-Za-z\s]+)?\s*(?:in|on)?\s*(\d{4})\b',
                sentence, re.IGNORECASE
            )
            if disc_match:
                subj_cand = disc_match.group(1).strip()
                yr = disc_match.group(2).strip()
                subj = subj_cand if len(subj_cand) >= 3 and not any(w in subj_cand.lower() for w in ["it", "this", "that", "there"]) else page_subject

                char_pos = text.find(sentence)
                facts.append(Fact(
                    subject=subj,
                    attribute="Historical Milestone",
                    value=yr,
                    normalized_value=float(yr),
                    unit="Year",
                    temporal_scope=yr,
                    context_scope="Historical",
                    evidence=Evidence(
                        document_name=doc,
                        page_number=p_num,
                        verbatim_quote=sentence,
                        char_offset=max(0, char_pos)
                    ),
                    confidence=0.93
                ))

            # --- Pattern Family 5: Classifications, Types, and Categories ---
            # e.g., "Triceratops is classified as a cerapod", "Diplodocus falls in the Sauropod category"
            cat_match = re.search(
                r'([A-Z][a-zA-Z\s\'-]{2,30}?)\s+(?:is|was)\s+(?:classified as|a type of|a category of|a member of)\s+(?:a|an)?\s*([a-zA-Z\s-]{3,35}?)(?:\b|[.,;])',
                sentence, re.IGNORECASE
            )
            if cat_match:
                subj_cand = cat_match.group(1).strip()
                cat_val = cat_match.group(2).strip().title()
                subj = subj_cand if len(subj_cand) >= 3 and not any(w in subj_cand.lower() for w in ["it", "this", "that"]) else page_subject

                char_pos = text.find(sentence)
                facts.append(Fact(
                    subject=subj,
                    attribute="Classification",
                    value=cat_val,
                    normalized_value=None,
                    unit="Category",
                    temporal_scope=temporal_scope,
                    context_scope=context_scope,
                    evidence=Evidence(
                        document_name=doc,
                        page_number=p_num,
                        verbatim_quote=sentence,
                        char_offset=max(0, char_pos)
                    ),
                    confidence=0.93
                ))

        # --- Pattern Family 6: Structured Table Cell Observations ---
        for table in page.tables:
            if not table or len(table) < 2:
                continue
            header_row = table[0]
            for r_idx, row in enumerate(table[1:], start=2):
                if not row or len(row) < 2:
                    continue
                row_label = row[0].strip()
                if not row_label or len(row_label) < 2:
                    continue
                attr = self._clean_attribute_name(row_label)
                if len(attr) < 3 or any(w in attr.lower() for w in ["total", "sl no", "sr no"]):
                    continue

                for col_idx, cell_val in enumerate(row[1:], start=1):
                    cell_val = cell_val.strip()
                    if not cell_val:
                        continue
                    num_match = re.search(r'(-?[\d,]+\.?\d*)', cell_val)
                    if not num_match:
                        continue
                    col_header = header_row[col_idx].strip() if col_idx < len(header_row) else ""
                    table_time = extract_temporal_scope(col_header) or extract_temporal_scope(row_label)
                    table_scope = extract_context_scope(col_header) or extract_context_scope(row_label)

                    norm_val, _ = parse_numeric_and_scale(num_match.group(1))
                    quote = f"{row_label} | {col_header}: {cell_val}"
                    facts.append(Fact(
                        subject=page_subject,
                        attribute=attr,
                        value=cell_val,
                        normalized_value=norm_val,
                        unit=col_header if len(col_header) < 20 else "Table Metric",
                        temporal_scope=table_time,
                        context_scope=table_scope,
                        evidence=Evidence(
                            document_name=doc,
                            page_number=p_num,
                            verbatim_quote=quote,
                            table_citation=f"Table on page {p_num}, Row '{row_label}'"
                        ),
                        confidence=0.92
                    ))

        return facts

    def _clean_attribute_name(self, raw_attr: str) -> str:
        """Sanitize attribute string to produce clean, canonical metric titles."""
        attr = raw_attr.strip()
        # Remove temporal phrases
        attr = re.sub(r'\b(?:for\s+FY\s*\d{2,4}|for\s+the\s+fiscal\s+year\s+ended\s+[A-Za-z0-9,\s]+|in\s+FY\s*\d{2,4}|in\s+\d{4}(?:-\d{2,4})?|for\s+\d{4}(?:-\d{2,4})?)\b', '', attr, flags=re.IGNORECASE)
        # Remove scope phrases (since scope is captured independently in context_scope)
        attr = re.sub(r'\b(?:on\s+standalone\s+basis|on\s+consolidated\s+basis|consolidated|standalone)\b', '', attr, flags=re.IGNORECASE)
        # Remove leading conjunctions or filler words
        attr = re.sub(r'^(?:and|or|in|with|the|a|an|its|our|reaching an|reaching|company|firm|we|observed|measured|total)\s+', '', attr, flags=re.IGNORECASE)
        # Remove trailing prepositions
        attr = re.sub(r'\s+(?:for|in|on|at|of|during|as\s+of|was|is|were|stood\s+at)\s*$', '', attr, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', attr).strip().title()
        return cleaned
