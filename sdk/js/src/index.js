/**
 * @runbook/sdk
 * ===========
 *
 * JavaScript SDK for registering automation rules with the Runbook registry.
 *
 * Unlike the Python SDK, JavaScript lacks a decorator model that attaches
 * metadata to functions without build-time transforms (e.g. Babel).  This SDK
 * instead uses an explicit registration API that is called at module load time.
 *
 * Usage
 * -----
 *
 *   import { runbook } from '@runbook/sdk';
 *
 *   runbook.define({
 *     id:          'SCN.RECIPIENTS.HIGH_VALUE_CC',
 *     title:       'High-value contract CC recipients',
 *     department:  'shipping',
 *     riskLevel:   'medium',
 *     why:         'Ensures leadership visibility on large deals',
 *     trigger:     'contract_value > threshold',
 *   });
 *
 *   runbook.editable('SCN.RECIPIENTS.HIGH_VALUE_CC', 'threshold', {
 *     type:        'number',
 *     default:     500_000,
 *     description: 'Contract value threshold for CC logic',
 *     validation:  { min: 0 },
 *   });
 *
 *   runbook.editable('SCN.RECIPIENTS.HIGH_VALUE_CC', 'cc_list', {
 *     type:        'list',
 *     default:     ['vp@company.com'],
 *     description: 'CC recipients for high-value contracts',
 *   });
 *
 *   // At startup / in a scan script:
 *   await runbook.push('https://api.runbook.io', 'rb_live_...');
 *
 * @module @runbook/sdk
 */

'use strict';

// ── Validation helpers ────────────────────────────────────────────────────────

const VALID_RISK_LEVELS  = new Set(['low', 'medium', 'high', 'critical']);
const VALID_STATUSES     = new Set(['active', 'paused', 'planned', 'deferred']);
const VALID_FIELD_TYPES  = new Set(['string', 'number', 'boolean', 'select', 'list', 'email', 'json']);
const VALID_EDITABLE_BY  = new Set(['operator', 'admin', 'dev']);

/**
 * Assert a condition and throw TypeError with a helpful message if it fails.
 * @param {boolean} condition
 * @param {string}  message
 */
function assert(condition, message) {
  if (!condition) throw new TypeError(`[runbook-sdk] ${message}`);
}

// ── Module-level registry ─────────────────────────────────────────────────────

/**
 * Internal registry storage.
 * Keys are rule IDs (strings), values are rule definition objects.
 *
 * @type {Map<string, Object>}
 */
const _registry = new Map();

// ── Public API ────────────────────────────────────────────────────────────────

const runbook = {
  /**
   * Register a rule definition.
   *
   * This is the JS equivalent of the Python @rule decorator.  Call it at
   * module load time so the rule is available when runbook.push() is invoked.
   *
   * @param {Object} options
   * @param {string}  options.id            - Stable rule ID, e.g. 'SCN.RECIPIENTS.HIGH_VALUE_CC'
   * @param {string}  options.title         - Short human-readable name
   * @param {string}  [options.department]  - Owning department
   * @param {string}  [options.subsystem]   - Sub-component within the department
   * @param {string}  [options.description] - Longer explanation of what the rule does
   * @param {string}  [options.why]         - Business justification
   * @param {string}  [options.riskLevel]   - 'low'|'medium'|'high'|'critical'
   * @param {string}  [options.owner]       - Team or person responsible
   * @param {string[]}[options.tags]        - Free-form tags
   * @param {string}  [options.status]      - 'active'|'paused'|'planned'|'deferred'
   * @param {string}  [options.trigger]     - Trigger description or expression
   * @param {boolean} [options.customerFacing] - True if customer-visible
   * @param {string}  [options.costImpact]  - Free-text financial implications
   * @returns {typeof runbook} The runbook object for chaining.
   *
   * @example
   * runbook.define({
   *   id: 'BILLING.INVOICES.OVERDUE_ESCALATION',
   *   title: 'Overdue invoice escalation',
   *   department: 'billing',
   *   riskLevel: 'high',
   *   trigger: 'invoice.daysOverdue >= escalationThreshold',
   * });
   */
  define(options) {
    const { id, title, status = 'active', ...rest } = options;

    assert(typeof id === 'string' && id.length > 0, 'define() requires a non-empty string "id"');
    assert(typeof title === 'string' && title.length > 0, 'define() requires a non-empty string "title"');

    if (rest.riskLevel !== undefined) {
      assert(
        VALID_RISK_LEVELS.has(rest.riskLevel),
        `riskLevel must be one of: ${[...VALID_RISK_LEVELS].join(', ')}`,
      );
    }

    assert(
      VALID_STATUSES.has(status),
      `status must be one of: ${[...VALID_STATUSES].join(', ')}`,
    );

    if (_registry.has(id)) {
      console.warn(`[runbook-sdk] Rule "${id}" is being re-defined. Previous definition will be overwritten.`);
    }

    _registry.set(id, {
      rule_id:         id,
      title,
      status,
      department:      rest.department     ?? null,
      subsystem:       rest.subsystem      ?? null,
      description:     rest.description    ?? null,
      why:             rest.why            ?? null,
      risk_level:      rest.riskLevel      ?? null,
      owner:           rest.owner          ?? null,
      tags:            rest.tags           ?? [],
      trigger:         rest.trigger        ?? null,
      customer_facing: rest.customerFacing ?? null,
      cost_impact:     rest.costImpact     ?? null,
      editable:        [],
      upstream:        rest.upstream       ?? [],
      downstream:      rest.downstream     ?? [],
      source_file:     rest.sourceFile     ?? null,
    });

    return this;
  },

  /**
   * Declare an operator-tunable field on a previously registered rule.
   *
   * This is the JS equivalent of the Python @editable decorator.
   * Multiple calls with the same ruleId accumulate into the rule's editable list.
   *
   * @param {string} ruleId     - ID of the rule to attach the field to
   * @param {string} fieldName  - Name of the variable or config key
   * @param {Object} options
   * @param {string}  options.type        - 'string'|'number'|'boolean'|'select'|'list'|'email'|'json'
   * @param {*}       options.default     - Default/code-baked value
   * @param {string}  options.description - One-sentence explanation for the operator
   * @param {string}  [options.editableBy='operator'] - 'operator'|'admin'|'dev'
   * @param {*}       [options.current]   - Live value if different from default
   * @param {Object}  [options.validation] - Constraints: { min, max, options, pattern, maxItems }
   * @returns {typeof runbook} The runbook object for chaining.
   *
   * @example
   * runbook.editable('BILLING.INVOICES.OVERDUE_ESCALATION', 'escalationThreshold', {
   *   type:        'number',
   *   default:     30,
   *   description: 'Days overdue before escalation email is sent',
   *   validation:  { min: 1, max: 365 },
   * });
   */
  editable(ruleId, fieldName, options) {
    assert(typeof ruleId === 'string', 'editable() requires a string ruleId');
    assert(typeof fieldName === 'string', 'editable() requires a string fieldName');
    assert(options && typeof options === 'object', 'editable() requires an options object');

    const { type, description, editableBy = 'operator', validation, current } = options;
    const defaultValue = options.default; // 'default' is a reserved word

    assert(VALID_FIELD_TYPES.has(type), `type must be one of: ${[...VALID_FIELD_TYPES].join(', ')}`);
    assert(typeof description === 'string' && description.length > 0, 'editable() requires a non-empty "description"');
    assert(VALID_EDITABLE_BY.has(editableBy), `editableBy must be one of: ${[...VALID_EDITABLE_BY].join(', ')}`);

    if (type === 'select') {
      assert(
        validation && Array.isArray(validation.options) && validation.options.length > 0,
        `editable field "${fieldName}" has type "select" but no validation.options were provided`,
      );
    }

    if (!_registry.has(ruleId)) {
      console.warn(`[runbook-sdk] editable() called for unknown rule "${ruleId}". Did you call define() first?`);
      // Still register — the rule may be defined later in load order
      _registry.set(ruleId, { rule_id: ruleId, title: ruleId, status: 'active', editable: [] });
    }

    const rule = _registry.get(ruleId);
    rule.editable.push({
      field_name:  fieldName,
      field_type:  type,
      default:     defaultValue,
      current:     current !== undefined ? current : defaultValue,
      description,
      editable_by: editableBy,
      ...(validation !== undefined && { validation }),
    });

    return this;
  },

  /**
   * Retrieve all registered rules as an array of plain objects.
   *
   * The returned array is a snapshot — subsequent calls to define() or
   * editable() will not mutate previously returned snapshots.
   *
   * @returns {Object[]} List of rule definition objects, sorted by rule_id.
   *
   * @example
   * const rules = runbook.registry();
   * console.log(`${rules.length} rules registered`);
   */
  registry() {
    return [..._registry.values()].sort((a, b) => a.rule_id.localeCompare(b.rule_id));
  },

  /**
   * POST all registered rules to the Runbook API bulk-upsert endpoint.
   *
   * Uses the global fetch API (Node 18+ / all modern browsers).
   * Falls back to dynamic require('node:http') is intentionally not done —
   * consumers on older Node should polyfill fetch.
   *
   * @param {string} apiUrl  - Base URL of the Runbook API, e.g. 'https://api.runbook.io'
   * @param {string} apiKey  - API key with write access to the target tenant
   * @returns {Promise<Object>} Parsed JSON response from the API
   * @throws {Error} If the HTTP response is not ok (4xx/5xx)
   *
   * @example
   * await runbook.push('https://api.runbook.io', process.env.RUNBOOK_API_KEY);
   */
  async push(apiUrl, apiKey) {
    assert(typeof apiUrl === 'string' && apiUrl.length > 0, 'push() requires a non-empty apiUrl');
    assert(typeof apiKey === 'string' && apiKey.length > 0, 'push() requires a non-empty apiKey');

    const url = `${apiUrl.replace(/\/$/, '')}/api/v1/registry/bulk`;
    const payload = { rules: this.registry() };

    const response = await fetch(url, {
      method:  'POST',
      headers: {
        'Content-Type':     'application/json',
        'Authorization':    `Bearer ${apiKey}`,
        'X-Runbook-SDK':    'js/0.1.0',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '(no body)');
      throw new Error(
        `[runbook-sdk] push() failed — HTTP ${response.status} ${response.statusText}: ${text}`,
      );
    }

    return response.json();
  },

  /**
   * Remove all registered rules from the in-memory registry.
   *
   * Primarily useful in test suites to reset state between tests.
   *
   * @returns {typeof runbook}
   */
  clear() {
    _registry.clear();
    return this;
  },

  /**
   * Return the number of rules currently registered.
   *
   * @returns {number}
   */
  get size() {
    return _registry.size;
  },
};

export { runbook };
export default runbook;
