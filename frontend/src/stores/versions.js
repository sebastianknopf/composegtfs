import { reactive, computed } from 'vue'
import { api } from '@/api/client.js'

const LS_KEY = 'active_version_id'

const state = reactive({
  versions: [],
  activeVersionId: localStorage.getItem(LS_KEY) ?? null,
  loaded: false,
  loading: false,
})

/** The full version object for the currently active version, or null. */
const activeVersion = computed(() =>
  state.versions.find(v => v.id === state.activeVersionId) ?? null
)

async function load() {
  if (state.loading) return
  state.loading = true
  try {
    state.versions = await api.versions.list()
    state.loaded = true
    // If the stored ID is no longer valid, auto-select first alphabetically
    const valid = state.versions.find(v => v.id === state.activeVersionId)
    if (!valid && state.versions.length > 0) {
      const sorted = [...state.versions].sort((a, b) => {
        const ao = a.sort_order ?? Infinity
        const bo = b.sort_order ?? Infinity
        if (ao !== bo) return ao - bo
        return a.name.localeCompare(b.name)
      })
      setActive(sorted[0].id)
    }
  } catch {
    // Silently fail — e.g. 403 if user lacks versions:read
  } finally {
    state.loading = false
  }
}

function setActive(id) {
  state.activeVersionId = id
  localStorage.setItem(LS_KEY, id)
}

function reset() {
  state.versions = []
  state.activeVersionId = null
  state.loaded = false
  state.loading = false
  localStorage.removeItem(LS_KEY)
}

export const versionsStore = { state, activeVersion, load, setActive, reset }
