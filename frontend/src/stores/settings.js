import { reactive } from 'vue'
import { api } from '@/api/client.js'

const DEFAULT_TITLE = 'composegtfs'
const DEFAULT_MAP_TILE_URL = 'https://tiles.openfreemap.org/styles/positron'

const state = reactive({
  appTitle: DEFAULT_TITLE,
  mapTileUrl: DEFAULT_MAP_TILE_URL,
})

async function load() {
  try {
    const data = await api.settings.get()
    state.appTitle = data.app_title || DEFAULT_TITLE
    state.mapTileUrl = data.map_tile_url || DEFAULT_MAP_TILE_URL
  } catch {
    // keep defaults
  }
}

function apply(data) {
  state.appTitle = data.app_title || DEFAULT_TITLE
  state.mapTileUrl = data.map_tile_url || DEFAULT_MAP_TILE_URL
}

export const settingsStore = { state, load, apply }
