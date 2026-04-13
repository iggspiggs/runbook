# Runbook — Operational Transparency as a Service

## What This Is
A pluggable platform that scans codebases and connected systems, extracts automation rules into a living registry, and gives non-technical operators a dashboard to understand and safely edit system behavior — without filing engineering tickets.

## Core Loop
1. **Scan** — LLM agent crawls codebase, identifies automation rules, thresholds, schedules, conditional logic
2. **Register** — Generates structured registry with rule IDs, triggers, conditions, actions, editable fields, dependencies
3. **Review** — Human validates/corrects extracted rules (trust-building step)
4. **Serve** — Operators get a living dashboard: search, filter, process DAG, edit safe parameters
5. **Guard** — Edits are validated, audit-logged, approval-gated by risk level. "What-if" simulation before commit.
6. **Drift** — On code change, agent re-scans and flags new/changed/broken rules vs. registry

## Stack
- **Backend**: Python 3.12+ / FastAPI / SQLAlchemy / Alembic / PostgreSQL
- **Frontend**: React 18 / Vite / TailwindCSS / ReactFlow (DAG viz) / Zustand (state)
- **Extraction Agent**: Claude API (Anthropic SDK) / AST parsing / git integration
- **SDK**: Python + JS packages for customers to annotate their own rules

## Ports
- Backend API: 8000
- Frontend Dev: 5173

## Key Directories
```
backend/
  app/
    models/          — SQLAlchemy models (rule, audit_log, tenant, user)
    routers/         — FastAPI endpoints (registry, extraction, audit, simulation)
    services/
      extractor/     — LLM-powered codebase scanning + rule extraction
      registry/      — Rule CRUD, validation, config writer sync
      drift/         — Change detection between code and registry
      simulator/     — "What-if" impact analysis engine
frontend/
  src/
    pages/           — Dashboard, Registry, Graph, Onboarding views
    components/      — Shared UI (EditableField, RiskBadge, DAG nodes)
    api/             — API client
    stores/          — Zustand state management
sdk/
  python/            — runbook_sdk — decorator + annotation library
  js/                — @runbook/sdk — JS equivalent
```

## Design Principles
- Registry is the source of truth for "what does this system do"
- Editable fields are a contract — only declared-safe parameters are exposed
- Every edit is audit-logged with who, when, old value, new value, and why
- Risk levels gate approval workflows (low = instant, high = requires approval)
- Drift detection keeps docs from going stale — the #1 killer of documentation
- Multi-tenant from day one — this is a SaaS product
