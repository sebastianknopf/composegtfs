<script setup>
import { onMounted, onActivated, onBeforeUnmount, ref, watch, computed } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useI18n } from 'vue-i18n'
import { settingsStore } from '@/stores/settings.js'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import StopEditPanel from '@/components/StopEditPanel.vue'
import PlatformEditPanel from '@/components/PlatformEditPanel.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import RoutesSideBar from '@/components/RoutesSideBar.vue'
import RouteEditPanel from '@/components/RouteEditPanel.vue'
import { routesStore } from '@/stores/routes.js'
import '@material/web/icon/icon.js'

const { t } = useI18n()
const { has } = usePermissions()
const canRead        = has('stops:read')
const canWrite       = has('stops:write')
const canDelete      = has('stops:delete')
const canReadRoutes   = has('routes:read')
const canWriteRoutes  = has('routes:write')
const canDeleteRoutes = has('routes:delete')

// ---------------------------------------------------------------------------
// Routes panel state
// ---------------------------------------------------------------------------
const routePanelVisible = ref(false)
const editingRoute      = ref(null)
const routePanelLoading = ref(false)
const routePanelError   = ref(null)

const versionId = computed(() => versionsStore.state.activeVersionId)

// Pre-loaded agencies for the route edit panel (fetched before the panel opens)
const preloadedAgencies = ref([])
async function fetchAgenciesForPanel() {
  if (!versionId.value) return
  try {
    preloadedAgencies.value = await api.routes.agenciesLookup(versionId.value)
  } catch {
    preloadedAgencies.value = []
  }
}

async function openCreateRoutePanel() {
  panelVisible.value = false
  platformPanelVisible.value = false
  editingRoute.value      = null
  routePanelError.value   = null
  await fetchAgenciesForPanel()
  routePanelVisible.value = true
}

async function openEditRoutePanel(route) {
  panelVisible.value = false
  platformPanelVisible.value = false
  editingRoute.value      = route
  routePanelError.value   = null
  await fetchAgenciesForPanel()
  routePanelVisible.value = true
}

async function handleRouteSave(data) {
  routePanelLoading.value = true
  routePanelError.value   = null
  try {
    if (editingRoute.value) {
      await api.routes.update(versionId.value, editingRoute.value.route_id, data)
    } else {
      await api.routes.create(versionId.value, data)
    }
    routePanelVisible.value = false
    await routesStore.load(versionId.value)
  } catch (err) {
    const msg = err?.response?.data?.detail ?? t('routes.error_generic')
    routePanelError.value = Array.isArray(msg) ? msg.map(e => e.msg).join('; ') : msg
  } finally {
    routePanelLoading.value = false
  }
}

const routeConfirmOpen    = ref(false)
const routeConfirmTitle   = ref('')
const routeConfirmMessage = ref('')

async function handleRouteReorder(orderedRoutes) {
  const vid = versionId.value
  if (!vid) return
  for (let i = 0; i < orderedRoutes.length; i++) {
    const route = orderedRoutes[i]
    if (route.route_sort_order !== i) {
      try {
        await api.routes.update(vid, route.route_id, { route_sort_order: i })
      } catch {
        toast.error(t('routes.error_generic'))
      }
    }
  }
  await routesStore.load(vid)
}

function handleRouteDeleteRequest() {
  routeConfirmTitle.value   = t('routes.delete_confirm_title')
  routeConfirmMessage.value = t('routes.delete_confirm_message')
  routeConfirmOpen.value    = true
}

async function handleRouteDeleteConfirmed() {
  if (!editingRoute.value) return
  routePanelLoading.value = true
  routePanelError.value   = null
  try {
    await api.routes.delete(versionId.value, editingRoute.value.route_id)
    routePanelVisible.value = false
    await routesStore.load(versionId.value)
  } catch (err) {
    const msg = err?.response?.data?.detail ?? t('routes.error_generic')
    routePanelError.value = Array.isArray(msg) ? msg.map(e => e.msg).join('; ') : msg
  } finally {
    routePanelLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------
const mapContainer = ref(null)
let map = null

const STOP_SOURCE     = 'stops-source'
const STOP_LAYER      = 'stops-layer'
const STOP_LABEL      = 'stops-label-layer'
const PLATFORM_SOURCE = 'platforms-source'
const PLATFORM_GLOW   = 'platforms-glow-layer'
const PLATFORM_LAYER  = 'platforms-layer'
const PLATFORM_LABEL  = 'platforms-label-layer'
const CLUSTER_LAYER   = 'stops-cluster-layer'
const CLUSTER_COUNT   = 'stops-cluster-count-layer'

// ---------------------------------------------------------------------------
// Stops data
// ---------------------------------------------------------------------------
const stopsData        = ref([])   // top-level stops from API (parent_station IS NULL)
const platformsData    = ref([])   // platforms for the currently-selected stop (panel list only)
const allPlatformsData = ref([])   // all platforms in the version (map source)

function buildGeojson(stops, overrideLat, overrideLon, overrideId) {
  return {
    type: 'FeatureCollection',
    features: stops
      .filter(s => s.stop_lat != null && s.stop_lon != null)
      .map(s => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: s.stop_id === overrideId
            ? [overrideLon, overrideLat]
            : [s.stop_lon, s.stop_lat],
        },
        properties: {
          stop_id:       s.stop_id,
          stop_name:     s.stop_name ?? '',
          location_type: s.location_type ?? 1,
        },
      })),
  }
}

async function loadStops() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId || !canRead.value) {
    stopsData.value = []
    updateMapSource([])
    allPlatformsData.value = []
    updatePlatformSource([])
    return
  }
  try {
    const result = await api.stops.list(versionId)
    stopsData.value = result
    updateMapSource(result)
  } catch {
    stopsData.value = []
    updateMapSource([])
  }
  await loadAllPlatforms()
}

function updateMapSource(stops) {
  if (!map || !map.getSource(STOP_SOURCE)) return
  map.getSource(STOP_SOURCE).setData(buildGeojson(stops))
}

function buildPlatformsGeojson(platforms, overrideLat, overrideLon, overrideId) {
  return {
    type: 'FeatureCollection',
    features: platforms
      .filter(p => p.stop_lat != null && p.stop_lon != null)
      .map(p => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: p.stop_id === overrideId
            ? [overrideLon, overrideLat]
            : [p.stop_lon, p.stop_lat],
        },
        properties: {
          stop_id:        p.stop_id,
          stop_name:      p.stop_name ?? '',
          parent_station: p.parent_station ?? '',
          platform_code:  p.platform_code ?? '',
        },
      })),
  }
}

function updatePlatformSource(platforms) {
  if (!map || !map.getSource(PLATFORM_SOURCE)) return
  map.getSource(PLATFORM_SOURCE).setData(buildPlatformsGeojson(platforms))
}

async function loadAllPlatforms() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId || !canRead.value) {
    allPlatformsData.value = []
    updatePlatformSource([])
    return
  }
  try {
    const result = await api.stops.listAllPlatforms(versionId)
    allPlatformsData.value = result
    updatePlatformSource(result)
  } catch {
    allPlatformsData.value = []
    updatePlatformSource([])
  }
}

async function loadPlatformsForStop(stop) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId || !stop) {
    platformsData.value = []
    return
  }
  try {
    const result = await api.stops.listPlatforms(versionId, stop.stop_id)
    platformsData.value = result
  } catch {
    platformsData.value = []
  }
}

// Draw a circular "H" badge onto a canvas and return ImageData for MapLibre.
function createStopMarkerImage() {
  const sz = 64   // rendered at 2x; displayed as 32px logical pixels
  const canvas = document.createElement('canvas')
  canvas.width  = sz
  canvas.height = sz
  const ctx = canvas.getContext('2d')

  // Drop shadow
  ctx.shadowColor   = 'rgba(0,0,0,0.35)'
  ctx.shadowBlur    = 5
  ctx.shadowOffsetY = 2

  // Blue filled circle
  ctx.beginPath()
  ctx.arc(sz / 2, sz / 2, sz / 2 - 3, 0, Math.PI * 2)
  ctx.fillStyle = '#1f69e0'
  ctx.fill()

  // Reset shadow before drawing text
  ctx.shadowColor   = 'transparent'
  ctx.shadowBlur    = 0
  ctx.shadowOffsetY = 0

  // White "H"
  ctx.fillStyle    = '#ffffff'
  ctx.font         = `bold ${Math.round(sz * 0.46)}px Arial, sans-serif`
  ctx.textAlign    = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('H', sz / 2, sz / 2)

  return ctx.getImageData(0, 0, sz, sz)
}

// ---------------------------------------------------------------------------
// Map layer setup
// ---------------------------------------------------------------------------
function addStopLayers() {
  // Register the circular stop marker image (2x for retina)
  if (!map.hasImage('stop-marker')) {
    const imgData = createStopMarkerImage()
    map.addImage('stop-marker', { width: 64, height: 64, data: imgData.data })
  }

  if (!map.getSource(STOP_SOURCE)) {
    map.addSource(STOP_SOURCE, {
      type: 'geojson',
      data: buildGeojson(stopsData.value),
      cluster:        true,
      clusterMaxZoom: 11,   // only cluster below zoom 12
      clusterRadius:  50,
    })
  }

  // Separate, non-clustered source for platforms
  if (!map.getSource(PLATFORM_SOURCE)) {
    map.addSource(PLATFORM_SOURCE, {
      type: 'geojson',
      data: buildPlatformsGeojson(platformsData.value),
    })
  }

  // --- Cluster bubbles (zoom < 12) ---
  if (!map.getLayer(CLUSTER_LAYER)) {
    map.addLayer({
      id: CLUSTER_LAYER,
      type: 'circle',
      source: STOP_SOURCE,
      filter: ['has', 'point_count'],
      maxzoom: 12,
      paint: {
        'circle-color': [
          'step', ['get', 'point_count'],
          '#1f69e0',  10,
          '#1555b8',  50,
          '#0d3d8a',
        ],
        'circle-radius': [
          'step', ['get', 'point_count'],
          18,  10,
          24,  50,
          30,
        ],
        'circle-opacity': 0.9,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2,
      },
    })
  }

  // --- Cluster count labels ---
  if (!map.getLayer(CLUSTER_COUNT)) {
    map.addLayer({
      id: CLUSTER_COUNT,
      type: 'symbol',
      source: STOP_SOURCE,
      filter: ['has', 'point_count'],
      maxzoom: 12,
      layout: {
        'text-field': '{point_count_abbreviated}',
        'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
        'text-size': 13,
        'text-allow-overlap': true,
      },
      paint: {
        'text-color': '#ffffff',
      },
    })
  }

  // --- Platform glow ring (drawn before platform circle so it sits underneath) ---
  if (!map.getLayer(PLATFORM_GLOW)) {
    map.addLayer({
      id: PLATFORM_GLOW,
      type: 'circle',
      source: PLATFORM_SOURCE,
      minzoom: 16,
      paint: {
        'circle-radius': 18,
        'circle-color': '#1f69e0',
        'circle-opacity': 0.28,
        'circle-blur': 1.2,
      },
    })
  }

  // --- Platform markers (own source, not clustered) ---
  if (!map.getLayer(PLATFORM_LAYER)) {
    map.addLayer({
      id: PLATFORM_LAYER,
      type: 'circle',
      source: PLATFORM_SOURCE,
      minzoom: 16,
      paint: {
        'circle-radius': 9,
        'circle-color': '#d6eaf8',
        'circle-stroke-color': '#1f69e0',
        'circle-stroke-width': 3,
      },
    })
  }

  // --- Platform name labels ---
  if (!map.getLayer(PLATFORM_LABEL)) {
    map.addLayer({
      id: PLATFORM_LABEL,
      type: 'symbol',
      source: PLATFORM_SOURCE,
      minzoom: 16,
      layout: {
        'text-field': ['coalesce', ['get', 'platform_code'], ['get', 'stop_name']],
        'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
        'text-size': 10,
        'text-offset': [0, 1.6],
        'text-anchor': 'top',
      },
      paint: {
        'text-color': '#1f69e0',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.5,
      },
    })
  }

  // --- Stop markers: circular H badge — added AFTER platform layers so stops render on top ---
  if (!map.getLayer(STOP_LAYER)) {
    map.addLayer({
      id: STOP_LAYER,
      type: 'symbol',
      source: STOP_SOURCE,
      filter: ['all', ['!', ['has', 'point_count']], ['!=', ['get', 'location_type'], 0]],
      layout: {
        'icon-image':            'stop-marker',
        'icon-size':             0.47,  // 64px image → ~30px display
        'icon-allow-overlap':    true,
        'icon-ignore-placement': true,
        'text-field':            '',
      },
    })
  }

  // --- Stop name labels ---
  if (!map.getLayer(STOP_LABEL)) {
    map.addLayer({
      id: STOP_LABEL,
      type: 'symbol',
      source: STOP_SOURCE,
      filter: ['!=', ['get', 'location_type'], 0],
      minzoom: 16,
      layout: {
        'text-field': ['get', 'stop_name'],
        'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
        'text-size': 13,
        'text-offset': [0, 1.6],
        'text-anchor': 'top',
        'text-allow-overlap': false,
      },
      paint: {
        'text-color': '#222222',
        'text-halo-color': '#ffffff',
        'text-halo-width': 2,
      },
    })
  }
}

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------
const contextMenu = ref({ visible: false, x: 0, y: 0, lng: 0, lat: 0 })

function showContextMenu(e) {
  if (!canWrite.value) return
  contextMenu.value = {
    visible: true,
    x: e.point.x,
    y: e.point.y,
    lng: e.lngLat.lng,
    lat: e.lngLat.lat,
  }
}

function hideContextMenu() {
  contextMenu.value.visible = false
}

// ---------------------------------------------------------------------------
// Edit panel
// ---------------------------------------------------------------------------
const panelVisible = ref(false)
const editingStop  = ref(null)   // null = create mode
const initLat      = ref(null)
const initLon      = ref(null)
const panelLoading = ref(false)
const panelError   = ref(null)

function openCreatePanel(lat, lon) {
  routePanelVisible.value = false
  editingStop.value  = null
  initLat.value      = lat
  initLon.value      = lon
  panelError.value   = null
  panelVisible.value = true
}

function openEditPanel(stop, { zoom = true } = {}) {
  routePanelVisible.value = false
  editingStop.value  = stop
  panelError.value   = null
  panelVisible.value = true
  loadPlatformsForStop(stop)
  if (zoom && stop.stop_lat != null && stop.stop_lon != null && map && map.getZoom() < 16) {
    map.easeTo({ center: [stop.stop_lon, stop.stop_lat], zoom: 17 })
  }
}

// Clear per-stop panel list when stop panel is intentionally closed (not during platform workflow)
watch(panelVisible, (val) => {
  if (!val && !addingPlatform.value && !platformPanelVisible.value) {
    platformsData.value = []
    platformParentStop.value = null
  }
})

async function handleSave(data) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  panelLoading.value = true
  panelError.value   = null
  try {
    if (editingStop.value) {
      await api.stops.update(versionId, editingStop.value.stop_id, data)
    } else {
      await api.stops.create(versionId, { ...data, location_type: 1 })
    }
    panelVisible.value = false
    await loadStops()
  } catch (err) {
    if (err?.status === 409) {
      panelError.value = t('stops.error_conflict')
    } else if (err?.status === 404) {
      panelError.value = t('stops.error_not_found')
    } else {
      toast.show(t('error.server'), 'error')
    }
  } finally {
    panelLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Delete confirm dialog
// ---------------------------------------------------------------------------
const confirmOpen    = ref(false)
const confirmTitle   = ref('')
const confirmMessage = ref('')

function handleDeleteRequest() {
  if (!editingStop.value) return
  confirmTitle.value   = t('stops.delete_confirm_title')
  confirmMessage.value = t('stops.delete_confirm_message', { name: editingStop.value.stop_name ?? editingStop.value.stop_id })
  confirmOpen.value    = true
}

async function handleDeleteConfirmed() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId || !editingStop.value) return
  panelLoading.value = true
  panelError.value   = null
  try {
    await api.stops.delete(versionId, editingStop.value.stop_id)
    panelVisible.value = false
    await loadStops()
  } catch (err) {
    toast.show(t('error.server'), 'error')
  } finally {
    panelLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Platform panel state & workflow
// ---------------------------------------------------------------------------
const platformPanelVisible = ref(false)
const editingPlatform      = ref(null)   // null = create mode
const platformInitLat      = ref(null)
const platformInitLon      = ref(null)
const platformLoading      = ref(false)
const platformError        = ref(null)
const platformParentStop   = ref(null)   // stop that was open when entering platform workflow

const addingPlatform = ref(false)        // crosshair placement mode

// Platform confirm dialog
const platformConfirmOpen    = ref(false)
const platformConfirmTitle   = ref('')
const platformConfirmMessage = ref('')

function handleAddPlatform() {
  platformParentStop.value = editingStop.value   // remember parent stop
  platformPanelVisible.value = false
  panelVisible.value = false                      // hide stop panel (sets addingPlatform FIRST to avoid watcher clearing platformParentStop)
  addingPlatform.value = true
  if (map) map.getCanvas().style.cursor = 'crosshair'
}

function cancelAddPlatform() {
  addingPlatform.value = false
  if (map) map.getCanvas().style.cursor = ''
  if (platformParentStop.value) panelVisible.value = true
}

function openPlatformCreatePanel(lat, lon) {
  // platformParentStop is already set by handleAddPlatform
  editingPlatform.value      = null
  platformInitLat.value      = lat
  platformInitLon.value      = lon
  platformError.value        = null
  platformPanelVisible.value = true
}

function openPlatformEditPanel(platform) {
  // Capture parent context before hiding stop panel
  platformParentStop.value = panelVisible.value ? editingStop.value : null
  editingPlatform.value    = platform
  platformError.value      = null
  // Open platform panel BEFORE hiding stop panel so panelVisible watcher doesn't clear platformParentStop
  platformPanelVisible.value = true
  panelVisible.value = false
  // No zoom when opening platform panel
}

// When platform panel closes → return to parent stop (if any)
watch(platformPanelVisible, (val) => {
  if (!val) {
    if (platformParentStop.value) {
      openEditPanel(platformParentStop.value, { zoom: false })
    } else {
      platformsData.value = []
    }
  }
})

async function handlePlatformSave(data) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  platformLoading.value = true
  platformError.value   = null
  try {
    if (editingPlatform.value) {
      await api.stops.updatePlatform(versionId, editingPlatform.value.parent_station, editingPlatform.value.stop_id, data)
    } else {
      const parentStopId = platformParentStop.value?.stop_id
      if (!parentStopId) throw new Error('No parent stop')
      await api.stops.createPlatform(versionId, parentStopId, data)
    }
    await loadAllPlatforms()
    platformPanelVisible.value = false   // watch will re-open stop panel and reload platforms
  } catch (err) {
    if (err?.status === 409) {
      platformError.value = t('platforms.error_conflict')
    } else if (err?.status === 404) {
      platformError.value = t('platforms.error_not_found')
    } else {
      toast.show(t('error.server'), 'error')
    }
  } finally {
    platformLoading.value = false
  }
}

function handlePlatformDeleteRequest() {
  if (!editingPlatform.value) return
  platformConfirmTitle.value   = t('platforms.delete_confirm_title')
  platformConfirmMessage.value = t('platforms.delete_confirm_message', {
    name: editingPlatform.value.stop_name ?? editingPlatform.value.stop_id,
  })
  platformConfirmOpen.value = true
}

async function handlePlatformDeleteConfirmed() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId || !editingPlatform.value) return
  platformLoading.value = true
  platformError.value   = null
  try {
    await api.stops.deletePlatform(versionId, editingPlatform.value.parent_station, editingPlatform.value.stop_id)
    await loadAllPlatforms()
    platformPanelVisible.value = false   // watch will re-open stop panel and reload platforms
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    platformLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Stop + Platform marker interaction (click + drag-to-move)
// ---------------------------------------------------------------------------
let draggingStop    = null   // stop object currently being interacted with
let dragCurrentLat  = null
let dragCurrentLng  = null
let isDragEnabled   = false

let draggingPlatform     = null   // platform object currently being interacted with
let platformDragLat      = null
let platformDragLng      = null
let isPlatformDragEnabled = false

function attachMarkerInteraction() {
  if (!map) return

  // --- Cluster click: zoom in ---
  map.on('click', CLUSTER_LAYER, async (e) => {
    const features = map.queryRenderedFeatures(e.point, { layers: [CLUSTER_LAYER] })
    if (!features.length) return
    const clusterId = features[0].properties.cluster_id
    try {
      const zoom = await map.getSource(STOP_SOURCE).getClusterExpansionZoom(clusterId)
      map.easeTo({ center: features[0].geometry.coordinates, zoom: Math.max(zoom, 12) })
    } catch (_) { /* ignore */ }
  })
  map.on('mouseenter', CLUSTER_LAYER, () => { map.getCanvas().style.cursor = 'pointer' })
  map.on('mouseleave', CLUSTER_LAYER, () => { map.getCanvas().style.cursor = '' })

  // --- Stop mousedown (track for click/drag) ---
  map.on('mousedown', STOP_LAYER, (e) => {
    if (addingPlatform.value) return   // in crosshair mode, ignore
    const feat = e.features?.[0]
    if (!feat) return
    const stop = stopsData.value.find(s => s.stop_id === feat.properties.stop_id)
    if (!stop) return

    draggingStop = stop; dragCurrentLat = null; dragCurrentLng = null; isDragEnabled = false

    const isEditingThisStop = panelVisible.value && editingStop.value?.stop_id === stop.stop_id
    if (isEditingThisStop && canWrite.value) {
      e.preventDefault()
      map.dragPan.disable()
      isDragEnabled = true
      map.getCanvas().style.cursor = 'grabbing'
    }
  })

  // --- Platform mousedown (drag only — no direct-click open; use stop panel to edit platforms) ---
  map.on('mousedown', PLATFORM_LAYER, (e) => {
    if (addingPlatform.value) return
    const feat = e.features?.[0]
    if (!feat) return
    const platform = allPlatformsData.value.find(p => p.stop_id === feat.properties.stop_id)
    if (!platform) return

    draggingPlatform = platform; platformDragLat = null; platformDragLng = null; isPlatformDragEnabled = false

    const isEditingThis = platformPanelVisible.value && editingPlatform.value?.stop_id === platform.stop_id
    if (isEditingThis && canWrite.value) {
      e.preventDefault()
      map.dragPan.disable()
      isPlatformDragEnabled = true
      map.getCanvas().style.cursor = 'grabbing'
    }
  })

  // --- Global mousemove: live drag preview ---
  map.on('mousemove', (e) => {
    if (draggingStop && isDragEnabled) {
      dragCurrentLat = e.lngLat.lat
      dragCurrentLng = e.lngLat.lng
      map.getSource(STOP_SOURCE)?.setData(
        buildGeojson(stopsData.value, dragCurrentLat, dragCurrentLng, draggingStop.stop_id)
      )
    }
    if (draggingPlatform && isPlatformDragEnabled) {
      platformDragLat = e.lngLat.lat
      platformDragLng = e.lngLat.lng
      map.getSource(PLATFORM_SOURCE)?.setData(
        buildPlatformsGeojson(allPlatformsData.value, platformDragLat, platformDragLng, draggingPlatform.stop_id)
      )
    }
  })

  // --- Global mouseup: commit drag or open panel ---
  map.on('mouseup', () => {
    // Handle stop
    if (draggingStop) {
      if (isDragEnabled) { map.dragPan.enable(); isDragEnabled = false }
      map.getCanvas().style.cursor = ''
      const stopId = draggingStop.stop_id

      if (dragCurrentLat !== null) {
        const idx = stopsData.value.findIndex(s => s.stop_id === stopId)
        if (idx !== -1) stopsData.value[idx] = { ...stopsData.value[idx], stop_lat: dragCurrentLat, stop_lon: dragCurrentLng }
        const updated = stopsData.value.find(s => s.stop_id === stopId)
        if (updated) {
          if (panelVisible.value && editingStop.value?.stop_id === stopId) editingStop.value = { ...updated }
          else openEditPanel(updated)
        }
      } else if (!addingPlatform.value) {
        const stop = stopsData.value.find(s => s.stop_id === stopId)
        if (stop) {
          // If platform panel is open, close it silently (no return-to-parent) before opening the new stop
          if (platformPanelVisible.value) {
            platformParentStop.value = null
            platformPanelVisible.value = false
          }
          openEditPanel(stop)
        }
      }
      draggingStop = null; dragCurrentLat = null; dragCurrentLng = null
    }

    // Handle platform
    if (draggingPlatform) {
      if (isPlatformDragEnabled) { map.dragPan.enable(); isPlatformDragEnabled = false }
      map.getCanvas().style.cursor = ''
      const platformId = draggingPlatform.stop_id

      if (platformDragLat !== null) {
        // Update allPlatformsData (map source) and platformsData (panel list)
        const allIdx = allPlatformsData.value.findIndex(p => p.stop_id === platformId)
        if (allIdx !== -1) allPlatformsData.value[allIdx] = { ...allPlatformsData.value[allIdx], stop_lat: platformDragLat, stop_lon: platformDragLng }
        const panelIdx = platformsData.value.findIndex(p => p.stop_id === platformId)
        if (panelIdx !== -1) platformsData.value[panelIdx] = { ...platformsData.value[panelIdx], stop_lat: platformDragLat, stop_lon: platformDragLng }
        const updated = allPlatformsData.value.find(p => p.stop_id === platformId)
        if (updated && platformPanelVisible.value && editingPlatform.value?.stop_id === platformId) {
          editingPlatform.value = { ...updated }
        }
      }
      // No click-to-open: platforms are only opened via the stop panel
      draggingPlatform = null; platformDragLat = null; platformDragLng = null
    }
  })

  // --- Stop hover cursor ---
  map.on('mouseenter', STOP_LAYER, (e) => {
    if (draggingStop || draggingPlatform || addingPlatform.value) return
    const stopId = e.features?.[0]?.properties?.stop_id
    const isDraggable = canWrite.value && panelVisible.value && editingStop.value?.stop_id === stopId
    map.getCanvas().style.cursor = isDraggable ? 'grab' : 'pointer'
  })
  map.on('mouseleave', STOP_LAYER, () => {
    if (!draggingStop && !draggingPlatform && !addingPlatform.value) map.getCanvas().style.cursor = ''
  })

  // --- Platform hover cursor ---
  map.on('mouseenter', PLATFORM_LAYER, (e) => {
    if (draggingStop || draggingPlatform || addingPlatform.value) return
    const pId = e.features?.[0]?.properties?.stop_id
    const isDraggable = canWrite.value && platformPanelVisible.value && editingPlatform.value?.stop_id === pId
    map.getCanvas().style.cursor = isDraggable ? 'grab' : 'default'
  })
  map.on('mouseleave', PLATFORM_LAYER, () => {
    if (!draggingStop && !draggingPlatform && !addingPlatform.value) map.getCanvas().style.cursor = ''
  })
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(async () => {
  if (!settingsStore.state.mapTileUrl) {
    await settingsStore.load()
  }
  map = new maplibregl.Map({
    container: mapContainer.value,
    style: settingsStore.state.mapTileUrl,
    center: [10.0, 51.0],
    zoom: 6,
  })
  map.addControl(new maplibregl.NavigationControl(), 'top-right')
  map.dragRotate.disable()
  map.touchZoomRotate.disableRotation()
  window.addEventListener('keydown', handleKeyDown)

  map.on('load', () => {
    addStopLayers()
    attachMarkerInteraction()
    loadStops()
    if (canReadRoutes.value) {
      routesStore.load(versionsStore.state.activeVersionId)
    }
  })

  map.on('contextmenu', (e) => {
    e.preventDefault()
    showContextMenu(e)
  })

  map.on('click', (e) => {
    hideContextMenu()
    if (addingPlatform.value) {
      addingPlatform.value = false
      if (map) map.getCanvas().style.cursor = ''
      openPlatformCreatePanel(e.lngLat.lat, e.lngLat.lng)
    }
  })

  map.on('dragstart', () => {
    hideContextMenu()
  })
})

onActivated(() => {
  map?.resize()
})

function handleKeyDown(e) {
  if (e.key === 'Escape' && addingPlatform.value) {
    cancelAddPlatform()
  }
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  map?.remove()
  map = null
})

// Reload stops when the active version changes
watch(() => versionsStore.state.activeVersionId, () => {
  loadStops()
  if (canReadRoutes.value) {
    routesStore.load(versionsStore.state.activeVersionId)
  } else {
    routesStore.reset()
  }
})
</script>

<template>
  <div class="network-view">

    <!-- Routes sidebar (left) -->
    <RoutesSideBar
      v-if="canReadRoutes"
      :can-write="canWriteRoutes"
      :can-read="canReadRoutes"
      section-id="routes"
      @add-route="openCreateRoutePanel"
      @route-select="openEditRoutePanel"
      @reorder="handleRouteReorder"
    />

    <!-- Map container fills remaining space -->
    <div ref="mapContainer" class="network-map" />

    <!-- Right-click context menu -->
    <Transition name="ctx-menu">
      <div
        v-if="contextMenu.visible"
        class="ctx-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <button class="ctx-menu__item" @click="openCreatePanel(contextMenu.lat, contextMenu.lng); hideContextMenu()">
          <span class="ctx-menu__icon">H</span>
          {{ t('stops.context_add_stop') }}
        </button>
      </div>
    </Transition>

    <!-- Edit panel slides in from the right -->
    <StopEditPanel
      v-model="panelVisible"
      :stop="editingStop"
      :init-lat="initLat"
      :init-lon="initLon"
      :loading="panelLoading"
      :server-error="panelError"
      :can-delete="canDelete"
      :platforms="platformsData"
      :readonly="!canWrite"
      @save="handleSave"
      @delete="handleDeleteRequest"
      @add-platform="handleAddPlatform"
      @edit-platform="openPlatformEditPanel"
    />

    <!-- Platform edit panel (slides in from the right, z-index above stop panel) -->
    <PlatformEditPanel
      v-model="platformPanelVisible"
      :platform="editingPlatform"
      :init-lat="platformInitLat"
      :init-lon="platformInitLon"
      :loading="platformLoading"
      :server-error="platformError"
      :can-delete="canDelete"
      :parent-stop-name="platformParentStop?.stop_name ?? platformParentStop?.stop_id ?? null"
      :readonly="!canWrite"
      @save="handlePlatformSave"
      @delete="handlePlatformDeleteRequest"
    />

    <!-- Crosshair placement hint overlay -->
    <Transition name="ctx-menu">
      <div v-if="addingPlatform" class="crosshair-hint">
        <md-icon>ads_click</md-icon>
        {{ t('platforms.pick_location_hint') }}
      </div>
    </Transition>

    <!-- Delete confirm: stop -->
    <ConfirmDialog
      v-model="confirmOpen"
      :title="confirmTitle"
      :message="confirmMessage"
      :confirm-label="t('stops.delete')"
      :cancel-label="t('stops.cancel')"
      :danger="true"
      @confirm="handleDeleteConfirmed"
    />

    <!-- Route edit panel -->
    <RouteEditPanel
      v-model="routePanelVisible"
      :route="editingRoute"
      :loading="routePanelLoading"
      :server-error="routePanelError"
      :can-delete="canDeleteRoutes"
      :readonly="!canWriteRoutes"
      :agencies="preloadedAgencies"
      @save="handleRouteSave"
      @delete="handleRouteDeleteRequest"
    />

    <!-- Delete confirm: route -->
    <ConfirmDialog
      v-model="routeConfirmOpen"
      :title="routeConfirmTitle"
      :message="routeConfirmMessage"
      :confirm-label="t('routes.delete')"
      :cancel-label="t('routes.cancel')"
      :danger="true"
      @confirm="handleRouteDeleteConfirmed"
    />

    <!-- Delete confirm: platform -->
    <ConfirmDialog
      v-model="platformConfirmOpen"
      :title="platformConfirmTitle"
      :message="platformConfirmMessage"
      :confirm-label="t('stops.delete')"
      :cancel-label="t('stops.cancel')"
      :danger="true"
      @confirm="handlePlatformDeleteConfirmed"
    />

  </div>
</template>

<style scoped>
.network-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
}

.network-map {
  flex: 1;
  min-width: 0;
  height: 100%;
}

/* ---- Crosshair placement hint ---- */
.crosshair-hint {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.72);
  color: #ffffff;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: var(--font-size-1, 0.875rem);
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 25;
  pointer-events: none;
  white-space: nowrap;
}

/* ---- Context menu ---- */
.ctx-menu {
  position: absolute;
  background: #ffffff;
  border: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
  border-radius: 6px;
  box-shadow: var(--shadow-4);
  z-index: 20;
  min-width: 200px;
  padding: 4px 0;
  pointer-events: all;
}

.ctx-menu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  background: none;
  border: none;
  padding: 8px 16px;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #222);
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.ctx-menu__item:hover {
  background: var(--md-sys-color-surface-container, #f0f0f7);
}

.ctx-menu__icon {
  width: 20px;
  height: 20px;
  background: var(--md-sys-color-primary, #1f69e0);
  color: #ffffff;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  line-height: 1;
}

/* Transition */
.ctx-menu-enter-active,
.ctx-menu-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}
.ctx-menu-enter-from,
.ctx-menu-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>
