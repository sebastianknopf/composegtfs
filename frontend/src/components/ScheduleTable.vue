<script setup>
/**
 * ScheduleTable — Timetable component for the schedule view.
 *
 * Rows  = stops in the route band (sort_order)
 * Cols  = [stop name | platform code | …trips added later]
 *
 * Props:
 *   versionId  — string | null
 *   routeId    — string | null
 *   direction  — number (0 outbound, 1 inbound)
 *   platforms  — Array [{stop_id, stop_name, platform_code}]
 *   canWrite   — boolean (add + reorder)
 *   canDelete  — boolean (remove)
 */
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import ScheduleTableFlyout from '@/components/ScheduleTableFlyout.vue'
import ScheduleTableAttrFlyout from '@/components/ScheduleTableAttrFlyout.vue'
import ScheduleTimeContextMenu from '@/components/ScheduleTimeContextMenu.vue'
import '@material/web/icon/icon.js'
import '@material/web/progress/circular-progress.js'

const props = defineProps({
  versionId:         { type: String,  default: null },
  routeId:           { type: String,  default: null },
  routeType:         { type: Number,  default: null },
  direction:         { type: Number,  default: 0 },
  platforms:         { type: Array,   default: () => [] },
  canRead:           { type: Boolean, default: false },
  canWrite:          { type: Boolean, default: false },
  canDelete:         { type: Boolean, default: false },
  filterServiceIds:  { type: Array,   default: () => [] },
})

const { t } = useI18n()

// ---- Band data ----
const bandEntries = ref([])
const _loadingCount = ref(0)
const loading       = computed(() => _loadingCount.value > 0)
const tableRef      = ref(null)

// Build lookup maps from platforms array
const platformMap = computed(() => {
  const m = {}
  for (const p of props.platforms) m[p.stop_id] = p
  return m
})

function stopName(stopId) {
  return platformMap.value[stopId]?.stop_name ?? stopId
}
function platformCode(stopId) {
  return platformMap.value[stopId]?.platform_code ?? null
}
function stopLabel(stopId) {
  const code = platformCode(stopId)
  return code ? `${stopName(stopId)} (${code})` : stopName(stopId)
}

// ---- Trips (frontend-only mockup for now) ----
function createEmptyTrip() {
  return {
    id:        null,
    tripId:    null,
    saved:     false,
    selected:  false,
    short_name: '',
    day_type: '',
    route_path: '',
    headsign_id: null,
    attributes: { wheelchair_accessible: null, bikes_allowed: null, cars_allowed: null },
    times: {},
    stopTimes: {},
    geo_pattern_hash:      null,
    schedule_pattern_hash: null,
  }
}

const trips     = ref([])
const dummyTrip = ref(createEmptyTrip())
const shapeLabelById    = ref({})
const shapeRouteTypeById = ref({})
const headsigns          = ref([])
const headsignLabelById  = ref({})
const headsignOpen       = ref(null)  // tripId | 'dummy' | null

const headsignItems = computed(() =>
  headsigns.value.map(h => ({
    id:    h.id,
    label: h.name,
  }))
)

async function loadHeadsigns() {
  if (!props.versionId || !props.canRead) { headsigns.value = []; return }
  try {
    headsigns.value = await api.schedule.headsigns(props.versionId)
    const next = { ...headsignLabelById.value }
    for (const h of headsigns.value) next[h.id] = h.name
    headsignLabelById.value = next
  } catch {
    headsigns.value = []
  }
}

async function deleteTrip(trip) {
  if (!canMakeRequest('delete')) {
    toast.show(t('common.permission_denied'), 'error')
    return
  }
  if (trip.saved) {
    try {
      await api.schedule.trips.delete(props.versionId, props.routeId, trip.tripId)
    } catch {
      toast.show(t('schedule.error_delete_trip'), 'error')
      return
    }
  }
  trips.value = trips.value.filter(t => t.id !== trip.id)
}

function promoteDummy({ entryId = null, fieldName = null } = {}) {
  const newId = crypto.randomUUID()
  const newTrip = {
    ...dummyTrip.value,
    id:         newId,
    tripId:     generateTripId(),
    saved:      false,
    times:      { ...dummyTrip.value.times },
    stopTimes:  { ...dummyTrip.value.stopTimes },
    attributes: { ...dummyTrip.value.attributes },
  }
  trips.value.push(newTrip)
  dummyTrip.value = createEmptyTrip()
  maybeSaveTrip(newTrip)  // fire-and-forget; noop if not yet valid
  nextTick(() => {
    let el
    if (entryId !== null) {
      el = tableRef.value?.querySelector(`[data-trip="${newId}"][data-entry="${entryId}"]`)
      el?.focus()
      el?.select()
    } else if (fieldName !== null) {
      el = tableRef.value?.querySelector(`[data-trip="${newId}"][data-field="${fieldName}"]`)
      el?.focus()
      // Place cursor at end, don't select – user is mid-typing
      if (el) el.setSelectionRange(el.value.length, el.value.length)
    }
  })
}

function onDummyInput(opts = {}) {
  nextTick(() => {
    const d = dummyTrip.value
    const hasContent =
      d.short_name.trim() || d.day_type.trim() || d.route_path.trim() || d.headsign_id ||
      Object.values(d.attributes).some(v => v !== null) ||
      Object.values(d.times).some(v => (v ?? '').trim())
    if (!hasContent) return
    promoteDummy(opts)
  })
}

// ---- Trip ID generation & attribute conversion ----
function generateTripId() {
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(3)))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
  return `${props.routeId}-${props.direction}-${hex}`
}

// Frontend: null | true | false  ↔  GTFS: null | 1 | 2
function attrToGtfs(v) { return v === true ? 1 : v === false ? 2 : null }
function attrFromGtfs(v) { return v === 1 ? true : v === 2 ? false : null }

// Parse "H+:MM" or "H+:MM:SS" → total minutes (for sorting)
function toMinutes(timeStr) {
  if (!timeStr) return null
  const parts = timeStr.split(':').map(Number)
  if (parts.length < 2 || isNaN(parts[0]) || isNaN(parts[1])) return null
  return parts[0] * 60 + parts[1]
}

// Normalize GTFS "H:MM:SS" to display format "H:MM" (strip seconds)
function normalizeTime(t) {
  if (!t) return ''
  const parts = t.split(':')
  if (parts.length < 2) return t
  return `${parts[0]}:${parts[1]}`
}

// ---- Load trips from backend ----
let _tripLoadKey = 0

async function loadTrips() {
  if (!props.versionId || !props.routeId || !props.canRead) {
    trips.value = []
    return
  }
  const key = ++_tripLoadKey
  _loadingCount.value++
  try {
    // Stop times are embedded in the list response – no per-trip requests needed.
    const backendTrips = await api.schedule.trips.list(props.versionId, props.routeId, props.direction)
    if (key !== _tripLoadKey) return  // navigation happened during fetch

    const mapped = backendTrips.map((bt) => {
      const stList = bt.stop_times ?? []
      const times = {}
      const stopTimes = {}
      for (const st of stList) {
        const id = st.route_band_stop_id
        if (st.departure_time) {
          times[id] = normalizeTime(st.departure_time)
        }
        if (st.arrival_time || st.pickup_type !== null || st.drop_off_type !== null || st.stop_headsign_id) {
          stopTimes[id] = {
            arrival_time:     normalizeTime(st.arrival_time) || null,
            pickup_type:      st.pickup_type   ?? null,
            drop_off_type:    st.drop_off_type ?? null,
            stop_headsign_id: st.stop_headsign_id ?? null,
          }
        }
      }
      return {
        id:         crypto.randomUUID(),
        tripId:     bt.trip_id,
        saved:      true,
        short_name: bt.trip_short_name ?? '',
        day_type:   bt.service_id ?? '',
        route_path: bt.shape_id ?? '',
        headsign_id: bt.trip_headsign_id ?? null,
        attributes: {
          wheelchair_accessible: attrFromGtfs(bt.wheelchair_accessible),
          bikes_allowed:         attrFromGtfs(bt.bikes_allowed),
          cars_allowed:          attrFromGtfs(bt.cars_allowed),
        },
        times,
        stopTimes,
        selected: false,
        geo_pattern_hash:      bt.geo_pattern_hash      ?? null,
        schedule_pattern_hash: bt.schedule_pattern_hash ?? null,
      }
    })

    // Sort ascending by first (earliest) departure time in the band
    mapped.sort((a, b) => {
      const firstTime = trip => {
        const mins = Object.values(trip.times)
          .map(v => toMinutes(v))
          .filter(v => v !== null)
        return mins.length ? Math.min(...mins) : Infinity
      }
      return firstTime(a) - firstTime(b)
    })

    trips.value = mapped
    await ensureShapeLabels(mapped.map(trip => trip.route_path).filter(Boolean))
    ensureHeadsignLabels(mapped.map(trip => trip.headsign_id).filter(Boolean))
  } catch {
    if (key === _tripLoadKey) trips.value = []
  } finally {
    _loadingCount.value--
  }
}

async function ensureShapeLabels(shapeIds) {
  const unique = [...new Set(shapeIds.filter(Boolean))]
  const missing = unique.filter(id => !shapeLabelById.value[id])
  if (!props.versionId || missing.length === 0) return

  const results = await Promise.all(
    missing.map(id => api.schedule.shapes.get(props.versionId, id).catch(() => null))
  )
  const nextLabels     = { ...shapeLabelById.value }
  const nextRouteTypes = { ...shapeRouteTypeById.value }
  for (const row of results) {
    if (!row) continue
    nextLabels[row.shape_id]     = row.shape_name ?? row.shape_id
    nextRouteTypes[row.shape_id] = row.route_type ?? null
  }
  shapeLabelById.value     = nextLabels
  shapeRouteTypeById.value = nextRouteTypes
}

function ensureHeadsignLabels(headsignIds) {
  const next = { ...headsignLabelById.value }
  let changed = false
  for (const id of headsignIds) {
    if (next[id]) continue
    const found = headsigns.value.find(h => h.id === id)
    if (found) {
      next[id] = found.name
      changed = true
    }
  }
  if (changed) headsignLabelById.value = next
}

// ---- Trip persistence helpers ----

async function maybeSaveTrip(trip) {
  if (!canMakeRequest('write')) return
  if (trip.saved || !isTripValid(trip)) return
  try {
    await api.schedule.trips.create(props.versionId, props.routeId, {
      trip_id:               trip.tripId,
      service_id:            trip.day_type || null,
      direction_id:          props.direction,
      trip_short_name:       trip.short_name || null,
      shape_id:              trip.route_path || null,
      trip_headsign_id:      trip.headsign_id || null,
      wheelchair_accessible: attrToGtfs(trip.attributes.wheelchair_accessible),
      bikes_allowed:         attrToGtfs(trip.attributes.bikes_allowed),
      cars_allowed:          attrToGtfs(trip.attributes.cars_allowed),
    })
    trip.saved = true
    try {
      // Persist all departure times that are already filled in
      const timeEntries = Object.entries(trip.times).filter(([, v]) => (v ?? '').trim())
      await Promise.all(
        timeEntries.map(([entryId, depTime]) =>
          api.schedule.stopTimes.upsert(
            props.versionId, props.routeId, trip.tripId, entryId,
            { departure_time: depTime, ...(trip.stopTimes[entryId] ?? {}) },
          )
        )
      )
    } finally {
      // Always sync hashes from backend after create, even if a stop-time upsert failed.
      await _refreshTripHash(trip)
    }
  } catch {
    toast.show(t('schedule.error_save_trip'), 'error')
  }
}

async function updateTripOnBackend(trip) {
  if (!canMakeRequest('write')) return
  if (!trip.saved) return
  try {
    await api.schedule.trips.update(props.versionId, props.routeId, trip.tripId, {
      service_id:            trip.day_type || null,
      trip_short_name:       trip.short_name || null,
      shape_id:              trip.route_path || null,
      trip_headsign_id:      trip.headsign_id || null,
      wheelchair_accessible: attrToGtfs(trip.attributes.wheelchair_accessible),
      bikes_allowed:         attrToGtfs(trip.attributes.bikes_allowed),
      cars_allowed:          attrToGtfs(trip.attributes.cars_allowed),
    })
    await _refreshTripHash(trip)
  } catch {
    toast.show(t('schedule.error_save_trip'), 'error')
  }
}

async function upsertStopTimeToBackend(trip, entryId) {
  if (!canMakeRequest('write')) return
  if (!trip.saved) return
  const depTime = (trip.times[entryId] ?? '').trim()
  if (!depTime) return
  const st = trip.stopTimes[entryId] ?? {}
  try {
    await api.schedule.stopTimes.upsert(
      props.versionId, props.routeId, trip.tripId, entryId,
      {
        departure_time:   depTime,
        arrival_time:     st.arrival_time     ?? null,
        pickup_type:      st.pickup_type      ?? null,
        drop_off_type:    st.drop_off_type    ?? null,
        stop_headsign_id: st.stop_headsign_id ?? null,
      },
    )
    await _refreshTripHash(trip)
  } catch {
    toast.show(t('schedule.error_save_trip'), 'error')
  }
}

async function deleteStopTimeFromBackend(trip, entryId) {
  if (!canMakeRequest('write')) return
  if (!trip.saved) return
  try {
    await api.schedule.stopTimes.delete(props.versionId, props.routeId, trip.tripId, entryId)
    await _refreshTripHash(trip)
  } catch {
    // Ignore 404 (already gone); other errors are silently swallowed
  }
}

async function _refreshTripHash(trip) {
  if (!trip.saved) return
  try {
    const data = await api.schedule.trips.get(props.versionId, props.routeId, trip.tripId)
    trip.geo_pattern_hash      = data.geo_pattern_hash      ?? null
    trip.schedule_pattern_hash = data.schedule_pattern_hash ?? null
  } catch {
    // Non-critical — hash stays stale until next full load
  }
}

// ---- Load band ----
async function loadBand() {
  if (!props.versionId || !props.routeId) {
    bandEntries.value = []
    return
  }
  _loadingCount.value++
  try {
    bandEntries.value = await api.schedule.band.get(props.versionId, props.routeId, props.direction)
  } catch {
    bandEntries.value = []
  } finally {
    _loadingCount.value--
  }
}

watch(
  () => [props.versionId, props.routeId, props.direction],
  () => {
    loadBand()
    trips.value = []
    dummyTrip.value = createEmptyTrip()
    loadTrips()
  },
  { immediate: true },
)

// ---- Day types (Tagesarten) ----
const dayTypes     = ref([])
const dayTypeOpen  = ref(null)   // tripId | 'dummy' | null

const dayTypeItems = computed(() =>
  dayTypes.value.map(dt => ({
    id:       dt.service_id,
    label:    dt.name ?? dt.service_id,
    sublabel: dt.name ? dt.service_id : undefined,
  }))
)

async function loadDayTypes() {
  if (!props.versionId || !props.canRead) { dayTypes.value = []; return }
  try {
    dayTypes.value = await api.schedule.dayTypes(props.versionId)
  } catch {
    dayTypes.value = []
  }
}

function openDayTypeDropdown(id) {
  dayTypeOpen.value = id
  nextTick(() => {
    tableRef.value?.querySelector(`[data-dt-trip="${id}"] .sft-search`)?.focus()
  })
}

function closeDayTypeDropdown() {
  dayTypeOpen.value = null
}

function selectDummyDayType(serviceId) {
  dummyTrip.value.day_type = serviceId
  closeDayTypeDropdown()
  onDummyInput({ fieldName: 'day_type' })
}

watch(
  () => [props.versionId, props.canRead],
  () => loadDayTypes(),
  { immediate: true },
)

watch(
  () => [props.versionId, props.canRead],
  () => loadHeadsigns(),
  { immediate: true },
)

watch(() => props.canRead, () => loadTrips())
watch(() => props.versionId, () => {
  routePathSearchResults.value = []
  shapeLabelById.value     = {}
  shapeRouteTypeById.value = {}
  headsignLabelById.value  = {}
  headsigns.value          = []
})

// ---- Permission-based UI modes ----
const readonlyMode = computed(() => !props.canWrite)
const deleteDisabled = computed(() => !props.canDelete)

// ---- Request guards (permission pre-checks) ----
function canMakeRequest(requiredPerm) {
  if (requiredPerm === 'read') return props.canRead
  if (requiredPerm === 'write') return props.canWrite
  if (requiredPerm === 'delete') return props.canDelete
  return false
}

// ---- Route path flyout ----
const routePathOpen = ref(null)  // tripId | 'dummy' | null
const routePathSearchResults = ref([])
const routePathSearchQuery = ref('')
let routePathSearchTimer = null

const routePathItems = computed(() => {
  const merged = {}

  for (const [id, label] of Object.entries(shapeLabelById.value)) {
    merged[id] = { id, label }
  }
  for (const item of routePathSearchResults.value) {
    merged[item.id] = item
  }

  return Object.values(merged).sort((a, b) => a.label.localeCompare(b.label))
})

function routePathItemsForTrip(trip) {
  const query = routePathSearchQuery.value.trim()
  const allItems = query
    ? [...routePathSearchResults.value].sort((a, b) => a.label.localeCompare(b.label))
    : [...routePathItems.value]

  // Client-side filter by route type
  const filtered = props.routeType != null
    ? allItems.filter(item => shapeRouteTypeById.value[item.id] === props.routeType)
    : allItems

  if (query) return filtered

  const preferredId = trip?.geo_pattern_hash ?? null
  if (!preferredId) return filtered

  const preferredIndex = filtered.findIndex(item => item.id === preferredId)
  if (preferredIndex < 0) return filtered

  const preferredItem = {
    ...filtered[preferredIndex],
    icon: 'task_alt',
    iconClass: 'sft-item__icon--success',
  }

  return [preferredItem, ...filtered.filter((_, index) => index !== preferredIndex)]
}

async function loadRoutePaths(query = '') {
  if (!props.versionId || !props.canRead) {
    routePathSearchResults.value = []
    return
  }
  try {
    const rows = await api.schedule.shapes.search(props.versionId, query, 50, null)
    routePathSearchResults.value = rows.map(shape => ({
      id: shape.shape_id,
      label: shape.shape_name ?? shape.shape_id,
      routeType: shape.route_type ?? null,
    }))
    const nextLabels     = { ...shapeLabelById.value }
    const nextRouteTypes = { ...shapeRouteTypeById.value }
    for (const shape of rows) {
      nextLabels[shape.shape_id]     = shape.shape_name ?? shape.shape_id
      nextRouteTypes[shape.shape_id] = shape.route_type ?? null
    }
    shapeLabelById.value     = nextLabels
    shapeRouteTypeById.value = nextRouteTypes
  } catch {
    routePathSearchResults.value = []
  }
}

function queueRoutePathSearch(query) {
  routePathSearchQuery.value = query
  if (routePathSearchTimer !== null) {
    clearTimeout(routePathSearchTimer)
  }
  routePathSearchTimer = setTimeout(() => {
    routePathSearchTimer = null
    loadRoutePaths(query)
  }, 150)
}

function openRoutePathDropdown(id) {
  routePathOpen.value = id
  routePathSearchQuery.value = ''
  loadRoutePaths('')
  nextTick(() => {
    tableRef.value?.querySelector(`[data-rp-trip="${id}"] .sft-search`)?.focus()
  })
}
function closeRoutePathDropdown() {
  routePathOpen.value = null
  routePathSearchQuery.value = ''
}

function selectDummyRoutePath(val) {
  dummyTrip.value.route_path = val
  closeRoutePathDropdown()
  onDummyInput({ fieldName: 'route_path' })
}

function onTripRoutePathChange(trip, value) {
  trip.route_path = value
  const found = routePathItemsForTrip(trip).find(item => item.id === value)
  if (found) {
    shapeLabelById.value = { ...shapeLabelById.value, [value]: found.label }
  }
  closeRoutePathDropdown()
  if (trip.saved) {
    updateTripOnBackend(trip)
  } else {
    maybeSaveTrip(trip)
  }
}

function clearTripRoutePath(trip) {
  trip.route_path = ''
  closeRoutePathDropdown()
  if (trip.saved) {
    updateTripOnBackend(trip)
  }
}

function clearDummyRoutePath() {
  dummyTrip.value.route_path = ''
  closeRoutePathDropdown()
}

// ---- Headsign flyout ----
function openHeadsignDropdown(id) {
  headsignOpen.value = id
  nextTick(() => {
    tableRef.value?.querySelector(`[data-hs-trip="${id}"] .sft-search`)?.focus()
  })
}
function closeHeadsignDropdown() {
  headsignOpen.value = null
}

function selectDummyHeadsign(id) {
  dummyTrip.value.headsign_id = id
  if (id) {
    const found = headsignItems.value.find(item => item.id === id)
    if (found) headsignLabelById.value = { ...headsignLabelById.value, [id]: found.label }
  }
  closeHeadsignDropdown()
  onDummyInput({ fieldName: 'headsign_id' })
}

function onTripHeadsignChange(trip, value) {
  trip.headsign_id = value
  const found = headsignItems.value.find(item => item.id === value)
  if (found) headsignLabelById.value = { ...headsignLabelById.value, [value]: found.label }
  closeHeadsignDropdown()
  if (trip.saved) {
    updateTripOnBackend(trip)
  } else {
    maybeSaveTrip(trip)
  }
}

function clearTripHeadsign(trip) {
  trip.headsign_id = null
  closeHeadsignDropdown()
  if (trip.saved) {
    updateTripOnBackend(trip)
  }
}

function clearDummyHeadsign() {
  dummyTrip.value.headsign_id = null
  closeHeadsignDropdown()
}

// ---- Stop-time headsign indicator helper ----
function hasStopHeadsign(trip, entryId) {
  return !!(trip.stopTimes?.[entryId]?.stop_headsign_id)
}

const attrOpen = ref(null)  // tripId | 'dummy' | null

function openAttrDropdown(id)  { attrOpen.value = id }
function closeAttrDropdown()   { attrOpen.value = null }

function onDummyAttrChange(newVal) {
  dummyTrip.value.attributes = newVal
  closeAttrDropdown()
  onDummyInput({ fieldName: 'attributes' })
}

// Handlers for day-type / attribute changes on already-promoted real trips
function onTripDayTypeChange(trip, serviceId) {
  trip.day_type = serviceId
  closeDayTypeDropdown()
  if (trip.saved) {
    updateTripOnBackend(trip)
  } else {
    maybeSaveTrip(trip)
  }
}

function onTripAttrChange(trip, newAttrs) {
  trip.attributes = newAttrs
  if (trip.saved) {
    updateTripOnBackend(trip)
  } else {
    maybeSaveTrip(trip)
  }
}

// ---- Drag & drop reorder ----
const dragSrcIdx  = ref(null)
const dragOverIdx = ref(null)
const saving      = ref(false)

function onDragStart(idx, evt) {
  dragSrcIdx.value = idx
  evt.dataTransfer.effectAllowed = 'move'
}

function onDragOver(idx, evt) {
  evt.preventDefault()
  evt.dataTransfer.dropEffect = 'move'
  dragOverIdx.value = idx
}

function onDrop(idx, evt) {
  evt.preventDefault()
  const src = dragSrcIdx.value
  if (src === null || src === idx) {
    dragSrcIdx.value  = null
    dragOverIdx.value = null
    return
  }
  const entries = [...bandEntries.value]
  const [moved] = entries.splice(src, 1)
  entries.splice(idx, 0, moved)
  bandEntries.value = entries
  dragSrcIdx.value  = null
  dragOverIdx.value = null
  saveBandOrder()
}

function onDragEnd() {
  dragSrcIdx.value  = null
  dragOverIdx.value = null
}

/**
 * Two-phase save to avoid UNIQUE(sort_order) conflicts during reorder:
 *   Phase 1 — set all to safe temp positions (100000 + i)
 *   Phase 2 — set final positions (0, 1, 2, …)
 */
async function saveBandOrder() {
  if (saving.value) return
  saving.value = true
  const entries = [...bandEntries.value]
  const TEMP = 100000
  try {
    for (let i = 0; i < entries.length; i++) {
      await api.schedule.band.reorder(
        props.versionId, props.routeId, props.direction,
        entries[i].id, { sort_order: TEMP + i },
      )
      entries[i] = { ...entries[i], sort_order: TEMP + i }
    }
    for (let i = 0; i < entries.length; i++) {
      await api.schedule.band.reorder(
        props.versionId, props.routeId, props.direction,
        entries[i].id, { sort_order: i },
      )
      entries[i] = { ...entries[i], sort_order: i }
    }
    bandEntries.value = entries
  } catch {
    toast.show(t('schedule.error_reorder'), 'error')
    await loadBand()
  } finally {
    saving.value = false
  }
}

// ---- Add stop ----
const searchQuery    = ref('')
const dropdownOpen   = ref(false)
const adding         = ref(false)
const searchInputRef = ref(null)

const filteredPlatforms = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return []
  return props.platforms.filter(p => {
    const name = (p.stop_name ?? '').toLowerCase()
    const code = (p.platform_code ?? '').toLowerCase()
    return name.includes(q) || code.includes(q) || p.stop_id.toLowerCase().includes(q)
  }).slice(0, 20)
})

function onSearchInput() {
  dropdownOpen.value = searchQuery.value.trim().length > 0
}

function onSearchBlur() {
  // Delay so click on dropdown item fires first
  setTimeout(() => { dropdownOpen.value = false }, 150)
}

async function selectPlatform(platform) {
  dropdownOpen.value = false
  searchQuery.value  = ''
  if (!canMakeRequest('write')) {
    toast.show(t('common.permission_denied'), 'error')
    return
  }
  if (!props.versionId || !props.routeId) return
  adding.value = true
  try {
    const entry = await api.schedule.band.add(
      props.versionId,
      props.routeId,
      props.direction,
      { stop_id: platform.stop_id },
    )
    bandEntries.value.push(entry)
  } catch {
    toast.show(t('schedule.error_add'), 'error')
  } finally {
    adding.value = false
    await nextTick()
    searchInputRef.value?.focus()
  }
}

// ---- Delete stop ----
const confirmOpen   = ref(false)
const pendingDelete = ref(null)

function requestDelete(entry) {
  pendingDelete.value = entry
  confirmOpen.value   = true
}

async function handleConfirmDelete() {
  const entry = pendingDelete.value
  pendingDelete.value = null
  if (!entry) return
  if (!canMakeRequest('delete')) {
    toast.show(t('common.permission_denied'), 'error')
    return
  }
  try {
    await api.schedule.band.remove(props.versionId, props.routeId, props.direction, entry.id)
    bandEntries.value = bandEntries.value.filter(e => e.id !== entry.id)
  } catch {
    toast.show(t('schedule.error_delete'), 'error')
    await loadBand()
  }
}

// ---- Time input: GTFS HH:MM, hours may exceed 23 ----
function onTimeInput(event, times, key) {
  let val = event.target.value.replace(/[^\d:]/g, '')
  // Auto-insert colon after exactly 2 leading digits when typing forward
  if (
    val.length >= 2 &&
    !val.includes(':') &&
    event.inputType !== 'deleteContentBackward' &&
    event.inputType !== 'deleteContentForward'
  ) {
    val = val.slice(0, 2) + ':' + val.slice(2)
  }
  // Cap minutes part at 2 digits once colon is present
  const colonIdx = val.indexOf(':')
  if (colonIdx !== -1) {
    const mm = val.slice(colonIdx + 1).replace(/\D/g, '').slice(0, 2)
    val = val.slice(0, colonIdx + 1) + mm
  }
  times[key] = val
  event.target.value = val
}

function onTimeBlur(event, times, key, trip = null) {
  const val = (times[key] ?? '').trim()
  if (!val) {
    // Cleared — reset all stop-time attributes in the frontend state
    if (trip) {
      delete trip.stopTimes[key]
    }
    // Delete stop time from backend if the trip is already saved
    if (trip?.saved) {
      deleteStopTimeFromBackend(trip, key)
    }
    return
  }
  if (!/^\d+:\d{2}$/.test(val)) {
    times[key] = ''
    event.target.value = ''
    return
  }
  const mm = parseInt(val.split(':')[1], 10)
  if (mm > 59) {
    times[key] = ''
    event.target.value = ''
    return
  }
  // Valid departure time — persist
  if (trip) {
    if (trip.saved) {
      upsertStopTimeToBackend(trip, key)
    } else {
      maybeSaveTrip(trip)
    }
  }
}

// ---- Enter key navigation in time matrix ----
function onTimeEnter(tripId, entryId) {
  const entries = bandEntries.value
  const curIdx = entries.findIndex(e => e.id === entryId)
  if (curIdx < 0 || curIdx + 1 >= entries.length) return
  const nextEntry = entries[curIdx + 1]
  const nextInput = tableRef.value?.querySelector(
    `[data-trip="${tripId}"][data-entry="${nextEntry.id}"]`
  )
  if (!nextInput) return
  nextInput.focus()
  nextInput.select()
}

// ---- Stop-time context menu ----
// Track open cell by tripId + entryId separately (enables single portal instance + template ref)
const contextMenuTripId  = ref(null)
const contextMenuEntryId = ref(null)
const contextMenuPos     = ref({ top: 0, left: 0 })
const contextMenuRef     = ref(null)

function getStopTime(trip, entryId) {
  if (!trip.stopTimes[entryId]) {
    trip.stopTimes[entryId] = { arrival_time: null, pickup_type: null, drop_off_type: null, stop_headsign_id: null }
  }
  return trip.stopTimes[entryId]
}

function getActiveTrip() {
  return trips.value.find(t => t.id === contextMenuTripId.value) ?? null
}

async function openContextMenu(tripId, entryId, event) {
  event.preventDefault()
  const cell = event.currentTarget
  const scrollEl = cell.closest('.schedule-table-scroll')
  const cellRect   = cell.getBoundingClientRect()
  const scrollRect = scrollEl ? scrollEl.getBoundingClientRect() : { top: 0, left: 0 }
  const scrollTop  = scrollEl?.scrollTop  ?? 0
  const scrollLeft = scrollEl?.scrollLeft ?? 0
  contextMenuTripId.value  = tripId
  contextMenuEntryId.value = entryId
  // Default: below the cell, left-aligned with the cell
  contextMenuPos.value = {
    top:  cellRect.bottom - scrollRect.top  + scrollTop,
    left: cellRect.left   - scrollRect.left + scrollLeft,
  }

  await nextTick()

  // Smart flip: measure popup and flip if it overflows the viewport
  const menuEl = contextMenuRef.value?.$el
  if (menuEl) {
    const menuRect = menuEl.getBoundingClientRect()
    const margin   = 8
    let { top, left } = contextMenuPos.value

    // Flip left if right edge overflows viewport
    if (menuRect.right > window.innerWidth - margin) {
      left = cellRect.right - scrollRect.left + scrollLeft - menuRect.width
    }
    // Flip up if bottom edge overflows viewport
    if (menuRect.bottom > window.innerHeight - margin) {
      top = cellRect.top - scrollRect.top + scrollTop - menuRect.height
    }
    // Clamp to avoid scrolling out of the container's visible area
    top  = Math.max(scrollTop, top)
    left = Math.max(scrollLeft, left)

    contextMenuPos.value = { top, left }
  }

  contextMenuRef.value?.$el?.querySelector('.stcm__arrival-input')?.focus()
}

function closeContextMenu() {
  contextMenuTripId.value  = null
  contextMenuEntryId.value = null
}

// ---- Trip column context menu ----
const tripCtxTripId = ref(null)
const tripCtxPos    = ref({ top: 0, left: 0 })

function openTripCtx(trip, event) {
  event.preventDefault()
  const th = event.currentTarget
  const scrollEl = th.closest('.schedule-table-scroll')
  const thRect     = th.getBoundingClientRect()
  const scrollRect = scrollEl ? scrollEl.getBoundingClientRect() : { top: 0, left: 0 }
  tripCtxTripId.value = trip.id
  tripCtxPos.value = {
    top:  thRect.bottom - scrollRect.top  + (scrollEl?.scrollTop  ?? 0),
    left: thRect.left   - scrollRect.left + (scrollEl?.scrollLeft ?? 0),
  }
  nextTick(() => {
    document.querySelector('.st-trip-ctx')?.focus()
  })
}

function closeTripCtx() {
  tripCtxTripId.value = null
}

function selectBySchedulePattern(trip) {
  const active = trip ?? trips.value.find(t => t.id === tripCtxTripId.value) ?? null
  if (!active?.schedule_pattern_hash) {
    closeTripCtx()
    return
  }
  const hash = active.schedule_pattern_hash
  for (const t of trips.value) {
    if (t.schedule_pattern_hash === hash) {
      t.selected = true
    }
  }
  closeTripCtx()
}

// ---- Selection dropdown menu functions ----
function selectAllTrips() {
  for (const trip of visibleTrips.value) {
    trip.selected = true
  }
}

function selectTripsWithSamePath() {
  const selectedTrips = visibleTrips.value.filter(t => t.selected)
  if (selectedTrips.length !== 1) return
  const active = selectedTrips[0]
  if (!active?.schedule_pattern_hash) return
  const hash = active.schedule_pattern_hash
  for (const t of visibleTrips.value) {
    if (t.schedule_pattern_hash === hash) {
      t.selected = true
    }
  }
}

function deselectAllTrips() {
  for (const trip of trips.value) {
    trip.selected = false
  }
}

function updateStopTime(trip, entryId, val) {
  trip.stopTimes[entryId] = { ...getStopTime(trip, entryId), ...val }
  if (trip.saved) {
    upsertStopTimeToBackend(trip, entryId)
  }
}

function onTripShortNameBlur(trip) {
  if (trip.saved) {
    updateTripOnBackend(trip)
  } else {
    maybeSaveTrip(trip)
  }
}

// Indicator helpers
function hasArrivalDiff(trip, entryId) {
  const st = trip.stopTimes?.[entryId]
  if (!st?.arrival_time) return false
  return st.arrival_time !== trip.times[entryId]
}

function hasPickup(trip, entryId) {
  return (trip.stopTimes?.[entryId]?.pickup_type ?? null) !== null
}

function hasDropOff(trip, entryId) {
  return (trip.stopTimes?.[entryId]?.drop_off_type ?? null) !== null
}

function pickupIsNone(trip, entryId) {
  return trip.stopTimes?.[entryId]?.pickup_type === 1
}

function dropOffIsNone(trip, entryId) {
  return trip.stopTimes?.[entryId]?.drop_off_type === 1
}

// ---- Trip validation ----
// A trip is valid when it has a day type AND at least 2 filled departure times.
function isTripValid(trip) {
  const hasDayType = (trip.day_type ?? '').trim() !== ''
  const timeCount  = Object.values(trip.times).filter(v => (v ?? '').trim() !== '').length
  return hasDayType && timeCount >= 2
}

// Returns a warning title string when a valid trip is missing required data, empty string otherwise.
function tripWarningTitle(trip) {
  if (!trip.route_path?.trim()) return t('schedule.trip_missing_route_path_warning')
  if (trip.route_path !== trip.geo_pattern_hash) return t('schedule.trip_route_path_mismatch_warning')
  if (!trip.headsign_id) return t('schedule.trip_missing_headsign_warning')
  return ''
}

// ---- Expose public methods for parent components ----
// Trips visible after applying the day-type filter (empty filterServiceIds = show all)
const visibleTrips = computed(() => {
  if (!props.filterServiceIds.length) return trips.value
  return trips.value.filter(t => props.filterServiceIds.includes(t.day_type))
})

// All unique service_ids present in the currently loaded trips
const availableServiceIds = computed(() => [
  ...new Set(trips.value.map(t => t.day_type).filter(Boolean)),
])

defineExpose({
  trips,
  visibleTrips,
  availableServiceIds,
  loadTrips,
  selectAllTrips,
  selectTripsWithSamePath,
  deselectAllTrips,
})
</script>

<template>
  <div class="schedule-table-wrap">

    <!-- Loading spinner -->
    <div v-if="loading" class="schedule-table__loading">
      <md-circular-progress indeterminate />
    </div>

    <template v-else>
      <div class="schedule-table-scroll">
        <table ref="tableRef" class="schedule-table" aria-label="Linienband">
          <colgroup>
            <col class="col-stop" />
            <col class="col-platform" />
          </colgroup>

          <thead>
            <!-- Row 1: Actions — spacer (colspan 2) + per-trip action buttons -->
            <tr class="schedule-table__header-row">
              <th colspan="2" class="schedule-table__th schedule-table__th--row-label" />
              <th
                v-for="trip in visibleTrips"
                :key="trip.id + '-a'"
                class="schedule-table__th schedule-table__trip-th"
                :class="{ 'schedule-table__trip-th--selected': trip.selected }"
                @contextmenu.prevent="openTripCtx(trip, $event)"
              >
                <div class="schedule-table__trip-actions">
                  <md-icon
                    v-if="!isTripValid(trip)"
                    class="schedule-table__trip-warning"
                    :title="t('schedule.trip_invalid_warning')"
                  >warning</md-icon>
                  <md-icon
                    v-else-if="tripWarningTitle(trip)"
                    class="schedule-table__trip-warning-route"
                    :title="tripWarningTitle(trip)"
                  >warning</md-icon>
                  <label class="schedule-table__trip-select-label" :title="t('schedule.select_trip')" @click.stop>
                    <input
                      type="checkbox"
                      class="schedule-table__trip-select"
                      :checked="trip.selected"
                      @click.stop
                      @change="trip.selected = $event.target.checked"
                    />
                  </label>
                </div>
              </th>
              <template v-if="bandEntries.length > 0">
                <th class="schedule-table__th schedule-table__trip-th schedule-table__trip-th--dummy" />
              </template>
              <th class="schedule-table__filler-cell schedule-table__th" />
            </tr>

            <!-- Row 2: Short name -->
            <tr class="schedule-table__header-row">
              <th colspan="2" class="schedule-table__th schedule-table__th--row-label" scope="row">{{ t('schedule.trip_short_name') }}</th>
              <td
                v-for="trip in visibleTrips"
                :key="trip.id + '-n'"
                class="schedule-table__trip-input-cell"
              >
                <input
                  class="schedule-table__trip-input"
                  :data-trip="trip.id"
                  data-field="short_name"
                  v-model="trip.short_name"
                  :disabled="readonlyMode"
                  @blur="onTripShortNameBlur(trip)"
                />
              </td>
              <template v-if="props.canWrite && bandEntries.length > 0">
                <td class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dummy">
                  <input
                    class="schedule-table__trip-input schedule-table__trip-input--ghost"
                    v-model="dummyTrip.short_name"
                    :placeholder="t('schedule.trip_placeholder')"
                    @input="e => onDummyInput({ fieldName: 'short_name' })"
                  />
                </td>
              </template>
              <td class="schedule-table__filler-cell" />
            </tr>

            <!-- Row 3: Day type -->
            <tr class="schedule-table__header-row">
              <th colspan="2" class="schedule-table__th schedule-table__th--row-label" scope="row">{{ t('schedule.trip_day_type') }}</th>
              <td
                v-for="trip in visibleTrips"
                :key="trip.id + '-d'"
                class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dt"
              >
                <div :data-dt-trip="trip.id">
                  <ScheduleTableFlyout
                    :model-value="trip.day_type"
                    :items="dayTypeItems"
                    :placeholder="'—'"
                    :search-placeholder="t('schedule.day_type_search')"
                    :open="dayTypeOpen === trip.id"
                    :disabled="readonlyMode"
                    :readonly="readonlyMode"
                    :data-trip="trip.id"
                    data-field="day_type"
                    @update:model-value="(v) => onTripDayTypeChange(trip, v)"
                    @open="openDayTypeDropdown(trip.id)"
                    @close="closeDayTypeDropdown"
                  >
                    <template #empty>{{ t('schedule.add_stop_no_results') }}</template>
                  </ScheduleTableFlyout>
                </div>
              </td>
              <template v-if="props.canWrite && bandEntries.length > 0">
                <td class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dummy schedule-table__trip-input-cell--dt">
                  <div data-dt-trip="dummy">
                    <ScheduleTableFlyout
                      :model-value="dummyTrip.day_type"
                      :items="dayTypeItems"
                      :placeholder="t('schedule.trip_placeholder')"
                      :search-placeholder="t('schedule.day_type_search')"
                      :open="dayTypeOpen === 'dummy'"
                      :is-ghost="true"
                      @update:model-value="selectDummyDayType"
                      @open="openDayTypeDropdown('dummy')"
                      @close="closeDayTypeDropdown"
                    >
                      <template #empty>{{ t('schedule.add_stop_no_results') }}</template>
                    </ScheduleTableFlyout>
                  </div>
                </td>
              </template>
              <td class="schedule-table__filler-cell" />
            </tr>

            <!-- Row 4: Route path -->
            <tr class="schedule-table__header-row">
              <th colspan="2" class="schedule-table__th schedule-table__th--row-label" scope="row">{{ t('schedule.trip_route_path') }}</th>
              <td
                v-for="trip in visibleTrips"
                :key="trip.id + '-r'"
                class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dt"
              >
                <div :data-rp-trip="trip.id">
                  <ScheduleTableFlyout
                    :model-value="trip.route_path"
                    :value-label="trip.route_path ? (shapeLabelById[trip.route_path] || trip.route_path) : ''"
                    :items="routePathItemsForTrip(trip)"
                    placeholder="—"
                    :search-placeholder="t('schedule.route_path_search')"
                    :open="routePathOpen === trip.id"
                    :disabled="readonlyMode"
                    :readonly="readonlyMode"
                    @update:model-value="(v) => onTripRoutePathChange(trip, v)"
                    @open="openRoutePathDropdown(trip.id)"
                    @close="closeRoutePathDropdown"
                    @search-change="queueRoutePathSearch"
                  >
                    <template #empty>{{ t('schedule.add_stop_no_results') }}</template>
                    <template v-if="props.canWrite" #footer>
                      <button class="schedule-table__map-btn schedule-table__map-btn--danger" type="button" @mousedown.prevent @click.stop="clearTripRoutePath(trip)">
                        <md-icon>delete</md-icon>
                        {{ t('schedule.route_path_delete') }}
                      </button>
                    </template>
                  </ScheduleTableFlyout>
                </div>
              </td>
              <template v-if="props.canWrite && bandEntries.length > 0">
                <td class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dummy schedule-table__trip-input-cell--dt">
                  <div data-rp-trip="dummy">
                    <ScheduleTableFlyout
                      :model-value="dummyTrip.route_path"
                      :value-label="dummyTrip.route_path ? (shapeLabelById[dummyTrip.route_path] || dummyTrip.route_path) : ''"
                      :items="routePathItemsForTrip(dummyTrip)"
                      :placeholder="t('schedule.trip_placeholder')"
                      :search-placeholder="t('schedule.route_path_search')"
                      :open="routePathOpen === 'dummy'"
                      :is-ghost="true"
                      @update:model-value="selectDummyRoutePath"
                      @open="openRoutePathDropdown('dummy')"
                      @close="closeRoutePathDropdown"
                      @search-change="queueRoutePathSearch"
                    >
                      <template #empty>{{ t('schedule.add_stop_no_results') }}</template>
                      <template #footer>
                        <button class="schedule-table__map-btn schedule-table__map-btn--danger" type="button" @mousedown.prevent @click.stop="clearDummyRoutePath">
                          <md-icon>delete</md-icon>
                          {{ t('schedule.route_path_delete') }}
                        </button>
                      </template>
                    </ScheduleTableFlyout>
                  </div>
                </td>
              </template>
              <td class="schedule-table__filler-cell" />
            </tr>

            <!-- Row 5: Headsign -->
            <tr class="schedule-table__header-row">
              <th colspan="2" class="schedule-table__th schedule-table__th--row-label" scope="row">{{ t('schedule.trip_headsign') }}</th>
              <td
                v-for="trip in visibleTrips"
                :key="trip.id + '-hs'"
                class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dt"
              >
                <div :data-hs-trip="trip.id">
                  <ScheduleTableFlyout
                    :model-value="trip.headsign_id ?? ''"
                    :value-label="trip.headsign_id ? (headsignLabelById[trip.headsign_id] || trip.headsign_id) : ''"
                    :items="headsignItems"
                    placeholder="—"
                    :search-placeholder="t('schedule.headsign_search')"
                    :open="headsignOpen === trip.id"
                    :disabled="readonlyMode"
                    :readonly="readonlyMode"
                    @update:model-value="(v) => onTripHeadsignChange(trip, v)"
                    @open="openHeadsignDropdown(trip.id)"
                    @close="closeHeadsignDropdown"
                  >
                    <template #empty>{{ t('schedule.add_stop_no_results') }}</template>
                    <template v-if="props.canWrite" #footer>
                      <button class="schedule-table__map-btn schedule-table__map-btn--danger" type="button" @mousedown.prevent @click.stop="clearTripHeadsign(trip)">
                        <md-icon>delete</md-icon>
                        {{ t('schedule.headsign_delete') }}
                      </button>
                    </template>
                  </ScheduleTableFlyout>
                </div>
              </td>
              <template v-if="props.canWrite && bandEntries.length > 0">
                <td class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dummy schedule-table__trip-input-cell--dt">
                  <div data-hs-trip="dummy">
                    <ScheduleTableFlyout
                      :model-value="dummyTrip.headsign_id ?? ''"
                      :value-label="dummyTrip.headsign_id ? (headsignLabelById[dummyTrip.headsign_id] || dummyTrip.headsign_id) : ''"
                      :items="headsignItems"
                      :placeholder="t('schedule.trip_placeholder')"
                      :search-placeholder="t('schedule.headsign_search')"
                      :open="headsignOpen === 'dummy'"
                      :is-ghost="true"
                      @update:model-value="selectDummyHeadsign"
                      @open="openHeadsignDropdown('dummy')"
                      @close="closeHeadsignDropdown"
                    >
                      <template #empty>{{ t('schedule.add_stop_no_results') }}</template>
                      <template #footer>
                        <button class="schedule-table__map-btn schedule-table__map-btn--danger" type="button" @mousedown.prevent @click.stop="clearDummyHeadsign">
                          <md-icon>delete</md-icon>
                          {{ t('schedule.headsign_delete') }}
                        </button>
                      </template>
                    </ScheduleTableFlyout>
                  </div>
                </td>
              </template>
              <td class="schedule-table__filler-cell" />
            </tr>

            <!-- Row 6: Attributes -->
            <tr class="schedule-table__header-row">
              <th colspan="2" class="schedule-table__th schedule-table__th--row-label" scope="row">{{ t('schedule.trip_attributes') }}</th>
              <td
                v-for="trip in visibleTrips"
                :key="trip.id + '-at'"
                class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dt"
              >
                <ScheduleTableAttrFlyout
                  :model-value="trip.attributes"
                  :open="attrOpen === trip.id"
                  :disabled="readonlyMode"
                  :readonly="readonlyMode"
                  @update:model-value="(v) => onTripAttrChange(trip, v)"
                  @open="openAttrDropdown(trip.id)"
                  @close="closeAttrDropdown"
                />
              </td>
              <template v-if="props.canWrite && bandEntries.length > 0">
                <td class="schedule-table__trip-input-cell schedule-table__trip-input-cell--dummy schedule-table__trip-input-cell--dt">
                  <ScheduleTableAttrFlyout
                    :model-value="dummyTrip.attributes"
                    :open="attrOpen === 'dummy'"
                    :is-ghost="true"
                    @update:model-value="onDummyAttrChange"
                    @open="openAttrDropdown('dummy')"
                    @close="closeAttrDropdown"
                  />
                </td>
              </template>
              <td class="schedule-table__filler-cell" />
            </tr>

            <!-- Row 6: Column headers (Haltestelle / Steig) — bottommost header row -->
            <tr class="schedule-table__header-row schedule-table__header-row--last">
              <th class="schedule-table__th schedule-table__th--stop" scope="col">
                {{ t('schedule.column_stop') }}
              </th>
              <th class="schedule-table__th schedule-table__th--platform" scope="col">
                {{ t('schedule.column_platform') }}
              </th>
              <td v-for="trip in visibleTrips" :key="trip.id + '-col'" class="schedule-table__trip-col-spacer" />
              <template v-if="bandEntries.length > 0">
                <td class="schedule-table__trip-col-spacer schedule-table__trip-col-spacer--dummy" />
              </template>
              <td class="schedule-table__filler-cell schedule-table__th" />
            </tr>
          </thead>

          <tbody>
            <!-- Empty state — always spanning all columns when band has no stops -->
            <tr v-if="bandEntries.length === 0" class="schedule-table__empty-row">
              <td class="schedule-table__empty-cell" colspan="99">
                <md-icon class="schedule-table__empty-icon">info</md-icon>
                <span>{{ t('schedule.band_empty') }}</span>
              </td>
            </tr>

            <!-- Band entries -->
            <tr
              v-for="(entry, idx) in bandEntries"
              :key="entry.id"
              class="schedule-table__row"
              :class="{
                'is-dragging':  dragSrcIdx === idx,
                'is-drag-over': dragOverIdx === idx && dragSrcIdx !== idx,
              }"
              :draggable="canWrite ? 'true' : 'false'"
              @dragstart="canWrite && contextMenuTripId === null && onDragStart(idx, $event)"
              @dragover="canWrite && onDragOver(idx, $event)"
              @drop="canWrite && onDrop(idx, $event)"
              @dragend="onDragEnd"
            >
              <!-- Stop cell (sticky row header) -->
              <td class="schedule-table__stop-cell">
                <div class="schedule-table__stop-inner">
                  <span
                    v-if="canWrite"
                    class="schedule-table__drag-handle"
                    title="Verschieben"
                  >
                    <md-icon>drag_indicator</md-icon>
                  </span>
                  <button
                    v-if="canDelete"
                    class="schedule-table__delete-btn"
                    :title="t('common.delete')"
                    @click="requestDelete(entry)"
                  >
                    <md-icon>remove_circle_outline</md-icon>
                  </button>
                  <span class="schedule-table__stop-name">{{ stopName(entry.stop_id) }}</span>
                </div>
              </td>
              <!-- Platform cell -->
              <td class="schedule-table__platform-cell">
                {{ platformCode(entry.stop_id) ?? '' }}
              </td>
              <!-- Time cells per trip -->
              <td
                v-for="trip in visibleTrips"
                :key="trip.id"
                class="schedule-table__time-cell"
                :class="{
                  'schedule-table__time-cell--context': contextMenuTripId === trip.id && contextMenuEntryId === entry.id,
                  'schedule-table__time-cell--selected': trip.selected,
                }"
                @contextmenu="openContextMenu(trip.id, entry.id, $event)"
              >
                <!-- Arrival diff indicator (top-left triangle) -->
                <span
                  v-if="hasArrivalDiff(trip, entry.id)"
                  class="schedule-table__arr-badge"
                  :title="trip.stopTimes[entry.id].arrival_time"
                />

                <input
                  class="schedule-table__time-input"
                  :data-trip="trip.id"
                  :data-entry="entry.id"
                  :value="trip.times[entry.id] ?? ''"
                  :disabled="readonlyMode"
                  @input="onTimeInput($event, trip.times, entry.id)"
                  @blur="onTimeBlur($event, trip.times, entry.id, trip)"
                  @keydown.enter.prevent="onTimeEnter(trip.id, entry.id)"
                  type="text"
                  inputmode="numeric"
                  autocomplete="off"
                  maxlength="6"
                />

                <!-- Pickup / drop-off arrow indicators (right side) -->
                <span
                  v-if="hasPickup(trip, entry.id) || hasDropOff(trip, entry.id)"
                  class="schedule-table__stop-indicators"
                >
                  <md-icon
                    v-if="hasPickup(trip, entry.id)"
                    class="schedule-table__stop-ind"
                    :class="{ 'schedule-table__stop-ind--none': pickupIsNone(trip, entry.id) }"
                  >arrow_upward</md-icon>
                  <md-icon
                    v-if="hasDropOff(trip, entry.id)"
                    class="schedule-table__stop-ind"
                    :class="{ 'schedule-table__stop-ind--none': dropOffIsNone(trip, entry.id) }"
                  >arrow_downward</md-icon>
                </span>

                <!-- Stop-time headsign indicator (purely decorative, no click) -->
                <span
                  v-if="hasStopHeadsign(trip, entry.id)"
                  class="schedule-table__hs-ind"
                  :title="headsignLabelById[trip.stopTimes[entry.id].stop_headsign_id] || '—'"
                >
                  <md-icon>directions_bus</md-icon>
                </span>
              </td>
              <!-- Dummy time cell -->
              <template v-if="props.canWrite && bandEntries.length > 0">
                <td class="schedule-table__time-cell schedule-table__time-cell--dummy">
                  <input
                    class="schedule-table__time-input schedule-table__time-input--ghost"
                    :value="dummyTrip.times[entry.id] ?? ''"
                    @input="e => { onTimeInput(e, dummyTrip.times, entry.id); onDummyInput({ entryId: entry.id }) }"
                    @blur="onTimeBlur($event, dummyTrip.times, entry.id)"
                    type="text"
                    inputmode="numeric"
                    autocomplete="off"
                    maxlength="6"
                  />
                </td>
              </template>
              <td class="schedule-table__filler-cell" />
            </tr>

            <!-- Add stop row (sticky bottom) -->
            <tr v-if="canWrite" class="schedule-table__add-row schedule-table__add-row--sticky">
              <td class="schedule-table__add-cell" colspan="2">
                <div class="schedule-table__add-wrap">
                  <span class="schedule-table__add-icon">
                    <md-icon>add_circle_outline</md-icon>
                  </span>
                  <div class="schedule-table__search-wrap">
                    <input
                      ref="searchInputRef"
                      v-model="searchQuery"
                      type="text"
                      class="schedule-table__search-input"
                      :placeholder="t('schedule.add_stop_placeholder')"
                      :disabled="adding"
                      autocomplete="off"
                      @input="onSearchInput"
                      @blur="onSearchBlur"
                    />
                    <ul
                      v-if="dropdownOpen"
                      class="schedule-table__dropdown"
                      role="listbox"
                    >
                      <li
                        v-if="filteredPlatforms.length === 0"
                        class="schedule-table__dropdown-empty"
                      >
                        {{ t('schedule.add_stop_no_results') }}
                      </li>
                      <li
                        v-for="platform in filteredPlatforms"
                        :key="platform.stop_id"
                        class="schedule-table__dropdown-item"
                        role="option"
                        @mousedown.prevent="selectPlatform(platform)"
                      >
                        <span class="schedule-table__dropdown-name">{{ platform.stop_name }}</span>
                        <span v-if="platform.platform_code" class="schedule-table__dropdown-code">
                          {{ platform.platform_code }}
                        </span>
                      </li>
                    </ul>
                  </div>
                  <md-circular-progress v-if="adding || saving" indeterminate class="schedule-table__spinner" />
                </div>
              </td>
              <td class="schedule-table__filler-cell" />
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Context menu portal — single instance, positioned relative to .schedule-table-scroll -->
      <ScheduleTimeContextMenu
        v-if="contextMenuTripId !== null"
        ref="contextMenuRef"
        :model-value="getStopTime(getActiveTrip(), contextMenuEntryId)"
        :departure-time="getActiveTrip()?.times[contextMenuEntryId] ?? ''"
        :open="true"
        :disabled="readonlyMode"
        :headsigns="headsigns"
        :style="{ position: 'absolute', top: contextMenuPos.top + 'px', left: contextMenuPos.left + 'px' }"
        @update:model-value="v => updateStopTime(getActiveTrip(), contextMenuEntryId, v)"
        @close="closeContextMenu"
      />

      <!-- (stop-time headsign selection is now inside the ScheduleTimeContextMenu popup) -->
    </template>

    <!-- Delete confirmation -->
    <ConfirmDialog
      v-model="confirmOpen"
      :title="t('schedule.delete_confirm_title')"
      :message="pendingDelete ? t('schedule.delete_confirm_message', { name: stopLabel(pendingDelete.stop_id) }) : ''"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      :danger="true"
      @confirm="handleConfirmDelete"
    />

  </div>
</template>

<style scoped>
/* ---- Layout variables ---- */
.schedule-table-wrap {
  --col-stop-w:     250px;
  --col-platform-w: 64px;
}

.col-stop     { width: var(--col-stop-w); }
.col-platform { width: var(--col-platform-w); }

/* ---- Container ---- */
.schedule-table-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.schedule-table__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--md-sys-color-primary, #1f69e0);
}

/* ---- Scrollable area ---- */
.schedule-table-scroll {
  flex: 1;
  overflow: auto;
  position: relative;  /* anchor for context menu portal */
  isolation: isolate;  /* own stacking context — prevents sticky headers from overlapping modals */
}

/* ---- Table ---- */
.schedule-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-1, 0.875rem);
  table-layout: fixed;
}

/* ---- Header ---- */
.schedule-table__th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--md-sys-color-surface-container, #f4f4f4);
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-weight: 600;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  white-space: nowrap;
}

.schedule-table__th--stop {
  z-index: 3;
  left: 0;
}

.schedule-table__th--platform {
  left: var(--col-stop-w);
  z-index: 3;
  white-space: nowrap;
}

/* Row-label th (used in trip header rows 1–5, colspan=2) */
.schedule-table__th--row-label {
  left: 0;
  font-style: normal;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  white-space: nowrap;
}

/* ---- Rows ---- */
.schedule-table__row {
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  transition: background 0.1s;
}

.schedule-table__row:hover {
  background: var(--md-sys-color-surface-container-low, #f9f9f9);
}

.schedule-table__row.is-dragging {
  opacity: 0.4;
}

.schedule-table__row.is-drag-over {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 10%, transparent);
  outline: 2px solid var(--md-sys-color-primary, #1f69e0);
  outline-offset: -2px;
}

/* ---- Stop cell (sticky row header) ---- */
.schedule-table__stop-cell {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--md-sys-color-surface, #fff);
  padding: 0;
  height: 2.5rem;
  overflow: hidden;
  border-right: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

.schedule-table__stop-inner {
  display: flex;
  align-items: center;
  gap: 0.1rem;
  height: 100%;
  padding: 0 0.5rem 0 0;
  overflow: hidden;
}

.schedule-table__row:hover .schedule-table__stop-cell,
.schedule-table__row:hover .schedule-table__platform-cell {
  background: var(--md-sys-color-surface-container-low, #f9f9f9);
}

.schedule-table__row:hover .schedule-table__stop-inner {
  background: var(--md-sys-color-surface-container-low, #f9f9f9);
}

.schedule-table__row.is-drag-over .schedule-table__stop-cell,
.schedule-table__row.is-drag-over .schedule-table__platform-cell {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 10%, transparent);
}

/* ---- Drag handle ---- */
.schedule-table__drag-handle {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  cursor: grab;
  color: var(--md-sys-color-outline, #aaa);
  padding: 0 2px;
  transition: color 0.15s;
}

.schedule-table__drag-handle:active {
  cursor: grabbing;
}

.schedule-table__drag-handle md-icon {
  --md-icon-size: 1.1rem;
  font-size: 1.1rem;
}

.schedule-table__drag-handle:hover {
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}

/* ---- Delete button ---- */
.schedule-table__delete-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  border-radius: 50%;
  color: var(--md-sys-color-error, #b00020);
  opacity: 0.45;
  transition: opacity 0.15s, background 0.15s;
  line-height: 1;
}

.schedule-table__delete-btn:hover {
  opacity: 1;
  background: color-mix(in srgb, var(--md-sys-color-error, #b00020) 12%, transparent);
}

.schedule-table__delete-btn md-icon {
  --md-icon-size: 1.1rem;
  font-size: 1.1rem;
}

/* ---- Stop name ---- */
.schedule-table__stop-name {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  color: var(--md-sys-color-on-surface, #222);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-left: 0.25rem;
}

/* ---- Platform cell ---- */
.schedule-table__platform-cell {
  position: sticky;
  left: var(--col-stop-w);
  z-index: 1;
  background: var(--md-sys-color-surface, #fff);
  padding: 0 0.75rem;
  height: 2.5rem;
  vertical-align: middle;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  white-space: nowrap;
  border-right: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

/* ---- Empty state ---- */
.schedule-table__empty-row td {
  border-bottom: none;
}

.schedule-table__empty-cell {
  padding: 3rem 1rem;
  text-align: center;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}

.schedule-table__empty-icon {
  --md-icon-size: 2rem;
  font-size: 2rem;
  color: var(--md-sys-color-outline, #aaa);
  display: block;
  margin: 0 auto 0.5rem;
}

/* ---- Add row (sticky bottom) ---- */
.schedule-table__add-row {
  background: var(--md-sys-color-surface, #fff);
}

.schedule-table__add-row--sticky {
  position: sticky;
  bottom: 0;
  z-index: 2;
  border-top: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

.schedule-table__add-cell {
  padding: 0.375rem 0.5rem;
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--md-sys-color-surface, #fff);
}

.schedule-table__add-wrap {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

/* Add icon — same size as drag/delete icons */
.schedule-table__add-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  color: var(--md-sys-color-primary, #1f69e0);
}

.schedule-table__add-icon md-icon {
  --md-icon-size: 1.1rem;
  font-size: 1.1rem;
}

/* ---- Search input + dropdown ---- */
.schedule-table__search-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
}

.schedule-table__search-input {
  width: 100%;
  padding: 0.325rem 0.625rem;
  border: 1px solid var(--md-sys-color-outline, #bbb);
  border-radius: 4px;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  background: var(--md-sys-color-surface, #fff);
  color: var(--md-sys-color-on-surface, #222);
  outline: none;
  transition: border-color 0.15s;
}

.schedule-table__search-input:focus {
  border-color: var(--md-sys-color-primary, #1f69e0);
}

.schedule-table__search-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.schedule-table__dropdown {
  position: absolute;
  top: calc(100% + 2px);
  left: 0;
  right: 0;
  z-index: 100;
  margin: 0;
  padding: 0.25rem 0;
  list-style: none;
  background: var(--md-sys-color-surface-container, #fff);
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 4px;
  box-shadow: var(--shadow-3, 0 4px 12px rgba(0,0,0,0.12));
  max-height: 220px;
  overflow-y: auto;
}

.schedule-table__dropdown-empty {
  padding: 0.5rem 0.875rem;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}

.schedule-table__dropdown-item {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.4rem 0.875rem;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  transition: background 0.1s;
}

.schedule-table__dropdown-item:hover {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
}

.schedule-table__dropdown-name {
  color: var(--md-sys-color-on-surface, #222);
}

.schedule-table__dropdown-code {
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}

.schedule-table__spinner {
  --md-circular-progress-size: 1.1rem;
  flex-shrink: 0;
}

/* Column spacer cells (last header row, trip columns — keeps column width consistent) */
.schedule-table__trip-col-spacer {
  width: 120px;
  max-width: 120px;
  min-width: 60px;
  border-right: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

.schedule-table__trip-col-spacer--dummy {
  background: color-mix(in srgb, var(--md-sys-color-surface-container, #f4f4f4) 60%, transparent);
  border-left: 2px dashed var(--md-sys-color-outline-variant, #e0e0e0);
  border-right: none;
}

/* ---- Trip header rows ---- */
/* Border lives on the th/td cells, not on the tr, to avoid doubling with sticky cell borders */
.schedule-table__header-row {
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

.schedule-table__header-row--last {
  border-bottom: 2px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

/* Trip column th (actions row, per-trip) */
.schedule-table__trip-th {
  z-index: 1;
  width: 120px;
  max-width: 120px;
  min-width: 60px;
  height: calc(2rem + 6px);
  vertical-align: middle;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.schedule-table__trip-th--dummy {
  width: 120px;
  max-width: 120px;
  background: color-mix(in srgb, var(--md-sys-color-surface-container, #f4f4f4) 60%, transparent);
  border-left: 2px dashed var(--md-sys-color-outline-variant, #e0e0e0);
}

/* Gap cell (platform column in trip header rows 2–5) — no longer used, kept for safety */
.schedule-table__trip-input-cell--gap {
  border-right: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

/* Trip input cells (header rows 2–5) */
.schedule-table__trip-input-cell {
  padding: 0.2rem 0.25rem;
  width: 120px;
  max-width: 120px;
  min-width: 60px;
  overflow: hidden;
  border-right: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

.schedule-table__trip-input-cell--dt {
  overflow: visible;
}

.schedule-table__trip-input-cell--dummy {
  background: color-mix(in srgb, var(--md-sys-color-surface-container, #f4f4f4) 60%, transparent);
  border-left: 2px dashed var(--md-sys-color-outline-variant, #e0e0e0);
  border-right: none;
}

/* Trip header inputs */
.schedule-table__trip-input {
  display: block;
  width: 100%;
  padding: 0 0.25rem;
  border: none;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  background: transparent;
  color: var(--md-sys-color-on-surface, #222);
  outline: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.schedule-table__trip-input--ghost::placeholder {
  color: var(--md-sys-color-outline, #bbb);
  font-style: italic;
}

/* ---- Trip column context menu ---- */
.st-trip-ctx {
  position: absolute;
  z-index: 300;
  min-width: 220px;
  background: var(--md-sys-color-surface, #fff);
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 6px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
  padding: 0.2rem 0;
  outline: none;
}

.st-trip-ctx__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.45rem 0.75rem;
  background: none;
  border: none;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-on-surface, #222);
  text-align: left;
  border-radius: 4px;
  transition: background 0.1s;
}

.st-trip-ctx__item:hover {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
}

.st-trip-ctx__icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

/* Trip action buttons row (actions row) */
.schedule-table__trip-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
}

.schedule-table__trip-warning {
  --md-icon-size: 1rem;
  font-size: 1rem;
  color: var(--md-sys-color-error, #b00020);
  cursor: default;
  flex-shrink: 0;
}

.schedule-table__trip-warning-route {
  --md-icon-size: 1rem;
  font-size: 1rem;
  color: #f57c00;
  cursor: default;
  flex-shrink: 0;
}

.schedule-table__trip-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  border-radius: 50%;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  opacity: 0.55;
  transition: opacity 0.15s, background 0.15s;
}

.schedule-table__trip-action-btn:hover {
  opacity: 1;
  background: color-mix(in srgb, var(--md-sys-color-on-surface, #222) 10%, transparent);
}

.schedule-table__trip-action-btn md-icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
}

/* Delete button keeps its red color */
.schedule-table__trip-action-btn.schedule-table__trip-delete {
  color: var(--md-sys-color-error, #b00020);
}

.schedule-table__trip-action-btn.schedule-table__trip-delete:hover {
  background: color-mix(in srgb, var(--md-sys-color-error, #b00020) 12%, transparent);
}

/* Selection checkbox inside trip action row */
.schedule-table__trip-select-label {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  opacity: 0.55;
  transition: opacity 0.15s, background 0.15s;
}

.schedule-table__trip-select-label:hover {
  opacity: 1;
  background: color-mix(in srgb, var(--md-sys-color-on-surface, #222) 10%, transparent);
}

.schedule-table__trip-select {
  width: 14px;
  height: 14px;
  margin: 0;
  cursor: pointer;
  accent-color: var(--md-sys-color-primary, #1f69e0);
}

.schedule-table__trip-select-label:has(.schedule-table__trip-select:checked) {
  opacity: 1;
}

/* Selected column highlight */
.schedule-table__trip-th--selected {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 10%, var(--md-sys-color-surface-container, #f4f4f4));
}

.schedule-table__time-cell--selected {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 6%, transparent);
}

/* ---- Time cells (body band rows) ---- */
.schedule-table__time-cell {
  padding: 0 0.25rem;
  height: 2.5rem;
  vertical-align: middle;
  border-right: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  width: 120px;
  max-width: 120px;
  min-width: 60px;
  position: relative;   /* anchor for arrival badge + context menu portal */
  overflow: visible;
}

.schedule-table__time-cell--context {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 6%, transparent);
}

.schedule-table__time-cell--dummy {
  background: color-mix(in srgb, var(--md-sys-color-surface-container, #f4f4f4) 60%, transparent);
  border-left: 2px dashed var(--md-sys-color-outline-variant, #e0e0e0);
  border-right: none;
}

.schedule-table__time-input {
  display: block;
  width: 100%;
  padding: 0;
  border: none;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  background: transparent;
  color: var(--md-sys-color-on-surface, #222);
  outline: none;
  text-align: center;
  /* leave room for right-side arrow indicators */
  padding-right: 14px;
  /* balance with equal left padding so text stays visually centred */
  padding-left: 14px;
}

/* ---- Arrival-diff indicator (top-left triangle) ---- */
.schedule-table__arr-badge {
  position: absolute;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
  border-style: solid;
  border-width: 11px 11px 0 0;
  border-color: var(--md-sys-color-primary, #1f69e0) transparent transparent transparent;
  pointer-events: none;
  z-index: 0;
}

/* ---- Pickup / drop-off arrow indicators (right side, vertically centred) ---- */
.schedule-table__stop-indicators {
  position: absolute;
  right: 3px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  pointer-events: none;
  line-height: 1;
}

.schedule-table__stop-ind {
  --md-icon-size: 0.9rem;
  font-size: 0.9rem;
  color: var(--md-sys-color-primary, #1f69e0);
  display: block;
  -webkit-font-smoothing: antialiased;
}

.schedule-table__stop-ind--none {
  color: var(--md-sys-color-error, #b00020);
}

/* ---- Filler cell (last column, absorbs remaining table width) ---- */
thead .schedule-table__filler-cell {
  position: sticky;
  top: 0;
  background: var(--md-sys-color-surface-container, #f4f4f4);
}

.schedule-table__header-row--last .schedule-table__filler-cell {
  border-bottom: 2px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

tbody .schedule-table__filler-cell {
  background: inherit;
}

/* ---- Flyout cells (day type / route path / attributes) ---- */
.schedule-table__trip-input-cell--dt {
  overflow: visible;
}

/* footer button inside the route-path flyout */
.schedule-table__map-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  width: 100%;
  padding: 0.375rem 0.625rem;
  border: none;
  background: none;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-primary, #1f69e0);
  cursor: pointer;
  text-align: left;
  transition: background 0.1s;
}

.schedule-table__map-btn:hover {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
}

.schedule-table__map-btn--danger {
  color: var(--md-sys-color-error, #b00020);
}

.schedule-table__map-btn--danger:hover {
  background: color-mix(in srgb, var(--md-sys-color-error, #b00020) 8%, transparent);
}

.schedule-table__map-btn md-icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
}

/* ---- Stop-time headsign indicator (same height as stop-indicators, left side) ---- */
.schedule-table__hs-ind {
  position: absolute;
  top: 50%;
  left: 2px;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  pointer-events: none;
  color: var(--md-sys-color-primary, #1f69e0);
}

.schedule-table__hs-ind md-icon {
  --md-icon-size: 0.9rem;
  font-size: 0.9rem;
}
</style>
