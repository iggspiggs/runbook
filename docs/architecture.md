# Runbook — Technical Architecture

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Data Flow](#2-data-flow)
3. [Component Descriptions](#3-component-descriptions)
4. [Multi-Tenancy Model](#4-multi-tenancy-model)
5. [Security Model](#5-security-model)
6. [SDK Integration Patterns](#6-sdk-integration-patterns)
7. [Deployment Architecture](#7-deployment-architecture)
8. [API Authentication](#8-api-authentication)

---

## 1. System Overview

Runbook is an **Operational Transparency Platform** — a SaaS product that scans
codebases, extracts automation rules into a living registry, and gives operators
a dashboard to understand and safely edit system behaviour without filing
engineering tickets.

### ASCII System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CUSTOMER CODEBASE                           │
│                                                                     │
│  ┌──────────────────────┐      ┌────────────────────────────────┐   │
│  │  Python / JS / etc.  │      │  runbook_sdk decorators        │   │
│  │  (any language)      │      │  @rule / @editable / @trigger  │   │
│  └──────────┬───────────┘      └────────────────┬───────────────┘   │
│             │                                   │                   │
│             │  git push / webhook               │  .push() / CI     │
│             │  or manual trigger                │                   │
└─────────────┼─────────────────────────────────┼───────────────────┘
              │                                  │
              ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         RUNBOOK PLATFORM                            │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     API SERVER (FastAPI)                       │ │
│  │                                                                │ │
│  │  /registry   /extraction   /audit   /simulation   /drift      │ │
│  └──────────────────────┬─────────────────────────────────────────┘ │
│                         │                                          │ │
│          ┌──────────────┼──────────────┐                           │ │
│          ▼              ▼              ▼                           │ │
│  ┌──────────────┐ ┌──────────┐ ┌─────────────┐                    │ │
│  │  Extraction  │ │ Registry │ │   Drift      │                    │ │
│  │  Service     │ │ Service  │ │   Service    │                    │ │
│  │  (LLM agent) │ │  (CRUD)  │ │  (diff/alert)│                   │ │
│  └──────┬───────┘ └────┬─────┘ └──────┬──────┘                    │ │
│         │              │              │                            │ │
│  ┌──────▼──────────────▼──────────────▼──────┐                    │ │
│  │           Simulator Service               │                    │ │
│  │        ("what-if" impact analysis)        │                    │ │
│  └───────────────────────────────────────────┘                    │ │
│                         │                                          │ │
│  ┌──────────────────────┴──────────────────────────────────────┐  │ │
│  │                   Job Queue (Redis + ARQ)                    │  │ │
│  │     Extraction Jobs  │  Drift Scan Jobs  │  Notify Jobs      │  │ │
│  └──────────────────────┬──────────────────────────────────────┘  │ │
│                         │                                          │ │
│  ┌──────────────────────▼──────────────────────────────────────┐  │ │
│  │                  PostgreSQL Database                         │  │ │
│  │   tenants │ users │ rules │ audit_logs │ extraction_runs     │  │ │
│  └─────────────────────────────────────────────────────────────┘  │ │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  React Frontend (Vite)                      │   │
│  │  Dashboard │ Registry │ DAG Graph │ Edit │ Simulation UI    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Flow

The Runbook lifecycle has six phases: **Scan → Extract → Register → Serve → Guard → Drift**.

### Phase 1 — Scan

```
Customer triggers scan:
  Option A: Git webhook (push to main branch)
  Option B: CI/CD step (runbook scan --api-key ...)
  Option C: SDK push (registry.push(url, key))
  Option D: Dashboard "Rescan" button
       │
       ▼
ExtractionJob enqueued in Redis
       │
       ▼
Worker picks up job:
  1. Clone / fetch repo at target commit
  2. Walk filesystem, collect .py / .js / .ts files
  3. Run AST pre-filter (skip test files, migrations, type stubs)
  4. Chunk large files into ~200-line overlapping windows
  5. For each chunk: send CHUNK_ANALYSIS_PROMPT to Claude API
  6. Aggregate rule candidates
  7. Run DEPENDENCY_RESOLUTION_PROMPT on full rule set
  8. Persist ExtractionRun + raw results to PostgreSQL
  9. Emit "extraction_complete" event
```

### Phase 2 — Extract

```
For each code chunk:
  Input:  file_path, language, code_content, surrounding_context
  LLM:    Claude (claude-opus-4 / claude-sonnet-4 depending on tier)
  Output: list of RuleDefinition JSON objects

  Quality gates:
  • Confidence < 0.3  → discard silently
  • Confidence 0.3–0.6 → include, flag "needs_review"
  • Confidence > 0.6  → include as draft (unverified=False)

  Deduplication:
  • If same rule_id already in registry for this tenant → compare and merge
  • If new rule_id → create as unverified draft
```

### Phase 3 — Register

```
ExtractionRun complete:
  1. Operator reviews draft rules in dashboard
  2. Edits descriptions, risk levels, editable field details
  3. Marks rules as "verified" (sets verified=True)
  4. Registry service writes final RuleDefinition to PostgreSQL
  5. Config writer sync (optional): pushes editable defaults back to
     customer's config file via PR or direct commit
```

### Phase 4 — Serve

```
Operators use dashboard daily:
  • Search and filter rules by department / risk / status / tags
  • View process DAG (upstream/downstream graph via ReactFlow)
  • Click a rule → see trigger, conditions, actions, editable fields
  • "What would happen if I change threshold from $500k to $250k?"
     → Simulator service traces downstream impact chain
```

### Phase 5 — Guard

```
Operator submits a field edit:
  1. Frontend POSTs to PATCH /api/v1/registry/{rule_id}/fields/{field_name}
  2. API validates new value against field's validation schema
  3. Risk gate check:
       low    → apply immediately, audit-log
       medium → apply immediately, notify owner by email
       high   → create approval request, notify owner + approvers
       critical → require two-person approval + written justification
  4. AuditLog record written: who, when, old_value, new_value, reason
  5. If config sync enabled: open PR with change in customer's repo
```

### Phase 6 — Drift

```
On every new code push / scheduled re-scan:
  For each existing verified rule in the registry:
    1. Locate source_file + source_lines in new code
    2. If file/function deleted → RULE_REMOVED drift alert
    3. If code changed → DRIFT_COMPARISON_PROMPT → classify change type
    4. If drift detected:
         • Mark rule as drift_detected=True
         • Create DriftAlert record with diff
         • Notify owner via webhook / email
         • Dashboard highlights drifted rules in orange
    5. Operator reviews drift alert, accepts or overrides
```

---

## 3. Component Descriptions

### API Server (`backend/app`)

Built with **FastAPI + SQLAlchemy + Alembic**.  Stateless; all persistence goes
through PostgreSQL.  Deployed as a standard ASGI application behind Nginx.

| Router | Responsibility |
|--------|----------------|
| `registry` | CRUD for rules, bulk upsert from SDK push |
| `extraction` | Trigger scans, query run status and results |
| `audit` | Read-only access to the audit log |
| `simulation` | Submit what-if scenarios, read simulation results |
| `drift` | List drift alerts, mark as resolved |
| `tenants` | Tenant provisioning (internal/admin only) |
| `auth` | JWT issue, refresh, API key management |

### Extraction Service (`services/extractor`)

Orchestrates the LLM-powered scan pipeline.

- `scanner.py` — filesystem walker, AST pre-filter, chunk generator
- `agent.py` — sends chunks to the Claude API, handles rate limits and retries
- `prompts.py` — all LLM prompt templates (see `prompts.py` for full detail)
- `merger.py` — deduplicates and merges new extractions against existing registry
- `runner.py` — ARQ worker task that ties the pipeline together

### Registry Service (`services/registry`)

Pure CRUD layer over the `rules` table with business rule enforcement.

- Validates rule_id format and uniqueness per tenant
- Enforces editable field validation schemas before applying changes
- Manages the approval workflow state machine for high-risk edits
- Emits change events consumed by the audit service

### Drift Service (`services/drift`)

- `detector.py` — compares current code against registry snapshots
- `classifier.py` — wraps the DRIFT_COMPARISON_PROMPT, parses results
- `alerts.py` — creates DriftAlert records, dispatches notifications

### Simulator Service (`services/simulator`)

- Given a proposed field value change, traverses the downstream dependency
  graph and produces a human-readable impact report
- Runs as a synchronous request (small graphs) or async job (large graphs)
- Impact report includes: affected rules, estimated blast radius, reversibility

### Frontend (`frontend/src`)

| Page / Component | Purpose |
|-----------------|---------|
| `pages/Dashboard` | Overview metrics, recent activity, drift alerts |
| `pages/Registry` | Searchable, filterable rule list |
| `pages/Graph` | ReactFlow DAG of rule dependencies |
| `pages/RuleDetail` | Full rule view + inline field editor |
| `pages/Simulation` | What-if sandbox |
| `components/EditableField` | Form control for operator edits |
| `components/RiskBadge` | Colour-coded risk indicator |
| `components/DriftAlert` | Inline drift notification card |

---

## 4. Multi-Tenancy Model

Runbook is fully multi-tenant from day one.  All data is scoped to a `tenant_id`
UUID; there is no shared data between tenants.

### Isolation Strategy

- **Database**: Row-level tenant isolation.  Every table with tenant-owned data
  has a `tenant_id` foreign key with a `CASCADE` delete.  No cross-tenant queries
  are possible via the ORM layer because the `TenantScopedSession` dependency
  injects `WHERE tenant_id = :current_tenant_id` into every query.

- **API**: Every request carries a tenant context derived from the authenticated
  principal (JWT claim `tenant_id` or API key → tenant lookup).  The FastAPI
  dependency `get_current_tenant()` is required on every protected route.

- **Storage**: Scanned repositories are cloned into tenant-namespaced temporary
  directories and deleted after the extraction job completes.

- **Jobs**: Redis job queues are namespaced by tenant ID.  A tenant's jobs cannot
  affect another tenant's processing time through queue starvation (per-tenant
  rate limits enforced at the API gateway).

### Tenant Tiers

| Tier | Rules | Scans/month | API calls/min | Features |
|------|-------|-------------|---------------|---------|
| Free | 25 | 5 | 60 | Manual scan only |
| Starter | 500 | 50 | 300 | Webhook triggers, email alerts |
| Pro | Unlimited | Unlimited | 1000 | Config sync, Slack/webhook |
| Enterprise | Unlimited | Unlimited | Custom | SSO, custom approval flows |

---

## 5. Security Model

### Authentication

See [Section 8](#8-api-authentication) for the full auth flow.

### Authorisation

Role-based access control (RBAC) within each tenant:

| Role | Permissions |
|------|------------|
| `viewer` | Read rules and audit log |
| `operator` | View + edit fields marked `editable_by: operator` |
| `admin` | Operator + edit `admin`-tier fields, approve medium-risk changes |
| `dev` | Admin + edit all fields, manage rule definitions |
| `owner` | Dev + manage users, billing, API keys |

Field-level permissions are enforced at the API layer: the
`FieldEditPermission` dependency checks that the requesting user's role
satisfies the field's `editable_by` requirement before allowing the edit.

### Audit Log

Every mutation to a rule is immutably recorded in `audit_logs`:

```
{
  "id":          UUID,
  "tenant_id":   UUID,
  "rule_id":     str,
  "actor_id":    UUID,        // user who made the change
  "actor_email": str,
  "action":      str,         // "field_edit" | "rule_create" | "rule_delete" | ...
  "field_name":  str | null,
  "old_value":   JSON,
  "new_value":   JSON,
  "reason":      str | null,  // required for high/critical changes
  "ip_address":  str,
  "user_agent":  str,
  "created_at":  datetime
}
```

Audit logs are append-only (no UPDATE or DELETE in application code).
Enterprise tenants can stream audit logs to their SIEM via webhook or S3 export.

### Secrets and Credentials

- API keys are stored as SHA-256 hashes; the plaintext is shown once at creation
- JWT secrets are rotated via environment variable; old tokens expire within
  the configured `ACCESS_TOKEN_TTL`
- Customer repository credentials (for scan access) are encrypted at rest using
  AES-256-GCM with a KMS-managed key

### Network Security

- All API traffic requires TLS 1.2+
- CORS is restricted to the dashboard origin and configured customer domains
- Rate limiting is enforced at the Nginx/API gateway layer
- LLM API calls are made server-side only; no API keys are ever sent to the browser

---

## 6. SDK Integration Patterns

### Pattern A — Decorator-First (Recommended for Python)

Best for greenfield or actively-maintained codebases.  Engineers annotate
functions directly; the scanner picks up decorators without an LLM call.

```python
# pip install runbook-sdk
from runbook_sdk import rule, editable, trigger

@rule(
    id="OPS.INVENTORY.LOW_STOCK_ALERT",
    title="Low stock alert threshold",
    department="operations",
    risk_level="medium",
)
@editable("threshold_units", type="number", default=50,
          description="Units remaining before alert fires")
@trigger("product.units_on_hand <= threshold_units")
def check_low_stock(product):
    ...
```

Extraction: `RunbookRegistry().scan_package("./src").push(api_url, api_key)`

### Pattern B — CI/CD Push

Best for organisations that want zero code changes.  The scanner runs as a
CI step and extracts rules via LLM analysis.

```yaml
# .github/workflows/runbook.yml
- name: Runbook Scan
  uses: runbook-io/action@v1
  with:
    api-key: ${{ secrets.RUNBOOK_API_KEY }}
    source-path: ./src
```

### Pattern C — JavaScript Registration

For JS/TS codebases.  Call `runbook.define()` at module load time.

```js
// npm install @runbook/sdk
import { runbook } from '@runbook/sdk';

runbook.define({
  id: 'COMM.CALC.SENIOR_TIER_THRESHOLD',
  title: 'Senior commission tier threshold',
  department: 'commissions',
  riskLevel: 'critical',
  trigger: 'rep.ytd_revenue >= tierThreshold',
});

runbook.editable('COMM.CALC.SENIOR_TIER_THRESHOLD', 'tierThreshold', {
  type: 'number', default: 1_000_000,
  description: 'YTD revenue threshold for senior commission tier',
  editableBy: 'admin',
  validation: { min: 0 },
});
```

### Pattern D — Webhook + Auto-Rescan

For teams using the LLM scanner without SDK annotations.  Configure a webhook
in the Runbook dashboard pointing to your GitHub/GitLab/Bitbucket repo.  On
every push to main, the platform automatically re-scans and presents a diff of
new, changed, and removed rules for review.

---

## 7. Deployment Architecture

### Production Topology

```
                            ┌──────────────────┐
                            │   DNS / CDN       │
                            │  (Cloudflare)     │
                            └────────┬─────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                  │
              ┌─────▼──────┐                   ┌──────▼──────┐
              │  Frontend  │                   │  API Server  │
              │  (static)  │                   │  (FastAPI)   │
              │  CDN edge  │                   │  2+ replicas │
              └────────────┘                   └──────┬───────┘
                                                      │
                                    ┌─────────────────┼────────────────┐
                                    │                 │                │
                              ┌─────▼──────┐   ┌─────▼──────┐  ┌─────▼──────┐
                              │ PostgreSQL  │   │  Redis     │  │  S3-compat │
                              │ (Primary + │   │  (job queue│  │  (repo     │
                              │  Replica)  │   │  + cache)  │  │   storage) │
                              └────────────┘   └─────┬──────┘  └────────────┘
                                                      │
                                              ┌───────▼───────┐
                                              │  ARQ Workers  │
                                              │  (extraction  │
                                              │   + drift     │
                                              │   + notify)   │
                                              └───────────────┘
```

### Service Sizing (starting point)

| Service | Replicas | vCPU | Memory | Notes |
|---------|----------|------|--------|-------|
| API server | 2–4 | 1 | 512 MB | Stateless, scale horizontally |
| ARQ workers | 2–8 | 2 | 1 GB | CPU-bound during extraction |
| PostgreSQL | 1 primary + 1 replica | 2 | 4 GB | Use managed DB in production |
| Redis | 1 (+ sentinel) | 1 | 512 MB | Job queue + caching |

### Container Layout

```
docker-compose.yml (development)
├── api          — FastAPI app (uvicorn, --reload)
├── worker       — ARQ worker (handles extraction, drift, notify queues)
├── db           — PostgreSQL 16
├── redis        — Redis 7
└── frontend     — Vite dev server

Dockerfile.api
Dockerfile.worker
```

### Environment Variables

```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/runbook

# Redis
REDIS_URL=redis://host:6379/0

# Auth
JWT_SECRET=<256-bit random>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL_SECONDS=3600

# LLM
ANTHROPIC_API_KEY=sk-ant-...
EXTRACTION_MODEL=claude-opus-4-5   # default model for extraction
EXTRACTION_MODEL_FAST=claude-haiku-4-5  # fast model for drift checks

# Optional
SENTRY_DSN=...
LOG_LEVEL=info
```

---

## 8. API Authentication

### Two Auth Schemes

Runbook uses two complementary auth schemes on the same API:

| Scheme | Used By | Token Format | Lifetime |
|--------|---------|--------------|---------|
| **JWT Bearer** | Dashboard (human users) | `eyJ...` | Short (1h access + 7d refresh) |
| **API Key Bearer** | SDK, CI/CD, integrations | `rb_live_...` | Until revoked |

### JWT Flow (Dashboard Users)

```
1. POST /auth/login  { email, password }
   → Returns: { access_token, refresh_token, expires_in }

2. All subsequent requests:
   Authorization: Bearer <access_token>

3. Token structure (claims):
   {
     "sub":       "<user_id>",
     "tenant_id": "<tenant_id>",
     "role":      "operator|admin|dev|owner",
     "iat":       <unix_ts>,
     "exp":       <unix_ts + 3600>
   }

4. Token refresh:
   POST /auth/refresh  { refresh_token }
   → Returns new access_token

5. Logout:
   POST /auth/logout  (revokes refresh token via Redis blocklist)
```

### API Key Flow (SDK / CI)

```
1. Owner creates API key in dashboard:
   POST /api/v1/auth/api-keys  { name: "production-scanner", scopes: ["registry:write"] }
   → Returns: { key: "rb_live_<random64>", key_id: "<uuid>" }
      (plaintext shown ONCE — stored as SHA-256 hash)

2. SDK usage:
   Authorization: Bearer rb_live_<key>
   X-Runbook-SDK: python/0.1.0   (for analytics)

3. Server validates:
   a. Hash incoming key: SHA-256(rb_live_<key>)
   b. Look up hash in api_keys table
   c. Check tenant_id, is_active, scopes
   d. Extract tenant context — same middleware path as JWT

4. API key scopes:
   registry:read    — GET /registry
   registry:write   — POST/PATCH /registry (SDK push, field edits)
   extraction:run   — POST /extraction/scan
   audit:read       — GET /audit
```

### Multi-Tenancy Enforcement

Both auth schemes flow through the same `get_current_tenant()` FastAPI
dependency, which:

1. Extracts `tenant_id` from the validated token/key
2. Loads the `Tenant` record and checks `is_active`
3. Injects a `TenantScopedSession` — an SQLAlchemy session with a default
   `WHERE tenant_id = :tid` filter applied to all queries via the ORM
4. Any attempt to query data outside the tenant's scope raises a 403

This means application code never needs to manually filter by tenant — the
session handles it, and accidentally omitting the filter is not possible.
