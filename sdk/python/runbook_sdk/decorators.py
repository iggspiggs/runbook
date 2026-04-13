"""
runbook_sdk.decorators
======================

Zero-runtime-overhead decorators that annotate functions and classes with
structured metadata for the Runbook extraction scanner.

Decoration order (bottom-to-top in source):

    @rule(id="...", title="...", ...)          # outermost — applied last
    @editable("threshold", type="number", ...) # stacks into __runbook_editable__
    @editable("cc_list",   type="list",   ...) # stacks into __runbook_editable__
    @trigger("contract_value > threshold")     # sets __runbook_trigger__
    def my_function(...):
        ...

None of these decorators alter calling convention, return values, or
exception behaviour.  They only write dunder attributes onto the wrapped
callable or class.

Attributes written
------------------
__runbook_rule__     dict   — core rule metadata (@rule)
__runbook_editable__ list   — editable field specs (@editable, ordered)
__runbook_trigger__  str    — human-readable trigger description (@trigger)
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Literal, Optional, TypeVar, Union, overload

F = TypeVar("F", bound=Union[Callable[..., Any], type])

# Sentinel so we can distinguish "not provided" from None/False/0
_MISSING = object()

FieldType = Literal["string", "number", "boolean", "select", "list", "email", "json"]
EditableBy = Literal["operator", "admin", "dev"]


# ── @rule ─────────────────────────────────────────────────────────────────────


def rule(
    *,
    id: str,
    title: str,
    department: Optional[str] = None,
    subsystem: Optional[str] = None,
    description: Optional[str] = None,
    why: Optional[str] = None,
    risk_level: Optional[Literal["low", "medium", "high", "critical"]] = None,
    owner: Optional[str] = None,
    tags: Optional[list[str]] = None,
    customer_facing: Optional[bool] = None,
    cost_impact: Optional[str] = None,
    status: Literal["active", "paused", "planned", "deferred"] = "active",
) -> Callable[[F], F]:
    """
    Declare that a function or class represents an automation rule.

    Parameters
    ----------
    id:
        Stable, human-readable rule identifier scoped to the tenant.
        Convention: ``DEPARTMENT.SUBSYSTEM.SPECIFIC``
        Example:    ``"SCN.RECIPIENTS.HIGH_VALUE_CC"``
    title:
        Short human-readable name shown in the dashboard.
    department:
        Owning department (e.g. ``"shipping"``, ``"finance"``).
    subsystem:
        Sub-component within the department (e.g. ``"notifications"``).
    description:
        Longer explanation of what this rule does.
    why:
        Business justification — why does this rule exist?
    risk_level:
        ``"low"`` | ``"medium"`` | ``"high"`` | ``"critical"``
    owner:
        Team or person responsible for this rule.
    tags:
        Free-form tags for filtering/grouping in the dashboard.
    customer_facing:
        ``True`` if this rule has a direct customer-visible effect.
    cost_impact:
        Free-text description of cost/financial implications.
    status:
        Initial lifecycle status (default ``"active"``).

    Returns
    -------
    Callable
        The original function/class with ``__runbook_rule__`` attached.

    Example
    -------
    >>> @rule(
    ...     id="SCN.RECIPIENTS.HIGH_VALUE_CC",
    ...     title="High-value contract CC recipients",
    ...     department="shipping",
    ...     risk_level="medium",
    ...     why="Ensures leadership visibility on large deals",
    ... )
    ... def get_scn_recipients(contract):
    ...     ...
    """
    metadata: dict[str, Any] = {
        "id": id,
        "title": title,
        "status": status,
    }
    # Only include optional fields when provided so the scanner can distinguish
    # "not set" from an explicit None.
    _optionals = {
        "department": department,
        "subsystem": subsystem,
        "description": description,
        "why": why,
        "risk_level": risk_level,
        "owner": owner,
        "tags": tags,
        "customer_facing": customer_facing,
        "cost_impact": cost_impact,
    }
    for key, value in _optionals.items():
        if value is not None:
            metadata[key] = value

    def decorator(fn_or_cls: F) -> F:
        # Preserve the original function's identity
        if isinstance(fn_or_cls, type):
            fn_or_cls.__runbook_rule__ = metadata  # type: ignore[attr-defined]
        else:
            # For plain functions we use functools.wraps to keep __name__ etc.
            @functools.wraps(fn_or_cls)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return fn_or_cls(*args, **kwargs)

            wrapper.__runbook_rule__ = metadata  # type: ignore[attr-defined]
            # Carry over any editable/trigger metadata already placed by inner
            # decorators so the scanner sees everything on a single object.
            if hasattr(fn_or_cls, "__runbook_editable__"):
                wrapper.__runbook_editable__ = fn_or_cls.__runbook_editable__  # type: ignore[attr-defined]
            if hasattr(fn_or_cls, "__runbook_trigger__"):
                wrapper.__runbook_trigger__ = fn_or_cls.__runbook_trigger__  # type: ignore[attr-defined]
            return wrapper  # type: ignore[return-value]

        return fn_or_cls

    return decorator


# ── @editable ─────────────────────────────────────────────────────────────────


def editable(
    field_name: str,
    *,
    type: FieldType,
    default: Any,
    description: str,
    editable_by: EditableBy = "operator",
    validation: Optional[dict[str, Any]] = None,
    current: Any = _MISSING,
) -> Callable[[F], F]:
    """
    Declare that ``field_name`` is a parameter operators may safely tune.

    Multiple ``@editable`` decorators may be stacked on the same target.
    They accumulate into ``__runbook_editable__`` in the order they appear
    in source (outermost first after Python's decoration order reversal).

    Parameters
    ----------
    field_name:
        Name of the variable or config key being exposed.
    type:
        Data type hint for the dashboard widget.
        One of: ``"string"``, ``"number"``, ``"boolean"``,
        ``"select"``, ``"list"``, ``"email"``, ``"json"``.
    default:
        The value baked into code at time of annotation.
    description:
        One-sentence explanation shown to the operator.
    editable_by:
        Minimum role required to change this field.
        One of: ``"operator"`` (default), ``"admin"``, ``"dev"``.
    validation:
        Optional constraints dict.  Recognised keys:
        ``min``, ``max`` (numbers), ``options`` (list for select),
        ``pattern`` (regex string), ``maxItems`` (lists).
    current:
        Live value if different from ``default``; defaults to ``default``
        when omitted.

    Returns
    -------
    Callable
        The original function/class with the field spec appended to
        ``__runbook_editable__``.

    Example
    -------
    >>> @editable(
    ...     "threshold",
    ...     type="number",
    ...     default=500_000,
    ...     description="Contract value threshold for CC",
    ...     validation={"min": 0},
    ... )
    ... def get_scn_recipients(contract):
    ...     ...
    """
    field_spec: dict[str, Any] = {
        "field_name": field_name,
        "field_type": type,
        "default": default,
        "current": default if current is _MISSING else current,
        "description": description,
        "editable_by": editable_by,
    }
    if validation is not None:
        field_spec["validation"] = validation

    def decorator(fn_or_cls: F) -> F:
        target = fn_or_cls
        if not hasattr(target, "__runbook_editable__"):
            target.__runbook_editable__ = []  # type: ignore[attr-defined]
        # Prepend so that when decorators are applied bottom-up, the final list
        # reflects top-to-bottom source order.
        target.__runbook_editable__.insert(0, field_spec)  # type: ignore[attr-defined]
        return target

    return decorator


# ── @trigger ──────────────────────────────────────────────────────────────────


def trigger(description: str) -> Callable[[F], F]:
    """
    Declare the event or condition that activates this rule.

    Parameters
    ----------
    description:
        Human-readable or pseudo-code trigger expression.
        Examples:
        - ``"contract_value > threshold"``
        - ``"every day at 08:00 UTC"``
        - ``"order.status transitions to 'shipped'"``
        - ``"POST /api/v1/contracts"``

    Returns
    -------
    Callable
        The original function/class with ``__runbook_trigger__`` attached.

    Example
    -------
    >>> @trigger("contract_value > threshold")
    ... def get_scn_recipients(contract):
    ...     ...
    """

    def decorator(fn_or_cls: F) -> F:
        fn_or_cls.__runbook_trigger__ = description  # type: ignore[attr-defined]
        return fn_or_cls

    return decorator


# ── RunbookRegistry ───────────────────────────────────────────────────────────


class RunbookRegistry:
    """
    Discovers and aggregates rules annotated with ``@rule``.

    Usage
    -----
    ::

        registry = RunbookRegistry()
        registry.scan_module(my_module)
        registry.scan_package("/path/to/my/package")
        rules = registry.export()
        registry.push("https://api.runbook.io", api_key="rb_live_...")

    Thread safety
    -------------
    ``RunbookRegistry`` is not thread-safe by design.  Build and export from a
    single thread; the result list is safe to read from multiple threads.
    """

    def __init__(self) -> None:
        self._rules: dict[str, dict[str, Any]] = {}

    # ── Discovery ─────────────────────────────────────────────────────────────

    def scan_module(self, module: Any) -> list[dict[str, Any]]:
        """
        Inspect every attribute in ``module`` and register those that carry
        ``__runbook_rule__`` metadata.

        Parameters
        ----------
        module:
            An imported Python module object.

        Returns
        -------
        list[dict]
            The rule dicts discovered in this call (may be empty).
        """
        import inspect

        found: list[dict[str, Any]] = []
        for _name, obj in inspect.getmembers(module):
            if callable(obj) and hasattr(obj, "__runbook_rule__"):
                rule_dict = self._extract(obj, module)
                rule_id = rule_dict["rule_id"]
                self._rules[rule_id] = rule_dict
                found.append(rule_dict)
        return found

    def scan_package(self, package_path: str) -> list[dict[str, Any]]:
        """
        Recursively walk all ``.py`` files under ``package_path``, import each
        as a module, and call :meth:`scan_module` on it.

        Files that raise ``ImportError`` or ``SyntaxError`` are skipped with a
        warning rather than crashing the scan.

        Parameters
        ----------
        package_path:
            Absolute or relative filesystem path to the package root.

        Returns
        -------
        list[dict]
            All rule dicts found across every module in the package.
        """
        import importlib.util
        import sys
        import warnings
        from pathlib import Path

        root = Path(package_path).resolve()
        all_found: list[dict[str, Any]] = []

        for py_file in sorted(root.rglob("*.py")):
            # Build a dotted module name relative to the package root's parent
            rel = py_file.relative_to(root.parent)
            module_name = ".".join(rel.with_suffix("").parts)

            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules.setdefault(module_name, module)
            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except (ImportError, SyntaxError, Exception) as exc:
                warnings.warn(
                    f"runbook: skipping {py_file} — {type(exc).__name__}: {exc}",
                    stacklevel=2,
                )
                continue

            found = self.scan_module(module)
            all_found.extend(found)

        return all_found

    # ── Export ────────────────────────────────────────────────────────────────

    def export(self) -> list[dict[str, Any]]:
        """
        Return all registered rules as a list of plain dicts, ready for
        JSON serialisation or POSTing to the Runbook API.

        Returns
        -------
        list[dict]
            Sorted by ``rule_id``.
        """
        return sorted(self._rules.values(), key=lambda r: r["rule_id"])

    def push(self, api_url: str, api_key: str) -> dict[str, Any]:
        """
        POST all registered rules to the Runbook API bulk-upsert endpoint.

        Parameters
        ----------
        api_url:
            Base URL of the Runbook API, e.g. ``"https://api.runbook.io"``.
        api_key:
            API key with write access to the target tenant.

        Returns
        -------
        dict
            Parsed JSON response from the API.

        Raises
        ------
        httpx.HTTPStatusError
            If the API returns a 4xx or 5xx response.
        """
        import httpx

        payload = {"rules": self.export()}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Runbook-SDK": "python/0.1.0",
        }
        url = api_url.rstrip("/") + "/api/v1/registry/bulk"
        response = httpx.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _extract(obj: Any, module: Any) -> dict[str, Any]:
        """Build a rule dict from a decorated callable or class."""
        import inspect

        rule_meta: dict[str, Any] = dict(getattr(obj, "__runbook_rule__", {}))
        rule_id = rule_meta.pop("id")

        result: dict[str, Any] = {
            "rule_id": rule_id,
            **rule_meta,
        }

        # Editable fields
        editable_fields = list(getattr(obj, "__runbook_editable__", []))
        if editable_fields:
            result["editable"] = editable_fields

        # Trigger
        trigger_val = getattr(obj, "__runbook_trigger__", None)
        if trigger_val is not None:
            result["trigger"] = trigger_val

        # Source provenance
        try:
            source_file = inspect.getfile(obj)
            source_lines_info = inspect.getsourcelines(obj)
            start_line = source_lines_info[1]
            end_line = start_line + len(source_lines_info[0]) - 1
            result["source_file"] = source_file
            result["source_lines"] = {"start": start_line, "end": end_line}
        except (TypeError, OSError):
            pass

        # Module attribution
        result["source_module"] = getattr(module, "__name__", None)

        return result
