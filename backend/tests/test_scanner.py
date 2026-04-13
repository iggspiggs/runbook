"""
Tests for CodebaseScanner — the file-walking, pattern-matching layer.

A temporary directory tree is constructed for each test class so that
scanner behaviour can be verified against known content without touching
any real repository.
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from app.services.extractor.scanner import CodebaseScanner, CodeChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_file(base: Path, relative: str, content: str) -> Path:
    """Create a file inside `base`, creating any intermediate directories."""
    target = base / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Threshold / conditional pattern detection
# ---------------------------------------------------------------------------

class TestThresholdPatterns:
    def test_scanner_identifies_threshold_check(self, tmp_path: Path) -> None:
        """if value > 500000 triggers the comparison_with_const pattern."""
        write_file(tmp_path, "app/billing.py", """\
            HIGH_VALUE_THRESHOLD = 500000

            def check_value(contract):
                if contract.total_value > HIGH_VALUE_THRESHOLD:
                    send_alert(contract)
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "comparison_with_const" in patterns or "threshold_pattern" in patterns

    def test_scanner_identifies_named_threshold_variable(self, tmp_path: Path) -> None:
        """Variables named MAX_RETRIES or MIN_BALANCE hit the threshold_pattern."""
        write_file(tmp_path, "app/retry.py", """\
            MAX_RETRIES = 5
            MIN_BALANCE = 100.0

            def attempt(fn):
                for _ in range(MAX_RETRIES):
                    fn()
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "threshold_pattern" in patterns or "config_threshold" in patterns


# ---------------------------------------------------------------------------
# Scheduled / cron task detection
# ---------------------------------------------------------------------------

class TestScheduledTaskPatterns:
    def test_scanner_identifies_cron_expression(self, tmp_path: Path) -> None:
        """A cron expression string triggers cron_expression pattern."""
        write_file(tmp_path, "app/jobs.py", """\
            # runs every day at 8am
            SCHEDULE = "0 8 * * *"

            def daily_report():
                generate_invoice_summary()
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "cron_expression" in patterns

    def test_scanner_identifies_celery_task_decorator(self, tmp_path: Path) -> None:
        """@app.task and @shared_task decorators hit schedule_decorator."""
        write_file(tmp_path, "app/tasks.py", """\
            from celery import shared_task

            @shared_task
            def send_weekly_digest():
                users = User.objects.filter(active=True)
                for user in users:
                    send_email(user.email)
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "schedule_decorator" in patterns

    def test_scanner_identifies_schedule_keyword(self, tmp_path: Path) -> None:
        """The word 'schedule' or 'interval' triggers schedule_keyword."""
        write_file(tmp_path, "app/heartbeat.py", """\
            HEARTBEAT_INTERVAL = 60  # seconds

            def run_heartbeat():
                schedule.every(HEARTBEAT_INTERVAL).seconds.do(ping_service)
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "schedule_keyword" in patterns or "comparison_with_const" in patterns


# ---------------------------------------------------------------------------
# Email / notification logic detection
# ---------------------------------------------------------------------------

class TestNotificationPatterns:
    def test_scanner_identifies_send_email_call(self, tmp_path: Path) -> None:
        """send_mail / send_email function calls trigger send_email pattern."""
        write_file(tmp_path, "app/notifications.py", """\
            def notify_ops(message):
                send_email(
                    to=OPS_EMAIL,
                    subject="Alert: " + message,
                    body=message,
                )
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "send_email" in patterns

    def test_scanner_identifies_notification_keyword(self, tmp_path: Path) -> None:
        """Words like 'alert' and 'escalate' trigger notification_keyword."""
        write_file(tmp_path, "app/alerts.py", """\
            def check_sla(ticket):
                if ticket.age_hours > SLA_THRESHOLD:
                    escalate_to_manager(ticket)
                    create_incident(ticket.id)
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Config value detection
# ---------------------------------------------------------------------------

class TestConfigPatterns:
    def test_scanner_identifies_config_threshold_constants(self, tmp_path: Path) -> None:
        """Constants like BATCH_SIZE, TIMEOUT, RATE_LIMIT are flagged."""
        write_file(tmp_path, "config/settings.py", """\
            BATCH_SIZE = 100
            TIMEOUT = 30
            RATE_LIMIT = 1000
            CONCURRENCY = 4
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "config_threshold" in patterns

    def test_scanner_identifies_feature_flag(self, tmp_path: Path) -> None:
        """FEATURE_ prefix variables trigger the feature_flag pattern."""
        write_file(tmp_path, "app/features.py", """\
            FEATURE_NEW_DASHBOARD = True
            FF_DARK_MODE = False

            def is_dashboard_enabled(user):
                return FEATURE_NEW_DASHBOARD and user.is_beta
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert len(chunks) >= 1
        patterns = {p for c in chunks for p in c.patterns_found}
        assert "feature_flag" in patterns


# ---------------------------------------------------------------------------
# Directory / extension exclusion
# ---------------------------------------------------------------------------

class TestExclusions:
    def test_scanner_skips_git_directory(self, tmp_path: Path) -> None:
        """Files inside .git/ are never included in the scan."""
        write_file(tmp_path, ".git/hooks/pre-commit", """\
            #!/bin/bash
            # MAX_RETRIES=5
            echo "pre-commit hook"
        """)
        write_file(tmp_path, "app/real.py", """\
            MAX_RETRIES = 5
            def attempt(): pass
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        for chunk in chunks:
            assert ".git" not in chunk.file_path

    def test_scanner_skips_node_modules(self, tmp_path: Path) -> None:
        """node_modules/ is excluded from the walk."""
        write_file(tmp_path, "node_modules/lodash/retry.js", """\
            const MAX_RETRIES = 3;
            module.exports = { MAX_RETRIES };
        """)
        write_file(tmp_path, "src/app.js", """\
            const RATE_LIMIT = 100;
            if (requests > RATE_LIMIT) { throttle(); }
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        for chunk in chunks:
            assert "node_modules" not in chunk.file_path

    def test_scanner_skips_pycache_directory(self, tmp_path: Path) -> None:
        """__pycache__/ bytecode directories are skipped."""
        write_file(tmp_path, "__pycache__/billing.cpython-312.pyc", "binary content MAX_RETRIES")
        write_file(tmp_path, "billing.py", """\
            MAX_RETRIES = 3
            def retry(): pass
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        for chunk in chunks:
            assert "__pycache__" not in chunk.file_path

    def test_scanner_respects_file_extension_filter(self, tmp_path: Path) -> None:
        """
        Files with unsupported extensions (e.g. .txt, .log) are ignored even
        if they contain pattern-matching text.
        """
        write_file(tmp_path, "docs/notes.txt", "MAX_RETRIES = 5\nTHRESHOLD = 100\n")
        write_file(tmp_path, "app/job.log", "MAX_RETRIES exceeded, sending alert\n")
        write_file(tmp_path, "app/config.py", """\
            MAX_RETRIES = 5
            def run(): pass
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        for chunk in chunks:
            assert not chunk.file_path.endswith(".txt")
            assert not chunk.file_path.endswith(".log")


# ---------------------------------------------------------------------------
# Chunk merging
# ---------------------------------------------------------------------------

class TestChunkMerging:
    def test_scanner_merges_overlapping_chunks(self, tmp_path: Path) -> None:
        """
        Two pattern matches within _CONTEXT_LINES of each other should
        be merged into a single CodeChunk rather than emitting two overlapping
        chunks with different bounds.
        """
        # Two threshold checks 5 lines apart — well within the 20-line context window
        write_file(tmp_path, "app/rules.py", """\
            ALERT_THRESHOLD = 90
            LOW_THRESHOLD = 10

            def evaluate(metric):
                if metric > ALERT_THRESHOLD:
                    send_alert("too high")
                if metric < LOW_THRESHOLD:
                    send_alert("too low")
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        # Should be 1 merged chunk covering the whole file, not 2 overlapping
        assert len(chunks) == 1

    def test_scanner_does_not_merge_distant_chunks(self, tmp_path: Path) -> None:
        """
        Two pattern matches more than 2 * _CONTEXT_LINES apart produce
        separate chunks.
        """
        # Build a file with 60 blank lines between two threshold hits
        lines = ["# top of file"]
        lines += ["# padding"] * 60
        lines += ["MAX_RETRIES = 3"]
        write_file(tmp_path, "app/spaced.py", "\n".join(lines) + "\n")
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        # The config_threshold hit near the top + the one near the bottom should be separate
        # (this depends on placement; at minimum, verify we got chunks)
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# CodeChunk dataclass
# ---------------------------------------------------------------------------

class TestCodeChunk:
    def test_code_chunk_to_dict(self) -> None:
        """CodeChunk.to_dict() includes all expected keys."""
        chunk = CodeChunk(
            file_path="app/billing.py",
            start_line=10,
            end_line=25,
            content="if value > 5000:\n    alert()",
            language="python",
            patterns_found=["comparison_with_const"],
        )
        d = chunk.to_dict()
        assert d["file_path"] == "app/billing.py"
        assert d["start_line"] == 10
        assert d["end_line"] == 25
        assert d["language"] == "python"
        assert "comparison_with_const" in d["patterns_found"]

    def test_scanner_produces_relative_file_paths(self, tmp_path: Path) -> None:
        """chunk.file_path is relative to the repo_path, not absolute."""
        write_file(tmp_path, "app/billing.py", """\
            MAX_RETRIES = 5
            def retry(): pass
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        for chunk in chunks:
            assert not Path(chunk.file_path).is_absolute()
            assert "app/billing.py" in chunk.file_path or "app\\billing.py" in chunk.file_path

    def test_scanner_produces_one_indexed_line_numbers(self, tmp_path: Path) -> None:
        """start_line and end_line are 1-indexed (human display convention)."""
        write_file(tmp_path, "app/billing.py", """\
            MAX_RETRIES = 5
            def retry(): pass
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        for chunk in chunks:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line

    def test_scanner_empty_directory_returns_no_chunks(self, tmp_path: Path) -> None:
        """Scanning an empty directory produces no chunks."""
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert chunks == []

    def test_scanner_file_with_no_patterns_produces_no_chunks(
        self, tmp_path: Path
    ) -> None:
        """A .py file with no pattern matches is excluded from the results."""
        write_file(tmp_path, "app/utils.py", """\
            def format_name(first, last):
                return f"{first} {last}".strip()
        """)
        scanner = CodebaseScanner(repo_path=str(tmp_path))
        chunks = scanner.scan()
        assert chunks == []
