import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import AppView from '@/views/AppView.vue'
import AgencyView from '@/views/AgencyView.vue'
import CalendarView from '@/views/CalendarView.vue'
import AccountsView from '@/views/AccountsView.vue'
import SettingsView from '@/views/SettingsView.vue'
import NetworkView from '@/views/NetworkView.vue'
import ScheduleView from '@/views/ScheduleView.vue'
import VersionsView from '@/views/VersionsView.vue'
import ExchangeView from '@/views/ExchangeView.vue'
import GtfsExportView from '@/views/GtfsExportView.vue'
import { authStore } from '@/stores/auth.js'
import { permissionsStore } from '@/stores/permissions.js'
import { forbiddenState } from '@/stores/forbidden.js'
import { setUnauthorizedHandler, setForbiddenHandler } from '@/api/client.js'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/',
    name: 'app',
    component: AppView,
    children: [
      { path: '', redirect: { name: 'agency' } },
      {
        path: 'agency',
        name: 'agency',
        component: AgencyView,
        meta: { section: 'masterdata' },
      },
      {
        path: 'calendar',
        name: 'calendar',
        component: CalendarView,
        meta: { section: 'masterdata' },
      },
      {
        path: 'accounts',
        name: 'accounts',
        component: AccountsView,
        meta: { section: 'masterdata', permission: 'accounts:read' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: SettingsView,
        meta: { section: 'masterdata', permission: 'settings:read' },
      },
      {
        path: 'network',
        name: 'network',
        component: NetworkView,
        meta: { section: 'network', fullscreen: true, permission: 'network:read' },
      },
      {
        path: 'schedule',
        name: 'schedule',
        component: ScheduleView,
        meta: { section: 'schedule', fullscreen: true, permission: 'schedule:read' },
      },
      {
        path: 'versions',
        name: 'versions',
        component: VersionsView,
        meta: { fullscreen: true, permission: 'versions:read' },
      },
      {
        path: 'exchange',
        name: 'exchange',
        component: ExchangeView,
        meta: { section: 'exchange' },
      },
      {
        path: 'gtfs-export',
        name: 'gtfs-export',
        component: GtfsExportView,
        meta: { section: 'exchange', permission: 'gtfs:export' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if (!authStore.isAuthenticated()) {
    // Clear stale permissions so the next user gets a fresh load
    permissionsStore.reset()
    return '/login'
  }

  // Clear any previous forbidden state on every navigation
  forbiddenState.value = false

  // Ensure permissions are loaded before checking
  if (!permissionsStore.state.loaded && !permissionsStore.state.loading) {
    await permissionsStore.load()
  }

  // Client-side permission guard: show forbidden view but stay on the route
  const required = to.meta.permission
  if (required && !permissionsStore.state.isSuperuser && !permissionsStore.has(required)) {
    forbiddenState.value = true
  }

  return true
})

// Auto-logout when the backend rejects a token with 401
setUnauthorizedHandler(() => {
  authStore.logout()
  permissionsStore.reset()
  router.push('/login')
})

// Show forbidden view when the backend rejects a request with 403
setForbiddenHandler(() => {
  forbiddenState.value = true
})

export default router
