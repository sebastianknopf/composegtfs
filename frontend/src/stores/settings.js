import { reactive } from 'vue'
import { api } from '@/api/client.js'

const DEFAULT_TITLE = 'composegtfs'
const DEFAULT_MAP_TILE_URL = 'https://tiles.openfreemap.org/styles/positron'

const state = reactive({
  appTitle: DEFAULT_TITLE,
  mapTileUrl: DEFAULT_MAP_TILE_URL,
  appVersion: '',
})

async function load() {
  try {
    const data = await api.settings.get()
    state.appTitle = data.app_title || DEFAULT_TITLE
    state.mapTileUrl = data.map_tile_url || DEFAULT_MAP_TILE_URL
  } catch {
    // keep defaults
  }
  try {
    const data = await api.version()
    state.appVersion = data.version || ''
  } catch {
    // keep empty – non-critical
  }
}

function apply(data) {
  state.appTitle = data.app_title || DEFAULT_TITLE
  state.mapTileUrl = data.map_tile_url || DEFAULT_MAP_TILE_URL
}

export const settingsStore = { state, load, apply }
