import { reactive } from 'vue'
import { api } from '@/api/client.js'

const DEFAULT_TITLE = 'composegtfs'
const DEFAULT_PRIMARY_COLOR = '303845'
const DEFAULT_SECONDARY_COLOR = '1f69e0'
const DEFAULT_MAP_TILE_URL = 'https://tiles.openfreemap.org/styles/positron'

const state = reactive({
  appTitle: DEFAULT_TITLE,
  appPrimaryColor: DEFAULT_PRIMARY_COLOR,
  appSecondaryColor: DEFAULT_SECONDARY_COLOR,
  mapTileUrl: DEFAULT_MAP_TILE_URL,
  appVersion: '',
})

// ---------------------------------------------------------------------------
// Theme application helpers
// ---------------------------------------------------------------------------

function _hexToRgb(hex) {
  const h = hex.replace('#', '')
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ]
}

function _luminance([r, g, b]) {
  const lin = c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

/** Returns '#ffffff' for dark backgrounds, '#222222' for light ones. */
function _onColor(hex) {
  return _luminance(_hexToRgb(hex)) > 0.179 ? '#222222' : '#ffffff'
}

/**
 * Applies the current primary/secondary colors as CSS custom properties on
 * the document root so every component picks them up automatically.
 */
function applyTheme() {
  const primary   = '#' + state.appPrimaryColor.replace('#', '')
  const secondary = '#' + state.appSecondaryColor.replace('#', '')
  const onPrimary   = _onColor(primary)
  const onSecondary = _onColor(secondary)
  const root = document.documentElement.style
  // Primary (anthracite) → TopBar, Login, Toast backgrounds
  root.setProperty('--app-primary-color', primary)
  root.setProperty('--app-topbar-bg',     primary)
  root.setProperty('--app-login-bg',      primary)
  root.setProperty('--app-topbar-color',  onPrimary)
  root.setProperty('--app-login-accent',  onPrimary)
  // Secondary (blue) → filled buttons, section titles, active items, …
  root.setProperty('--md-sys-color-primary',    secondary)
  root.setProperty('--md-sys-color-on-primary', onSecondary)
}

async function load() {
  try {
    const data = await api.settings.get()
    state.appTitle = data.app_title || DEFAULT_TITLE
    state.appPrimaryColor = data.app_primary_color || DEFAULT_PRIMARY_COLOR
    state.appSecondaryColor = data.app_secondary_color || DEFAULT_SECONDARY_COLOR
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
  applyTheme()
}

function apply(data) {
  state.appTitle = data.app_title || DEFAULT_TITLE
  state.appPrimaryColor = data.app_primary_color || DEFAULT_PRIMARY_COLOR
  state.appSecondaryColor = data.app_secondary_color || DEFAULT_SECONDARY_COLOR
  state.mapTileUrl = data.map_tile_url || DEFAULT_MAP_TILE_URL
  applyTheme()
}

export const settingsStore = { state, load, apply }
