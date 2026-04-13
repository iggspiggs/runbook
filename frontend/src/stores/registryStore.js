import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { getRules, getRule, updateEditable, verifyRule } from '../api/client.js'

// ---------------------------------------------------------------------------
// Default filter shape
// ---------------------------------------------------------------------------
const DEFAULT_FILTERS = {
  search:      '',
  department:  '',
  status:      '',
  risk_level:  '',
  verified:    null,  // null = all, true = verified only, false = unverified only
  page:        1,
  page_size:   50,
  sort_by:     'rule_id',
  sort_dir:    'asc',
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------
const useRegistryStore = create(
  devtools(
    (set, get) => ({
      // -----------------------------------------------------------------------
      // State
      // -----------------------------------------------------------------------
      rules:        [],
      totalCount:   0,
      selectedRule: null,
      drawerOpen:   false,
      filters:      { ...DEFAULT_FILTERS },
      loading:      false,
      loadingRule:  false,
      error:        null,

      // -----------------------------------------------------------------------
      // Derived helpers (called as selectors, not stored values)
      // -----------------------------------------------------------------------

      // -----------------------------------------------------------------------
      // Actions
      // -----------------------------------------------------------------------

      /**
       * Fetch the rules list using current filters.
       */
      fetchRules: async () => {
        set({ loading: true, error: null }, false, 'fetchRules/start')
        try {
          const filters = get().filters
          const data = await getRules(filters)
          set(
            {
              rules:      data.items ?? data,
              totalCount: data.total ?? (data.items ?? data).length,
              loading:    false,
            },
            false,
            'fetchRules/success'
          )
        } catch (err) {
          set({ error: err.message, loading: false }, false, 'fetchRules/error')
        }
      },

      /**
       * Select and load a single rule into the drawer.
       * @param {string|null} ruleId - pass null to close
       */
      selectRule: async (ruleId) => {
        if (!ruleId) {
          set({ selectedRule: null, drawerOpen: false }, false, 'selectRule/close')
          return
        }

        // Optimistically show from list while loading full detail
        const existing = get().rules.find(r => r.rule_id === ruleId) ?? null
        set({ selectedRule: existing, drawerOpen: true, loadingRule: true }, false, 'selectRule/optimistic')

        try {
          const full = await getRule(ruleId)
          set({ selectedRule: full, loadingRule: false }, false, 'selectRule/success')
        } catch (err) {
          set({ loadingRule: false, error: err.message }, false, 'selectRule/error')
        }
      },

      /**
       * Close the rule drawer.
       */
      closeDrawer: () => {
        set({ drawerOpen: false, selectedRule: null }, false, 'closeDrawer')
      },

      /**
       * Update one or more filter values and re-fetch.
       * Resets page to 1 when a filter (non-page) changes.
       * @param {Object} patch - partial filter object
       */
      updateFilter: (patch) => {
        const isPageChange = Object.keys(patch).every(k => k === 'page' || k === 'page_size')
        set(
          state => ({
            filters: {
              ...state.filters,
              ...patch,
              ...(isPageChange ? {} : { page: 1 }),
            },
          }),
          false,
          'updateFilter'
        )
        get().fetchRules()
      },

      /**
       * Reset all filters to defaults and re-fetch.
       */
      clearFilters: () => {
        set({ filters: { ...DEFAULT_FILTERS } }, false, 'clearFilters')
        get().fetchRules()
      },

      /**
       * Toggle sort column. If same column, flip direction.
       * @param {string} column
       */
      setSort: (column) => {
        set(
          state => ({
            filters: {
              ...state.filters,
              sort_by:  column,
              sort_dir: state.filters.sort_by === column && state.filters.sort_dir === 'asc'
                ? 'desc'
                : 'asc',
              page: 1,
            },
          }),
          false,
          'setSort'
        )
        get().fetchRules()
      },

      /**
       * Save editable field updates and refresh selected rule.
       * @param {string} ruleId
       * @param {Object} updates
       */
      saveEditable: async (ruleId, updates) => {
        try {
          const updated = await updateEditable(ruleId, updates)
          // Patch in place within the list
          set(
            state => ({
              rules: state.rules.map(r => r.rule_id === ruleId ? { ...r, ...updated } : r),
              selectedRule: state.selectedRule?.rule_id === ruleId
                ? { ...state.selectedRule, ...updated }
                : state.selectedRule,
            }),
            false,
            'saveEditable/success'
          )
          return updated
        } catch (err) {
          set({ error: err.message }, false, 'saveEditable/error')
          throw err
        }
      },

      /**
       * Mark a rule as verified.
       * @param {string} ruleId
       */
      markVerified: async (ruleId) => {
        try {
          const updated = await verifyRule(ruleId)
          set(
            state => ({
              rules: state.rules.map(r => r.rule_id === ruleId ? { ...r, ...updated } : r),
              selectedRule: state.selectedRule?.rule_id === ruleId
                ? { ...state.selectedRule, ...updated }
                : state.selectedRule,
            }),
            false,
            'markVerified/success'
          )
          return updated
        } catch (err) {
          set({ error: err.message }, false, 'markVerified/error')
          throw err
        }
      },

      /**
       * Inline update selectedRule (e.g. after a simulation preview).
       */
      patchSelectedRule: (patch) => {
        set(
          state => ({
            selectedRule: state.selectedRule ? { ...state.selectedRule, ...patch } : null,
          }),
          false,
          'patchSelectedRule'
        )
      },
    }),
    { name: 'runbook/registry' }
  )
)

export default useRegistryStore
