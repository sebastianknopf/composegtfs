<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { api } from '@/api/client.js'
import { settingsStore } from '@/stores/settings.js'
import '@material/web/dialog/dialog.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/checkbox/checkbox.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:              { type: Boolean, default: false },
  shapeId:                 { type: String,  default: '' },
  initialName:             { type: String,  default: '' },
  servedStops:             { type: Array,   default: () => [] },
  existingPolyline:        { type: String,  default: null },
  existingRoutedPolyline:  { type: String,  default: null },
  routeType:               { type: Number,  default: null },
  loading:                 { type: Boolean, default: false },
  serverError:             { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

const dialogRef = ref(null)
const mapContainerRef = ref(null)
let map = null

const form = ref({ shape_name: '' })
const fieldErrors = ref({ shape_name: null })
const localError = ref(null)
const editableWaypoints = ref([]) // [lon, lat]
const selectedWaypointIndex = ref(-1)
const isDraggingWaypoint = ref(false)
const didDragWaypoint = ref(false)

// Routing state
const routingAvailable = ref(false)   // true once health check passes
const autoRoute = ref(true)
const routedCoords = ref([])  // [[lon, lat], ...] decoded from Graphhopper response
const isRouting = ref(false)
const routingError = ref(null)
let routingDebounceTimer = null
let routingGeneration = 0

// GTFS rail-based route types for which routing is not supported by Graphhopper.
const UNSUPPORTED_ROUTE_TYPES = new Set([0, 1, 2, 5, 7, 12])

// Routing is only shown when GH is available AND the route type is supported.
const routingSupported = computed(() =>
  routingAvailable.value &&
  props.routeType !== null &&
  props.routeType !== undefined &&
  !UNSUPPORTED_ROUTE_TYPES.has(props.routeType)
)

async function checkRoutingHealth() {
  try {
    const res = await api.routing.health()
    routingAvailable.value = res.available === true
  } catch {
    routingAvailable.value = false
  }
}

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

const schema = computed(() => z.object({
  shape_name: z
    .string()
    .min(1, t('schedule.route_path_modal.validation_name_required'))
    .max(255, t('schedule.route_path_modal.validation_name_too_long')),
}))

function encodeSigned(value) {
  let v = value < 0 ? ~(value << 1) : (value << 1)
  let output = ''
  while (v >= 0x20) {
    output += String.fromCharCode((0x20 | (v & 0x1f)) + 63)
    v >>= 5
  }
  output += String.fromCharCode(v + 63)
  return output
}

function encodePolyline(coords) {
  let lastLat = 0
  let lastLon = 0
  let result = ''

  for (const [lon, lat] of coords) {
    const latE5 = Math.round(lat * 1e5)
    const lonE5 = Math.round(lon * 1e5)
    result += encodeSigned(latE5 - lastLat)
    result += encodeSigned(lonE5 - lastLon)
    lastLat = latE5
    lastLon = lonE5
  }
  return result
}

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

function coordKey(lon, lat) {
  return `${Number(lon).toFixed(5)}:${Number(lat).toFixed(5)}`
}

const servedStopByCoord = computed(() => {
  const mapByCoord = {}
  for (const stop of props.servedStops) {
    if (!Number.isFinite(stop.stop_lon) || !Number.isFinite(stop.stop_lat)) continue
    mapByCoord[coordKey(stop.stop_lon, stop.stop_lat)] = {
      stop_name: stop.stop_name ?? stop.stop_id,
      platform_code: stop.platform_code ?? null,
    }
  }
  return mapByCoord
})

function findStopMetaForWaypoint(point) {
  return servedStopByCoord.value[coordKey(point[0], point[1])] ?? null
}

function initializeWaypoints() {
  // Invalidate any in-flight routing request
  routingGeneration++

  autoRoute.value = true
  routingError.value = null

  if (props.existingPolyline) {
    editableWaypoints.value = decodePolyline(props.existingPolyline)
  } else {
    editableWaypoints.value = props.servedStops
      .filter(stop => Number.isFinite(stop.stop_lon) && Number.isFinite(stop.stop_lat))
      .map(stop => [stop.stop_lon, stop.stop_lat])
  }

  // Pre-populate routedCoords from stored routed_polyline so the line is
  // shown immediately before the fresh routing request completes.
  routedCoords.value = props.existingRoutedPolyline
    ? decodePolyline(props.existingRoutedPolyline)
    : []

  if (editableWaypoints.value.length > 0) {
    selectedWaypointIndex.value = editableWaypoints.value.length - 1
  } else {
    selectedWaypointIndex.value = -1
  }
}

async function triggerRouting() {
  if (!routingSupported.value || !autoRoute.value || editableWaypoints.value.length < 2) return
  const gen = ++routingGeneration
  isRouting.value = true
  routingError.value = null
  try {
    const waypoints = editableWaypoints.value.map(([lng, lat]) => ({ lat, lng }))
    const result = await api.routing.calculate(props.routeType, waypoints)
    if (gen !== routingGeneration) return // stale response — discard
    routedCoords.value = result.points.map(p => [p.lng, p.lat])
    refreshMapData()
  } catch (err) {
    if (gen !== routingGeneration) return
    const code = err?.status ?? 502
    routingError.value = t('schedule.route_path_modal.routing_error', { code })
    routedCoords.value = []
    refreshMapData()
  } finally {
    if (gen === routingGeneration) isRouting.value = false
  }
}

function scheduleRouting() {
  if (!routingSupported.value || !autoRoute.value) return
  clearTimeout(routingDebounceTimer)
  routingDebounceTimer = setTimeout(triggerRouting, 500)
}

// The coordinates to draw as the route line: routed when available, otherwise straight segments.
const displayLineCoords = computed(() =>
  autoRoute.value && routedCoords.value.length >= 2
    ? routedCoords.value
    : editableWaypoints.value
)

const mapCoords = computed(() => editableWaypoints.value)

const waypointRows = computed(() =>
  editableWaypoints.value.map((point, index) => ({
    index,
    point,
    stopMeta: findStopMetaForWaypoint(point),
  }))
)

const mapData = computed(() => ({
  type: 'FeatureCollection',
  features: props.servedStops
    .filter(stop => Number.isFinite(stop.stop_lon) && Number.isFinite(stop.stop_lat))
    .map((stop, index) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [stop.stop_lon, stop.stop_lat],
      },
      properties: {
        stop_id: stop.stop_id,
        stop_name: stop.stop_name ?? stop.stop_id,
        platform_code: stop.platform_code ?? '',
        stop_order: index + 1,
      },
    })),
}))

const waypointData = computed(() => ({
  type: 'FeatureCollection',
  features: editableWaypoints.value.map((wp, index) => ({
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: wp,
    },
    properties: {
      waypoint_index: index,
      selected: index === selectedWaypointIndex.value,
    },
  })),
}))


const lineData = computed(() => ({
  type: 'FeatureCollection',
  features: displayLineCoords.value.length >= 2
    ? [{
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: displayLineCoords.value,
        },
        properties: {},
      }]
    : [],
}))

function validateForm() {
  fieldErrors.value = { shape_name: null }
  localError.value = null

  const result = schema.value.safeParse({ shape_name: form.value.shape_name.trim() })
  if (!result.success) {
    for (const issue of result.error.issues) {
      const field = issue.path?.[0]
      if (field && fieldErrors.value[field] == null) {
        fieldErrors.value[field] = issue.message
      }
    }
    return false
  }

  if (!props.shapeId) {
    localError.value = t('schedule.route_path_modal.validation_missing_shape_id')
    return false
  }

  if (mapCoords.value.length < 2) {
    localError.value = t('schedule.route_path_modal.validation_min_stops')
    return false
  }

  return true
}

function handleSave() {
  if (!validateForm()) return
  const routedPolyline = autoRoute.value && routedCoords.value.length >= 2
    ? encodePolyline(routedCoords.value)
    : null
  emit('save', {
    shape_id: props.shapeId,
    shape_name: form.value.shape_name.trim(),
    shape_polyline: encodePolyline(mapCoords.value),
    routed_polyline: routedPolyline,
  })
}

function handleSaveAndDistribute() {
  if (!validateForm()) return
  const routedPolyline = autoRoute.value && routedCoords.value.length >= 2
    ? encodePolyline(routedCoords.value)
    : null
  emit('save', {
    shape_id: props.shapeId,
    shape_name: form.value.shape_name.trim(),
    shape_polyline: encodePolyline(mapCoords.value),
    routed_polyline: routedPolyline,
    apply_to_pattern: true,
    pattern_hash: props.shapeId,
  })
}

function selectWaypoint(index) {
  selectedWaypointIndex.value = index
  refreshMapData()
}

function deleteWaypoint(index) {
  if (index < 0 || index >= editableWaypoints.value.length) return
  editableWaypoints.value.splice(index, 1)

  if (editableWaypoints.value.length === 0) {
    selectedWaypointIndex.value = -1
  } else if (selectedWaypointIndex.value > index) {
    selectedWaypointIndex.value -= 1
  } else if (selectedWaypointIndex.value === index) {
    selectedWaypointIndex.value = Math.min(index, editableWaypoints.value.length - 1)
  }

  refreshMapData()
  scheduleRouting()
}

function waypointIndexFromFeature(feature) {
  const raw = feature?.properties?.waypoint_index
  const index = Number.parseInt(raw, 10)
  return Number.isInteger(index) ? index : -1
}

function setMapCursor(cursor = 'crosshair') {
  if (!map) return
  const canvas = map.getCanvas()
  if (canvas) canvas.style.cursor = cursor
}

function handleClose() {
  emit('update:modelValue', false)
}

async function ensureMap() {
  if (map || !mapContainerRef.value) return

  if (!settingsStore.state.mapTileUrl) {
    await settingsStore.load()
  }

  map = new maplibregl.Map({
    container: mapContainerRef.value,
    style: settingsStore.state.mapTileUrl,
    center: [10.0, 51.0],
    zoom: 6,
  })
  map.addControl(new maplibregl.NavigationControl(), 'top-right')
  setMapCursor('crosshair')

  map.on('load', () => {
    map.addSource('route-path-stops', { type: 'geojson', data: mapData.value })
    map.addSource('route-path-waypoints', { type: 'geojson', data: waypointData.value })
    map.addSource('route-path-line', { type: 'geojson', data: lineData.value })

    map.addLayer({
      id: 'route-path-line-layer',
      type: 'line',
      source: 'route-path-line',
      paint: {
        'line-color': '#1f69e0',
        'line-width': 4,
        'line-opacity': 0.75,
      },
    })

    map.addLayer({
      id: 'route-path-waypoints-layer',
      type: 'circle',
      source: 'route-path-waypoints',
      paint: {
        'circle-radius': [
          'case',
          ['boolean', ['get', 'selected'], false],
          7,
          5,
        ],
        'circle-color': [
          'case',
          ['boolean', ['get', 'selected'], false],
          '#f57c00',
          '#ffffff',
        ],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#1f69e0',
      },
    })

    map.addLayer({
      id: 'route-path-stops-layer',
      type: 'circle',
      source: 'route-path-stops',
      paint: {
        'circle-radius': 4,
        'circle-color': '#ffffff',
        'circle-stroke-width': 1,
        'circle-stroke-color': '#5e6472',
      },
    })

    map.addLayer({
      id: 'route-path-stops-label-layer',
      type: 'symbol',
      source: 'route-path-stops',
      layout: {
        'text-field': ['concat', ['to-string', ['get', 'stop_order']], '. ', ['get', 'stop_name']],
        'text-size': 11,
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
      },
      paint: {
        'text-color': '#1c1d22',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1,
      },
    })

    map.on('mouseenter', 'route-path-waypoints-layer', () => {
      if (!isDraggingWaypoint.value) setMapCursor('pointer')
    })

    map.on('mouseleave', 'route-path-waypoints-layer', () => {
      if (!isDraggingWaypoint.value) setMapCursor('crosshair')
    })

    map.on('mousedown', 'route-path-waypoints-layer', (e) => {
      if (!e.features || e.features.length === 0) return
      const index = waypointIndexFromFeature(e.features[0])
      if (index < 0 || index >= editableWaypoints.value.length) return

      if (selectedWaypointIndex.value !== index) {
        selectedWaypointIndex.value = index
        refreshMapData()
        return
      }

      isDraggingWaypoint.value = true
      didDragWaypoint.value = false
      map.dragPan.disable()
      setMapCursor('grabbing')
      e.preventDefault()
    })

    map.on('mousemove', (e) => {
      if (!isDraggingWaypoint.value) return
      const index = selectedWaypointIndex.value
      if (index < 0 || index >= editableWaypoints.value.length) return

      didDragWaypoint.value = true
      editableWaypoints.value.splice(index, 1, [e.lngLat.lng, e.lngLat.lat])
      refreshMapData()
      scheduleRouting()
    })

    const stopDraggingWaypoint = () => {
      if (!isDraggingWaypoint.value) return
      isDraggingWaypoint.value = false
      map.dragPan.enable()
      setMapCursor('crosshair')
    }

    map.on('mouseup', stopDraggingWaypoint)
    map.on('mouseleave', stopDraggingWaypoint)

    map.on('click', (e) => {
      if (didDragWaypoint.value) {
        didDragWaypoint.value = false
        return
      }

      if (isDraggingWaypoint.value) return

      const hitWaypointFeatures = map.queryRenderedFeatures(e.point, {
        layers: ['route-path-waypoints-layer'],
      })
      const waypointFeature = hitWaypointFeatures.find(
        feature => feature?.geometry?.type === 'Point'
      )
      if (waypointFeature) {
        const index = waypointIndexFromFeature(waypointFeature)
        if (index >= 0 && index < editableWaypoints.value.length) {
          selectedWaypointIndex.value = index
          refreshMapData()
          return
        }
      }

      let lon = e.lngLat.lng
      let lat = e.lngLat.lat

      const hitStopFeatures = map.queryRenderedFeatures(e.point, {
        layers: ['route-path-stops-layer', 'route-path-stops-label-layer'],
      })
      const stopFeature = hitStopFeatures.find(
        feature => feature?.geometry?.type === 'Point'
      )
      if (stopFeature && Array.isArray(stopFeature.geometry.coordinates)) {
        const [stopLon, stopLat] = stopFeature.geometry.coordinates
        if (Number.isFinite(stopLon) && Number.isFinite(stopLat)) {
          lon = stopLon
          lat = stopLat
        }
      }

      const insertAfter = selectedWaypointIndex.value
      const insertIndex = insertAfter >= 0
        ? Math.min(insertAfter + 1, editableWaypoints.value.length)
        : editableWaypoints.value.length

      editableWaypoints.value.splice(insertIndex, 0, [lon, lat])
      selectedWaypointIndex.value = insertIndex
      refreshMapData()
      scheduleRouting()
    })
  })
}

function fitMapBounds() {
  if (!map) return
  // Prefer the routed line for bounds; fall back to waypoints
  const coords = displayLineCoords.value.length >= 2
    ? displayLineCoords.value
    : editableWaypoints.value
  if (coords.length === 0) return
  if (coords.length === 1) {
    map.jumpTo({ center: coords[0], zoom: 14 })
    return
  }

  const bounds = new maplibregl.LngLatBounds(coords[0], coords[0])
  for (const coord of coords) {
    bounds.extend(coord)
  }
  map.fitBounds(bounds, { padding: 60, duration: 0 })
}

function refreshMapData() {
  if (!map) return
  const stopSource = map.getSource('route-path-stops')
  const waypointSource = map.getSource('route-path-waypoints')
  const lineSource = map.getSource('route-path-line')
  stopSource?.setData(mapData.value)
  waypointSource?.setData(waypointData.value)
  lineSource?.setData(lineData.value)
}

watch(
  () => props.modelValue,
  async (open) => {
    const dialog = dialogRef.value
    if (!dialog) return

    if (open) {
      form.value.shape_name = props.initialName ?? ''
      initializeWaypoints()
      fieldErrors.value = { shape_name: null }
      localError.value = null
      dialog.show?.()

      await nextTick()
      await ensureMap()
      refreshMapData()
      map?.resize()
      fitMapBounds()
      // Check Graphhopper availability, then auto-route if applicable.
      await checkRoutingHealth()
      // Only auto-route on open when there is no stored routed polyline yet.
      // If one exists, initializeWaypoints() already loaded it into routedCoords.
      if (routingSupported.value && !props.existingRoutedPolyline) {
        triggerRouting()
      }
    } else {
      clearTimeout(routingDebounceTimer)
      dialog.close?.()
    }
  },
)

watch(
  () => [props.servedStops, props.initialName, props.existingPolyline, props.existingRoutedPolyline],
  () => {
    if (!props.modelValue) return
    form.value.shape_name = props.initialName ?? ''
    initializeWaypoints()
    refreshMapData()
    map?.resize()
    if (routingSupported.value && !props.existingRoutedPolyline) {
      triggerRouting()
    }
  },
  { deep: true },
)

watch(autoRoute, (val) => {
  if (!val) {
    clearTimeout(routingDebounceTimer)
    routedCoords.value = []
    refreshMapData()
  } else {
    triggerRouting()
  }
})

onBeforeUnmount(() => {
  clearTimeout(routingDebounceTimer)
  map?.remove()
  map = null
})
</script>

<template>
  <md-dialog ref="dialogRef" class="route-path-modal" @closed="handleClose">
    <div slot="headline" class="route-path-modal__headline">
      <md-icon class="route-path-modal__headline-icon">map</md-icon>
      <span class="route-path-modal__title">{{ t('schedule.route_path_modal.title') }}</span>
    </div>

    <form slot="content" class="route-path-modal__form" method="dialog">
      <div class="route-path-modal__section">
        <p class="route-path-modal__section-label">{{ t('schedule.route_path_modal.section_name') }}</p>
        <md-outlined-text-field
          class="route-path-modal__name-field"
          :label="t('schedule.route_path_modal.field_name')"
          :value="form.shape_name"
          :error="!!fieldErrors.shape_name"
          :error-text="fieldErrors.shape_name ?? ''"
          required
          @input="form.shape_name = $event.target.value; clearFieldError('shape_name')"
        />
      </div>

      <div class="route-path-modal__workspace">
        <div class="route-path-modal__section route-path-modal__section--map">
          <p class="route-path-modal__section-label">{{ t('schedule.route_path_modal.section_map') }}</p>
          <div class="route-path-modal__map-wrap">
            <div ref="mapContainerRef" class="route-path-modal__map" />
          </div>
        </div>

        <div class="route-path-modal__section route-path-modal__section--waypoints">
          <p class="route-path-modal__section-label">{{ t('schedule.route_path_modal.section_waypoints') }}</p>
          <div class="route-path-modal__waypoints">
            <div
              v-for="row in waypointRows"
              :key="'wp-' + row.index"
              class="route-path-modal__waypoint-row"
              :class="{ 'route-path-modal__waypoint-row--selected': row.index === selectedWaypointIndex }"
              @click="selectWaypoint(row.index)"
            >
              <span class="route-path-modal__waypoint-text">
                <template v-if="row.stopMeta">
                  {{ row.index + 1 }}. {{ row.stopMeta.stop_name }}<template v-if="row.stopMeta.platform_code"> ({{ row.stopMeta.platform_code }})</template>
                </template>
                <template v-else>
                  {{ row.index + 1 }}. ({{ row.point[1].toFixed(5) }}, {{ row.point[0].toFixed(5) }})
                </template>
              </span>
              <button
                type="button"
                class="route-path-modal__waypoint-delete"
                :title="t('common.delete')"
                @click.stop.prevent="deleteWaypoint(row.index)"
              >
                <md-icon>delete</md-icon>
              </button>
            </div>
          </div>
        </div>
      </div>
    </form>

    <div slot="actions">
      <div class="route-path-modal__actions-left">
        <label v-if="routingSupported" class="route-path-modal__auto-route-label">
          <md-checkbox
            :checked="autoRoute"
            touch-target="wrapper"
            @change="autoRoute = $event.target.checked"
          />
          <span>{{ t('schedule.route_path_modal.auto_route') }}</span>
        </label>
        <span v-else-if="routingAvailable && !routingSupported" class="route-path-modal__routing-unavailable">
          {{ t('schedule.route_path_modal.routing_unsupported_type') }}
        </span>
        <span v-if="isRouting" class="route-path-modal__routing-indicator">
          <md-icon class="route-path-modal__routing-spinner">sync</md-icon>
          {{ t('schedule.route_path_modal.routing_in_progress') }}
        </span>
        <p v-if="localError || serverError || routingError" class="route-path-modal__error">
          {{ localError || serverError || routingError }}
        </p>
      </div>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button :disabled="loading" @click="handleSaveAndDistribute">
        <md-icon slot="icon">send</md-icon>
        {{ t('schedule.route_path_modal.save_and_distribute') }}
      </md-filled-button>
      <md-filled-button :disabled="loading" @click="handleSave">
        <md-icon slot="icon">save</md-icon>
        {{ t('common.save') }}
      </md-filled-button>
    </div>
  </md-dialog>
</template>

<style scoped>
.route-path-modal {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
  width: min(1516px, 98vw);
  height: 710px;
  max-height: 710px;
  overflow: hidden;
}

.route-path-modal::part(dialog) {
  overflow: hidden;
}

.route-path-modal::part(content) {
  overflow: hidden;
}

.route-path-modal__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.route-path-modal__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
}

.route-path-modal__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.route-path-modal__form {
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 1.25rem;
  padding-top: 0.5rem;
  height: 550px;
  min-height: 0;
  overflow: hidden;
}

.route-path-modal__section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.route-path-modal__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.route-path-modal__name-field {
  width: 100%;
}

.route-path-modal__map-wrap {
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 6px;
  overflow: hidden;
  flex: 1;
}

.route-path-modal__map {
  width: 100%;
  height: 100%;
}

.route-path-modal__workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 1rem;
  height: 100%;
  min-height: 0;
}

.route-path-modal__section--map,
.route-path-modal__section--waypoints {
  height: 100%;
  min-height: 0;
}

.route-path-modal__error {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}

.route-path-modal__actions-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-right: auto;
  flex-wrap: wrap;
}

.route-path-modal__auto-route-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.875rem;
  color: var(--md-sys-color-on-surface, #222);
  cursor: pointer;
  user-select: none;
}

.route-path-modal__routing-indicator {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8125rem;
  color: var(--md-sys-color-primary, #1f69e0);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.route-path-modal__routing-spinner {
  font-size: 1rem;
  --md-icon-size: 1rem;
  animation: spin 1s linear infinite;
}

.route-path-modal__waypoints {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  height: 100%;
  overflow-y: auto;
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 4px;
  padding: 0.75rem;
}

.route-path-modal__waypoint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem;
  background: var(--md-sys-color-surface-dim, #f5f5f5);
  border-radius: 3px;
  font-size: 0.875rem;
  cursor: pointer;
}

.route-path-modal__waypoint-row--selected {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 14%, #ffffff);
  outline: 1px solid color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 50%, #ffffff);
}

.route-path-modal__waypoint-text {
  font-family: 'Courier New', monospace;
  font-size: 0.8125rem;
  color: var(--md-sys-color-on-surface, #222);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-path-modal__waypoint-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  border-radius: 50%;
  color: var(--md-sys-color-error, #ba1a1a);
  flex-shrink: 0;
}

.route-path-modal__waypoint-delete:hover {
  background: rgba(186, 26, 26, 0.1);
}
</style>
