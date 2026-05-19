<script setup>
import { onMounted, onActivated, onBeforeUnmount, ref, watch, computed, nextTick } from 'vue'
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
import ShapeEditPanel from '@/components/ShapeEditPanel.vue'
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
const canReadShapes   = has('shapes:read')
const canWriteShapes  = has('shapes:write')
const canDeleteShapes = has('shapes:delete')

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
  shapePanelVisible.value = false
  editingRoute.value      = null
  routePanelError.value   = null
  await fetchAgenciesForPanel()
  routePanelVisible.value = true
}

async function openEditRoutePanel(route) {
  panelVisible.value = false
  platformPanelVisible.value = false
  shapePanelVisible.value = false
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
const SHAPE_SOURCE    = 'shapes-source'
const SHAPE_LAYER     = 'shapes-layer'
const SHAPE_GLOW      = 'shapes-glow-layer'
const SHAPE_SELECT    = 'shapes-select-layer'
const SHAPE_POINTS_SOURCE = 'shapes-points-source'
const SHAPE_POINTS_LAYER  = 'shapes-points-layer'

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

// ---------------------------------------------------------------------------
// Shapes (Fahrwege) data
// ---------------------------------------------------------------------------
const shapesData = ref([])  // all shapes in the version

/**
 * Decode a Google-encoded polyline string into [[lon, lat], ...] coordinate pairs.
 */
function decodePolyline(encoded) {
  if (!encoded || typeof encoded !== 'string') return []
  const coords = []
  let lat = 0
  let lng = 0
  let index = 0

  while (index < encoded.length) {
    let result = 0
    let shift = 0
    let char

    do {
      char = encoded.charCodeAt(index++) - 63
      result |= (char & 0x1f) << shift
      shift += 5
    } while (char >= 0x20)

    lat += result & 1 ? ~(result >> 1) : result >> 1

    result = 0
    shift = 0

    do {
      char = encoded.charCodeAt(index++) - 63
      result |= (char & 0x1f) << shift
      shift += 5
    } while (char >= 0x20)

    lng += result & 1 ? ~(result >> 1) : result >> 1

    coords.push([lng / 1e5, lat / 1e5])
  }

  return coords
}

function buildShapesGeojson(shapes) {
  return {
    type: 'FeatureCollection',
    features: shapes
      .map(s => {
        // display_polyline is provided by the list endpoint (routed or computed straight-line).
        // Fall back to routed_polyline for shapes that came from a POST/PATCH response.
        const polyline = s.display_polyline || s.routed_polyline
        const coords = decodePolyline(polyline)
        if (coords.length < 2) return null
        return {
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: coords,
          },
          properties: {
            shape_id:   s.shape_id,
            shape_name: s.shape_name ?? s.shape_id,
          },
        }
      })
      .filter(Boolean),
  }
}

function updateShapeSource(shapes) {
  if (!map || !map.getSource(SHAPE_SOURCE)) return
  map.getSource(SHAPE_SOURCE).setData(buildShapesGeojson(shapes))
}

// Fly to the bounding-box centre of a decoded coordinate array at zoom 16.
function flyToShapeCenter(coords) {
  if (!map || !coords || coords.length < 2) return
  let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity
  for (const [lng, lat] of coords) {
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }
  map.flyTo({ center: [(minLng + maxLng) / 2, (minLat + maxLat) / 2], zoom: 16, duration: 800 })
}

// Build [lng, lat] coordinates from the current shapeIntermediatePoints using
// allPlatformsData for stop-based points (same logic as buildShapePointsGeojson).
function buildIntermediatePointCoords() {
  const coords = []
  for (const pt of shapeIntermediatePoints.value) {
    if (pt.stop_id) {
      const platform = allPlatformsData.value.find(p => p.stop_id === pt.stop_id)
      if (platform?.stop_lon != null && platform?.stop_lat != null) {
        coords.push([platform.stop_lon, platform.stop_lat])
      }
    } else if (pt.lon != null && pt.lat != null) {
      coords.push([pt.lon, pt.lat])
    }
  }
  return coords
}

// Rebuild SHAPE_SOURCE with a live preview of the shape currently being edited.
// All other shapes are taken from shapesData as-is; the editing shape is replaced
// by its routed polyline (if auto-routing produced one) or a straight-line fallback.
function updateEditingShapePreview() {
  if (!map || !map.getSource(SHAPE_SOURCE) || !shapePanelVisible.value) return
  // Use the routed polyline when available, otherwise straight-line from points.
  const coords = currentRoutedPolyline.value
    ? decodePolyline(currentRoutedPolyline.value)
    : buildIntermediatePointCoords()
  const currentShapeId = editingShape.value?.shape_id
  const baseFeatures = buildShapesGeojson(
    currentShapeId
      ? shapesData.value.filter(s => s.shape_id !== currentShapeId)
      : shapesData.value
  ).features
  if (coords.length >= 2) {
    baseFeatures.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: coords },
      properties: {
        shape_id:   currentShapeId ?? '__new__',
        shape_name: editingShape.value?.shape_name ?? '',
      },
    })
  }
  map.getSource(SHAPE_SOURCE).setData({ type: 'FeatureCollection', features: baseFeatures })
}

async function loadShapes() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId || !canReadShapes.value) {
    shapesData.value = []
    updateShapeSource([])
    return
  }
  try {
    const result = await api.shapes.list(versionId)
    shapesData.value = result
    updateShapeSource(result)
  } catch {
    shapesData.value = []
    updateShapeSource([])
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

function buildShapePointsGeojson(points, selectedIdx) {
  const features = []
  for (let i = 0; i < points.length; i++) {
    const pt = points[i]
    let lng, lat
    if (pt.stop_id) {
      const platform = allPlatformsData.value.find(p => p.stop_id === pt.stop_id)
      lng = platform?.stop_lon ?? pt.lon
      lat = platform?.stop_lat ?? pt.lat
    } else {
      lng = pt.lon
      lat = pt.lat
    }
    if (lng == null || lat == null) continue
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, lat] },
      properties: { idx: i, selected: i === selectedIdx, is_stop: !!pt.stop_id },
    })
  }
  return { type: 'FeatureCollection', features }
}

function updateShapePointsSource() {
  if (!map || !map.getSource(SHAPE_POINTS_SOURCE)) return
  map.getSource(SHAPE_POINTS_SOURCE).setData(
    buildShapePointsGeojson(shapeIntermediatePoints.value, selectedPointIndex.value)
  )
}

function addShapeLayers() {
  // Add shapes source (non-clustered LineStrings)
  if (!map.getSource(SHAPE_SOURCE)) {
    map.addSource(SHAPE_SOURCE, {
      type: 'geojson',
      data: buildShapesGeojson(shapesData.value),
    })
  }

  // 1 — Glow layer: wide soft halo, only visible for the selected shape
  if (!map.getLayer(SHAPE_GLOW)) {
    map.addLayer(
      {
        id: SHAPE_GLOW,
        type: 'line',
        source: SHAPE_SOURCE,
        minzoom: 14,
        filter: ['==', ['get', 'shape_id'], '__none__'],
        paint: {
          'line-color': '#7eb3ff',
          'line-width': 22,
          'line-opacity': 0.75,
          'line-blur': 5,
        },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      },
      PLATFORM_GLOW,
    )
  }

  // 2 — White casing layer: crisp bright border around selected shape
  if (!map.getLayer(SHAPE_SELECT)) {
    map.addLayer(
      {
        id: SHAPE_SELECT,
        type: 'line',
        source: SHAPE_SOURCE,
        minzoom: 14,
        filter: ['==', ['get', 'shape_id'], '__none__'],
        paint: {
          'line-color': '#ffffff',
          'line-width': 10,
          'line-opacity': 0.85,
        },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      },
      PLATFORM_GLOW,
    )
  }

  // 3 — Shape lines: base layer, rendered at zoom >= 16, behind all stop/platform layers
  if (!map.getLayer(SHAPE_LAYER)) {
    map.addLayer(
      {
        id: SHAPE_LAYER,
        type: 'line',
        source: SHAPE_SOURCE,
        minzoom: 16,
        paint: {
          'line-color': '#1f69e0',
          'line-width': 5,
          'line-opacity': 0.75,
        },
        layout: {
          'line-cap': 'round',
          'line-join': 'round',
        },
      },
      PLATFORM_GLOW,
    )
  }

  // 4 — Intermediate points during shape editing (orange circles, hidden by default)
  if (!map.getSource(SHAPE_POINTS_SOURCE)) {
    map.addSource(SHAPE_POINTS_SOURCE, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
  }
  if (!map.getLayer(SHAPE_POINTS_LAYER)) {
    map.addLayer({
      id: SHAPE_POINTS_LAYER,
      type: 'circle',
      source: SHAPE_POINTS_SOURCE,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius':       ['case', ['get', 'selected'], 9, 6],
        'circle-color':        ['case', ['get', 'selected'], '#FF8F00', '#FF6D00'],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff',
        'circle-opacity':      0.9,
      },
    })
  }
}

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
  if (!canWrite.value && !canWriteShapes.value) return
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
// Shape picker menu (disambiguation when multiple shapes overlap a click)
// ---------------------------------------------------------------------------
const shapePickerMenu = ref({ visible: false, x: 0, y: 0, shapes: [] })

function hideShapePickerMenu() {
  shapePickerMenu.value.visible = false
}

// ---------------------------------------------------------------------------
// Shape edit panel
// ---------------------------------------------------------------------------
const shapePanelVisible = ref(false)
const editingShape      = ref(null)
const isCreatingShape   = ref(false)
const shapePanelLoading = ref(false)
const shapePanelError   = ref(null)

// Intermediate points being edited for the currently-open shape.
// Each item: { id, sort_order, lat, lon, stop_id, stop_name, platform_code }
const shapeIntermediatePoints = ref([])

// Index of the currently-selected intermediate point (new points are inserted after it).
// null = nothing selected (append to end).
const selectedPointIndex = ref(null)

// Auto-routing state: tracks whether auto-routing is enabled, the current
// route type, and the last successfully computed routed polyline.
const isAutoRouteActive    = ref(false)
const editingRouteType     = ref(null)
const currentRoutedPolyline = ref(null)
// Request-version counter: ensures stale responses from cancelled requests are ignored.
let _routingRequestId = 0
// Suppresses auto-routing during initial point load when a routed_polyline already exists.
let _shapeInitializing = false

// Encode [{lat, lng}] points (as returned by the routing API) into a
// Google Encoded Polyline string (same format as routed_polyline in the DB).
function encodePolylineFromLatLng(points) {
  function encodeVal(v) {
    v = v < 0 ? ~(v << 1) : v << 1
    let s = ''
    while (v >= 0x20) {
      s += String.fromCharCode((0x20 | (v & 0x1f)) + 63)
      v >>= 5
    }
    return s + String.fromCharCode(v + 63)
  }
  let prevLat = 0, prevLng = 0, out = ''
  for (const { lat, lng } of points) {
    const latE5 = Math.round(lat * 1e5)
    const lngE5 = Math.round(lng * 1e5)
    out += encodeVal(latE5 - prevLat)
    out += encodeVal(lngE5 - prevLng)
    prevLat = latE5
    prevLng = lngE5
  }
  return out
}

// Call the routing API with the current intermediate points and store the
// result in currentRoutedPolyline. Uses a version counter to discard stale
// responses from concurrent/overlapping calls.
async function triggerAutoRouting() {
  const requestId = ++_routingRequestId
  const coords = buildIntermediatePointCoords()  // [[lng, lat], ...]
  if (coords.length < 2 || editingRouteType.value == null) {
    currentRoutedPolyline.value = null
    updateEditingShapePreview()
    return
  }
  try {
    // The routing API expects { lat, lng } waypoints.
    const waypoints = coords.map(([lng, lat]) => ({ lat, lng }))
    const result = await api.routing.calculate(editingRouteType.value, waypoints)
    if (requestId !== _routingRequestId) return  // stale — a newer request is in flight
    currentRoutedPolyline.value = encodePolylineFromLatLng(result.points)
  } catch {
    if (requestId !== _routingRequestId) return
    currentRoutedPolyline.value = null
  }
  updateEditingShapePreview()
}

// Handler for the @autoroute-change event from ShapeEditPanel.
// Updates local routing state and triggers/clears routing accordingly.
function handleAutoRouteChange({ active, routeType }) {
  isAutoRouteActive.value = active
  editingRouteType.value  = routeType
  if (active) {
    if (_shapeInitializing) {
      // Panel still initializing — show the existing routed_polyline without re-routing.
      updateEditingShapePreview()
    } else {
      triggerAutoRouting()
    }
  } else {
    currentRoutedPolyline.value = null
    updateEditingShapePreview()
  }
}

// True whenever the shape panel is open and the user has write access.
// In this mode: map cursor = crosshair, map clicks add intermediate points.
const isEditingShapePoints = computed(() => shapePanelVisible.value && canWriteShapes.value)

function addShapeIntermediatePoint(point) {
  const pts = [...shapeIntermediatePoints.value]
  const insertAt = selectedPointIndex.value !== null
    ? selectedPointIndex.value + 1
    : pts.length
  pts.splice(insertAt, 0, {
    id:            null,
    sort_order:    insertAt,
    lat:           point.lat,
    lon:           point.lon,
    stop_id:       point.stop_id,
    stop_name:     point.stop_name,
    platform_code: point.platform_code,
  })
  shapeIntermediatePoints.value = pts
  selectedPointIndex.value = insertAt
}

function removeShapeIntermediatePoint(index) {
  const pts = [...shapeIntermediatePoints.value]
  pts.splice(index, 1)
  shapeIntermediatePoints.value = pts
  if (selectedPointIndex.value !== null) {
    if (selectedPointIndex.value === index) {
      selectedPointIndex.value = pts.length > 0 ? Math.min(index, pts.length - 1) : null
    } else if (selectedPointIndex.value > index) {
      selectedPointIndex.value -= 1
    }
  }
}

function selectShapePoint(index) {
  selectedPointIndex.value = selectedPointIndex.value === index ? null : index
}

// Returns the cursor that should be active in the current mode.
function cursorForCurrentMode() {
  return isEditingShapePoints.value ? 'crosshair' : ''
}

function openShapePanel(shape) {
  // Master-level: close all other level-1 panels first
  routePanelVisible.value = false
  panelVisible.value = false
  platformParentStop.value = null
  platformPanelVisible.value = false
  hideShapePickerMenu()

  editingShape.value            = shape
  shapePanelError.value         = null
  _shapeInitializing            = true
  shapeIntermediatePoints.value = []
  shapePanelVisible.value       = true

  // Initialise routing state from the saved shape.
  isAutoRouteActive.value     = shape.is_autoroute_active ?? false
  editingRouteType.value      = shape.route_type ?? null
  currentRoutedPolyline.value = shape.routed_polyline ?? null

  // Highlight the selected shape on the map
  if (map) {
    if (map.getLayer(SHAPE_GLOW))   map.setFilter(SHAPE_GLOW,   ['==', ['get', 'shape_id'], shape.shape_id])
    if (map.getLayer(SHAPE_SELECT)) map.setFilter(SHAPE_SELECT, ['==', ['get', 'shape_id'], shape.shape_id])
  }

  // Async-load full shape (including intermediate points) without blocking the panel open.
  const vid = versionsStore.state.activeVersionId
  if (vid) {
    api.shapes.get(vid, shape.shape_id).then((full) => {
      // Guard: only apply if this shape is still the one being edited
      if (!shapePanelVisible.value || editingShape.value?.shape_id !== shape.shape_id) return
      shapeIntermediatePoints.value = (full.intermediate_points ?? []).map((pt) => {
        const platform = pt.stop_id
          ? allPlatformsData.value.find(p => p.stop_id === pt.stop_id)
          : null
        return {
          id:            pt.id,
          sort_order:    pt.sort_order,
          lat:           pt.lat,
          lon:           pt.lon,
          stop_id:       pt.stop_id,
          stop_name:     platform?.stop_name  ?? null,
          platform_code: platform?.platform_code ?? null,
        }
      })
      // Update the map with the freshly-loaded point data.
      updateEditingShapePreview()
      // Clear the init flag only AFTER the watcher has flushed (Vue 3 pre-flush
      // watchers run before nextTick callbacks, so this is safe).
      nextTick(() => { _shapeInitializing = false })
    }).catch(() => { _shapeInitializing = false /* silently ignore — points stay empty */ })
  }
}

function openCreateShapePanel() {
  if (!canWriteShapes.value) return
  isCreatingShape.value         = true
  editingShape.value            = null
  shapePanelError.value         = null
  shapeIntermediatePoints.value = []
  selectedPointIndex.value      = null
  shapePanelVisible.value       = true
  isAutoRouteActive.value       = false
  editingRouteType.value        = null
  currentRoutedPolyline.value   = null
  // Clear any existing shape highlight
  if (map) {
    if (map.getLayer(SHAPE_GLOW))   map.setFilter(SHAPE_GLOW,   ['==', ['get', 'shape_id'], '__none__'])
    if (map.getLayer(SHAPE_SELECT)) map.setFilter(SHAPE_SELECT, ['==', ['get', 'shape_id'], '__none__'])
  }
}

watch(shapePanelVisible, (visible) => {
  if (!visible && map) {
    if (map.getLayer(SHAPE_GLOW))   map.setFilter(SHAPE_GLOW,   ['==', ['get', 'shape_id'], '__none__'])
    if (map.getLayer(SHAPE_SELECT)) map.setFilter(SHAPE_SELECT, ['==', ['get', 'shape_id'], '__none__'])
    // Restore all shapes to their last-saved state (discard any live editing preview).
    updateShapeSource(shapesData.value)
  }
  if (!visible) {
    _shapeInitializing            = false
    shapeIntermediatePoints.value = []
    selectedPointIndex.value = null
    isCreatingShape.value = false
    isAutoRouteActive.value = false
    editingRouteType.value = null
    currentRoutedPolyline.value = null
  }
  // Update map cursor when panel opens/closes
  if (map) map.getCanvas().style.cursor = visible && canWriteShapes.value ? 'crosshair' : ''
})

// When shape editing starts/ends: adjust zoom levels and show/hide the
// intermediate-points marker layer.
watch(isEditingShapePoints, (active) => {
  if (!map) return
  if (active) {
    map.setLayerZoomRange(SHAPE_LAYER, 12, 24)
    map.setLayerZoomRange(SHAPE_GLOW, 12, 24)
    map.setLayerZoomRange(SHAPE_SELECT, 12, 24)
    if (map.getLayer(PLATFORM_LAYER)) map.setLayerZoomRange(PLATFORM_LAYER, 12, 24)
    if (map.getLayer(PLATFORM_GLOW))  map.setLayerZoomRange(PLATFORM_GLOW, 12, 24)
    if (map.getLayer(SHAPE_POINTS_LAYER)) map.setLayoutProperty(SHAPE_POINTS_LAYER, 'visibility', 'visible')
  } else {
    map.setLayerZoomRange(SHAPE_LAYER, 16, 24)
    map.setLayerZoomRange(SHAPE_GLOW, 14, 24)
    map.setLayerZoomRange(SHAPE_SELECT, 14, 24)
    if (map.getLayer(PLATFORM_LAYER)) map.setLayerZoomRange(PLATFORM_LAYER, 16, 24)
    if (map.getLayer(PLATFORM_GLOW))  map.setLayerZoomRange(PLATFORM_GLOW, 16, 24)
    if (map.getLayer(SHAPE_POINTS_LAYER)) {
      map.setLayoutProperty(SHAPE_POINTS_LAYER, 'visibility', 'none')
      map.getSource(SHAPE_POINTS_SOURCE)?.setData({ type: 'FeatureCollection', features: [] })
    }
  }
})

// Keep the intermediate-points marker layer and the shape line in sync with local state.
// When auto-routing is enabled, changes to the point list also trigger a routing call.
watch([shapeIntermediatePoints, selectedPointIndex], () => {
  if (isEditingShapePoints.value) updateShapePointsSource()
  if (shapePanelVisible.value) {
    if (!_shapeInitializing && isAutoRouteActive.value) {
      triggerAutoRouting()  // async; calls updateEditingShapePreview internally
    } else {
      updateEditingShapePreview()
    }
  }
})

async function handleShapeSave(data) {
  if (!canWriteShapes.value) return
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return

  // Frontend validation: require at least 2 stop-based points
  const stopCount = shapeIntermediatePoints.value.filter(pt => pt.stop_id).length
  if (stopCount < 2) {
    shapePanelError.value = t('shapes.error_min_stops')
    return
  }

  shapePanelLoading.value = true
  shapePanelError.value   = null
  try {
    const payload = {
      ...data,
      routed_polyline: currentRoutedPolyline.value,
      intermediate_points: shapeIntermediatePoints.value.map((pt, idx) => ({
        sort_order: idx,
        lat:        pt.stop_id ? null : pt.lat,
        lon:        pt.stop_id ? null : pt.lon,
        stop_id:    pt.stop_id ?? null,
      })),
    }

    if (isCreatingShape.value) {
      // ── CREATE ──────────────────────────────────────────────────────────
      const created = await api.shapes.create(versionId, payload)
      // Reload all shapes so display_polyline is computed fresh from the list endpoint
      await loadShapes()
      // Close panel — creation is complete.
      shapePanelVisible.value = false
    } else {
      // ── UPDATE ──────────────────────────────────────────────────────────
      if (!editingShape.value) return
      const oldShapeId = editingShape.value.shape_id
      const updated = await api.shapes.update(versionId, oldShapeId, payload)
      editingShape.value = updated
      shapePanelVisible.value = false
      // Reload all shapes so display_polyline is computed fresh from the list endpoint
      await loadShapes()
    }
  } catch (err) {
    if (err?.status === 404) {
      shapePanelError.value = t('shapes.error_not_found')
    } else if (err?.status === 409) {
      shapePanelError.value = t('shapes.error_duplicate')
    } else {
      shapePanelError.value = t('shapes.error_generic')
    }
  } finally {
    shapePanelLoading.value = false
  }
}

const shapeConfirmOpen    = ref(false)
const shapeConfirmTitle   = ref('')
const shapeConfirmMessage = ref('')

function handleShapeDeleteRequest() {
  if (!editingShape.value) return
  shapeConfirmTitle.value   = t('shapes.delete_confirm_title')
  shapeConfirmMessage.value = t('shapes.delete_confirm_message', {
    name: editingShape.value.shape_name || editingShape.value.shape_id,
  })
  shapeConfirmOpen.value = true
}

async function handleShapeDeleteConfirmed() {
  if (!canDeleteShapes.value) return
  const versionId = versionsStore.state.activeVersionId
  if (!versionId || !editingShape.value) return
  shapePanelLoading.value = true
  shapePanelError.value   = null
  try {
    await api.shapes.delete(versionId, editingShape.value.shape_id)
    shapePanelVisible.value = false
    await loadShapes()
  } catch {
    shapePanelError.value = t('shapes.error_generic')
  } finally {
    shapePanelLoading.value = false
  }
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
const stopRerouting        = ref(false)
const stopReroutingMessage = ref(null)

function openCreatePanel(lat, lon) {
  routePanelVisible.value = false
  shapePanelVisible.value = false
  editingStop.value  = null
  initLat.value      = lat
  initLon.value      = lon
  panelError.value   = null
  panelVisible.value = true
}

function openEditPanel(stop, { zoom = true } = {}) {
  routePanelVisible.value = false
  shapePanelVisible.value = false
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
  if (!val) {
    stopRerouting.value = false
    stopReroutingMessage.value = null
    if (!addingPlatform.value && !platformPanelVisible.value) {
      platformsData.value = []
      platformParentStop.value = null
    }
  }
})

// When the user cancels after a drag, restore the stop/platform to its pre-drag position.
function handleStopCancel() {
  if (savedDragStopLat === null || !editingStop.value) return
  const stopId = editingStop.value.stop_id
  const idx = stopsData.value.findIndex(s => s.stop_id === stopId)
  if (idx !== -1) {
    stopsData.value[idx] = { ...stopsData.value[idx], stop_lat: savedDragStopLat, stop_lon: savedDragStopLon }
    map?.getSource(STOP_SOURCE)?.setData(buildGeojson(stopsData.value, null, null, null))
  }
  savedDragStopLat = null
  savedDragStopLon = null
}

function handlePlatformCancel() {
  if (savedDragPlatformLat === null || !editingPlatform.value) return
  const platformId = editingPlatform.value.stop_id
  const allIdx = allPlatformsData.value.findIndex(p => p.stop_id === platformId)
  if (allIdx !== -1) {
    allPlatformsData.value[allIdx] = { ...allPlatformsData.value[allIdx], stop_lat: savedDragPlatformLat, stop_lon: savedDragPlatformLon }
    map?.getSource(PLATFORM_SOURCE)?.setData(buildPlatformsGeojson(allPlatformsData.value, null, null, null))
  }
  const panelIdx = platformsData.value.findIndex(p => p.stop_id === platformId)
  if (panelIdx !== -1) {
    platformsData.value[panelIdx] = { ...platformsData.value[panelIdx], stop_lat: savedDragPlatformLat, stop_lon: savedDragPlatformLon }
  }
  savedDragPlatformLat = null
  savedDragPlatformLon = null
}

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
  stopRerouting.value = true
  stopReroutingMessage.value = null
  panelError.value = null
  try {
    const res = await api.stops.delete(versionId, editingStop.value.stop_id)
    if (!res.ok) {
      if (res.status === 404) {
        panelError.value = t('stops.error_not_found')
      } else {
        toast.show(t('error.server'), 'error')
      }
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let done = false
    while (!done) {
      const { done: streamDone, value } = await reader.read()
      if (streamDone) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() ?? ''
      for (const chunk of chunks) {
        const dataLine = chunk.split('\n').find(l => l.startsWith('data:'))
        if (!dataLine) continue
        let event
        try { event = JSON.parse(dataLine.slice(5).trim()) } catch { continue }
        if (event.type === 'progress') {
          stopReroutingMessage.value = t('platforms.rerouting_progress', {
            current: event.current,
            total: event.total,
          })
        } else if (event.type === 'done') {
          done = true
        } else if (event.type === 'error') {
          toast.show(t('platforms.rerouting_error'), 'error')
          done = true
        }
      }
    }
    await loadStops()
    await loadShapes()
    panelVisible.value = false
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    stopRerouting.value = false
    stopReroutingMessage.value = null
  }
}

// ---------------------------------------------------------------------------
// Platform panel state & workflow
// ---------------------------------------------------------------------------
const platformPanelVisible = ref(false)
const editingPlatform      = ref(null)   // null = create mode
const platformRerouting    = ref(false)
const platformReroutingMessage = ref(null)
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
    platformRerouting.value = false
    platformReroutingMessage.value = null
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

  // For new platforms, use the regular JSON endpoint and close immediately
  if (!editingPlatform.value) {
    platformLoading.value = true
    platformError.value   = null
    try {
      const parentStopId = platformParentStop.value?.stop_id
      if (!parentStopId) throw new Error('No parent stop')
      await api.stops.createPlatform(versionId, parentStopId, data)
      await loadAllPlatforms()
      platformPanelVisible.value = false
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
    return
  }

  // For updates: PUT returns an SSE stream — lock panel and consume it
  platformRerouting.value = true
  platformReroutingMessage.value = null
  platformError.value = null
  try {
    const res = await api.stops.updatePlatform(
      versionId,
      editingPlatform.value.parent_station,
      editingPlatform.value.stop_id,
      data,
    )
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const detail = body?.detail ?? null
      if (res.status === 409) {
        platformError.value = t('platforms.error_conflict')
      } else if (res.status === 404) {
        platformError.value = t('platforms.error_not_found')
      } else {
        toast.show(t('error.server'), 'error')
      }
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let done = false
    while (!done) {
      const { done: streamDone, value } = await reader.read()
      if (streamDone) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() ?? ''
      for (const chunk of chunks) {
        const dataLine = chunk.split('\n').find(l => l.startsWith('data:'))
        if (!dataLine) continue
        let event
        try { event = JSON.parse(dataLine.slice(5).trim()) } catch { continue }
        if (event.type === 'progress') {
          platformReroutingMessage.value = t('platforms.rerouting_progress', {
            current: event.current,
            total: event.total,
          })
        } else if (event.type === 'done') {
          done = true
        } else if (event.type === 'error') {
          toast.show(t('platforms.rerouting_error'), 'error')
          done = true
        }
      }
    }
    await loadAllPlatforms()
    await loadShapes()
    platformPanelVisible.value = false
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    platformRerouting.value = false
    platformReroutingMessage.value = null
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
  platformRerouting.value = true
  platformReroutingMessage.value = null
  platformError.value = null
  try {
    const res = await api.stops.deletePlatform(
      versionId,
      editingPlatform.value.parent_station,
      editingPlatform.value.stop_id,
    )
    if (!res.ok) {
      if (res.status === 404) {
        platformError.value = t('platforms.error_not_found')
      } else {
        toast.show(t('error.server'), 'error')
      }
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let done = false
    while (!done) {
      const { done: streamDone, value } = await reader.read()
      if (streamDone) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() ?? ''
      for (const chunk of chunks) {
        const dataLine = chunk.split('\n').find(l => l.startsWith('data:'))
        if (!dataLine) continue
        let event
        try { event = JSON.parse(dataLine.slice(5).trim()) } catch { continue }
        if (event.type === 'progress') {
          platformReroutingMessage.value = t('platforms.rerouting_progress', {
            current: event.current,
            total: event.total,
          })
        } else if (event.type === 'done') {
          done = true
        } else if (event.type === 'error') {
          toast.show(t('platforms.rerouting_error'), 'error')
          done = true
        }
      }
    }
    await loadAllPlatforms()
    await loadShapes()
    platformPanelVisible.value = false   // watch will re-open stop panel and reload platforms
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    platformRerouting.value = false
    platformReroutingMessage.value = null
  }
}

// ---------------------------------------------------------------------------
// Stop + Platform marker interaction (click + drag-to-move)
// ---------------------------------------------------------------------------
let draggingStop    = null   // stop object currently being interacted with
let dragCurrentLat  = null
let dragCurrentLng  = null
let isDragEnabled   = false
// Saved original position before a drag — used to revert on cancel.
let savedDragStopLat  = null
let savedDragStopLon  = null

let draggingPlatform     = null   // platform object currently being interacted with
let platformDragLat      = null
let platformDragLng      = null
let isPlatformDragEnabled = false
// Saved original platform position before a drag — used to revert on cancel.
let savedDragPlatformLat = null
let savedDragPlatformLon = null

function attachMarkerInteraction() {
  if (!map) return

  // --- Cluster click: zoom in ---
  map.on('click', CLUSTER_LAYER, async (e) => {
    if (isEditingShapePoints.value) return
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
    if (isEditingShapePoints.value) return   // in shape editing mode, ignore
    const feat = e.features?.[0]
    if (!feat) return
    const stop = stopsData.value.find(s => s.stop_id === feat.properties.stop_id)
    if (!stop) return

    draggingStop = stop; dragCurrentLat = null; dragCurrentLng = null; isDragEnabled = false
    savedDragStopLat = stop.stop_lat
    savedDragStopLon = stop.stop_lon

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
    if (isEditingShapePoints.value) return   // in shape editing mode, ignore
    const feat = e.features?.[0]
    if (!feat) return
    const platform = allPlatformsData.value.find(p => p.stop_id === feat.properties.stop_id)
    if (!platform) return

    draggingPlatform = platform; platformDragLat = null; platformDragLng = null; isPlatformDragEnabled = false
    savedDragPlatformLat = platform.stop_lat
    savedDragPlatformLon = platform.stop_lon

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
    if (draggingStop || draggingPlatform || addingPlatform.value || isEditingShapePoints.value) return
    const stopId = e.features?.[0]?.properties?.stop_id
    const isDraggable = canWrite.value && panelVisible.value && editingStop.value?.stop_id === stopId
    map.getCanvas().style.cursor = isDraggable ? 'grab' : 'pointer'
  })
  map.on('mouseleave', STOP_LAYER, () => {
    if (!draggingStop && !draggingPlatform && !addingPlatform.value) map.getCanvas().style.cursor = cursorForCurrentMode()
  })

  // --- Platform hover cursor ---
  map.on('mouseenter', PLATFORM_LAYER, (e) => {
    if (draggingStop || draggingPlatform || addingPlatform.value || isEditingShapePoints.value) return
    const pId = e.features?.[0]?.properties?.stop_id
    const isDraggable = canWrite.value && platformPanelVisible.value && editingPlatform.value?.stop_id === pId
    map.getCanvas().style.cursor = isDraggable ? 'grab' : 'default'
  })
  map.on('mouseleave', PLATFORM_LAYER, () => {
    if (!draggingStop && !draggingPlatform && !addingPlatform.value) map.getCanvas().style.cursor = cursorForCurrentMode()
  })

  // --- Platform click in shape-editing mode: add stop reference ---
  map.on('click', PLATFORM_LAYER, (e) => {
    if (!isEditingShapePoints.value) return
    const feat = e.features?.[0]
    if (!feat) return
    const stopId = feat.properties.stop_id
    const platform = allPlatformsData.value.find(p => p.stop_id === stopId)
    if (!platform) return
    addShapeIntermediatePoint({
      lat:           platform.stop_lat,
      lon:           platform.stop_lon,
      stop_id:       stopId,
      stop_name:     platform.stop_name,
      platform_code: platform.platform_code,
    })
  })

  // --- Existing intermediate point click in shape-editing mode: select it ---
  map.on('click', SHAPE_POINTS_LAYER, (e) => {
    if (!isEditingShapePoints.value) return
    const feat = e.features?.[0]
    if (feat != null) selectShapePoint(feat.properties.idx)
  })
  map.on('mouseenter', SHAPE_POINTS_LAYER, () => {
    if (isEditingShapePoints.value) map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', SHAPE_POINTS_LAYER, () => {
    if (isEditingShapePoints.value) map.getCanvas().style.cursor = cursorForCurrentMode()
  })

  // --- Shape click: open edit panel or disambiguation menu ---
  map.on('click', SHAPE_LAYER, (e) => {
    if (addingPlatform.value) return
    if (isEditingShapePoints.value) return  // clicks handled by global handler
    hideContextMenu()
    hideShapePickerMenu()

    // If a stop marker, platform marker or cluster is also at this point, let
    // those higher-priority handlers take over instead of opening a shape panel.
    const stopHits = map.queryRenderedFeatures(e.point, { layers: [STOP_LAYER, PLATFORM_LAYER, CLUSTER_LAYER] })
    if (stopHits.length > 0) return

    const features = map.queryRenderedFeatures(e.point, { layers: [SHAPE_LAYER] })
    if (!features.length) return

    // Deduplicate by shape_id (a shape might render multiple tile features)
    const seen = new Set()
    const unique = features.filter(f => {
      const id = f.properties?.shape_id
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })

    if (unique.length === 1) {
      const shape = shapesData.value.find(s => s.shape_id === unique[0].properties.shape_id)
      if (shape) openShapePanel(shape)
    } else {
      // Multiple overlapping shapes — show picker menu
      const shapes = unique
        .map(f => shapesData.value.find(s => s.shape_id === f.properties.shape_id))
        .filter(Boolean)
      shapePickerMenu.value = {
        visible: true,
        x: e.point.x,
        y: e.point.y,
        shapes,
      }
    }
  })

  map.on('mouseenter', SHAPE_LAYER, () => {
    if (!draggingStop && !draggingPlatform && !addingPlatform.value && !isEditingShapePoints.value) {
      map.getCanvas().style.cursor = 'pointer'
    }
  })
  map.on('mouseleave', SHAPE_LAYER, () => {
    if (!draggingStop && !draggingPlatform && !addingPlatform.value) map.getCanvas().style.cursor = cursorForCurrentMode()
  })
}

// ---------------------------------------------------------------------------
// Stop search
// ---------------------------------------------------------------------------
const searchQuery = ref('')
const searchOpen  = ref(false)

const searchResults = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return []
  const results = []
  if (canRead.value) {
    for (const s of stopsData.value) {
      if (s.stop_name?.toLowerCase().includes(q) || s.stop_id?.toLowerCase().includes(q)) {
        results.push({ type: 'stop', data: s })
      }
    }
  }
  if (canReadShapes.value) {
    for (const s of shapesData.value) {
      if (s.shape_name?.toLowerCase().includes(q) || s.shape_id?.toLowerCase().includes(q)) {
        results.push({ type: 'shape', data: s })
      }
    }
  }
  return results.slice(0, 8)
})

function flyToResult(result) {
  if (result.type === 'stop') {
    flyToStop(result.data)
  } else {
    flyToShape(result.data)
  }
}

function flyToStop(stop) {
  if (!map || stop.stop_lat == null || stop.stop_lon == null) return
  map.flyTo({ center: [stop.stop_lon, stop.stop_lat], zoom: 16 })
  searchQuery.value = ''
  searchOpen.value  = false
}

function flyToShape(shape) {
  const polyline = shape.routed_polyline || shape.shape_polyline
  const coords = decodePolyline(polyline)
  if (!map || coords.length === 0) return
  const mid = coords[Math.floor(coords.length / 2)]
  map.flyTo({ center: mid, zoom: 16 })
  searchQuery.value = ''
  searchOpen.value  = false
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
    addShapeLayers()
    attachMarkerInteraction()
    loadStops()
    loadShapes()
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
    hideShapePickerMenu()

    if (addingPlatform.value) {
      addingPlatform.value = false
      if (map) map.getCanvas().style.cursor = ''
      openPlatformCreatePanel(e.lngLat.lat, e.lngLat.lng)
      return
    }

    if (isEditingShapePoints.value) {
      // Clusters are for zoom-navigation only — don't add a point.
      const clusterHits = map.queryRenderedFeatures(e.point, { layers: [CLUSTER_LAYER] })
      if (clusterHits.length > 0) return

      // Existing intermediate point clicks are handled by SHAPE_POINTS_LAYER handler.
      const ptHits = map.queryRenderedFeatures(e.point, { layers: [SHAPE_POINTS_LAYER] })
      if (ptHits.length > 0) return

      // Platform clicks are handled by PLATFORM_LAYER click handler (adds stop ref).
      const platformHits = map.queryRenderedFeatures(e.point, { layers: [PLATFORM_LAYER] })
      if (platformHits.length > 0) return

      // Clicks on stops, shapes, or empty map background: add a coordinate point.
      addShapeIntermediatePoint({
        lat:           e.lngLat.lat,
        lon:           e.lngLat.lng,
        stop_id:       null,
        stop_name:     null,
        platform_code: null,
      })
      return
    }
  })

  map.on('dragstart', () => {
    hideContextMenu()
    hideShapePickerMenu()
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

// Reload stops and shapes when the active version changes
watch(() => versionsStore.state.activeVersionId, () => {
  loadStops()
  loadShapes()
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
    <div class="map-area">
      <div ref="mapContainer" class="network-map" />

      <!-- Stop/shape search overlay -->
      <div v-if="canRead || canReadShapes" class="map-search">
        <div class="map-search__box">
          <md-icon class="map-search__icon">search</md-icon>
          <input
            class="map-search__input"
            type="text"
            :placeholder="t('stops.search_placeholder')"
            v-model="searchQuery"
            autocomplete="off"
            @focus="searchOpen = true"
            @blur="searchOpen = false"
          />
          <button
            v-if="searchQuery"
            class="map-search__clear"
            @mousedown.prevent
            @click="searchQuery = ''"
            :aria-label="t('stops.cancel')"
          >
            <md-icon>close</md-icon>
          </button>
        </div>
        <ul v-if="searchOpen && searchResults.length > 0" class="map-search__results">
          <li v-for="result in searchResults" :key="result.type + '_' + (result.data.stop_id || result.data.shape_id)">
            <button class="map-search__item" @mousedown.prevent="flyToResult(result)">
              <template v-if="result.type === 'stop'">
                <span class="map-search__item-name">{{ result.data.stop_name || result.data.stop_id }}</span>
                <span class="map-search__item-id">{{ result.data.stop_id }}</span>
              </template>
              <template v-else>
                <span class="map-search__item-name">{{ result.data.shape_name || result.data.shape_id }}</span>
              </template>
            </button>
          </li>
        </ul>
        <div
          v-else-if="searchOpen && searchQuery.trim() && searchResults.length === 0"
          class="map-search__empty"
        >
          {{ t('stops.search_no_results') }}
        </div>
      </div>
    </div>

    <!-- Right-click context menu -->
    <Transition name="ctx-menu">
      <div
        v-if="contextMenu.visible"
        class="ctx-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <button v-if="canWrite" class="ctx-menu__item" @click="openCreatePanel(contextMenu.lat, contextMenu.lng); hideContextMenu()">
          <span class="ctx-menu__icon">H</span>
          {{ t('stops.context_add_stop') }}
        </button>
        <button v-if="canWriteShapes" class="ctx-menu__item" @click="openCreateShapePanel(); hideContextMenu()">
          <md-icon class="ctx-menu__line-icon">route</md-icon>
          {{ t('stops.context_add_shape') }}
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
      :rerouting="stopRerouting"
      :rerouting-message="stopReroutingMessage"
      @save="handleSave"
      @cancel="handleStopCancel"
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
      :rerouting="platformRerouting"
      :rerouting-message="platformReroutingMessage"
      @save="handlePlatformSave"
      @cancel="handlePlatformCancel"
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

    <!-- Shape (Fahrweg) edit panel -->
    <ShapeEditPanel
      v-model="shapePanelVisible"
      :shape="editingShape"
      :creating="isCreatingShape"
      :loading="shapePanelLoading"
      :server-error="shapePanelError"
      :can-write="canWriteShapes"
      :can-delete="!isCreatingShape && canDeleteShapes"
      :readonly="!canWriteShapes"
      :intermediate-points="shapeIntermediatePoints"
      :selected-point-index="selectedPointIndex"
      @save="handleShapeSave"
      @delete="handleShapeDeleteRequest"
      @remove-point="removeShapeIntermediatePoint"
      @select-point="selectShapePoint"
      @autoroute-change="handleAutoRouteChange"
    />

    <!-- Shape picker context menu (disambiguation when multiple shapes overlap) -->
    <Transition name="ctx-menu">
      <div
        v-if="shapePickerMenu.visible"
        class="ctx-menu shape-picker-menu"
        :style="{ left: shapePickerMenu.x + 'px', top: shapePickerMenu.y + 'px' }"
        @click.stop
      >
        <div class="ctx-menu__header">{{ t('shapes.picker_title') }}</div>
        <button
          v-for="shape in shapePickerMenu.shapes"
          :key="shape.shape_id"
          class="ctx-menu__item"
          @click="openShapePanel(shape)"
        >
          <md-icon class="ctx-menu__line-icon">route</md-icon>
          {{ shape.shape_name || shape.shape_id }}
        </button>
      </div>
    </Transition>

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

    <!-- Delete confirm: shape -->
    <ConfirmDialog
      v-model="shapeConfirmOpen"
      :title="shapeConfirmTitle"
      :message="shapeConfirmMessage"
      :confirm-label="t('shapes.delete')"
      :cancel-label="t('shapes.cancel')"
      :danger="true"
      @confirm="handleShapeDeleteConfirmed"
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
  width: 100%;
  height: 100%;
}

.map-area {
  flex: 1;
  min-width: 0;
  height: 100%;
  position: relative;
}

/* ---- Stop search overlay ---- */
.map-search {
  position: absolute;
  top: 16px;
  left: 16px;
  width: 320px;
  max-width: calc(100% - 32px);
  z-index: 10;
  pointer-events: all;
}

.map-search__box {
  display: flex;
  align-items: center;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: var(--shadow-4, 0 4px 16px rgba(0,0,0,.22));
  padding: 0 12px;
  height: 48px;
  gap: 8px;
}

.map-search__icon {
  color: var(--md-sys-color-outline, #74777f);
  flex-shrink: 0;
}

.map-search__input {
  flex: 1;
  border: none;
  outline: none;
  font-size: var(--font-size-1, 0.875rem);
  background: transparent;
  color: var(--md-sys-color-on-surface, #222);
}

.map-search__input::placeholder {
  color: var(--md-sys-color-outline, #74777f);
}

.map-search__clear {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  color: var(--md-sys-color-outline, #74777f);
}
.map-search__clear:hover {
  color: var(--md-sys-color-on-surface, #222);
}

.map-search__results {
  list-style: none;
  margin: 6px 0 0;
  padding: 4px 0;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: var(--shadow-4, 0 4px 16px rgba(0,0,0,.22));
  overflow: hidden;
}

.map-search__item {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  width: 100%;
  padding: 10px 16px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  gap: 12px;
  transition: background 0.1s;
}
.map-search__item:hover {
  background: #ddf0fb;
}

.map-search__item-name {
  font-size: var(--font-size-1, 0.875rem);
  font-weight: 500;
  color: var(--md-sys-color-on-surface, #222);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.map-search__item-id {
  font-size: var(--font-size-0, 0.78rem);
  color: var(--md-sys-color-outline, #74777f);
  white-space: nowrap;
  flex-shrink: 0;
}

.map-search__empty {
  margin-top: 6px;
  padding: 12px 16px;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: var(--shadow-3, 0 2px 8px rgba(0,0,0,.15));
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-outline, #74777f);
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

/* Shape picker menu header */
.ctx-menu__header {
  padding: 6px 16px 4px;
  font-size: var(--font-size-0, 0.75rem);
  font-weight: 600;
  color: var(--md-sys-color-outline, #74777f);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
  margin-bottom: 2px;
}

/* Inline icon for shape picker items */
.ctx-menu__line-icon {
  font-size: 18px;
  color: #1f69e0;
  flex-shrink: 0;
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
