"""
Lightweight content-based PII classifier. Regex-only — catches the obvious
shapes (SSN, credit card, IBAN, email dumps). Complements the filename-based
sensitivity heuristic in access_logger.classify_sensitivity.

A future iteration can add an LLM pass; this first version runs in-process
with zero external dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.models.file_access_log import FileSensitivity


# Regex patterns and labels. Order matters — more specific patterns first.
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("ssn",       re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                              "US SSN"),
    ("cc_visa",   re.compile(r"\b4\d{3}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),           "Credit card (Visa)"),
    ("cc_mc",     re.compile(r"\b5[1-5]\d{2}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),      "Credit card (MasterCard)"),
    ("cc_amex",   re.compile(r"\b3[47]\d{2}[- ]?\d{6}[- ]?\d{5}\b"),                 "Credit card (Amex)"),
    ("iban",      re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),                   "IBAN"),
    ("aws_key",   re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                               "AWS access key ID"),
    ("jwt",       re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "JWT token"),
    ("email_bulk", re.compile(r"(?:[\w.+-]+@[\w.-]+\.\w{2,}\s*[,\n]\s*){5,}"),       "Bulk email list"),
    ("phone_us",  re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b"), "US phone number"),
]


@dataclass
class PIIFinding:
    label: str
    tag: str
    count: int


def classify_content(text: str, *, max_findings_per_tag: int = 5) -> List[PIIFinding]:
    """Return list of PII patterns found in `text`."""
    findings: List[PIIFinding] = []
    if not text:
        return findings
    for tag, pat, label in _PATTERNS:
        matches = pat.findall(text)
        if not matches:
            continue
        count = min(len(matches), max_findings_per_tag * 1000)  # cap for perf
        findings.append(PIIFinding(label=label, tag=tag, count=count))
    return findings


def summary_reason(findings: List[PIIFinding]) -> Optional[str]:
    if not findings:
        return None
    parts = [f"{f.label} ×{f.count}" if f.count > 1 else f.label for f in findings]
    return "PII detected: " + ", ".join(parts)


def upgrade_sensitivity(
    existing: Optional[str], findings: List[PIIFinding]
) -> str:
    """If PII was detected, escalate sensitivity to FLAGGED."""
    if findings:
        return FileSensitivity.FLAGGED.value
    return existing or FileSensitivity.UNKNOWN.value
