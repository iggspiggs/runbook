"""
runbook_sdk
===========

Python SDK for annotating automation rules in your codebase so the Runbook
scanner can discover, extract, and register them.

Quick start
-----------
::

    from runbook_sdk import rule, editable, trigger, RunbookRegistry

    @rule(
        id="SCN.RECIPIENTS.HIGH_VALUE_CC",
        title="High-value contract CC recipients",
        department="shipping",
        risk_level="medium",
        why="Ensures leadership visibility on large deals",
    )
    @editable(
        "threshold",
        type="number",
        default=500_000,
        description="Contract value threshold for CC logic",
        validation={"min": 0},
    )
    @editable(
        "cc_list",
        type="list",
        default=["vp@company.com"],
        description="CC recipients for high-value contracts",
    )
    @trigger("contract_value > threshold")
    def get_scn_recipients(contract):
        ...

Programmatic extraction
-----------------------
::

    import my_package
    registry = RunbookRegistry()
    registry.scan_package("/path/to/my_package")
    registry.push("https://api.runbook.io", api_key="rb_live_...")
"""

from runbook_sdk.decorators import (
    RunbookRegistry,
    editable,
    rule,
    trigger,
)
from runbook_sdk.models import (
    Actor,
    EditableField,
    ExtractionMetadata,
    ExtractionResult,
    FieldValidation,
    RuleDefinition,
)

__version__ = "0.1.0"
__all__ = [
    # Decorators
    "rule",
    "editable",
    "trigger",
    # Registry
    "RunbookRegistry",
    # Models
    "RuleDefinition",
    "EditableField",
    "FieldValidation",
    "Actor",
    "ExtractionResult",
    "ExtractionMetadata",
]
