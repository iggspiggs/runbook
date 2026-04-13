import axios from 'axios'

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const api = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Default tenant ID — in production this comes from auth context.
// For local dev / demo, we inject the Acme Logistics demo tenant.
// On first load, we auto-detect from the API and cache in localStorage.
let DEFAULT_TENANT_ID = localStorage.getItem('runbook_tenant_id') || ''

// Auto-detect tenant on first API call if not cached
async function ensureTenantId() {
  if (DEFAULT_TENANT_ID) return DEFAULT_TENANT_ID
  try {
    const resp = await axios.get('/api/tenants/demo')
    DEFAULT_TENANT_ID = resp.data?.id || resp.data?.tenant_id || ''
    if (DEFAULT_TENANT_ID) localStorage.setItem('runbook_tenant_id', DEFAULT_TENANT_ID)
  } catch {
    // Fallback — will be empty, API calls may fail until tenant is set
  }
  return DEFAULT_TENANT_ID
}

// Bootstrap: auto-detect tenant on first load
ensureTenantId()

// Request interceptor — attach auth token and default tenant_id
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('runbook_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // Skip tenant injection for the tenant discovery endpoint itself
    const url = config.url || ''
    if (url.includes('/tenants/')) return config

    // Auto-inject tenant_id into query params if not already present
    if (config.params && !config.params.tenant_id && DEFAULT_TENANT_ID) {
      config.params.tenant_id = DEFAULT_TENANT_ID
    } else if (!config.params && DEFAULT_TENANT_ID) {
      config.params = { tenant_id: DEFAULT_TENANT_ID }
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor — normalise error messages
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ??
      error.response?.data?.message ??
      error.message ??
      'An unexpected error occurred'

    const status = error.response?.status

    // Surface auth errors globally
    if (status === 401) {
      console.warn('[Runbook] Unauthorized — check API credentials')
    }

    const enriched = new Error(message)
    enriched.status = status
    enriched.original = error
    return Promise.reject(enriched)
  }
)

// ---------------------------------------------------------------------------
// Rules API
// ---------------------------------------------------------------------------

/**
 * Fetch the full rules list, optionally filtered.
 * @param {Object} filters - { department, status, risk_level, verified, search, page, page_size }
 */
export function getRules(filters = {}) {
  return api.get('/rules', { params: filters }).then(r => r.data)
}

/**
 * Fetch a single rule by ID.
 * @param {string} ruleId
 */
export function getRule(ruleId) {
  return api.get(`/rules/${ruleId}`).then(r => r.data)
}

/**
 * Update the editable fields of a rule.
 * @param {string} ruleId
 * @param {Object} updates - { field_key: new_value, ... }
 */
export function updateEditable(ruleId, updates) {
  return api.patch(`/rules/${ruleId}/editable`, updates).then(r => r.data)
}

/**
 * Mark a rule as verified by the current operator.
 * @param {string} ruleId
 */
export function verifyRule(ruleId) {
  return api.patch(`/rules/${ruleId}/verify`).then(r => r.data)
}

/**
 * Change the status of a rule (active, paused, planned, deferred).
 * @param {string} ruleId
 * @param {string} status
 */
export function updateRuleStatus(ruleId, status) {
  return api.patch(`/rules/${ruleId}/status`, { status }).then(r => r.data)
}

/**
 * Fetch audit history for a specific rule.
 * @param {string} ruleId
 * @param {Object} filters - { page, page_size }
 */
export function getRuleAudit(ruleId, filters = {}) {
  return api.get(`/rules/${ruleId}/audit`, { params: filters }).then(r => r.data)
}

// ---------------------------------------------------------------------------
// Extractions API
// ---------------------------------------------------------------------------

/**
 * Start a new extraction job.
 * @param {Object} params - { source_paths, mode, tags }
 */
export function startExtraction(params = {}) {
  return api.post('/extract', params).then(r => r.data)
}

/**
 * Poll extraction job status.
 * @param {string} jobId
 */
export function getExtractionStatus(jobId) {
  return api.get(`/extract/${jobId}`).then(r => r.data)
}

/**
 * Get extraction results (candidate rules found).
 * @param {string} jobId
 */
export function getExtractionResults(jobId) {
  return api.get(`/extract/${jobId}/results`).then(r => r.data)
}

/**
 * Commit extraction results into the live registry.
 * @param {string} jobId
 * @param {Object} options - { rule_ids: [], overwrite: boolean }
 */
export function commitExtraction(jobId, options = {}) {
  return api.post(`/extract/${jobId}/commit`, options).then(r => r.data)
}

/**
 * Fetch extraction job history.
 * @param {Object} filters - { page, page_size }
 */
export function getExtractionHistory(filters = {}) {
  return api.get('/extract/history', { params: filters }).then(r => r.data)
}

// ---------------------------------------------------------------------------
// Audit API
// ---------------------------------------------------------------------------

/**
 * Fetch audit log entries.
 * @param {Object} filters - { rule_id, operator, action, since, until, page, page_size }
 */
export function getAuditLog(filters = {}) {
  return api.get('/audit', { params: filters }).then(r => r.data)
}

/**
 * Export audit log as CSV.
 * Returns a Blob suitable for download.
 */
export function exportAudit(filters = {}) {
  return api
    .get('/audit/export', {
      params: filters,
      responseType: 'blob',
    })
    .then(r => r.data)
}

// ---------------------------------------------------------------------------
// Simulation API
// ---------------------------------------------------------------------------

/**
 * Simulate the effect of changing editable fields before committing.
 * @param {string} ruleId
 * @param {Object} proposedChanges - { field_key: proposed_value, ... }
 */
export function simulateChange(ruleId, proposedChanges) {
  return api.post('/simulate', { rule_id: ruleId, proposed_changes: proposedChanges }).then(r => r.data)
}

// ---------------------------------------------------------------------------
// Graph API
// ---------------------------------------------------------------------------

/**
 * Fetch the full rule dependency graph (nodes + edges).
 */
export function getGraph(filters = {}) {
  return api.get('/rules/graph', { params: filters }).then(r => r.data)
}

// ---------------------------------------------------------------------------
// Dashboard summary
// ---------------------------------------------------------------------------

/**
 * Fetch dashboard summary stats.
 * The backend has no dedicated /dashboard endpoint; we derive stats from
 * GET /api/rules with a large page size so the caller gets aggregate data.
 * The response is shaped to match the MOCK_STATS structure used by DashboardPage.
 */
export function getDashboardStats() {
  return api.get('/rules', { params: { page: 1, page_size: 500 } }).then(r => {
    const rules = r.data.items ?? r.data ?? []

    const total_rules = r.data.total ?? rules.length
    const active_rules = rules.filter(rule => rule.status === 'active').length
    const unverified_rules = rules.filter(rule => !rule.verified).length

    // Count rules changed in the last 24 hours
    const cutoff = Date.now() - 86_400_000
    const recent_changes = rules.filter(rule =>
      rule.last_changed && new Date(rule.last_changed).getTime() > cutoff
    ).length

    // Department breakdown
    const deptCounts = {}
    rules.forEach(rule => {
      const d = rule.department ?? 'Other'
      deptCounts[d] = (deptCounts[d] ?? 0) + 1
    })
    const DEPT_COLORS = {
      Finance: 'bg-indigo-500', Ops: 'bg-sky-500', IT: 'bg-teal-500',
      HR: 'bg-violet-500', Sales: 'bg-amber-500', Marketing: 'bg-pink-500',
      Legal: 'bg-slate-400', Other: 'bg-slate-300',
    }
    const departments = Object.entries(deptCounts).map(([name, count]) => ({
      name,
      count,
      color: DEPT_COLORS[name] ?? 'bg-slate-300',
    }))

    // Risk distribution
    const risk_distribution = { low: 0, medium: 0, high: 0, critical: 0 }
    rules.forEach(rule => {
      const lvl = rule.risk_level
      if (lvl in risk_distribution) risk_distribution[lvl]++
    })

    return {
      total_rules,
      active_rules,
      unverified_rules,
      recent_changes,
      departments,
      risk_distribution,
      extraction_health: null,
    }
  })
}

// ---------------------------------------------------------------------------
// Default export (raw instance for one-off calls)
// ---------------------------------------------------------------------------
export default api
