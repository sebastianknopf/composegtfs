/**
 * Permissions store.
 *
 * Holds the current user's effective permission codenames (union across all
 * assigned groups) and their superuser flag. Superusers implicitly hold every
 * permission — the backend already returns all codenames for them via /auth/me.
 *
 * Usage:
 *   import { permissionsStore } from '@/stores/permissions.js'
 *
 *   // Load once after login / on app mount (idempotent):
 *   await permissionsStore.load()
 *
 *   // Check a permission:
 *   permissionsStore.has('accounts:read')   // → true / false
 *   permissionsStore.hasAny('network:read', 'network:write')
 *
 *   // Reset on logout:
 *   permissionsStore.reset()
 *
 * For template use, prefer the usePermissions() composable which wraps this
 * store and returns reactive helpers.
 */

import { reactive } from 'vue'
import { api } from '@/api/client.js'

const _state = reactive({
  loaded: false,
  loading: false,
  isSuperuser: false,
  /** @type {Set<string>} */
  codenames: new Set(),
})

/**
 * Fetch the current user's effective permissions from the backend.
 * Safe to call multiple times — subsequent calls while loading or already
 * loaded are no-ops (pass force=true to reload).
 */
async function load(force = false) {
  if ((_state.loaded || _state.loading) && !force) return
  _state.loading = true
  try {
    const data = await api.me()
    _state.isSuperuser = data.is_superuser
    _state.codenames = new Set(data.permission_codenames)
    _state.loaded = true
  } finally {
    _state.loading = false
  }
}

/** Clear all permission data (call on logout). */
function reset() {
  _state.loaded = false
  _state.loading = false
  _state.isSuperuser = false
  _state.codenames = new Set()
}

/** Returns true if the current user holds the given permission codename. */
function has(codename) {
  return _state.codenames.has(codename)
}

/** Returns true if the current user holds at least one of the given codenames. */
function hasAny(...codenames) {
  return codenames.some(c => _state.codenames.has(c))
}

/** Returns true if the current user holds all of the given codenames. */
function hasAll(...codenames) {
  return codenames.every(c => _state.codenames.has(c))
}

export const permissionsStore = {
  state: _state,
  load,
  reset,
  has,
  hasAny,
  hasAll,
}
