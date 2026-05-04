/**
 * usePermissions() — Vue composable for reactive permission checks.
 *
 * Returns computed helpers based on the permissions store so that templates
 * automatically re-render when permissions change (e.g. after load or logout).
 *
 * USAGE IN A COMPONENT:
 *
 *   import { usePermissions } from '@/composables/usePermissions.js'
 *
 *   const { has, hasAny, hasAll, isSuperuser } = usePermissions()
 *
 *   // In template:
 *   <md-filled-button v-if="has('accounts:write')">Add user</md-filled-button>
 *   <div v-if="hasAny('network:read', 'network:write')">...</div>
 *
 * The store must be loaded once after the user logs in. The recommended place
 * is App.vue's onMounted / the router beforeEach guard:
 *
 *   import { permissionsStore } from '@/stores/permissions.js'
 *   await permissionsStore.load()
 *
 * Call permissionsStore.reset() on logout.
 */

import { computed } from 'vue'
import { permissionsStore } from '@/stores/permissions.js'

export function usePermissions() {
  /** Reactive boolean — true when the current user is a superuser. */
  const isSuperuser = computed(() => permissionsStore.state.isSuperuser)

  /**
   * Returns a computed boolean that is true when the user holds the given
   * permission codename. Reactive — updates automatically after load/reset.
   *
   * @param {string} codename  e.g. 'accounts:read'
   * @returns {import('vue').ComputedRef<boolean>}
   */
  function has(codename) {
    return computed(() => permissionsStore.has(codename))
  }

  /**
   * Returns a computed boolean that is true when the user holds at least one
   * of the given codenames.
   *
   * @param {...string} codenames
   * @returns {import('vue').ComputedRef<boolean>}
   */
  function hasAny(...codenames) {
    return computed(() => permissionsStore.hasAny(...codenames))
  }

  /**
   * Returns a computed boolean that is true when the user holds all of the
   * given codenames.
   *
   * @param {...string} codenames
   * @returns {import('vue').ComputedRef<boolean>}
   */
  function hasAll(...codenames) {
    return computed(() => permissionsStore.hasAll(...codenames))
  }

  return { isSuperuser, has, hasAny, hasAll }
}
