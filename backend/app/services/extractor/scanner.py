"""
CodebaseScanner — walks a repository and produces CodeChunk objects.

A CodeChunk is a contiguous block of source code that has been flagged as
a candidate automation rule by one or more pattern matchers. The analyzer
(analyzer.py) then takes each chunk and asks Claude whether it actually
represents a rule and, if so, extracts its structured fields.

Pattern detection is intentionally broad at this stage — it is cheap to
send a false positive to Claude and have it reply "not a rule". It is
expensive to miss a real rule.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported file extensions (AST-parseable or text-scannable)
# ---------------------------------------------------------------------------

_SUPPORTED_EXTENSIONS: Set[str] = {
    # Python
    ".py",
    # JavaScript / TypeScript
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    # Ruby
    ".rb",
    # Go
    ".go",
    # Java / Kotlin
    ".java", ".kt",
    # Config / data (threshold-heavy)
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".env",
    # Shell
    ".sh", ".bash",
    # SQL (scheduled jobs, triggers)
    ".sql",
}

# ---------------------------------------------------------------------------
# Pattern catalogue
# Each entry is (pattern_name, compiled_regex).
# A chunk is emitted when ANY pattern matches within a sliding window.
# ---------------------------------------------------------------------------

_PATTERNS: List[tuple[str, re.Pattern]] = [
    # Scheduled / cron
    ("cron_expression",      re.compile(r"(@(hourly|daily|weekly|monthly|yearly|reboot)|(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+))")),
    ("schedule_decorator",   re.compile(r"@(celery\.task|shared_task|app\.task|cron|schedule|periodic_task|beat_schedule)", re.IGNORECASE)),
    ("schedule_keyword",     re.compile(r"\b(schedule|crontab|interval|every|timedelta|recurring|periodic)\b", re.IGNORECASE)),
    # Event / webhook
    ("event_handler",        re.compile(r"@(on_event|event_handler|webhook|signal|receiver|subscribe|listen)", re.IGNORECASE)),
    ("on_keyword",           re.compile(r"\bon_(created|updated|deleted|changed|received|sent|failed|success|complete)\b", re.IGNORECASE)),
    # Threshold / condition logic
    ("threshold_pattern",    re.compile(r"\b(threshold|limit|min_|max_|ceiling|floor|cap|quota|budget|target|baseline)\b", re.IGNORECASE)),
    ("comparison_with_const",re.compile(r"(>=|<=|>|<)\s*[0-9]+(\.[0-9]+)?")),
    ("if_then_block",        re.compile(r"\bif\b.{0,120}\bthen\b|\bif\b.{0,80}\braise\b|\bif\b.{0,80}\breturn\b", re.DOTALL | re.IGNORECASE)),
    # Notification / alerting
    ("send_email",           re.compile(r"\b(send_mail|send_email|EmailMessage|smtplib|SendGrid|Mailgun|ses\.send|notify|alert|pagerduty|slack\.post|webhook\.send)\b", re.IGNORECASE)),
    ("notification_keyword", re.compile(r"\b(notification|alert|escalat|on_call|incident|ticket)\b", re.IGNORECASE)),
    # External API / integrations
    ("api_call",             re.compile(r"\b(requests\.(get|post|put|patch|delete)|httpx\.|aiohttp\.|fetch\(|axios\.|curl\b)", re.IGNORECASE)),
    ("webhook_url",          re.compile(r"https?://[^\s\"']+/webhook", re.IGNORECASE)),
    # Config / feature flags
    ("feature_flag",         re.compile(r"\b(feature_flag|feature_toggle|FEATURE_|FF_|flags\[|getFlag|isEnabled)\b", re.IGNORECASE)),
    ("config_threshold",     re.compile(r"(MAX_RETRIES|MIN_BALANCE|ALERT_THRESHOLD|BATCH_SIZE|TIMEOUT|RATE_LIMIT|CONCURRENCY|WORKERS)", re.IGNORECASE)),
    # Retry / backoff
    ("retry_pattern",        re.compile(r"\b(retry|backoff|max_attempts|exponential|CircuitBreaker|tenacity)\b", re.IGNORECASE)),
    # Approval / workflow gating
    ("approval_gate",        re.compile(r"\b(approve|reject|pending_approval|require_approval|two_factor|mfa_required|authorization_required)\b", re.IGNORECASE)),
]

# Files that are almost always irrelevant
_SKIP_DIRS: Set[str] = {
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    "dist", "build", ".next", ".nuxt", "coverage", ".tox", "venv", ".venv",
    "migrations",  # DB migrations rarely contain business rules
}

_MAX_FILE_SIZE_BYTES = 500_000   # skip files > 500 KB
_CONTEXT_LINES = 20              # lines of context around a match


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    patterns_found: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "language": self.language,
            "patterns_found": self.patterns_found,
        }


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class CodebaseScanner:
    """
    Walk a repository directory tree, identify files that likely contain
    automation rules, and extract relevant code chunks for LLM analysis.
    """

    def __init__(self, repo_path: str, branch: str = "main") -> None:
        self.repo_path = Path(repo_path).resolve()
        self.branch = branch
        self._chunks: List[CodeChunk] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scan(self) -> List[CodeChunk]:
        """
        Entry point. Returns all CodeChunks found in the repository.
        Idempotent — resets the chunk list on each call.
        """
        self._chunks = []
        candidate_files = self._identify_automation_files()
        logger.info(
            "Scanner found %d candidate files under %s",
            len(candidate_files),
            self.repo_path,
        )
        for file_path in candidate_files:
            try:
                new_chunks = self._extract_code_chunks(file_path)
                self._chunks.extend(new_chunks)
            except Exception as exc:
                logger.warning("Failed to extract chunks from %s: %s", file_path, exc)

        logger.info("Total chunks extracted: %d", len(self._chunks))
        return self._chunks

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _identify_automation_files(self) -> List[Path]:
        """
        Walk the tree and return files that are (a) a supported extension
        and (b) contain at least one pattern match (quick text scan).
        """
        candidates: List[Path] = []

        for root, dirs, files in os.walk(self.repo_path):
            # Prune irrelevant directories in-place so os.walk skips them
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

            for filename in files:
                filepath = Path(root) / filename
                if filepath.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                    continue
                if filepath.stat().st_size > _MAX_FILE_SIZE_BYTES:
                    logger.debug("Skipping large file: %s", filepath)
                    continue
                try:
                    text = filepath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if self._has_any_pattern(text):
                    candidates.append(filepath)

        return candidates

    def _has_any_pattern(self, text: str) -> bool:
        for _name, pattern in _PATTERNS:
            if pattern.search(text):
                return True
        return False

    # ------------------------------------------------------------------
    # Chunk extraction
    # ------------------------------------------------------------------

    def _extract_code_chunks(self, file_path: Path) -> List[CodeChunk]:
        """
        Read the file, find every line that matches a pattern, then emit a
        de-duplicated set of context windows around those lines.

        Overlapping windows are merged into a single chunk to avoid sending
        the same code to Claude multiple times with slightly different bounds.
        """
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        language = _extension_to_language(file_path.suffix.lower())
        relative_path = str(file_path.relative_to(self.repo_path))

        # Build a map of line_number → [pattern_names] for every matching line
        line_patterns: Dict[int, List[str]] = {}
        for name, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n")  # 0-indexed
                line_patterns.setdefault(line_no, []).append(name)

        if not line_patterns:
            return []

        # Sort matching line numbers and build non-overlapping windows
        sorted_hits = sorted(line_patterns.keys())
        windows: List[tuple[int, int, List[str]]] = []  # (start, end, patterns)

        for hit in sorted_hits:
            w_start = max(0, hit - _CONTEXT_LINES)
            w_end = min(len(lines) - 1, hit + _CONTEXT_LINES)
            hit_patterns = line_patterns[hit]

            if windows and w_start <= windows[-1][1]:
                # Merge with the previous window
                prev_start, prev_end, prev_patterns = windows[-1]
                merged_patterns = list(set(prev_patterns + hit_patterns))
                windows[-1] = (prev_start, max(prev_end, w_end), merged_patterns)
            else:
                windows.append((w_start, w_end, hit_patterns))

        chunks: List[CodeChunk] = []
        for w_start, w_end, patterns in windows:
            chunk_lines = lines[w_start : w_end + 1]
            chunks.append(
                CodeChunk(
                    file_path=relative_path,
                    start_line=w_start + 1,      # 1-indexed for human display
                    end_line=w_end + 1,
                    content="\n".join(chunk_lines),
                    language=language,
                    patterns_found=patterns,
                )
            )

        return chunks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extension_to_language(ext: str) -> str:
    _map = {
        ".py": "python",
        ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".jsx": "javascript",
        ".rb": "ruby",
        ".go": "go",
        ".java": "java",
        ".kt": "kotlin",
        ".yaml": "yaml", ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".ini": "ini", ".cfg": "ini",
        ".env": "dotenv",
        ".sh": "bash", ".bash": "bash",
        ".sql": "sql",
    }
    return _map.get(ext, "text")
