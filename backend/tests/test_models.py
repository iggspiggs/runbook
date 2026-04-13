"""
Tests for SQLAlchemy model construction, serialisation, and invariants.

Covers:
  - Rule: creation, to_dict() output types, all field presence
  - AuditLog: creation, immutability (no updated_at), to_dict()
  - Tenant: creation, plan defaulting
  - ExtractionJob: creation, status enum, duration_seconds property
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.rule import (
    Rule,
    STATUS_ACTIVE,
    STATUS_DRAFT,
    RISK_HIGH,
    RISK_MEDIUM,
)
from app.models.audit_log import AuditLog, AuditAction
from app.models.tenant import Tenant, PLAN_FREE, PLAN_PRO
from app.models.extraction_job import ExtractionJob, JobStatus, SourceType


# ---------------------------------------------------------------------------
# Rule model
# ---------------------------------------------------------------------------

class TestRuleModel:
    def test_rule_creation_all_fields(self, sample_rule: Rule) -> None:
        """Rule fixture has all expected fields populated."""
        assert sample_rule.rule_id == "SCN.RECIPIENTS.HIGH_VALUE_CC"
        assert sample_rule.title == "High-value contract CC recipients"
        assert sample_rule.status == STATUS_ACTIVE
        assert sample_rule.risk_level == RISK_MEDIUM
        assert sample_rule.department == "shipping"
        assert sample_rule.subsystem == "recipients"
        assert sample_rule.language == "python"
        assert sample_rule.confidence == pytest.approx(0.97)
        assert sample_rule.verified is False
        assert isinstance(sample_rule.id, uuid.UUID)
        assert isinstance(sample_rule.tenant_id, uuid.UUID)

    def test_rule_editable_fields_structure(self, sample_rule: Rule) -> None:
        """editable_fields stores a list of field definition dicts."""
        assert isinstance(sample_rule.editable_fields, list)
        assert len(sample_rule.editable_fields) == 2
        names = {ef["field_name"] for ef in sample_rule.editable_fields}
        assert names == {"HIGH_VALUE_THRESHOLD", "EXECUTIVE_CC"}

    def test_rule_to_dict_uuid_serialized_as_string(self, sample_rule: Rule) -> None:
        """to_dict() converts UUID fields to strings."""
        d = sample_rule.to_dict()
        assert isinstance(d["id"], str)
        assert isinstance(d["tenant_id"], str)
        # Round-trip: must be valid UUIDs
        uuid.UUID(d["id"])
        uuid.UUID(d["tenant_id"])

    def test_rule_to_dict_datetime_serialized_as_iso_string(self, sample_rule: Rule) -> None:
        """to_dict() converts datetime fields to ISO-8601 strings."""
        d = sample_rule.to_dict()
        # created_at and updated_at come from TimestampMixin and are always set
        assert isinstance(d["created_at"], str)
        assert isinstance(d["updated_at"], str)
        # Should parse without error
        datetime.fromisoformat(d["created_at"])
        datetime.fromisoformat(d["updated_at"])

    def test_rule_to_dict_none_values_preserved(self, sample_rule: Rule) -> None:
        """None columns are emitted as None, not omitted."""
        d = sample_rule.to_dict()
        # verified_at is None because the rule has not been verified
        assert d["verified_at"] is None
        assert d["last_changed"] is None

    def test_rule_to_dict_metadata_key_alias(self, sample_rule: Rule) -> None:
        """The metadata_ column is exposed under the 'metadata' key."""
        d = sample_rule.to_dict()
        assert "metadata" in d
        assert "metadata_" not in d

    def test_rule_to_dict_all_expected_keys_present(self, sample_rule: Rule) -> None:
        """to_dict() emits every documented field — no surprises for API clients."""
        d = sample_rule.to_dict()
        expected_keys = {
            "id", "tenant_id", "rule_id", "slug", "title", "description", "why",
            "department", "subsystem", "owner", "tags", "status", "trigger",
            "conditions", "actions", "actors", "editable_fields",
            "editable_field_values", "upstream_rule_ids", "downstream_rule_ids",
            "source_file", "source_start_line", "source_end_line", "source_content",
            "language", "confidence", "verified", "verified_by", "verified_at",
            "risk_level", "cost_impact", "customer_facing", "last_changed",
            "last_changed_by", "metadata", "created_at", "updated_at",
        }
        assert expected_keys.issubset(d.keys())

    def test_rule_default_status_active(self, sample_tenant: Tenant) -> None:
        """Rules default to STATUS_ACTIVE when status is not specified."""
        rule = Rule(
            tenant_id=sample_tenant.id,
            title="Test Rule",
        )
        assert rule.status == STATUS_ACTIVE

    def test_rule_repr(self, sample_rule: Rule) -> None:
        """__repr__ includes rule_id and status for easy debugging."""
        r = repr(sample_rule)
        assert "SCN.RECIPIENTS.HIGH_VALUE_CC" in r
        assert "active" in r


# ---------------------------------------------------------------------------
# AuditLog model
# ---------------------------------------------------------------------------

class TestAuditLogModel:
    def test_audit_log_creation(self, sample_tenant: Tenant) -> None:
        """AuditLog can be constructed with all required fields."""
        log = AuditLog(
            tenant_id=sample_tenant.id,
            rule_id="SCN.RECIPIENTS.HIGH_VALUE_CC",
            rule_title="High-value contract CC recipients",
            action=AuditAction.EDITABLE_UPDATE,
            field_name="HIGH_VALUE_THRESHOLD",
            old_value="500000",
            new_value="750000",
            changed_by="alice@acme.com",
            reason="Adjusted for Q4 budget cycle",
        )
        assert log.action == AuditAction.EDITABLE_UPDATE
        assert log.changed_by == "alice@acme.com"
        assert log.field_name == "HIGH_VALUE_THRESHOLD"

    def test_audit_log_has_no_updated_at(self) -> None:
        """
        AuditLog is immutable: it uses UUIDMixin but NOT TimestampMixin,
        so it must NOT have an updated_at attribute.
        """
        assert not hasattr(AuditLog, "updated_at") or "updated_at" not in AuditLog.__table__.c

    def test_audit_log_to_dict_uuid_as_string(self, sample_tenant: Tenant) -> None:
        """AuditLog.to_dict() converts UUID fields to strings."""
        log = AuditLog(
            tenant_id=sample_tenant.id,
            rule_id="SCN.RECIPIENTS.HIGH_VALUE_CC",
            action="verify",
            changed_by="alice@acme.com",
        )
        # Manually set id and created_at so to_dict works without a DB flush
        log.id = uuid.uuid4()
        log.created_at = datetime.now(timezone.utc)
        d = log.to_dict()
        assert isinstance(d["id"], str)
        assert isinstance(d["tenant_id"], str)
        uuid.UUID(d["id"])

    def test_audit_log_to_dict_timestamp_alias(self, sample_tenant: Tenant) -> None:
        """
        to_dict() exposes 'timestamp' as an alias for created_at to match
        the CSV export field names documented in audit.py.
        """
        log = AuditLog(
            tenant_id=sample_tenant.id,
            rule_id="SCN.RECIPIENTS.HIGH_VALUE_CC",
            action="verify",
            changed_by="system",
        )
        log.id = uuid.uuid4()
        log.created_at = datetime.now(timezone.utc)
        d = log.to_dict()
        assert "timestamp" in d
        assert "created_at" in d
        assert d["timestamp"] == d["created_at"]

    def test_audit_log_to_dict_all_keys_present(self, sample_tenant: Tenant) -> None:
        """to_dict() emits all documented audit fields."""
        log = AuditLog(
            tenant_id=sample_tenant.id,
            rule_id="TEST.RULE.ID",
            action="editable_update",
            changed_by="bob@acme.com",
        )
        log.id = uuid.uuid4()
        log.created_at = datetime.now(timezone.utc)
        d = log.to_dict()
        for key in ("id", "tenant_id", "rule_id", "rule_title", "action",
                    "field_name", "old_value", "new_value", "changed_by",
                    "reason", "timestamp", "created_at"):
            assert key in d, f"Missing key in AuditLog.to_dict(): {key!r}"

    def test_audit_action_enum_values(self) -> None:
        """AuditAction enum covers all expected action strings."""
        expected = {
            "created", "updated", "approved", "rejected", "paused",
            "activated", "editable_update", "status_change", "verify",
            "extraction_create", "extraction_update",
        }
        actual = {a.value for a in AuditAction}
        assert expected == actual


# ---------------------------------------------------------------------------
# Tenant model
# ---------------------------------------------------------------------------

class TestTenantModel:
    def test_tenant_creation(self, sample_tenant: Tenant) -> None:
        """Tenant fixture is persisted with expected fields."""
        assert sample_tenant.name == "Acme Logistics"
        assert sample_tenant.slug == "acme-logistics"
        assert sample_tenant.plan == PLAN_PRO
        assert isinstance(sample_tenant.id, uuid.UUID)

    def test_tenant_default_plan_is_free(self) -> None:
        """New Tenant instances default to the free plan."""
        tenant = Tenant(name="Trial Corp", slug="trial-corp")
        assert tenant.plan == PLAN_FREE

    def test_tenant_repr(self, sample_tenant: Tenant) -> None:
        """__repr__ includes the slug for quick identification."""
        r = repr(sample_tenant)
        assert "acme-logistics" in r

    def test_tenant_settings_json(self, sample_tenant: Tenant) -> None:
        """settings column stores and retrieves arbitrary JSON."""
        assert sample_tenant.settings["feature_flags"]["simulation"] is True


# ---------------------------------------------------------------------------
# ExtractionJob model
# ---------------------------------------------------------------------------

class TestExtractionJobModel:
    def test_extraction_job_creation(self, sample_tenant: Tenant) -> None:
        """ExtractionJob can be constructed with required fields."""
        job = ExtractionJob(
            tenant_id=sample_tenant.id,
            status=JobStatus.PENDING,
            source_type=SourceType.GIT_REPO,
            source_uri="https://github.com/acme/backend.git",
            branch="main",
        )
        assert job.status == JobStatus.PENDING
        assert job.source_type == SourceType.GIT_REPO
        assert job.rules_found == 0
        assert job.rules_new == 0

    def test_extraction_job_default_status_is_pending(self, sample_tenant: Tenant) -> None:
        """status defaults to PENDING when not specified."""
        job = ExtractionJob(
            tenant_id=sample_tenant.id,
            source_type=SourceType.MANUAL,
            source_uri="/local/path",
        )
        assert job.status == JobStatus.PENDING

    def test_extraction_job_status_transitions(self, sample_tenant: Tenant) -> None:
        """Status can be transitioned through all valid values."""
        job = ExtractionJob(
            tenant_id=sample_tenant.id,
            source_type=SourceType.MANUAL,
            source_uri="/local/path",
        )
        for transition_status in (
            JobStatus.SCANNING,
            JobStatus.EXTRACTING,
            JobStatus.REVIEWING,
            JobStatus.COMPLETE,
        ):
            job.status = transition_status
            assert job.status == transition_status

    def test_extraction_job_failed_status(self, sample_tenant: Tenant) -> None:
        """Status can be set to FAILED with an error message."""
        job = ExtractionJob(
            tenant_id=sample_tenant.id,
            source_type=SourceType.GIT_REPO,
            source_uri="https://github.com/acme/backend.git",
        )
        job.status = JobStatus.FAILED
        job.error = "git clone timed out after 30s"
        assert job.status == JobStatus.FAILED
        assert "timed out" in job.error

    def test_extraction_job_duration_seconds_none_without_timestamps(
        self, sample_tenant: Tenant
    ) -> None:
        """duration_seconds returns None when timing data is absent."""
        job = ExtractionJob(
            tenant_id=sample_tenant.id,
            source_type=SourceType.MANUAL,
            source_uri="/path",
        )
        assert job.duration_seconds is None

    def test_extraction_job_duration_seconds_computed(
        self, sample_tenant: Tenant
    ) -> None:
        """duration_seconds returns the wall-clock difference in seconds."""
        from datetime import timedelta

        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=42)
        job = ExtractionJob(
            tenant_id=sample_tenant.id,
            source_type=SourceType.MANUAL,
            source_uri="/path",
            started_at=start,
            completed_at=end,
        )
        assert job.duration_seconds == pytest.approx(42.0)

    def test_extraction_job_repr(self, sample_tenant: Tenant) -> None:
        """__repr__ includes status and rules_found for debugging."""
        job = ExtractionJob(
            tenant_id=sample_tenant.id,
            source_type=SourceType.MANUAL,
            source_uri="/path",
            rules_found=7,
        )
        job.id = uuid.uuid4()
        r = repr(job)
        assert "pending" in r
        assert "7" in r

    def test_job_status_enum_string_values(self) -> None:
        """JobStatus values are correct strings (used in API responses)."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.SCANNING.value == "scanning"
        assert JobStatus.EXTRACTING.value == "extracting"
        assert JobStatus.REVIEWING.value == "reviewing"
        assert JobStatus.COMPLETE.value == "complete"
        assert JobStatus.FAILED.value == "failed"

    def test_source_type_enum_string_values(self) -> None:
        """SourceType values are correct strings."""
        assert SourceType.GIT_REPO.value == "git_repo"
        assert SourceType.API_SCAN.value == "api_scan"
        assert SourceType.MANUAL.value == "manual"
