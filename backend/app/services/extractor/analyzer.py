"""
RuleAnalyzer — LLM-powered extraction of structured automation rules
from raw code chunks produced by CodebaseScanner.

Design notes:
- Each CodeChunk is sent to Claude with a detailed system prompt.
- Claude returns a JSON object (or null if the chunk is not a rule).
- Batching: chunks are grouped into prompt batches to reduce API round-trips
  while staying well under the context window limit.
- Deduplication: after batch processing, rules with overlapping source
  locations or identical titles are merged.
- Cross-references: a second pass resolves upstream/downstream suggestions
  into confirmed rule IDs from the extracted set.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import anthropic

from app.services.extractor.scanner import CodeChunk

logger = logging.getLogger(__name__)

_MODEL = "claude-opus-4-5"
_MAX_TOKENS = 4096
_BATCH_SIZE = 5          # chunks per API call (tune for cost vs. latency)
_MAX_CONCURRENCY = 3     # parallel API calls


# ---------------------------------------------------------------------------
# Extracted rule DTO
# ---------------------------------------------------------------------------

@dataclass
class EditableField:
    # These names match the model's editable_fields JSON item schema exactly:
    # field_name, field_type, current (current_value stored as "current"),
    # default, description, editable_by, validation.
    field_name: str
    field_type: str                    # str | int | float | bool | list | email_list
    current: Any                       # current value (matches model "current" key)
    description: str
    default: Any = None
    editable_by: str = "operator"
    validation: Optional[Dict[str, Any]] = None


@dataclass
class ExtractedRule:
    # Field names below match model column names so that to_dict() output can
    # be passed directly to RuleService.upsert_from_extraction().
    rule_id: str                        # Business string key, e.g. "send-low-balance-alert"
    title: str
    description: str
    trigger: str                        # What event / schedule fires this rule
    conditions: List[str]              # Human-readable condition list
    actions: List[str]                 # What the rule does when conditions are met
    editable_fields: List[EditableField]
    risk_level: str                    # low | medium | high | critical
    customer_facing: bool
    cost_impact: bool
    source_file: str
    language: str
    upstream_rule_ids: List[str]       # Resolved rule_id strings (after cross-ref pass)
    downstream_rule_ids: List[str]     # Resolved rule_id strings (after cross-ref pass)
    # source_lines is stored as {"start": N, "end": N} per model spec
    source_lines: Dict[str, int] = field(default_factory=dict)
    source_content: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0            # 0.0–1.0, Claude's self-assessed confidence

    def to_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d["editable_fields"] = [ef.__dict__ for ef in self.editable_fields]
        return d


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an expert software architect specializing in identifying and documenting automation rules, business logic, and operational workflows in source code.

Your task is to analyze code snippets and extract structured "automation rules" — discrete units of logic that:
- Fire on a schedule, event, or threshold crossing
- Enforce a business policy (e.g., "if balance < $100, send alert")
- Trigger side effects (emails, notifications, API calls, database writes, state changes)
- Control flow via configurable thresholds, limits, or parameters

**What counts as an automation rule:**
- Scheduled tasks / cron jobs (billing runs, cleanup jobs, report generation)
- Event handlers (on_payment_received, on_user_signup, webhook handlers)
- Threshold-based alerts (CPU > 90%, balance < $50, error_rate > 5%)
- Retry and circuit-breaker policies
- Rate limits and quota enforcement
- Approval gates and escalation workflows
- Notification routing rules (who gets paged, under what conditions)
- Feature flags tied to business conditions

**What does NOT count:**
- Pure data transformation with no side effects
- Unit test code
- Database migration scripts
- Logging boilerplate
- Generic utility functions with no business semantics

**Output format (strict JSON, no markdown fences):**
Return a single JSON object with this exact schema. If the snippet is NOT an automation rule, return exactly: {"is_rule": false}

{
  "is_rule": true,
  "rule_id": "<kebab-case-slug, descriptive, globally unique suggestion>",
  "title": "<Short human-readable title, max 80 chars>",
  "description": "<1-3 sentences describing what this rule does and why it exists>",
  "trigger": "<What causes this rule to fire: schedule/cron expression, event name, API call, threshold crossing>",
  "conditions": ["<condition 1>", "<condition 2>"],
  "actions": ["<action 1>", "<action 2>"],
  "editable_fields": [
    {
      "name": "<field_name as it appears in code>",
      "type": "<str|int|float|bool|list|email_list>",
      "current_value": <the literal value from the code>,
      "description": "<what this parameter controls>",
      "min_value": null,
      "max_value": null,
      "allowed_values": []
    }
  ],
  "risk_level": "<low|medium|high|critical>",
  "customer_facing": <true if this rule directly affects customers/users>,
  "cost_impact": <true if changing this rule could increase/decrease costs>,
  "upstream_suggestions": ["<rule_id slugs of rules this depends on>"],
  "downstream_suggestions": ["<rule_id slugs of rules that depend on this>"],
  "tags": ["<relevant tag>"],
  "confidence": <0.0-1.0 float>
}

**Risk level guidance:**
- low: Internal tooling, metrics collection, non-critical notifications
- medium: Customer notifications, non-financial data changes, retry policies
- high: Financial transactions, user-facing feature gates, data deletion
- critical: Billing, payments, account suspension, security policies

**Editable fields guidance:**
Only include fields that a non-technical operator could safely change without understanding the underlying code — e.g., thresholds, recipient lists, time intervals, retry counts, on/off toggles. Never include things like database connection strings, API keys, or code logic.

Be thorough. Many rules have multiple editable parameters. If you see a hardcoded number next to a conditional, it is almost certainly an editable threshold."""


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class RuleAnalyzer:
    """
    Sends CodeChunks to Claude and returns a deduplicated list of
    ExtractedRule objects.
    """

    def __init__(self, anthropic_client: anthropic.Anthropic) -> None:
        self._client = anthropic_client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def analyze_chunk(self, chunk: CodeChunk) -> Optional[ExtractedRule]:
        """
        Analyze a single chunk. Returns None if Claude determines the
        chunk does not contain an automation rule.
        """
        user_message = self._build_user_message([chunk])
        response_text = await self._call_claude(user_message)
        results = self._parse_response(response_text, [chunk])
        return results[0] if results else None

    async def analyze_batch(
        self,
        chunks: List[CodeChunk],
        agent_logger: Optional[Any] = None,
    ) -> List[ExtractedRule]:
        """
        Process all chunks in parallel batches, then deduplicate and
        resolve cross-references.

        If an ``agent_logger`` is provided, one AgentRun record is emitted per
        batch with model name, token counts, and duration — surfaced on the
        /agent-logs page so operators can see exactly what the LLM did.
        """
        if not chunks:
            return []

        # Split into batches
        batches = [chunks[i : i + _BATCH_SIZE] for i in range(0, len(chunks), _BATCH_SIZE)]
        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def process_batch(idx: int, batch: List[CodeChunk]) -> List[ExtractedRule]:
            async with semaphore:
                message = self._build_user_message(batch)
                if agent_logger is None:
                    response_text = await self._call_claude(message)
                else:
                    label = (
                        batch[0].file_path
                        if len(batch) == 1
                        else f"{batch[0].file_path} (+{len(batch)-1} more)"
                    )
                    async with agent_logger.run(
                        step_index=idx,
                        step_label=label,
                        input_summary=message,
                    ) as rec:
                        response_obj = await self._call_claude_raw(message)
                        rec.set_anthropic_response(response_obj)
                        response_text = (
                            response_obj.content[0].text if response_obj.content else ""
                        )
                return self._parse_response(response_text, batch)

        task_results = await asyncio.gather(
            *[process_batch(i, b) for i, b in enumerate(batches)],
            return_exceptions=True,
        )

        all_rules: List[ExtractedRule] = []
        for result in task_results:
            if isinstance(result, Exception):
                logger.error("Batch analysis failed: %s", result)
                continue
            all_rules.extend(result)

        deduped = self._deduplicate(all_rules)
        resolved = self._resolve_cross_references(deduped)
        logger.info("Extracted %d rules from %d chunks", len(resolved), len(chunks))
        return resolved

    # ------------------------------------------------------------------
    # Claude API
    # ------------------------------------------------------------------

    async def _call_claude(self, user_message: str) -> str:
        resp = await self._call_claude_raw(user_message)
        return resp.content[0].text if resp.content else ""

    async def _call_claude_raw(self, user_message: str):
        """
        Returns the raw anthropic Message object so callers (like the agent
        logger) can read model, usage, and stop_reason.
        """
        loop = asyncio.get_event_loop()

        def _sync_call():
            return self._client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

        return await loop.run_in_executor(None, _sync_call)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_user_message(self, chunks: List[CodeChunk]) -> str:
        """
        Build a user message that includes all chunks in the batch.
        For a single chunk, we ask for one JSON object.
        For multiple chunks, we ask for a JSON array of objects.
        """
        if len(chunks) == 1:
            c = chunks[0]
            return (
                f"Analyze the following code snippet and extract any automation rule.\n\n"
                f"File: {c.file_path} (lines {c.start_line}–{c.end_line})\n"
                f"Language: {c.language}\n"
                f"Patterns detected: {', '.join(c.patterns_found)}\n\n"
                f"```{c.language}\n{c.content}\n```\n\n"
                f"Return a single JSON object as described."
            )

        parts = [
            f"Analyze the following {len(chunks)} code snippets. "
            f"For each one, return a JSON object as described. "
            f"Wrap all results in a JSON array: [{{...}}, {{...}}]\n"
        ]
        for i, c in enumerate(chunks, 1):
            parts.append(
                f"\n--- Snippet {i} ---\n"
                f"File: {c.file_path} (lines {c.start_line}–{c.end_line})\n"
                f"Language: {c.language}\n"
                f"Patterns detected: {', '.join(c.patterns_found)}\n\n"
                f"```{c.language}\n{c.content}\n```"
            )
        parts.append(
            "\nReturn a JSON array with exactly one element per snippet (in order). "
            "Use {\"is_rule\": false} for snippets that are not automation rules."
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self, response_text: str, chunks: List[CodeChunk]
    ) -> List[ExtractedRule]:
        """
        Parse Claude's response (single object or array) into ExtractedRule
        instances. Gracefully handles malformed JSON by logging and skipping.
        """
        # Strip any accidental markdown fences
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", response_text).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Claude response as JSON: %s\n%s", exc, cleaned[:500])
            return []

        # Normalise to list
        if isinstance(data, dict):
            data = [data]

        results: List[ExtractedRule] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict) or not item.get("is_rule", False):
                continue
            source_chunk = chunks[i] if i < len(chunks) else chunks[-1]
            try:
                rule = self._dict_to_rule(item, source_chunk)
                results.append(rule)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Failed to build ExtractedRule from item %d: %s", i, exc)

        return results

    def _dict_to_rule(self, data: Dict[str, Any], chunk: CodeChunk) -> ExtractedRule:
        # Claude returns editable fields using "name"/"type"/"current_value" keys.
        # We remap to the model's field_name/field_type/current schema here so
        # the resulting dicts are ready for upsert_from_extraction without
        # any further translation.
        editable_fields = [
            EditableField(
                field_name=ef.get("name", ""),
                field_type=ef.get("type", "str"),
                current=ef.get("current_value"),
                description=ef.get("description", ""),
                default=ef.get("current_value"),   # default = the extracted literal value
                editable_by="operator",
                validation={
                    k: ef[k]
                    for k in ("min_value", "max_value", "allowed_values")
                    if ef.get(k) is not None
                } or None,
            )
            for ef in data.get("editable_fields", [])
        ]
        # Claude uses upstream_suggestions / downstream_suggestions; store under
        # the model column names immediately so to_dict() emits correct keys.
        return ExtractedRule(
            rule_id=data["rule_id"],
            title=data["title"],
            description=data["description"],
            trigger=data.get("trigger", "unknown"),
            conditions=data.get("conditions", []),
            actions=data.get("actions", []),
            editable_fields=editable_fields,
            risk_level=data.get("risk_level", "medium"),
            customer_facing=bool(data.get("customer_facing", False)),
            cost_impact=bool(data.get("cost_impact", False)),
            source_file=chunk.file_path,
            source_lines={"start": chunk.start_line, "end": chunk.end_line},
            source_content=chunk.content,
            language=chunk.language,
            upstream_rule_ids=data.get("upstream_suggestions", []),
            downstream_rule_ids=data.get("downstream_suggestions", []),
            tags=data.get("tags", []),
            confidence=float(data.get("confidence", 1.0)),
        )

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _deduplicate(self, rules: List[ExtractedRule]) -> List[ExtractedRule]:
        """
        Remove duplicates by merging rules that refer to the same source
        location or share an identical title. Keeps the higher-confidence
        version when merging.
        """
        seen_locations: Dict[str, ExtractedRule] = {}
        seen_titles: Dict[str, ExtractedRule] = {}
        unique: List[ExtractedRule] = []

        for rule in rules:
            loc_key = f"{rule.source_file}:{rule.source_lines.get('start', 0)}"
            title_key = rule.title.lower().strip()

            if loc_key in seen_locations:
                existing = seen_locations[loc_key]
                if rule.confidence > existing.confidence:
                    # Replace the lower-confidence version
                    unique.remove(existing)
                    seen_locations[loc_key] = rule
                    seen_titles[title_key] = rule
                    unique.append(rule)
                continue

            if title_key in seen_titles:
                existing = seen_titles[title_key]
                if rule.confidence > existing.confidence:
                    unique.remove(existing)
                    seen_titles[title_key] = rule
                    seen_locations[loc_key] = rule
                    unique.append(rule)
                continue

            seen_locations[loc_key] = rule
            seen_titles[title_key] = rule
            unique.append(rule)

        return unique

    def _resolve_cross_references(self, rules: List[ExtractedRule]) -> List[ExtractedRule]:
        """
        Claude suggests upstream/downstream by slug.  Validate those slugs
        against the actual extracted set and remove unresolvable references.
        This keeps the registry graph clean.
        """
        known_ids = {r.rule_id for r in rules}
        for rule in rules:
            rule.upstream_rule_ids = [
                ref for ref in rule.upstream_rule_ids if ref in known_ids
            ]
            rule.downstream_rule_ids = [
                ref for ref in rule.downstream_rule_ids if ref in known_ids
            ]
        return rules
