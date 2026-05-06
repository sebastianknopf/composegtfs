import { reactive } from 'vue'
import { api } from '@/api/client.js'

const state = reactive({
  routes: [],
  loading: false,
  selectedRouteId: null,
})

async function load(versionId) {
  if (!versionId) {
    state.routes = []
    return
  }
  state.loading = true
  try {
    state.routes = await api.routes.list(versionId)
  } catch {
    state.routes = []
  } finally {
    state.loading = false
  }
}

function select(routeId) {
  state.selectedRouteId = routeId
}

function reset() {
  state.routes = []
  state.loading = false
  state.selectedRouteId = null
}

export const routesStore = { state, load, select, reset }
