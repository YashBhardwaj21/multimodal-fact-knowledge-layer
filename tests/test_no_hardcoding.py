"""Regression test to guarantee ZERO hardcoding or domain-specific assumptions in src/."""

import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"

FORBIDDEN_PATTERNS = [
    # Starter company names and entities
    (r'\bdelhivery\b', "Hardcoded starter company name 'Delhivery'"),
    (r'\bdelhivery limited\b', "Hardcoded entity 'Delhivery Limited'"),
    
    # Starter specific document names or hardcoded file substring assumptions
    (r'\bannual-report\b', "Hardcoded document filename assumption 'annual-report'"),
    (r'\bprospectus\b', "Hardcoded document filename assumption 'prospectus'"),
    
    # Hardcoded starter numeric constants used as extraction/reconciliation targets
    (r'\b8[,\.]?142\b', "Hardcoded starter dataset constant 8,142"),
    (r'\b19[,\.]?300\b', "Hardcoded starter dataset constant 19,300"),
    (r'\b18[,\.]?793\b', "Hardcoded starter dataset constant 18,793"),
    (r'\b7[,\.]?224\b', "Hardcoded starter dataset constant 7,224"),

    # Spurious domain fallbacks
    (r'"Financial Metric"', "Hardcoded fallback predicate 'Financial Metric'"),
    (r"'Financial Metric'", "Hardcoded fallback predicate 'Financial Metric'"),
]


def test_no_hardcoding_in_src():
    """Scan all Python files under src/ to ensure complete absence of hardcoded starter logic."""
    violations = []

    py_files = list(SRC_DIR.rglob("*.py"))
    assert len(py_files) > 0, "No python files found in src/"

    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for pattern, description in FORBIDDEN_PATTERNS:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            if matches:
                for m in matches:
                    # Find line number
                    line_no = content[:m.start()].count("\n") + 1
                    line_text = content.splitlines()[line_no - 1].strip()
                    violations.append(f"{py_file.name}:{line_no} [{description}] -> {line_text}")

    assert not violations, "Forbidden hardcoded domain patterns detected in application source code:\n" + "\n".join(violations)
