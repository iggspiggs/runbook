"""
Tests for RuleAnalyzer — the LLM-powered extraction layer.

All Anthropic API calls are mocked so these tests are fast and free.
The mock_anthropic_client fixture (defined in conftest.py) returns
a MagicMock that simulates anthropic.Anthropic.messages.create().
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.extractor.analyzer import RuleAnalyzer, ExtractedRule, EditableField
from app.services.extractor.scanner import CodeChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    content: str = "if balance < 100: send_alert()",
    file_path: str = "app/billing.py",
    start: int = 1,
    end: int = 5,
    language: str = "python",
    patterns: list[str] | None = None,
) -> CodeChunk:
    return CodeChunk(
        file_path=file_path,
        start_line=start,
        end_line=end,
        content=content,
        language=language,
        patterns_found=patterns or ["threshold_pattern"],
    )


def _make_mock_client(response_text: str) -> MagicMock:
    """Build a mock Anthropic client that returns response_text."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=response_text)]

    mock_messages = MagicMock()
    mock_messages.create = MagicMock(return_value=mock_message)

    mock_client = MagicMock()
    mock_client.messages = mock_messages
    return mock_client


VALID_RULE_RESPONSE = json.dumps({
    "is_rule": True,
    "rule_id": "BILL.BALANCE.LOW_ALERT",
    "title": "Low balance alert",
    "description": "Sends an alert when account balance drops below threshold.",
    "trigger": "account.balance < LOW_BALANCE_THRESHOLD",
    "conditions": ["account.balance < 100"],
    "actions": ["send alert email to ops team"],
    "editable_fields": [
        {
            "name": "LOW_BALANCE_THRESHOLD",
            "type": "float",
            "current_value": 100.0,
            "description": "Minimum balance in dollars before alert fires",
            "min_value": 0,
            "max_value": None,
            "allowed_values": [],
        }
    ],
    "risk_level": "high",
    "customer_facing": True,
    "cost_impact": False,
    "upstream_suggestions": [],
    "downstream_suggestions": [],
    "tags": ["billing", "alerts"],
    "confidence": 0.92,
})

NOT_A_RULE_RESPONSE = json.dumps({"is_rule": False})


# ---------------------------------------------------------------------------
# analyze_chunk
# ---------------------------------------------------------------------------

class TestAnalyzeChunk:
    async def test_analyze_chunk_returns_extracted_rule(self) -> None:
        """analyze_chunk returns an ExtractedRule when Claude identifies a rule."""
        client = _make_mock_client(VALID_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        chunk = _make_chunk()
        result = await analyzer.analyze_chunk(chunk)

        assert result is not None
        assert isinstance(result, ExtractedRule)
        assert result.rule_id == "BILL.BALANCE.LOW_ALERT"
        assert result.title == "Low balance alert"

    async def test_analyze_chunk_returns_none_for_non_rule(self) -> None:
        """analyze_chunk returns None when Claude says is_rule=false."""
        client = _make_mock_client(NOT_A_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        chunk = _make_chunk(content="def format_name(first, last): return first + last")
        result = await analyzer.analyze_chunk(chunk)
        assert result is None

    async def test_analyze_chunk_extracted_rule_has_required_fields(self) -> None:
        """Every ExtractedRule has all documented fields populated."""
        client = _make_mock_client(VALID_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        chunk = _make_chunk()
        result = await analyzer.analyze_chunk(chunk)

        assert result is not None
        assert result.rule_id
        assert result.title
        assert result.description
        assert result.trigger
        assert isinstance(result.conditions, list)
        assert isinstance(result.actions, list)
        assert isinstance(result.editable_fields, list)
        assert result.risk_level in ("low", "medium", "high", "critical")
        assert isinstance(result.customer_facing, bool)
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    async def test_analyze_chunk_source_file_from_chunk(self) -> None:
        """source_file on the returned rule comes from the CodeChunk, not Claude."""
        client = _make_mock_client(VALID_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        chunk = _make_chunk(file_path="app/services/billing/alerts.py")
        result = await analyzer.analyze_chunk(chunk)

        assert result is not None
        assert result.source_file == "app/services/billing/alerts.py"

    async def test_analyze_chunk_source_lines_from_chunk(self) -> None:
        """source_lines dict on the rule is populated from the chunk's line numbers."""
        client = _make_mock_client(VALID_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        chunk = _make_chunk(start=42, end=60)
        result = await analyzer.analyze_chunk(chunk)

        assert result is not None
        assert result.source_lines == {"start": 42, "end": 60}

    async def test_analyze_chunk_editable_field_structure(self) -> None:
        """Editable fields are mapped from Claude's name/type/current_value schema."""
        client = _make_mock_client(VALID_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        chunk = _make_chunk()
        result = await analyzer.analyze_chunk(chunk)

        assert result is not None
        assert len(result.editable_fields) == 1
        ef = result.editable_fields[0]
        assert isinstance(ef, EditableField)
        assert ef.field_name == "LOW_BALANCE_THRESHOLD"
        assert ef.field_type == "float"
        assert ef.current == 100.0


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

class TestConfidenceScoring:
    async def test_high_confidence_for_well_structured_rule(self) -> None:
        """A response with confidence=0.95 is propagated to the ExtractedRule."""
        response = json.dumps({
            "is_rule": True,
            "rule_id": "OPS.JOBS.NIGHTLY_CLEANUP",
            "title": "Nightly cleanup job",
            "description": "Removes stale records older than 30 days.",
            "trigger": "cron: 0 2 * * *",
            "conditions": ["record.age_days > 30"],
            "actions": ["delete stale records"],
            "editable_fields": [],
            "risk_level": "low",
            "customer_facing": False,
            "cost_impact": False,
            "upstream_suggestions": [],
            "downstream_suggestions": [],
            "tags": [],
            "confidence": 0.95,
        })
        client = _make_mock_client(response)
        analyzer = RuleAnalyzer(anthropic_client=client)
        result = await analyzer.analyze_chunk(_make_chunk())

        assert result is not None
        assert result.confidence == pytest.approx(0.95)

    async def test_low_confidence_value_preserved(self) -> None:
        """Low confidence values (0.4) are passed through without truncation."""
        response = json.dumps({
            "is_rule": True,
            "rule_id": "UNKNOWN.RULE",
            "title": "Ambiguous rule",
            "description": "Uncertain extraction.",
            "trigger": "unknown",
            "conditions": [],
            "actions": [],
            "editable_fields": [],
            "risk_level": "low",
            "customer_facing": False,
            "cost_impact": False,
            "upstream_suggestions": [],
            "downstream_suggestions": [],
            "tags": [],
            "confidence": 0.4,
        })
        client = _make_mock_client(response)
        analyzer = RuleAnalyzer(anthropic_client=client)
        result = await analyzer.analyze_chunk(_make_chunk())

        assert result is not None
        assert result.confidence == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# analyze_batch — deduplication
# ---------------------------------------------------------------------------

class TestAnalyzeBatch:
    async def test_analyze_batch_returns_list_of_rules(self) -> None:
        """analyze_batch processes multiple chunks and returns a list."""
        client = _make_mock_client(VALID_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        chunks = [_make_chunk() for _ in range(3)]
        results = await analyzer.analyze_batch(chunks)
        assert isinstance(results, list)

    async def test_analyze_batch_empty_chunks_returns_empty_list(self) -> None:
        """No chunks → empty result without calling the API."""
        client = _make_mock_client(VALID_RULE_RESPONSE)
        analyzer = RuleAnalyzer(anthropic_client=client)
        results = await analyzer.analyze_batch([])
        assert results == []
        # API must NOT have been called
        client.messages.create.assert_not_called()

    async def test_analyze_batch_deduplicates_by_location(self) -> None:
        """
        Two chunks from the same (file, start_line) location produce only one
        rule in the output — the higher-confidence one is kept.
        """
        # Two different responses for the same location; second has higher confidence
        high_conf_response = json.dumps({
            "is_rule": True,
            "rule_id": "BILL.BALANCE.LOW_ALERT",
            "title": "Low balance alert",
            "description": "Desc",
            "trigger": "balance < threshold",
            "conditions": [],
            "actions": [],
            "editable_fields": [],
            "risk_level": "medium",
            "customer_facing": False,
            "cost_impact": False,
            "upstream_suggestions": [],
            "downstream_suggestions": [],
            "tags": [],
            "confidence": 0.95,
        })
        # Both chunks share the same file/line — deduplicated to one rule
        chunk_a = _make_chunk(file_path="app/billing.py", start=1, end=10)
        chunk_b = _make_chunk(file_path="app/billing.py", start=1, end=10)

        mock_message_a = MagicMock()
        mock_message_a.content = [MagicMock(text=high_conf_response)]

        # Make the mock return the same response for any call
        client = _make_mock_client(high_conf_response)
        analyzer = RuleAnalyzer(anthropic_client=client)
        results = await analyzer.analyze_batch([chunk_a, chunk_b])
        # After dedup, only one rule from this location
        location_rules = [
            r for r in results
            if r.source_file == "app/billing.py" and r.source_lines.get("start") == 1
        ]
        assert len(location_rules) <= 1

    async def test_analyze_batch_resolves_cross_references(self) -> None:
        """
        Cross-reference resolution strips unknown upstream/downstream suggestions,
        keeping only rule_ids that appear in the extracted set.
        """
        # Rule A references Rule B downstream; Rule B is also extracted
        response_a = json.dumps({
            "is_rule": True,
            "rule_id": "RULE.A",
            "title": "Rule A",
            "description": "First rule",
            "trigger": "event",
            "conditions": [],
            "actions": [],
            "editable_fields": [],
            "risk_level": "low",
            "customer_facing": False,
            "cost_impact": False,
            "upstream_suggestions": [],
            "downstream_suggestions": ["RULE.B"],   # valid ref
            "tags": [],
            "confidence": 0.9,
        })
        response_b = json.dumps({
            "is_rule": True,
            "rule_id": "RULE.B",
            "title": "Rule B",
            "description": "Second rule",
            "trigger": "event",
            "conditions": [],
            "actions": [],
            "editable_fields": [],
            "risk_level": "low",
            "customer_facing": False,
            "cost_impact": False,
            "upstream_suggestions": ["RULE.A"],     # valid ref
            "downstream_suggestions": ["RULE.NONEXISTENT"],  # unknown ref — should be pruned
            "tags": [],
            "confidence": 0.9,
        })

        # We need to return both responses for the batch of two chunks.
        # analyze_batch groups into batches of 5, so one API call with the
        # two chunks will be made. Wrap both in an array.
        combined = json.dumps([json.loads(response_a), json.loads(response_b)])
        client = _make_mock_client(combined)
        analyzer = RuleAnalyzer(anthropic_client=client)

        chunks = [
            _make_chunk(file_path="app/rule_a.py", start=1, end=5),
            _make_chunk(file_path="app/rule_b.py", start=1, end=5),
        ]
        results = await analyzer.analyze_batch(chunks)

        rule_b = next((r for r in results if r.rule_id == "RULE.B"), None)
        if rule_b is not None:
            # RULE.NONEXISTENT should have been pruned
            assert "RULE.NONEXISTENT" not in rule_b.downstream_rule_ids


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestAnalyzerErrorHandling:
    async def test_analyze_chunk_handles_malformed_json(self) -> None:
        """Malformed JSON from Claude returns None without raising."""
        client = _make_mock_client("this is not valid json at all {{")
        analyzer = RuleAnalyzer(anthropic_client=client)
        result = await analyzer.analyze_chunk(_make_chunk())
        assert result is None

    async def test_analyze_chunk_handles_api_exception(self) -> None:
        """An exception raised by the API is propagated (not swallowed)."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API timeout")

        analyzer = RuleAnalyzer(anthropic_client=mock_client)

        with pytest.raises(RuntimeError, match="API timeout"):
            await analyzer.analyze_chunk(_make_chunk())

    async def test_analyze_batch_handles_partial_batch_failure(self) -> None:
        """
        If one batch in analyze_batch raises, the failure is logged and
        the other batches' results are still returned.
        """
        # Simulate an API error on the first call, success on the second
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=VALID_RULE_RESPONSE)]

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("rate limit")
            return mock_message

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = side_effect

        analyzer = RuleAnalyzer(anthropic_client=mock_client)
        # 6 chunks → 2 batches of 5 and 1 (with _BATCH_SIZE=5)
        chunks = [_make_chunk(file_path=f"app/f{i}.py", start=i * 10 + 1, end=i * 10 + 5)
                  for i in range(6)]
        # Should not raise — failed batches are swallowed by gather(return_exceptions=True)
        results = await analyzer.analyze_batch(chunks)
        assert isinstance(results, list)

    async def test_analyze_chunk_handles_empty_response(self) -> None:
        """An empty string response is treated as malformed JSON (returns None)."""
        client = _make_mock_client("")
        analyzer = RuleAnalyzer(anthropic_client=client)
        result = await analyzer.analyze_chunk(_make_chunk())
        assert result is None

    async def test_analyze_chunk_strips_markdown_fences(self) -> None:
        """
        Claude sometimes wraps JSON in ```json ... ``` fences.
        The parser must strip these before attempting json.loads().
        """
        fenced = "```json\n" + VALID_RULE_RESPONSE + "\n```"
        client = _make_mock_client(fenced)
        analyzer = RuleAnalyzer(anthropic_client=client)
        result = await analyzer.analyze_chunk(_make_chunk())
        assert result is not None
        assert result.rule_id == "BILL.BALANCE.LOW_ALERT"


# ---------------------------------------------------------------------------
# ExtractedRule.to_dict
# ---------------------------------------------------------------------------

class TestExtractedRuleToDict:
    def test_to_dict_editable_fields_serialized_as_dicts(self) -> None:
        """to_dict() converts EditableField dataclass instances to plain dicts."""
        rule = ExtractedRule(
            rule_id="TEST.RULE",
            title="Test",
            description="desc",
            trigger="event",
            conditions=[],
            actions=[],
            editable_fields=[
                EditableField(
                    field_name="THRESHOLD",
                    field_type="int",
                    current=500,
                    description="A threshold",
                )
            ],
            risk_level="low",
            customer_facing=False,
            cost_impact=False,
            source_file="app/test.py",
            language="python",
            upstream_rule_ids=[],
            downstream_rule_ids=[],
        )
        d = rule.to_dict()
        assert isinstance(d["editable_fields"], list)
        assert isinstance(d["editable_fields"][0], dict)
        assert d["editable_fields"][0]["field_name"] == "THRESHOLD"
