"""
seed_demo.py — Acme Logistics demo seed for the Runbook registry.

Seeds one demo tenant ("Acme Logistics") and 29 automation rules spanning
Order Intake, Fulfillment, Shipping, Billing, Notifications, Analytics, and
Compliance.  The script is idempotent: rules are upserted by (tenant_id,
rule_id).  Existing operator-set editable_field_values are preserved so
re-running after a demo session does not clobber a reviewer's changes.

Run from the backend/ directory:
    python seed_demo.py

Or with an explicit DATABASE_URL override:
    DATABASE_URL=postgresql://... python seed_demo.py
"""
from __future__ import annotations

import sys
import os

# Allow running from the backend/ directory without installing the package.
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from typing import Any

from contextlib import contextmanager

from app.db import get_sync_db, create_tables_sync
from app.models.tenant import Tenant, PLAN_ENTERPRISE
from app.models.rule import Rule
from app.models.audit_log import AuditLog

# ---------------------------------------------------------------------------
# Demo tenant definition
# ---------------------------------------------------------------------------

DEMO_TENANT_SLUG = "acme-logistics"
DEMO_TENANT_NAME = "Acme Logistics"

# ---------------------------------------------------------------------------
# Rule definitions
# Each dict maps 1-to-1 with Rule columns.  Keys that are absent default to
# None / empty.  editable_fields uses the schema documented in rule.py.
# ---------------------------------------------------------------------------

RULES: list[dict[str, Any]] = [

    # =========================================================================
    # ORDER INTAKE
    # =========================================================================
    {
        "rule_id": "INTAKE.EMAIL_PARSER",
        "slug": "intake-email-parser",
        "title": "AI Email Order Parser",
        "description": (
            "Uses an AI agent to extract structured order data (SKUs, quantities, "
            "ship-to address, requested delivery date) from inbound customer emails "
            "before handing off to the order creation workflow."
        ),
        "why": (
            "Manual data entry from email orders accounts for roughly 30 % of "
            "intake errors and consumes ~2 FTE per shift.  Automating extraction "
            "at high confidence removes that cost while the confidence threshold "
            "gates human review for ambiguous cases."
        ),
        "department": "Order Intake",
        "subsystem": "INTAKE",
        "owner": "Intake Operations Lead",
        "tags": ["ai", "email", "extraction", "intake"],
        "status": "active",
        "trigger": "New email arrives in orders@acme.com inbox",
        "conditions": {"email_has_attachment_or_body": True},
        "actions": {
            "parse_order_fields": True,
            "route_to_review_if_below_threshold": True,
            "auto_create_order_if_above_threshold": True,
        },
        "actors": [
            {"type": "ai_agent", "name": "OrderParserAgent", "role": "LLM extraction"},
            {"type": "human", "name": "Intake Reviewer", "role": "Reviews low-confidence parses"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": ["INTAKE.DUPLICATE_CHECK", "INTAKE.AUTO_APPROVE"],
        "source_file": "services/intake/email_parser.py",
        "source_start_line": 44,
        "source_end_line": 112,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Reduces manual data-entry labor by an estimated 2 FTE; mis-parses below threshold incur a $15 correction cost each.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "confidence_threshold",
                "type": "float",
                "current": 0.85,
                "default": 0.85,
                "description": "Minimum confidence score (0–1) for auto-creating an order without human review.",
                "editable_by": "operator",
                "min_value": 0.5,
                "max_value": 1.0,
            },
        ],
    },

    {
        "rule_id": "INTAKE.DUPLICATE_CHECK",
        "slug": "intake-duplicate-check",
        "title": "Duplicate Order Detection",
        "description": (
            "Compares a newly parsed order against existing open orders using "
            "fuzzy matching on customer ID, SKU list, and total value.  Flags "
            "probable duplicates for human review rather than creating a second order."
        ),
        "why": (
            "Customer email threads frequently contain forwarded or re-sent orders. "
            "Without this check, duplicate shipments result in excess freight costs "
            "and customer confusion.  A short match window keeps the check tight "
            "without blocking legitimate repeat orders."
        ),
        "department": "Order Intake",
        "subsystem": "INTAKE",
        "owner": "Intake Operations Lead",
        "tags": ["dedup", "intake", "quality"],
        "status": "active",
        "trigger": "Order record created by INTAKE.EMAIL_PARSER or manual entry",
        "conditions": {"order_status": "pending_review"},
        "actions": {
            "query_recent_orders": True,
            "compute_similarity_score": True,
            "flag_if_above_threshold": True,
        },
        "actors": [
            {"type": "automated", "name": "DuplicateCheckService", "role": "Similarity scorer"},
        ],
        "upstream_rule_ids": ["INTAKE.EMAIL_PARSER"],
        "downstream_rule_ids": ["INTAKE.AUTO_APPROVE", "INTAKE.PRIORITY_ROUTING"],
        "source_file": "services/intake/duplicate_check.py",
        "source_start_line": 10,
        "source_end_line": 68,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Prevents duplicate shipment losses averaging $340 per incident; false positives delay legitimate orders by up to 1 hour.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "match_window_hours",
                "type": "int",
                "current": 24,
                "default": 24,
                "description": "Look-back window (hours) when searching for potential duplicate orders.",
                "editable_by": "operator",
                "min_value": 1,
                "max_value": 168,
            },
            {
                "name": "similarity_threshold",
                "type": "float",
                "current": 0.9,
                "default": 0.9,
                "description": "Minimum similarity score (0–1) required to flag an order as a likely duplicate.",
                "editable_by": "operator",
                "min_value": 0.5,
                "max_value": 1.0,
            },
        ],
    },

    {
        "rule_id": "INTAKE.AUTO_APPROVE",
        "slug": "intake-auto-approve",
        "title": "Auto-Approve Low-Value Verified Orders",
        "description": (
            "Automatically approves orders that are below the dollar threshold "
            "and placed by customers with a verified account in good standing, "
            "bypassing the manual review queue entirely."
        ),
        "why": (
            "The majority of order volume comes from repeat, low-risk customers. "
            "Routing all of them through the review queue creates a backlog that "
            "delays fulfillment and increases time-to-ship.  Auto-approval for "
            "well-understood customers reclaims that queue capacity for edge cases."
        ),
        "department": "Order Intake",
        "subsystem": "INTAKE",
        "owner": "Intake Operations Lead",
        "tags": ["automation", "approval", "intake"],
        "status": "active",
        "trigger": "Order passes INTAKE.DUPLICATE_CHECK with no flag",
        "conditions": {
            "customer_status": "verified",
            "order_value_lt": "auto_approve_threshold",
        },
        "actions": {
            "set_order_status_approved": True,
            "enqueue_for_fulfillment": True,
        },
        "actors": [
            {"type": "automated", "name": "ApprovalEngine", "role": "Policy evaluator"},
        ],
        "upstream_rule_ids": ["INTAKE.DUPLICATE_CHECK"],
        "downstream_rule_ids": ["FULFILL.WAREHOUSE_ASSIGN"],
        "source_file": "services/intake/approval.py",
        "source_start_line": 22,
        "source_end_line": 55,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Eliminates ~3 min of review labor per auto-approved order; threshold too high risks approving fraudulent orders.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "auto_approve_threshold",
                "type": "float",
                "current": 5000,
                "default": 5000,
                "description": "Maximum order value (USD) eligible for automatic approval without manual review.",
                "editable_by": "operator",
                "min_value": 0,
                "max_value": 25000,
            },
        ],
    },

    {
        "rule_id": "INTAKE.PRIORITY_ROUTING",
        "slug": "intake-priority-routing",
        "title": "High-Value Order Priority Routing",
        "description": (
            "Routes orders exceeding the high-value threshold directly to the "
            "senior account management team, bypassing the standard review queue "
            "so large deals receive white-glove handling."
        ),
        "why": (
            "High-value orders carry disproportionate revenue and relationship risk. "
            "Senior account managers can negotiate terms, catch credit issues early, "
            "and coordinate warehouse pre-allocation.  Routing them separately "
            "ensures they are never buried behind routine intake work."
        ),
        "department": "Order Intake",
        "subsystem": "INTAKE",
        "owner": "Senior Account Management",
        "tags": ["routing", "high-value", "intake"],
        "status": "active",
        "trigger": "Order created or flagged with order_value > high_value_threshold",
        "conditions": {"order_value_gte": "high_value_threshold"},
        "actions": {
            "assign_to_senior_am_queue": True,
            "send_slack_notification": True,
        },
        "actors": [
            {"type": "automated", "name": "RoutingEngine", "role": "Queue assignment"},
            {"type": "human", "name": "Senior Account Manager", "role": "Order review and approval"},
        ],
        "upstream_rule_ids": ["INTAKE.DUPLICATE_CHECK"],
        "downstream_rule_ids": ["FULFILL.WAREHOUSE_ASSIGN", "NOTIFY.EXCEPTION_ALERT"],
        "source_file": "services/intake/routing.py",
        "source_start_line": 30,
        "source_end_line": 74,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "Misdirected high-value orders can delay fulfillment on deals worth $25k+; threshold setting directly affects queue composition.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "high_value_threshold",
                "type": "float",
                "current": 25000,
                "default": 25000,
                "description": "Minimum order value (USD) that triggers routing to senior account managers.",
                "editable_by": "operator",
                "min_value": 5000,
                "max_value": 500000,
            },
        ],
    },

    # =========================================================================
    # FULFILLMENT
    # =========================================================================
    {
        "rule_id": "FULFILL.WAREHOUSE_ASSIGN",
        "slug": "fulfill-warehouse-assign",
        "title": "Nearest In-Stock Warehouse Assignment",
        "description": (
            "Evaluates all warehouses that have sufficient stock for the order and "
            "selects the one closest to the ship-to address within the maximum "
            "allowed distance.  Falls back to a split-shipment if no single "
            "warehouse can fulfill the full order."
        ),
        "why": (
            "Shorter warehouse-to-destination distance reduces freight cost and "
            "transit time.  Capping the search radius prevents routing to a "
            "distant facility when local stock exists, which would increase cost "
            "without customer benefit."
        ),
        "department": "Fulfillment",
        "subsystem": "FULFILL",
        "owner": "Warehouse Operations Manager",
        "tags": ["warehouse", "routing", "inventory", "fulfillment"],
        "status": "active",
        "trigger": "Order approved and enqueued for fulfillment",
        "conditions": {"order_status": "approved"},
        "actions": {
            "query_inventory_by_sku": True,
            "calculate_distance_to_destinations": True,
            "assign_warehouse_id": True,
        },
        "actors": [
            {"type": "automated", "name": "WarehouseAssignmentService", "role": "Inventory and geo lookup"},
        ],
        "upstream_rule_ids": ["INTAKE.AUTO_APPROVE", "INTAKE.PRIORITY_ROUTING"],
        "downstream_rule_ids": ["FULFILL.PICK_BATCH", "FULFILL.BACKORDER_NOTIFY"],
        "source_file": "services/fulfillment/warehouse_assign.py",
        "source_start_line": 18,
        "source_end_line": 95,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Every 100-mile reduction in avg warehouse distance saves ~$1.20/shipment in freight; incorrect assignment triggers re-routing fees.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "max_distance_miles",
                "type": "int",
                "current": 500,
                "default": 500,
                "description": "Maximum distance (miles) between warehouse and ship-to address before splitting the shipment.",
                "editable_by": "operator",
                "min_value": 50,
                "max_value": 3000,
            },
        ],
    },

    {
        "rule_id": "FULFILL.PICK_BATCH",
        "slug": "fulfill-pick-batch",
        "title": "Batched Pick Queue Release",
        "description": (
            "Holds approved pick tasks and releases them to warehouse floor staff "
            "in batches at the configured interval during business hours, rather "
            "than one task at a time.  Outside business hours, tasks queue until "
            "the next business-hours window opens."
        ),
        "why": (
            "Batching pick tasks reduces picker travel distance by up to 40 % "
            "compared to first-in-first-out single-task dispatch.  Restricting "
            "to business hours prevents partial shifts from pulling tasks with no "
            "staff available to complete them."
        ),
        "department": "Fulfillment",
        "subsystem": "FULFILL",
        "owner": "Warehouse Operations Manager",
        "tags": ["picking", "batch", "warehouse", "scheduling"],
        "status": "active",
        "trigger": "Scheduled timer fires every batch_interval_minutes during business hours",
        "conditions": {
            "current_time_between": ["business_hours_start", "business_hours_end"],
            "pending_picks_gt": 0,
        },
        "actions": {
            "group_picks_by_zone": True,
            "release_batch_to_floor": True,
            "notify_pickers": True,
        },
        "actors": [
            {"type": "automated", "name": "BatchScheduler", "role": "Timer-driven release"},
            {"type": "human", "name": "Warehouse Picker", "role": "Executes pick tasks"},
        ],
        "upstream_rule_ids": ["FULFILL.WAREHOUSE_ASSIGN"],
        "downstream_rule_ids": ["FULFILL.QUALITY_CHECK", "FULFILL.PACK_VERIFY"],
        "source_file": "services/fulfillment/pick_batch.py",
        "source_start_line": 12,
        "source_end_line": 78,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "low",
        "cost_impact": "Batching reduces pick labor cost by ~15–20 %; shorter intervals improve throughput but increase picker travel overhead.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "batch_interval_minutes",
                "type": "int",
                "current": 30,
                "default": 30,
                "description": "How often (minutes) a new pick batch is released to the warehouse floor.",
                "editable_by": "operator",
                "min_value": 5,
                "max_value": 120,
            },
            {
                "name": "business_hours_start",
                "type": "str",
                "current": "08:00",
                "default": "08:00",
                "description": "Start of the picking window in HH:MM (24-hour, local warehouse time).",
                "editable_by": "operator",
            },
            {
                "name": "business_hours_end",
                "type": "str",
                "current": "18:00",
                "default": "18:00",
                "description": "End of the picking window in HH:MM (24-hour, local warehouse time).",
                "editable_by": "operator",
            },
        ],
    },

    {
        "rule_id": "FULFILL.BACKORDER_NOTIFY",
        "slug": "fulfill-backorder-notify",
        "title": "Backorder Customer Notification",
        "description": (
            "Detects when a warehouse assignment cannot be fulfilled due to "
            "insufficient stock and sends the customer a proactive notification "
            "within the configured delay window, including an estimated restock "
            "date if available."
        ),
        "why": (
            "Customers who discover a backorder at expected delivery time are "
            "significantly more likely to cancel or churn than those who received "
            "early notice.  A short notification delay keeps the message timely "
            "while allowing the system time to confirm stock from alternate sources."
        ),
        "department": "Fulfillment",
        "subsystem": "FULFILL",
        "owner": "Customer Success Manager",
        "tags": ["backorder", "notification", "customer", "fulfillment"],
        "status": "active",
        "trigger": "Warehouse assignment fails due to stock-out",
        "conditions": {"stock_status": "insufficient"},
        "actions": {
            "look_up_restock_eta": True,
            "send_customer_email": True,
            "flag_order_as_backordered": True,
        },
        "actors": [
            {"type": "automated", "name": "NotificationService", "role": "Email dispatch"},
            {"type": "external", "name": "Customer", "role": "Receives notification"},
        ],
        "upstream_rule_ids": ["FULFILL.WAREHOUSE_ASSIGN"],
        "downstream_rule_ids": ["NOTIFY.CUSTOMER_UPDATE"],
        "source_file": "services/fulfillment/backorder.py",
        "source_start_line": 5,
        "source_end_line": 60,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "Late backorder notice increases cancellation rate by ~8 %; each cancellation costs avg $220 in lost margin.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "notify_delay_hours",
                "type": "int",
                "current": 2,
                "default": 2,
                "description": "Maximum hours to wait after backorder detection before sending customer notification.",
                "editable_by": "operator",
                "min_value": 0,
                "max_value": 24,
            },
        ],
    },

    {
        "rule_id": "FULFILL.QUALITY_CHECK",
        "slug": "fulfill-quality-check",
        "title": "Quality Control Gate",
        "description": (
            "Routes an order to a QC inspection station before packing if the "
            "order value exceeds the QC threshold or if any line item belongs to "
            "a category that always requires inspection (e.g., hazmat, fragile)."
        ),
        "why": (
            "High-value shipments and hazardous-material orders carry outsized "
            "liability if they ship damaged or mislabeled.  A QC gate catches "
            "pick errors before they leave the warehouse; the cost of an inspection "
            "is a fraction of a return or compliance fine."
        ),
        "department": "Fulfillment",
        "subsystem": "FULFILL",
        "owner": "Quality Assurance Lead",
        "tags": ["qc", "quality", "hazmat", "compliance", "fulfillment"],
        "status": "active",
        "trigger": "Pick batch completed and order moves to pack queue",
        "conditions": {
            "order_value_gte": "qc_threshold",
            "or_contains_category": "always_qc_categories",
        },
        "actions": {
            "route_to_qc_station": True,
            "hold_pack_queue_until_pass": True,
        },
        "actors": [
            {"type": "automated", "name": "QCRouter", "role": "Conditional routing"},
            {"type": "human", "name": "QC Inspector", "role": "Physical inspection"},
        ],
        "upstream_rule_ids": ["FULFILL.PICK_BATCH"],
        "downstream_rule_ids": ["FULFILL.PACK_VERIFY", "SHIP.LABEL_GENERATE"],
        "source_file": "services/fulfillment/quality_check.py",
        "source_start_line": 28,
        "source_end_line": 88,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "QC adds 20–40 min per order but prevents returns averaging $480 and potential HAZMAT compliance fines up to $10k.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "qc_threshold",
                "type": "float",
                "current": 10000,
                "default": 10000,
                "description": "Minimum order value (USD) that automatically triggers a QC inspection.",
                "editable_by": "operator",
                "min_value": 1000,
                "max_value": 100000,
            },
            {
                "name": "always_qc_categories",
                "type": "list",
                "current": ["hazmat", "fragile"],
                "default": ["hazmat", "fragile"],
                "description": "Product categories that always require QC inspection regardless of order value.",
                "editable_by": "admin",
            },
        ],
    },

    {
        "rule_id": "FULFILL.PACK_VERIFY",
        "slug": "fulfill-pack-verify",
        "title": "Photo Verification for Large Orders",
        "description": (
            "Requires a packer to take and submit a photo of the packed box "
            "contents before the order is sealed when the number of line items "
            "meets or exceeds the configured threshold.  The photo is stored "
            "against the order record."
        ),
        "why": (
            "Multi-line orders have a higher pick-error rate per item.  Photo "
            "verification creates a tamper-evident record that resolves 'missing "
            "item' disputes quickly, reducing both refund costs and support "
            "escalations."
        ),
        "department": "Fulfillment",
        "subsystem": "FULFILL",
        "owner": "Warehouse Operations Manager",
        "tags": ["packing", "verification", "photo", "fulfillment"],
        "status": "active",
        "trigger": "Order enters pack station with line_item_count >= photo_threshold_items",
        "conditions": {"line_item_count_gte": "photo_threshold_items"},
        "actions": {
            "prompt_packer_for_photo": True,
            "store_photo_url_on_order": True,
            "block_seal_until_photo_submitted": True,
        },
        "actors": [
            {"type": "automated", "name": "PackWorkflowEngine", "role": "Photo gate enforcement"},
            {"type": "human", "name": "Packer", "role": "Takes and submits verification photo"},
        ],
        "upstream_rule_ids": ["FULFILL.QUALITY_CHECK", "FULFILL.PICK_BATCH"],
        "downstream_rule_ids": ["SHIP.LABEL_GENERATE"],
        "source_file": "services/fulfillment/pack_verify.py",
        "source_start_line": 14,
        "source_end_line": 66,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Prevents ~12 % of multi-line order disputes; average dispute resolution cost is $95 including labor and refund.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "photo_threshold_items",
                "type": "int",
                "current": 5,
                "default": 5,
                "description": "Minimum number of line items in an order before photo verification is required.",
                "editable_by": "operator",
                "min_value": 2,
                "max_value": 50,
            },
        ],
    },

    # =========================================================================
    # SHIPPING
    # =========================================================================
    {
        "rule_id": "SHIP.CARRIER_SELECT",
        "slug": "ship-carrier-select",
        "title": "Automated Carrier Selection",
        "description": (
            "Queries the rate APIs of all preferred carriers, filters out options "
            "that cannot meet the order SLA (delivery date), then selects the "
            "cheapest remaining option.  Falls back to the next preferred carrier "
            "if the cheapest is more than max_cost_multiplier times the baseline."
        ),
        "why": (
            "Manual carrier selection is inconsistent and slow.  Automating the "
            "decision against live rates ensures Acme pays market price rather "
            "than defaulting to a single carrier out of habit, while SLA "
            "filtering prevents saving $3 at the cost of a late delivery."
        ),
        "department": "Shipping",
        "subsystem": "SHIP",
        "owner": "Logistics Manager",
        "tags": ["carrier", "rate-shopping", "shipping", "cost"],
        "status": "active",
        "trigger": "Order sealed and ready for carrier assignment",
        "conditions": {"order_status": "packed"},
        "actions": {
            "fetch_live_carrier_rates": True,
            "filter_by_sla": True,
            "select_cheapest_qualifying": True,
            "assign_carrier_to_order": True,
        },
        "actors": [
            {"type": "automated", "name": "CarrierRateEngine", "role": "Rate API orchestration"},
            {"type": "external", "name": "FedEx / UPS / USPS", "role": "Rate providers"},
        ],
        "upstream_rule_ids": ["FULFILL.PACK_VERIFY"],
        "downstream_rule_ids": ["SHIP.LABEL_GENERATE"],
        "source_file": "services/shipping/carrier_select.py",
        "source_start_line": 35,
        "source_end_line": 130,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Rate shopping saves an average of $1.80 per shipment across volume; misconfigured multiplier can select non-competitive rates.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "preferred_carriers",
                "type": "list",
                "current": ["FedEx", "UPS", "USPS"],
                "default": ["FedEx", "UPS", "USPS"],
                "description": "Ordered list of carriers to include in rate shopping.  Only carriers on this list will be queried.",
                "editable_by": "admin",
                "allowed_values": ["FedEx", "UPS", "USPS", "DHL", "OnTrac", "LSO"],
            },
            {
                "name": "max_cost_multiplier",
                "type": "float",
                "current": 1.3,
                "default": 1.3,
                "description": "Reject any carrier rate more than this multiple above the cheapest qualifying rate.",
                "editable_by": "operator",
                "min_value": 1.0,
                "max_value": 3.0,
            },
        ],
    },

    {
        "rule_id": "SHIP.LABEL_GENERATE",
        "slug": "ship-label-generate",
        "title": "Shipping Label Generation",
        "description": (
            "Generates and prints the shipping label via the selected carrier's "
            "API, attaching the tracking number and label PDF to the order record, "
            "at a configurable lead time before the scheduled carrier pickup window."
        ),
        "why": (
            "Labels must be generated before carrier pickup.  Generating them too "
            "early risks address or weight changes invalidating the label; too late "
            "risks missing the pickup window.  The lead time is tunable to match "
            "each warehouse's operational tempo."
        ),
        "department": "Shipping",
        "subsystem": "SHIP",
        "owner": "Logistics Manager",
        "tags": ["label", "carrier", "shipping"],
        "status": "active",
        "trigger": "Carrier assigned and pickup window confirmed; lead_time_hours before pickup",
        "conditions": {"carrier_assigned": True, "pickup_scheduled": True},
        "actions": {
            "call_carrier_label_api": True,
            "store_tracking_number": True,
            "print_label_to_station": True,
        },
        "actors": [
            {"type": "automated", "name": "LabelService", "role": "Carrier API caller"},
            {"type": "external", "name": "Carrier Label API", "role": "Label issuer"},
        ],
        "upstream_rule_ids": ["SHIP.CARRIER_SELECT"],
        "downstream_rule_ids": ["SHIP.TRACKING_NOTIFY", "SHIP.DELAY_ESCALATE"],
        "source_file": "services/shipping/label_generate.py",
        "source_start_line": 20,
        "source_end_line": 75,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "Missing pickup window forces next-day rescheduling, adding 1 day to transit and ~$8 in storage fees per pallet.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "lead_time_hours",
                "type": "int",
                "current": 4,
                "default": 4,
                "description": "How many hours before the carrier pickup window to generate the shipping label.",
                "editable_by": "operator",
                "min_value": 1,
                "max_value": 24,
            },
        ],
    },

    {
        "rule_id": "SHIP.TRACKING_NOTIFY",
        "slug": "ship-tracking-notify",
        "title": "Tracking Number Customer Notification",
        "description": (
            "Sends the customer a tracking number and estimated delivery date "
            "across configured notification channels immediately after a label "
            "is successfully generated."
        ),
        "why": (
            "Post-purchase anxiety drives a significant share of inbound support "
            "contacts.  Proactively sending tracking information at label generation "
            "reduces 'where is my order' contacts by roughly 60 % in our benchmark "
            "cohort, freeing CS capacity for real exceptions."
        ),
        "department": "Shipping",
        "subsystem": "SHIP",
        "owner": "Customer Success Manager",
        "tags": ["tracking", "notification", "customer", "shipping"],
        "status": "active",
        "trigger": "Shipping label successfully generated (SHIP.LABEL_GENERATE succeeds)",
        "conditions": {"label_generated": True},
        "actions": {
            "compose_tracking_message": True,
            "send_via_notification_channels": True,
        },
        "actors": [
            {"type": "automated", "name": "NotificationService", "role": "Message dispatch"},
            {"type": "external", "name": "Customer", "role": "Receives tracking details"},
        ],
        "upstream_rule_ids": ["SHIP.LABEL_GENERATE"],
        "downstream_rule_ids": ["SHIP.DELIVERY_CONFIRM", "NOTIFY.CUSTOMER_UPDATE"],
        "source_file": "services/shipping/tracking_notify.py",
        "source_start_line": 8,
        "source_end_line": 52,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Reduces WISMO ('where is my order') support contacts by ~60 %; each deflected contact saves ~$7 in CS cost.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "notification_channels",
                "type": "list",
                "current": ["email"],
                "default": ["email"],
                "description": "Channels used to send the tracking notification.  Supported: 'email', 'sms'.",
                "editable_by": "operator",
                "allowed_values": ["email", "sms"],
            },
            {
                "name": "include_estimated_delivery",
                "type": "bool",
                "current": True,
                "default": True,
                "description": "Include the carrier-estimated delivery date in the tracking notification.",
                "editable_by": "operator",
            },
        ],
    },

    {
        "rule_id": "SHIP.DELAY_ESCALATE",
        "slug": "ship-delay-escalate",
        "title": "Stale Shipment Escalation",
        "description": (
            "Monitors all open shipments and escalates to the configured contact "
            "when a shipment has not received a carrier scan within the stale "
            "threshold.  Covers lost packages, carrier pickup failures, and "
            "customs holds."
        ),
        "why": (
            "Without active monitoring, lost-in-transit shipments surface only "
            "when the customer files a claim — often days or weeks after the fact. "
            "Early detection allows Acme to file a carrier claim while evidence "
            "is fresh and proactively re-ship, preserving the customer relationship."
        ),
        "department": "Shipping",
        "subsystem": "SHIP",
        "owner": "Logistics Manager",
        "tags": ["escalation", "delay", "monitoring", "shipping"],
        "status": "active",
        "trigger": "Scheduled scan: no carrier event on shipment for >= stale_hours",
        "conditions": {
            "shipment_status": "in_transit",
            "hours_since_last_scan_gte": "stale_hours",
        },
        "actions": {
            "email_escalate_to": True,
            "flag_shipment_as_stale": True,
            "open_carrier_inquiry": True,
        },
        "actors": [
            {"type": "automated", "name": "ShipmentMonitor", "role": "Periodic scan checker"},
            {"type": "human", "name": "Ops Manager", "role": "Receives escalation and investigates"},
            {"type": "external", "name": "Carrier Tracking API", "role": "Scan event source"},
        ],
        "upstream_rule_ids": ["SHIP.LABEL_GENERATE"],
        "downstream_rule_ids": ["NOTIFY.EXCEPTION_ALERT"],
        "source_file": "services/shipping/delay_escalate.py",
        "source_start_line": 16,
        "source_end_line": 84,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "Undetected lost shipments cost avg $210 per incident in re-ship plus carrier claim labor; early detection reclaims ~70 % of that.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "stale_hours",
                "type": "int",
                "current": 48,
                "default": 48,
                "description": "Hours without a carrier scan before a shipment is considered stale and escalated.",
                "editable_by": "operator",
                "min_value": 12,
                "max_value": 168,
            },
            {
                "name": "escalate_to",
                "type": "str",
                "current": "ops-manager@acme.com",
                "default": "ops-manager@acme.com",
                "description": "Email address that receives stale-shipment escalation alerts.",
                "editable_by": "admin",
            },
        ],
    },

    {
        "rule_id": "SHIP.DELIVERY_CONFIRM",
        "slug": "ship-delivery-confirm",
        "title": "Delivery Confirmation and Order Close",
        "description": (
            "Marks an order as 'delivered' and triggers invoice generation when "
            "the carrier reports a delivery scan.  If no delivery scan arrives "
            "within auto_close_days of the expected delivery date, the order is "
            "auto-closed and flagged for review."
        ),
        "why": (
            "Tying order closure to the delivery scan rather than to a fixed "
            "timer prevents invoicing before goods are received and gives the "
            "returns window a firm start date.  The auto-close backstop handles "
            "carriers that do not reliably report final scans."
        ),
        "department": "Shipping",
        "subsystem": "SHIP",
        "owner": "Logistics Manager",
        "tags": ["delivery", "confirmation", "shipping", "billing"],
        "status": "active",
        "trigger": "Carrier delivery scan event received OR auto_close_days past expected delivery",
        "conditions": {
            "carrier_event": "delivered",
            "or_days_past_expected_gte": "auto_close_days",
        },
        "actions": {
            "set_order_status_delivered": True,
            "trigger_invoice_generation": True,
            "start_returns_window_timer": True,
        },
        "actors": [
            {"type": "automated", "name": "DeliveryEventListener", "role": "Carrier webhook consumer"},
            {"type": "external", "name": "Carrier Tracking API", "role": "Delivery event source"},
        ],
        "upstream_rule_ids": ["SHIP.TRACKING_NOTIFY"],
        "downstream_rule_ids": ["BILL.INVOICE_GENERATE", "NOTIFY.CUSTOMER_UPDATE"],
        "source_file": "services/shipping/delivery_confirm.py",
        "source_start_line": 22,
        "source_end_line": 68,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Early order closure before confirmed delivery accelerates invoicing but risks disputes; too long a delay defers cash flow.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "auto_close_days",
                "type": "int",
                "current": 3,
                "default": 3,
                "description": "Days past the expected delivery date before an order is auto-closed if no delivery scan is received.",
                "editable_by": "operator",
                "min_value": 1,
                "max_value": 14,
            },
        ],
    },

    # =========================================================================
    # BILLING
    # =========================================================================
    {
        "rule_id": "BILL.INVOICE_GENERATE",
        "slug": "bill-invoice-generate",
        "title": "Invoice Generation on Delivery",
        "description": (
            "Generates a PDF invoice with the configured payment terms immediately "
            "after SHIP.DELIVERY_CONFIRM fires.  The invoice is emailed to the "
            "billing contact on file and stored in the document repository."
        ),
        "why": (
            "Invoicing at confirmed delivery rather than at shipment aligns "
            "Acme's billing cycle with when the customer has received value, "
            "reducing payment disputes.  Automated generation eliminates the "
            "2–4 day manual billing lag that currently delays cash flow."
        ),
        "department": "Billing",
        "subsystem": "BILL",
        "owner": "Billing Manager",
        "tags": ["invoice", "billing", "cash-flow"],
        "status": "active",
        "trigger": "SHIP.DELIVERY_CONFIRM fires (order status set to 'delivered')",
        "conditions": {"order_status": "delivered"},
        "actions": {
            "calculate_line_totals_with_discounts": True,
            "apply_tax_from_BILL_TAX_CALCULATE": True,
            "render_pdf_invoice": True,
            "email_to_billing_contact": True,
            "store_invoice_record": True,
        },
        "actors": [
            {"type": "automated", "name": "InvoiceService", "role": "Invoice renderer and sender"},
        ],
        "upstream_rule_ids": ["SHIP.DELIVERY_CONFIRM", "BILL.TAX_CALCULATE", "BILL.DISCOUNT_APPLY"],
        "downstream_rule_ids": ["BILL.OVERDUE_REMINDER"],
        "source_file": "services/billing/invoice_generate.py",
        "source_start_line": 30,
        "source_end_line": 110,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "Each day of billing lag represents ~$18k in outstanding AR at current volume; incorrect payment terms create collections complexity.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "payment_terms_days",
                "type": "int",
                "current": 30,
                "default": 30,
                "description": "Standard payment terms printed on the invoice (e.g., 30 = Net 30).",
                "editable_by": "operator",
                "min_value": 0,
                "max_value": 90,
                "allowed_values": [0, 15, 30, 45, 60, 90],
            },
        ],
    },

    {
        "rule_id": "BILL.TAX_CALCULATE",
        "slug": "bill-tax-calculate",
        "title": "Destination-State Tax Calculation",
        "description": (
            "Looks up the applicable sales tax rate for the ship-to state and "
            "applies it to taxable line items.  Exempt categories are excluded "
            "from the tax base.  Tax is calculated at invoice generation time "
            "using the rates current on the delivery date."
        ),
        "why": (
            "Nexus obligations vary by state and product category.  Hardcoded "
            "rates go stale when states adjust schedules.  Centralizing the "
            "calculation with an exempt-categories list ensures compliance without "
            "scattering tax logic across order processing code."
        ),
        "department": "Billing",
        "subsystem": "BILL",
        "owner": "Finance Controller",
        "tags": ["tax", "compliance", "billing"],
        "status": "active",
        "trigger": "Invoice generation initiated (called by BILL.INVOICE_GENERATE)",
        "conditions": {"order_has_taxable_items": True},
        "actions": {
            "look_up_state_tax_rate": True,
            "exclude_exempt_categories": True,
            "return_tax_amount": True,
        },
        "actors": [
            {"type": "automated", "name": "TaxCalculationService", "role": "Rate lookup and computation"},
            {"type": "external", "name": "Tax Rate Database", "role": "Rate data source"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": ["BILL.INVOICE_GENERATE"],
        "source_file": "services/billing/tax_calculate.py",
        "source_start_line": 12,
        "source_end_line": 80,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "Under-collection of sales tax creates state nexus liability; over-collection creates customer disputes and refund processing costs.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "tax_exempt_categories",
                "type": "list",
                "current": ["government", "nonprofit"],
                "default": ["government", "nonprofit"],
                "description": "Product or customer categories that are excluded from sales tax calculation.",
                "editable_by": "admin",
            },
        ],
    },

    {
        "rule_id": "BILL.DISCOUNT_APPLY",
        "slug": "bill-discount-apply",
        "title": "Volume Discount Tier Application",
        "description": (
            "Applies a tiered percentage discount to the order subtotal based on "
            "the customer's trailing 12-month spend.  Three configurable tiers "
            "with separate thresholds and discount percentages."
        ),
        "why": (
            "Volume discounts incentivize customers to consolidate purchasing "
            "with Acme rather than splitting across suppliers.  Tiered discounts "
            "are more effective than a single threshold because they create "
            "incremental incentive at each spend band."
        ),
        "department": "Billing",
        "subsystem": "BILL",
        "owner": "Finance Controller",
        "tags": ["discount", "billing", "pricing", "retention"],
        "status": "active",
        "trigger": "Invoice generation initiated; called alongside BILL.TAX_CALCULATE",
        "conditions": {"customer_has_trailing_spend_data": True},
        "actions": {
            "look_up_customer_trailing_spend": True,
            "select_applicable_tier": True,
            "apply_discount_to_subtotal": True,
            "record_discount_reason_on_invoice": True,
        },
        "actors": [
            {"type": "automated", "name": "DiscountEngine", "role": "Tier evaluation and application"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": ["BILL.INVOICE_GENERATE"],
        "source_file": "services/billing/discount_apply.py",
        "source_start_line": 18,
        "source_end_line": 92,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Misconfigured tier thresholds or percentages directly erode margin; tier 3 at 15 % on $100k+ orders is the highest exposure.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "tier_1_threshold",
                "type": "float",
                "current": 10000,
                "default": 10000,
                "description": "Minimum trailing 12-month spend (USD) to qualify for Tier 1 discount.",
                "editable_by": "admin",
                "min_value": 0,
            },
            {
                "name": "tier_1_pct",
                "type": "float",
                "current": 5,
                "default": 5,
                "description": "Discount percentage applied at Tier 1.",
                "editable_by": "admin",
                "min_value": 0,
                "max_value": 30,
            },
            {
                "name": "tier_2_threshold",
                "type": "float",
                "current": 50000,
                "default": 50000,
                "description": "Minimum trailing 12-month spend (USD) to qualify for Tier 2 discount.",
                "editable_by": "admin",
                "min_value": 0,
            },
            {
                "name": "tier_2_pct",
                "type": "float",
                "current": 10,
                "default": 10,
                "description": "Discount percentage applied at Tier 2.",
                "editable_by": "admin",
                "min_value": 0,
                "max_value": 30,
            },
            {
                "name": "tier_3_threshold",
                "type": "float",
                "current": 100000,
                "default": 100000,
                "description": "Minimum trailing 12-month spend (USD) to qualify for Tier 3 discount.",
                "editable_by": "admin",
                "min_value": 0,
            },
            {
                "name": "tier_3_pct",
                "type": "float",
                "current": 15,
                "default": 15,
                "description": "Discount percentage applied at Tier 3.",
                "editable_by": "admin",
                "min_value": 0,
                "max_value": 30,
            },
        ],
    },

    {
        "rule_id": "BILL.OVERDUE_REMINDER",
        "slug": "bill-overdue-reminder",
        "title": "Overdue Invoice Reminder Sequence",
        "description": (
            "Sends automated payment reminder emails at configured intervals after "
            "the invoice due date.  If the balance is still unpaid after the "
            "collections escalation threshold, the account is flagged and handed "
            "off to the AR collections team."
        ),
        "why": (
            "A structured reminder sequence collects payment faster than ad-hoc "
            "follow-up and reduces the number of invoices that age into collections, "
            "where the recovery rate drops significantly and collection fees apply."
        ),
        "department": "Billing",
        "subsystem": "BILL",
        "owner": "Accounts Receivable Manager",
        "tags": ["ar", "collections", "reminders", "billing"],
        "status": "active",
        "trigger": "Daily scheduled check: invoice past due and unpaid",
        "conditions": {"invoice_status": "unpaid", "days_past_due_gt": 0},
        "actions": {
            "send_reminder_email_at_intervals": True,
            "escalate_to_collections_at_threshold": True,
        },
        "actors": [
            {"type": "automated", "name": "ARReminderService", "role": "Scheduled reminder sender"},
            {"type": "human", "name": "AR Collections Specialist", "role": "Handles accounts past escalation threshold"},
        ],
        "upstream_rule_ids": ["BILL.INVOICE_GENERATE"],
        "downstream_rule_ids": ["BILL.CREDIT_HOLD"],
        "source_file": "services/billing/overdue_reminder.py",
        "source_start_line": 25,
        "source_end_line": 100,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Invoices that reach collections cost 15–25 % in agency fees; reminder sequence recovers ~68 % of overdue AR before escalation.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "reminder_days",
                "type": "list",
                "current": [7, 14, 30],
                "default": [7, 14, 30],
                "description": "Days past due at which automatic reminder emails are sent (e.g., [7, 14, 30]).",
                "editable_by": "operator",
            },
            {
                "name": "escalate_to_collections_days",
                "type": "int",
                "current": 45,
                "default": 45,
                "description": "Days past due after which the invoice is escalated to the AR collections team.",
                "editable_by": "admin",
                "min_value": 30,
                "max_value": 180,
            },
        ],
    },

    {
        "rule_id": "BILL.CREDIT_HOLD",
        "slug": "bill-credit-hold",
        "title": "Credit Hold on Overdue Balance",
        "description": (
            "Blocks new order approval for any customer whose overdue outstanding "
            "balance exceeds the credit hold threshold.  Orders from held accounts "
            "are queued but not released until the balance falls below the "
            "threshold or the hold is manually overridden by a billing manager."
        ),
        "why": (
            "Extending new credit to customers with large overdue balances "
            "compounds AR risk.  A hard block — rather than a soft warning — "
            "ensures the sales team cannot bypass it without an explicit manager "
            "decision, creating an auditable approval chain."
        ),
        "department": "Billing",
        "subsystem": "BILL",
        "owner": "Finance Controller",
        "tags": ["credit-hold", "ar", "risk", "billing"],
        "status": "active",
        "trigger": "New order submitted; customer AR balance checked at order approval step",
        "conditions": {"customer_overdue_balance_gte": "credit_hold_threshold"},
        "actions": {
            "reject_order_approval": True,
            "notify_sales_rep": True,
            "notify_billing_manager": True,
            "queue_order_pending_hold_release": True,
        },
        "actors": [
            {"type": "automated", "name": "CreditCheckService", "role": "Balance lookup and hold enforcement"},
            {"type": "human", "name": "Billing Manager", "role": "Manual hold override authority"},
            {"type": "human", "name": "Sales Representative", "role": "Notified of hold"},
        ],
        "upstream_rule_ids": ["BILL.OVERDUE_REMINDER"],
        "downstream_rule_ids": ["NOTIFY.EXCEPTION_ALERT"],
        "source_file": "services/billing/credit_hold.py",
        "source_start_line": 10,
        "source_end_line": 72,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "critical",
        "cost_impact": "Threshold set too high allows large bad-debt exposure; too low blocks legitimate customers and erodes sales relationship.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "credit_hold_threshold",
                "type": "float",
                "current": 50000,
                "default": 50000,
                "description": "Overdue outstanding balance (USD) above which new orders are blocked pending hold review.",
                "editable_by": "admin",
                "min_value": 1000,
            },
        ],
    },

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================
    {
        "rule_id": "NOTIFY.DAILY_DIGEST",
        "slug": "notify-daily-digest",
        "title": "Daily Operations Digest",
        "description": (
            "Compiles and emails a summary of key operational metrics — orders "
            "received, fulfilled, shipped, and any open exceptions — to the "
            "configured recipient list every morning at the scheduled time."
        ),
        "why": (
            "Operations leadership needs a consistent morning briefing to identify "
            "overnight backlogs, SLA risks, and exception trends before the day "
            "begins.  A single digest reduces the need to pull reports manually "
            "from multiple systems."
        ),
        "department": "Notifications",
        "subsystem": "NOTIFY",
        "owner": "VP of Operations",
        "tags": ["digest", "reporting", "notifications", "ops"],
        "status": "active",
        "trigger": "Scheduled cron: daily at digest_time",
        "conditions": {},
        "actions": {
            "aggregate_prior_day_metrics": True,
            "compile_open_exceptions": True,
            "send_digest_email": True,
        },
        "actors": [
            {"type": "automated", "name": "DigestScheduler", "role": "Report compiler and sender"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": [],
        "source_file": "services/notifications/daily_digest.py",
        "source_start_line": 8,
        "source_end_line": 62,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "low",
        "cost_impact": "Low direct cost; failure to send creates information gaps that lead to delayed exception response.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "digest_time",
                "type": "str",
                "current": "07:00",
                "default": "07:00",
                "description": "Time of day (HH:MM, 24-hour, company timezone) at which the daily digest is sent.",
                "editable_by": "operator",
            },
            {
                "name": "recipients",
                "type": "list",
                "current": ["ops-team@acme.com"],
                "default": ["ops-team@acme.com"],
                "description": "Email addresses that receive the daily operations digest.",
                "editable_by": "admin",
            },
        ],
    },

    {
        "rule_id": "NOTIFY.SLA_WARNING",
        "slug": "notify-sla-warning",
        "title": "SLA Deadline Proximity Alert",
        "description": (
            "Sends an internal alert when an open order's committed SLA delivery "
            "date is within the configured warning window, giving operations staff "
            "time to intervene before the SLA is missed."
        ),
        "why": (
            "SLA misses carry penalty costs and customer satisfaction impacts. "
            "A warning buffer gives operations time to expedite the shipment, "
            "switch carriers, or proactively communicate with the customer — "
            "options that close once the deadline passes."
        ),
        "department": "Notifications",
        "subsystem": "NOTIFY",
        "owner": "Operations Manager",
        "tags": ["sla", "alert", "notifications", "escalation"],
        "status": "active",
        "trigger": "Scheduled check every 30 min: order SLA date within warning_hours_before",
        "conditions": {
            "order_status_not_in": ["delivered", "cancelled"],
            "sla_deadline_within_hours": "warning_hours_before",
        },
        "actions": {
            "send_alert_to_account_owner": True,
            "send_alert_to_ops_channel": True,
            "tag_order_as_at_risk": True,
        },
        "actors": [
            {"type": "automated", "name": "SLAMonitor", "role": "Deadline checker"},
            {"type": "human", "name": "Operations Manager", "role": "Receives alert and acts"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": ["NOTIFY.EXCEPTION_ALERT"],
        "source_file": "services/notifications/sla_warning.py",
        "source_start_line": 14,
        "source_end_line": 58,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "high",
        "cost_impact": "Each missed SLA triggers an average $500 penalty credit; a 4-hour warning window allows carrier upgrades in most markets.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "warning_hours_before",
                "type": "int",
                "current": 4,
                "default": 4,
                "description": "Hours before the SLA deadline at which the warning alert fires.",
                "editable_by": "operator",
                "min_value": 1,
                "max_value": 48,
            },
        ],
    },

    {
        "rule_id": "NOTIFY.EXCEPTION_ALERT",
        "slug": "notify-exception-alert",
        "title": "Immediate Exception Alert",
        "description": (
            "Fires an immediate alert across all configured channels when any "
            "upstream rule raises an order exception (e.g., stale shipment, "
            "credit hold, duplicate flag, SLA at-risk).  Includes a direct link "
            "to the order in the alert message."
        ),
        "why": (
            "Exceptions that sit unacknowledged compound in cost over time.  "
            "Multi-channel alerting (email + Slack) ensures the right person is "
            "reached quickly regardless of what they happen to be monitoring, "
            "reducing mean time to resolution."
        ),
        "department": "Notifications",
        "subsystem": "NOTIFY",
        "owner": "Operations Manager",
        "tags": ["alert", "exceptions", "notifications", "slack"],
        "status": "active",
        "trigger": "Exception raised by any upstream rule (credit hold, stale shipment, SLA warning, etc.)",
        "conditions": {"exception_severity": ["high", "critical"]},
        "actions": {
            "send_email_alerts": True,
            "post_slack_message": True,
            "create_exception_record": True,
        },
        "actors": [
            {"type": "automated", "name": "ExceptionAlertService", "role": "Multi-channel alert dispatcher"},
        ],
        "upstream_rule_ids": [
            "BILL.CREDIT_HOLD",
            "SHIP.DELAY_ESCALATE",
            "NOTIFY.SLA_WARNING",
            "INTAKE.PRIORITY_ROUTING",
        ],
        "downstream_rule_ids": [],
        "source_file": "services/notifications/exception_alert.py",
        "source_start_line": 6,
        "source_end_line": 70,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Faster exception response reduces resolution cost; alert fatigue from over-broad channels degrades effectiveness.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "alert_channels",
                "type": "list",
                "current": ["email", "slack"],
                "default": ["email", "slack"],
                "description": "Channels through which exception alerts are dispatched.",
                "editable_by": "operator",
                "allowed_values": ["email", "slack", "pagerduty", "sms"],
            },
            {
                "name": "slack_channel",
                "type": "str",
                "current": "#ops-alerts",
                "default": "#ops-alerts",
                "description": "Slack channel where exception alerts are posted.",
                "editable_by": "admin",
            },
        ],
    },

    {
        "rule_id": "NOTIFY.CUSTOMER_UPDATE",
        "slug": "notify-customer-update",
        "title": "Proactive Customer Milestone Updates",
        "description": (
            "Sends the customer an automated status update email each time their "
            "order reaches a configured milestone in the fulfillment lifecycle "
            "(e.g., picked, packed, shipped, delivered)."
        ),
        "why": (
            "Customers who receive proactive milestone updates are measurably less "
            "likely to contact support and more likely to reorder.  Configuring "
            "which milestones trigger messages allows tuning the cadence to avoid "
            "notification fatigue while keeping customers informed."
        ),
        "department": "Notifications",
        "subsystem": "NOTIFY",
        "owner": "Customer Success Manager",
        "tags": ["customer", "milestones", "notifications", "cx"],
        "status": "active",
        "trigger": "Order status changes to any value in the milestones list",
        "conditions": {"new_order_status_in": "milestones"},
        "actions": {
            "compose_milestone_email": True,
            "send_to_customer_email_on_file": True,
        },
        "actors": [
            {"type": "automated", "name": "NotificationService", "role": "Milestone email sender"},
            {"type": "external", "name": "Customer", "role": "Receives status updates"},
        ],
        "upstream_rule_ids": [
            "FULFILL.BACKORDER_NOTIFY",
            "SHIP.TRACKING_NOTIFY",
            "SHIP.DELIVERY_CONFIRM",
        ],
        "downstream_rule_ids": [],
        "source_file": "services/notifications/customer_update.py",
        "source_start_line": 10,
        "source_end_line": 55,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "low",
        "cost_impact": "Proactive updates reduce inbound CS contacts by ~25 %; adding too many milestones increases unsubscribe rates.",
        "customer_facing": True,
        "editable_fields": [
            {
                "name": "milestones",
                "type": "list",
                "current": ["picked", "packed", "shipped", "delivered"],
                "default": ["picked", "packed", "shipped", "delivered"],
                "description": "Order status values that trigger a customer milestone notification email.",
                "editable_by": "operator",
                "allowed_values": ["picked", "packed", "shipped", "out_for_delivery", "delivered", "backordered"],
            },
        ],
    },

    # =========================================================================
    # ANALYTICS
    # =========================================================================
    {
        "rule_id": "ANALYTICS.DAILY_KPI",
        "slug": "analytics-daily-kpi",
        "title": "Daily KPI Calculation",
        "description": (
            "Calculates three core operational KPIs each night: order fill rate, "
            "on-time delivery percentage, and average order cycle time.  Results "
            "are written to the metrics store and surfaced on the operations "
            "dashboard."
        ),
        "why": (
            "Fill rate, on-time %, and cycle time are the three metrics most "
            "directly tied to customer satisfaction and operational efficiency.  "
            "Nightly calculation over a rolling window provides trend data without "
            "the overhead of real-time aggregation."
        ),
        "department": "Analytics",
        "subsystem": "ANALYTICS",
        "owner": "Head of Operations Analytics",
        "tags": ["kpi", "analytics", "reporting", "ops"],
        "status": "active",
        "trigger": "Scheduled cron: nightly at 02:00",
        "conditions": {},
        "actions": {
            "compute_fill_rate": True,
            "compute_on_time_pct": True,
            "compute_avg_cycle_time": True,
            "write_to_metrics_store": True,
        },
        "actors": [
            {"type": "automated", "name": "KPICalculationJob", "role": "Scheduled batch computation"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": ["NOTIFY.DAILY_DIGEST"],
        "source_file": "services/analytics/daily_kpi.py",
        "source_start_line": 20,
        "source_end_line": 115,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "low",
        "cost_impact": "No direct operational cost; stale metrics lead to delayed detection of performance degradation.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "kpi_window_days",
                "type": "int",
                "current": 30,
                "default": 30,
                "description": "Rolling window (days) over which daily KPIs are calculated.",
                "editable_by": "operator",
                "min_value": 7,
                "max_value": 365,
            },
        ],
    },

    {
        "rule_id": "ANALYTICS.FORECAST_REFRESH",
        "slug": "analytics-forecast-refresh",
        "title": "Demand Forecast Refresh",
        "description": (
            "Re-runs the demand forecasting model on a weekly schedule to update "
            "inventory replenishment recommendations.  Supports configurable "
            "forecast horizon and model type."
        ),
        "why": (
            "Demand patterns shift with seasonality, promotions, and market "
            "conditions.  A weekly refresh balances forecast accuracy against "
            "the compute cost of running the model daily, and a 12-week horizon "
            "aligns with typical supplier lead times."
        ),
        "department": "Analytics",
        "subsystem": "ANALYTICS",
        "owner": "Demand Planning Manager",
        "tags": ["forecasting", "inventory", "analytics", "demand-planning"],
        "status": "active",
        "trigger": "Scheduled cron: weekly on Sunday at 01:00",
        "conditions": {},
        "actions": {
            "pull_historical_order_data": True,
            "run_forecasting_model": True,
            "write_forecast_to_inventory_system": True,
        },
        "actors": [
            {"type": "automated", "name": "ForecastJob", "role": "Model runner"},
            {"type": "ai_agent", "name": "ForecastingModel", "role": "Statistical demand model"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": [],
        "source_file": "services/analytics/forecast_refresh.py",
        "source_start_line": 15,
        "source_end_line": 90,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Poor forecast accuracy leads to overstock (carrying cost) or stockout (lost sales); model type affects both accuracy and compute time.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "forecast_horizon_weeks",
                "type": "int",
                "current": 12,
                "default": 12,
                "description": "Number of weeks ahead the demand forecast covers.",
                "editable_by": "operator",
                "min_value": 4,
                "max_value": 52,
            },
            {
                "name": "model_type",
                "type": "str",
                "current": "arima",
                "default": "arima",
                "description": "Forecasting model algorithm to use.",
                "editable_by": "admin",
                "allowed_values": ["arima", "prophet", "exponential_smoothing"],
            },
        ],
    },

    {
        "rule_id": "ANALYTICS.ANOMALY_DETECT",
        "slug": "analytics-anomaly-detect",
        "title": "Order Pattern Anomaly Detection",
        "description": (
            "Computes rolling statistical baselines for order volume, value, and "
            "SKU mix over the lookback window and flags any new order that falls "
            "more than sigma_threshold standard deviations outside the expected "
            "range for review."
        ),
        "why": (
            "Statistical outliers in order patterns are leading indicators of "
            "fraud, data-entry errors, or unusual customer behavior that warrant "
            "human review before fulfillment.  Sigma-based detection is more "
            "robust than fixed-value thresholds, which go stale as volume grows."
        ),
        "department": "Analytics",
        "subsystem": "ANALYTICS",
        "owner": "Head of Operations Analytics",
        "tags": ["anomaly", "fraud", "analytics", "quality"],
        "status": "active",
        "trigger": "New order created; evaluated at intake completion",
        "conditions": {},
        "actions": {
            "compute_zscore_vs_baseline": True,
            "flag_if_above_sigma_threshold": True,
            "route_to_exception_queue": True,
        },
        "actors": [
            {"type": "automated", "name": "AnomalyDetectionService", "role": "Statistical evaluator"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": ["NOTIFY.EXCEPTION_ALERT", "INTAKE.PRIORITY_ROUTING"],
        "source_file": "services/analytics/anomaly_detect.py",
        "source_start_line": 22,
        "source_end_line": 98,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Lower sigma threshold increases false positives and review labor; too high misses genuine fraud or errors.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "sigma_threshold",
                "type": "float",
                "current": 3.0,
                "default": 3.0,
                "description": "Number of standard deviations from the rolling mean above which an order is flagged as anomalous.",
                "editable_by": "operator",
                "min_value": 1.0,
                "max_value": 6.0,
            },
            {
                "name": "lookback_days",
                "type": "int",
                "current": 90,
                "default": 90,
                "description": "Rolling window (days) used to compute the baseline statistics for anomaly detection.",
                "editable_by": "operator",
                "min_value": 14,
                "max_value": 365,
            },
        ],
    },

    # =========================================================================
    # COMPLIANCE
    # =========================================================================
    {
        "rule_id": "COMPLY.DATA_RETENTION",
        "slug": "comply-data-retention",
        "title": "PII Data Retention and Purge",
        "description": (
            "Runs a nightly job that identifies customer PII records (addresses, "
            "contact details) older than the retention window and purges or "
            "anonymizes them in compliance with data privacy regulations."
        ),
        "why": (
            "Retaining PII beyond business necessity creates regulatory liability "
            "under CCPA, GDPR, and state data-protection laws.  Automated purge "
            "ensures compliance without relying on manual data-cleanup processes "
            "that are consistently deprioritized."
        ),
        "department": "Compliance",
        "subsystem": "COMPLY",
        "owner": "Data Privacy Officer",
        "tags": ["compliance", "privacy", "pii", "gdpr", "ccpa"],
        "status": "active",
        "trigger": "Scheduled cron: nightly at 03:00",
        "conditions": {"record_age_days_gte": "retention_days"},
        "actions": {
            "identify_pii_records_past_retention": True,
            "anonymize_or_delete_pii_fields": True,
            "write_purge_audit_log": True,
        },
        "actors": [
            {"type": "automated", "name": "DataRetentionJob", "role": "Scheduled purge runner"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": [],
        "source_file": "services/compliance/data_retention.py",
        "source_start_line": 18,
        "source_end_line": 80,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "critical",
        "cost_impact": "GDPR/CCPA fines can reach 4 % of global revenue; reducing retention_days below business-need window may delete data required for dispute resolution.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "retention_days",
                "type": "int",
                "current": 365,
                "default": 365,
                "description": "Number of days after last activity before customer PII is purged or anonymized.",
                "editable_by": "admin",
                "min_value": 90,
                "max_value": 2555,
            },
        ],
    },

    {
        "rule_id": "COMPLY.EXPORT_SCREEN",
        "slug": "comply-export-screen",
        "title": "International Export Denied Party Screening",
        "description": (
            "Screens all international orders against the U.S. denied party list "
            "and automatically blocks shipments to auto-blocked countries.  Orders "
            "that match a watch-list entity require manual compliance review before "
            "proceeding."
        ),
        "why": (
            "Exporting goods to sanctioned countries or denied parties carries "
            "criminal liability for the company and responsible individuals.  "
            "Automated screening at order creation is the standard industry "
            "control and is required under the Export Administration Regulations "
            "(EAR)."
        ),
        "department": "Compliance",
        "subsystem": "COMPLY",
        "owner": "Trade Compliance Officer",
        "tags": ["compliance", "export", "sanctions", "international"],
        "status": "active",
        "trigger": "Order created with ship-to country != US",
        "conditions": {"destination_country_is_international": True},
        "actions": {
            "check_country_against_block_list": True,
            "screen_customer_against_denied_party_list": True,
            "block_or_hold_order": True,
            "notify_compliance_team_on_match": True,
        },
        "actors": [
            {"type": "automated", "name": "ExportScreeningService", "role": "Sanctions list checker"},
            {"type": "external", "name": "BIS Denied Party List", "role": "Screening data source"},
            {"type": "human", "name": "Trade Compliance Officer", "role": "Reviews flagged orders"},
        ],
        "upstream_rule_ids": ["INTAKE.EMAIL_PARSER"],
        "downstream_rule_ids": ["FULFILL.WAREHOUSE_ASSIGN"],
        "source_file": "services/compliance/export_screen.py",
        "source_start_line": 10,
        "source_end_line": 88,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "critical",
        "cost_impact": "EAR violations carry fines up to $1M per shipment and potential criminal charges; false positives block legitimate international revenue.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "auto_block_countries",
                "type": "list",
                "current": ["NK", "IR", "SY"],
                "default": ["NK", "IR", "SY"],
                "description": "ISO 3166-1 alpha-2 country codes that are automatically blocked without review.",
                "editable_by": "admin",
            },
        ],
    },

    {
        "rule_id": "COMPLY.AUDIT_ARCHIVE",
        "slug": "comply-audit-archive",
        "title": "Audit Log Cold Storage Archival",
        "description": (
            "Runs a monthly job to move audit log records older than the configured "
            "threshold from the primary database to compressed cold storage, "
            "reducing hot-storage costs while preserving records for regulatory "
            "and legal hold purposes."
        ),
        "why": (
            "Audit logs grow continuously and are rarely queried after the first "
            "90 days.  Archiving to cold storage reduces primary DB size and cost "
            "without destroying records, satisfying both operational and regulatory "
            "retention requirements."
        ),
        "department": "Compliance",
        "subsystem": "COMPLY",
        "owner": "IT Infrastructure Manager",
        "tags": ["compliance", "audit", "archival", "storage"],
        "status": "planned",
        "trigger": "Scheduled cron: first day of each month at 04:00",
        "conditions": {"audit_log_age_days_gte": "archive_after_days"},
        "actions": {
            "select_logs_past_threshold": True,
            "compress_and_write_to_cold_storage": True,
            "delete_from_primary_db": True,
            "record_archive_manifest": True,
        },
        "actors": [
            {"type": "automated", "name": "ArchiveJob", "role": "Scheduled archival runner"},
            {"type": "external", "name": "Cold Storage Service (S3 Glacier / equivalent)", "role": "Archive destination"},
        ],
        "upstream_rule_ids": [],
        "downstream_rule_ids": [],
        "source_file": "services/compliance/audit_archive.py",
        "source_start_line": 12,
        "source_end_line": 65,
        "language": "python",
        "confidence": 1.0,
        "verified": True,
        "verified_by": "demo",
        "risk_level": "medium",
        "cost_impact": "Archiving reduces primary DB storage cost by ~40 %; setting archive_after_days too low archives logs that ops teams still query regularly.",
        "customer_facing": False,
        "editable_fields": [
            {
                "name": "archive_after_days",
                "type": "int",
                "current": 90,
                "default": 90,
                "description": "Audit log records older than this many days are moved to cold storage.",
                "editable_by": "admin",
                "min_value": 30,
                "max_value": 730,
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Upsert logic
# ---------------------------------------------------------------------------

def _slug_from_rule_id(rule_id: str) -> str:
    """Convert 'INTAKE.EMAIL_PARSER' -> 'intake-email-parser'."""
    return rule_id.replace(".", "-").replace("_", "-").lower()


def seed(verbose: bool = True) -> None:
    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # Ensure tables exist (no-op on Postgres with Alembic, creates on SQLite)
    create_tables_sync()

    gen = get_sync_db()
    session = next(gen)
    try:

        # ------------------------------------------------------------------
        # 1. Upsert demo tenant
        # ------------------------------------------------------------------
        tenant = (
            session.query(Tenant)
            .filter(Tenant.slug == DEMO_TENANT_SLUG)
            .first()
        )
        if tenant is None:
            tenant = Tenant(
                name=DEMO_TENANT_NAME,
                slug=DEMO_TENANT_SLUG,
                plan=PLAN_ENTERPRISE,
                settings={
                    "demo": True,
                    "industry": "logistics",
                    "description": "Order fulfillment, shipping, and invoicing automation demo.",
                },
            )
            session.add(tenant)
            session.flush()  # populate tenant.id before we reference it
            log(f"  [tenant] Created  '{DEMO_TENANT_NAME}' (slug={DEMO_TENANT_SLUG})")
        else:
            log(f"  [tenant] Exists   '{DEMO_TENANT_NAME}' (id={tenant.id})")

        tenant_id = tenant.id

        # ------------------------------------------------------------------
        # 2. Upsert each rule
        # ------------------------------------------------------------------
        now = datetime.now(timezone.utc)
        created_count = 0
        updated_count = 0

        for rdef in RULES:
            rule_id = rdef["rule_id"]

            existing: Rule | None = (
                session.query(Rule)
                .filter(Rule.tenant_id == tenant_id, Rule.rule_id == rule_id)
                .first()
            )

            if existing is None:
                # Fresh insert — build the rule and seed editable_field_values
                # from the defaults declared in editable_fields.
                initial_values: dict[str, Any] = {
                    f["name"]: f["default"]
                    for f in rdef.get("editable_fields", [])
                }

                rule = Rule(
                    tenant_id=tenant_id,
                    rule_id=rule_id,
                    slug=rdef.get("slug") or _slug_from_rule_id(rule_id),
                    title=rdef["title"],
                    description=rdef.get("description"),
                    why=rdef.get("why"),
                    department=rdef.get("department"),
                    subsystem=rdef.get("subsystem"),
                    owner=rdef.get("owner"),
                    tags=rdef.get("tags", []),
                    status=rdef.get("status", "active"),
                    trigger=rdef.get("trigger"),
                    conditions=rdef.get("conditions"),
                    actions=rdef.get("actions"),
                    actors=rdef.get("actors", []),
                    editable_fields=rdef.get("editable_fields", []),
                    editable_field_values=initial_values,
                    upstream_rule_ids=rdef.get("upstream_rule_ids", []),
                    downstream_rule_ids=rdef.get("downstream_rule_ids", []),
                    source_file=rdef.get("source_file"),
                    source_start_line=rdef.get("source_start_line"),
                    source_end_line=rdef.get("source_end_line"),
                    language=rdef.get("language", "python"),
                    confidence=rdef.get("confidence", 1.0),
                    verified=rdef.get("verified", True),
                    verified_by=rdef.get("verified_by", "demo"),
                    verified_at=now,
                    risk_level=rdef.get("risk_level"),
                    cost_impact=rdef.get("cost_impact"),
                    customer_facing=rdef.get("customer_facing"),
                    last_changed=now,
                    last_changed_by="seed_demo",
                    metadata_={"seeded_by": "seed_demo.py", "demo": True},
                )
                session.add(rule)
                created_count += 1
                log(f"  [rule]   Created  {rule_id}")

            else:
                # Existing rule — update all structural fields but DO NOT
                # overwrite editable_field_values; preserve any operator
                # customisations from a previous demo session.
                existing.slug = rdef.get("slug") or _slug_from_rule_id(rule_id)
                existing.title = rdef["title"]
                existing.description = rdef.get("description")
                existing.why = rdef.get("why")
                existing.department = rdef.get("department")
                existing.subsystem = rdef.get("subsystem")
                existing.owner = rdef.get("owner")
                existing.tags = rdef.get("tags", [])
                existing.status = rdef.get("status", "active")
                existing.trigger = rdef.get("trigger")
                existing.conditions = rdef.get("conditions")
                existing.actions = rdef.get("actions")
                existing.actors = rdef.get("actors", [])
                existing.editable_fields = rdef.get("editable_fields", [])
                # Preserve existing operator overrides; back-fill any newly
                # introduced fields with their defaults.
                current_values: dict[str, Any] = existing.editable_field_values or {}
                for f in rdef.get("editable_fields", []):
                    if f["name"] not in current_values:
                        current_values[f["name"]] = f["default"]
                existing.editable_field_values = current_values
                existing.upstream_rule_ids = rdef.get("upstream_rule_ids", [])
                existing.downstream_rule_ids = rdef.get("downstream_rule_ids", [])
                existing.source_file = rdef.get("source_file")
                existing.source_start_line = rdef.get("source_start_line")
                existing.source_end_line = rdef.get("source_end_line")
                existing.language = rdef.get("language", "python")
                existing.confidence = rdef.get("confidence", 1.0)
                existing.verified = rdef.get("verified", True)
                existing.verified_by = rdef.get("verified_by", "demo")
                existing.verified_at = existing.verified_at or now
                existing.risk_level = rdef.get("risk_level")
                existing.cost_impact = rdef.get("cost_impact")
                existing.customer_facing = rdef.get("customer_facing")
                existing.last_changed = now
                existing.last_changed_by = "seed_demo"
                existing.metadata_ = {"seeded_by": "seed_demo.py", "demo": True}
                updated_count += 1
                log(f"  [rule]   Updated  {rule_id}")

        session.commit()

        # ------------------------------------------------------------------
        # 3. Seed demo audit log entries (idempotent — skip if any exist)
        # ------------------------------------------------------------------
        existing_audit = session.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_id
        ).first()

        if existing_audit is None:
            from datetime import timedelta
            import random
            random.seed(42)  # deterministic demo data

            DEMO_OPERATORS = [
                "sarah.chen@acme.com",
                "mike.rodriguez@acme.com",
                "priya.patel@acme.com",
                "ops-admin@acme.com",
                "james.wilson@acme.com",
            ]

            # Build a lookup of rule titles for denormalization
            rule_titles = {}
            for rdef in RULES:
                rule_titles[rdef["rule_id"]] = rdef["title"]

            AUDIT_ENTRIES = [
                # --- Day 0 (today) ---
                {
                    "rule_id": "INTAKE.AUTO_APPROVE",
                    "action": "editable_update",
                    "field_name": "auto_approve_threshold",
                    "old_value": 5000,
                    "new_value": 7500,
                    "changed_by": "sarah.chen@acme.com",
                    "reason": "Too many small orders hitting manual review queue. Raising threshold to reduce operator load.",
                    "hours_ago": 2,
                },
                {
                    "rule_id": "SHIP.DELAY_ESCALATE",
                    "action": "editable_update",
                    "field_name": "stale_hours",
                    "old_value": 48,
                    "new_value": 36,
                    "changed_by": "mike.rodriguez@acme.com",
                    "reason": "Customers complained about late visibility. Tightening escalation window.",
                    "hours_ago": 5,
                },
                {
                    "rule_id": "BILL.DISCOUNT_APPLY",
                    "action": "editable_update",
                    "field_name": "tier_2_threshold",
                    "old_value": 50000,
                    "new_value": 40000,
                    "changed_by": "james.wilson@acme.com",
                    "reason": "Q2 promotion — lowering tier 2 entry to drive mid-market volume.",
                    "hours_ago": 6,
                },
                # --- Day 1 (yesterday) ---
                {
                    "rule_id": "FULFILL.QUALITY_CHECK",
                    "action": "editable_update",
                    "field_name": "always_qc_categories",
                    "old_value": ["hazmat", "fragile"],
                    "new_value": ["hazmat", "fragile", "electronics"],
                    "changed_by": "priya.patel@acme.com",
                    "reason": "High damage rate on electronics orders last month. Adding mandatory QC.",
                    "hours_ago": 28,
                },
                {
                    "rule_id": "NOTIFY.SLA_WARNING",
                    "action": "editable_update",
                    "field_name": "warning_hours_before",
                    "old_value": 4,
                    "new_value": 6,
                    "changed_by": "sarah.chen@acme.com",
                    "reason": "4 hours wasn't enough lead time for the ops team to intervene.",
                    "hours_ago": 30,
                },
                {
                    "rule_id": "ANALYTICS.ANOMALY_DETECT",
                    "action": "verify",
                    "field_name": None,
                    "old_value": None,
                    "new_value": None,
                    "changed_by": "priya.patel@acme.com",
                    "reason": "Reviewed extraction output, logic matches the anomaly detection service.",
                    "hours_ago": 32,
                },
                # --- Day 2 ---
                {
                    "rule_id": "SCN.RECIPIENTS.HIGH_VALUE_CC",
                    "action": "editable_update",
                    "field_name": "threshold",
                    "old_value": 500000,
                    "new_value": 350000,
                    "changed_by": "mike.rodriguez@acme.com",
                    "reason": "VP wants visibility on more deals. Lowering CC threshold.",
                    "hours_ago": 52,
                },
                {
                    "rule_id": "COMPLY.DATA_RETENTION",
                    "action": "editable_update",
                    "field_name": "retention_days",
                    "old_value": 365,
                    "new_value": 730,
                    "changed_by": "ops-admin@acme.com",
                    "reason": "Legal requested 2-year retention for ongoing litigation hold.",
                    "hours_ago": 55,
                },
                {
                    "rule_id": "FULFILL.PICK_BATCH",
                    "action": "editable_update",
                    "field_name": "batch_interval_minutes",
                    "old_value": 30,
                    "new_value": 20,
                    "changed_by": "sarah.chen@acme.com",
                    "reason": "Testing tighter batch window to improve same-day fulfillment rate.",
                    "hours_ago": 58,
                },
                # --- Day 3 ---
                {
                    "rule_id": "SHIP.CARRIER_SELECT",
                    "action": "editable_update",
                    "field_name": "preferred_carriers",
                    "old_value": ["FedEx", "UPS", "USPS"],
                    "new_value": ["FedEx", "UPS", "USPS", "DHL"],
                    "changed_by": "mike.rodriguez@acme.com",
                    "reason": "DHL contract signed for international. Adding to carrier pool.",
                    "hours_ago": 76,
                },
                {
                    "rule_id": "BILL.OVERDUE_REMINDER",
                    "action": "editable_update",
                    "field_name": "reminder_days",
                    "old_value": [7, 14, 30],
                    "new_value": [5, 10, 20, 30],
                    "changed_by": "james.wilson@acme.com",
                    "reason": "More aggressive follow-up schedule per CFO directive.",
                    "hours_ago": 80,
                },
                {
                    "rule_id": "BILL.CREDIT_HOLD",
                    "action": "editable_update",
                    "field_name": "credit_hold_threshold",
                    "old_value": 50000,
                    "new_value": 75000,
                    "changed_by": "james.wilson@acme.com",
                    "reason": "Loosening credit hold for large accounts — too many false blocks.",
                    "hours_ago": 81,
                },
                # --- Day 4 ---
                {
                    "rule_id": "INTAKE.DUPLICATE_CHECK",
                    "action": "verify",
                    "field_name": None,
                    "old_value": None,
                    "new_value": None,
                    "changed_by": "sarah.chen@acme.com",
                    "reason": "Confirmed duplicate detection logic matches the intake service code.",
                    "hours_ago": 100,
                },
                {
                    "rule_id": "NOTIFY.EXCEPTION_ALERT",
                    "action": "editable_update",
                    "field_name": "slack_channel",
                    "old_value": "#ops-alerts",
                    "new_value": "#ops-critical",
                    "changed_by": "priya.patel@acme.com",
                    "reason": "Moved critical alerts to dedicated channel to reduce noise.",
                    "hours_ago": 105,
                },
                {
                    "rule_id": "COMPLY.AUDIT_ARCHIVE",
                    "action": "status_change",
                    "field_name": "status",
                    "old_value": "planned",
                    "new_value": "active",
                    "changed_by": "ops-admin@acme.com",
                    "reason": "Archive job is now running in production. Activating rule.",
                    "hours_ago": 110,
                },
                # --- Day 5+ ---
                {
                    "rule_id": "FULFILL.WAREHOUSE_ASSIGN",
                    "action": "editable_update",
                    "field_name": "max_distance_miles",
                    "old_value": 500,
                    "new_value": 750,
                    "changed_by": "mike.rodriguez@acme.com",
                    "reason": "Expanded service radius after opening the Dallas DC.",
                    "hours_ago": 135,
                },
                {
                    "rule_id": "ANALYTICS.FORECAST_REFRESH",
                    "action": "editable_update",
                    "field_name": "forecast_horizon_weeks",
                    "old_value": 12,
                    "new_value": 16,
                    "changed_by": "priya.patel@acme.com",
                    "reason": "Planning team needs longer horizon for Q3 capacity planning.",
                    "hours_ago": 160,
                },
                {
                    "rule_id": "SHIP.LABEL_GENERATE",
                    "action": "editable_update",
                    "field_name": "lead_time_hours",
                    "old_value": 4,
                    "new_value": 3,
                    "changed_by": "sarah.chen@acme.com",
                    "reason": "Carrier pickup schedule shifted earlier. Reducing label lead time.",
                    "hours_ago": 168,
                },
            ]

            audit_count = 0
            for entry in AUDIT_ENTRIES:
                ts = now - timedelta(hours=entry["hours_ago"])
                log_entry = AuditLog(
                    tenant_id=tenant_id,
                    rule_id=entry["rule_id"],
                    rule_title=rule_titles.get(entry["rule_id"], entry["rule_id"]),
                    action=entry["action"],
                    field_name=entry["field_name"],
                    old_value=entry["old_value"],
                    new_value=entry["new_value"],
                    changed_by=entry["changed_by"],
                    reason=entry["reason"],
                    created_at=ts,
                )
                session.add(log_entry)
                audit_count += 1

            session.commit()
            log(f"\n  [audit]  Created {audit_count} demo audit log entries")
        else:
            log(f"\n  [audit]  Audit logs already exist — skipping")

        total = created_count + updated_count
        log("")
        log(f"Done. {total} rules processed ({created_count} created, {updated_count} updated).")
        log(f"Tenant: {DEMO_TENANT_NAME} | slug: {DEMO_TENANT_SLUG} | id: {tenant_id}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\nRunbook demo seed — {DEMO_TENANT_NAME}")
    print("=" * 55)
    try:
        seed(verbose=True)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
