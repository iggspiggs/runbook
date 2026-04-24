import { create } from 'zustand'
import { getUsers } from '../api/client.js'

/**
 * Demo-mode "current user" store. Persists the selected user ID in
 * localStorage so page refreshes keep the same identity. All API calls
 * automatically send it as X-User-Id via the axios request interceptor.
 */
export const useCurrentUser = create((set, get) => ({
  users: [],
  currentUserId: localStorage.getItem('runbook_current_user_id') || '',
  currentUser: null,
  loading: false,
  error: null,

  loadUsers: async () => {
    set({ loading: true, error: null })
    try {
      const { items } = await getUsers()
      set({ users: items, loading: false })
      // Auto-select an admin or first user if nothing selected yet
      const currentId = get().currentUserId
      if (!currentId && items.length > 0) {
        const admin = items.find((u) => u.roles.includes('admin')) ?? items[0]
        get().setCurrentUser(admin.id)
      } else if (currentId) {
        const current = items.find((u) => u.id === currentId)
        if (current) set({ currentUser: current })
      }
    } catch (e) {
      set({ error: e.message ?? 'Failed to load users', loading: false })
    }
  },

  setCurrentUser: (userId) => {
    const user = get().users.find((u) => u.id === userId) || null
    localStorage.setItem('runbook_current_user_id', userId || '')
    set({ currentUserId: userId, currentUser: user })
  },

  hasRole: (role) => {
    const u = get().currentUser
    if (!u) return false
    return u.roles.includes(role)
  },

  hasAnyRole: (...roles) => {
    const u = get().currentUser
    if (!u) return false
    return roles.some((r) => u.roles.includes(r))
  },
}))
