<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import { api } from '@/api/client.js'
import TagSelect from '@/components/TagSelect.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-button.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/checkbox/checkbox.js'

const { t } = useI18n()
const { has } = usePermissions()
const canExport = has('gtfs:export')

const versionId = computed(() => versionsStore.state.activeVersionId)

// ---- Routes ----
const allRoutes        = ref([])
const selectedRouteIds = ref([])

const routeOptions = computed(() =>
  allRoutes.value.map(r => ({
    id: r.route_id,
    label: [r.route_short_name, r.route_long_name].filter(Boolean).join(' – ') || r.route_id,
  })))

async function loadRoutes() {
  const vid = versionId.value
  if (!vid) { allRoutes.value = []; selectedRouteIds.value = []; return }
  try {
    allRoutes.value = await api.schedule.routes(vid)
    selectedRouteIds.value = allRoutes.value.map(r => r.route_id)
  } catch {
    allRoutes.value = []
    selectedRouteIds.value = []
  }
}

watch(versionId, loadRoutes, { immediate: true })

// ---- Date range ----
const dateFrom = ref('')
const dateTo   = ref('')

function _isoToday() {
  return new Date().toISOString().slice(0, 10)
}

async function loadDefaultDates(vid) {
  dateFrom.value = _isoToday()
  dateTo.value   = ''
  if (!vid) return
  try {
    const res = await api.calendars.maxDate(vid)
    dateTo.value = res.max_date ?? ''
  } catch {
    // leave empty if unavailable
  }
}

watch(versionId, loadDefaultDates, { immediate: true })

// ---- Data reduction ----
const exportAllStops = ref(false)
const exportShapes   = ref(true)

// ---- Export / log ----
const isExporting = ref(false)
const exportLog   = ref([])   // { level: 'Info'|'LowPrio'|'MiddlePrio'|'HighPrio', text: string }

const LOG_BADGE = { Info: 'i', LowPrio: '↓', MiddlePrio: '↑', HighPrio: '↑↑' }
function logBadge(level) { return LOG_BADGE[level] ?? '?' }

const canStartExport = computed(() =>
  canExport.value &&
  !!versionId.value &&
  selectedRouteIds.value.length > 0 &&
  !!dateFrom.value &&
  !!dateTo.value &&
  dateFrom.value <= dateTo.value &&
  !isExporting.value)

function startExport() {
  exportLog.value = []
  isExporting.value = true
  api.gtfsExport.start(versionId.value, {
    route_ids:        selectedRouteIds.value,
    date_from:        dateFrom.value,
    date_to:          dateTo.value,
    export_all_stops: exportAllStops.value,
    export_shapes:    exportShapes.value,
  }).then(async (response) => {
    // Adopt a refreshed sliding token if the backend issued one
    const newToken = response.headers.get('X-New-Token')
    if (newToken) localStorage.setItem('access_token', newToken)

    if (!response.ok) {
      exportLog.value.push({ level: 'HighPrio', text: t('gtfs_export.log.internal_error', { detail: `HTTP ${response.status}` }) })
      isExporting.value = false
      return
    }
    const reader  = response.body.getReader()
    const decoder = new TextDecoder()
    let   buffer  = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        try {
          const event = JSON.parse(trimmed.slice('data:'.length).trim())
          if (event.level && event.key) {
            exportLog.value.push({ level: event.level, text: t(`gtfs_export.log.${event.key}`, event.params ?? {}) })
          }
          if (event.status === 'done' || event.status === 'error') {
            isExporting.value = false
          }
          if (event.status === 'done' && event.payload) {
            _downloadZip(event.payload, event.filename ?? 'gtfs_export.zip')
          }
        } catch {
          // ignore malformed lines
        }
      }
    }
    isExporting.value = false
  }).catch((err) => {
    exportLog.value.push({ level: 'HighPrio', text: t('gtfs_export.log.internal_error', { detail: String(err) }) })
    isExporting.value = false
  })
}

function _downloadZip(base64, filename) {
  const binary = atob(base64)
  const bytes  = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'application/zip' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="gtfs-export-view">

    <header class="view-header">
      <md-icon class="view-header__icon">file_download</md-icon>
      <h1 class="view-header__title">{{ t('views.gtfs_export') }}</h1>
      <div class="view-header__actions"></div>
    </header>

    <!-- No version selected -->
    <div v-if="!versionId" class="gtfs-export-view__placeholder">
      <md-icon>info</md-icon>
      <span>{{ t('gtfs_export.no_version') }}</span>
    </div>

    <template v-else>
      <!-- Routes -->
      <section class="export-section">
        <div class="export-section__body">
          <h2 class="export-section__title">
            <md-icon>route</md-icon>
            {{ t('gtfs_export.section_routes') }}
          </h2>
          <p class="export-section__hint">{{ t('gtfs_export.routes_hint') }}</p>
          <TagSelect
            class="export-section__tag-select"
            v-model="selectedRouteIds"
            :options="routeOptions"
            :label="t('gtfs_export.routes_label')"
            :no-results-text="t('gtfs_export.routes_no_results')"
          />
          <p class="export-section__count">
            {{ t('gtfs_export.routes_selected', { count: selectedRouteIds.length, total: allRoutes.length }) }}
          </p>
        </div>
      </section>

      <!-- Date range -->
      <section class="export-section">
        <div class="export-section__body">
          <h2 class="export-section__title">
            <md-icon>date_range</md-icon>
            {{ t('gtfs_export.section_period') }}
          </h2>
          <p class="export-section__hint">{{ t('gtfs_export.period_hint') }}</p>
          <div class="export-section__date-row">
            <md-outlined-text-field
              type="date"
              :label="t('gtfs_export.date_from')"
              :value="dateFrom"
              :max="dateTo || undefined"
              @change="dateFrom = $event.target.value"
            />
            <span class="export-section__date-sep">–</span>
            <md-outlined-text-field
              type="date"
              :label="t('gtfs_export.date_to')"
              :value="dateTo"
              :min="dateFrom || undefined"
              @change="dateTo = $event.target.value"
            />
          </div>
        </div>
      </section>

      <!-- Data reduction -->
      <section class="export-section">
        <div class="export-section__body">
          <h2 class="export-section__title">
            <md-icon>filter_alt</md-icon>
            {{ t('gtfs_export.section_reduction') }}
          </h2>
          <p class="export-section__hint">{{ t('gtfs_export.reduction_hint') }}</p>
          <label class="export-section__checkbox-row">
            <md-checkbox
              :checked="exportAllStops"
              @change="exportAllStops = $event.target.checked"
            />
            <span>{{ t('gtfs_export.export_all_stops') }}</span>
          </label>
          <label class="export-section__checkbox-row">
            <md-checkbox
              :checked="exportShapes"
              @change="exportShapes = $event.target.checked"
            />
            <span>{{ t('gtfs_export.export_shapes') }}</span>
          </label>
        </div>
      </section>

      <!-- Export action -->
      <div class="export-actions">
        <md-filled-button
          :disabled="!canStartExport"
          @click="startExport"
        >
          <md-icon slot="icon">file_download</md-icon>
          {{ t('gtfs_export.export_button') }}
        </md-filled-button>
      </div>

      <!-- Export log -->
      <div v-if="exportLog.length > 0" class="export-log">
        <div
          v-for="(entry, i) in exportLog"
          :key="i"
          class="export-log__entry"
        >
          <span :class="['export-log__badge', `export-log__badge--${entry.level}`]">
            {{ logBadge(entry.level) }}
          </span>
          <span class="export-log__text">{{ entry.text }}</span>
        </div>
      </div>
    </template>

  </div>
</template>

<style scoped>
.gtfs-export-view {
  display: flex;
  flex-direction: column;
  gap: 0;
  height: 100%;
  padding-bottom: 1.5rem;
}

/* ---- Placeholder ---- */
.gtfs-export-view__placeholder {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--md-sys-color-on-surface-variant);
  padding: 1rem 0;
}

/* ---- Section ---- */
.export-section {
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.export-section:last-of-type {
  border-bottom: none;
}

.export-section__body {
  max-width: 600px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.25rem 0 1.5rem;
}

.export-section__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  font-weight: 500;
  color: var(--md-sys-color-primary, #1f69e0);
  margin: 0;
}

.export-section__hint {
  font-size: 0.875rem;
  color: var(--md-sys-color-on-surface-variant);
  margin: 0;
}

.export-section__count {
  font-size: 0.8125rem;
  color: var(--md-sys-color-on-surface-variant);
  margin: 0;
}

.export-section__tag-select {
  width: 100%;
}

.export-section__date-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.export-section__date-row md-outlined-text-field {
  flex: 1;
}

.export-section__date-sep {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 1.125rem;
}

.export-section__checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.9375rem;
  color: var(--md-sys-color-on-surface);
  user-select: none;
}

/* ---- Export action ---- */
.export-actions {
  display: flex;
  justify-content: flex-end;
  padding: 1rem 0;
}

/* ---- Export log ---- */
.export-log {
  display: flex;
  flex-direction: column;
  padding-bottom: 1.5rem;
}

.export-log__entry {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  font-size: 0.9375rem;
}

.export-log__entry:last-child {
  border-bottom: none;
}

.export-log__badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.625rem;
  height: 1.625rem;
  border-radius: 5px;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
  font-family: monospace;
}

.export-log__badge--Info,
.export-log__badge--LowPrio {
  background: rgba(31, 105, 224, 0.12);
  color: #1f69e0;
}

.export-log__badge--MiddlePrio {
  background: rgba(200, 125, 0, 0.12);
  color: #c77d00;
}

.export-log__badge--HighPrio {
  background: rgba(186, 26, 26, 0.10);
  color: #ba1a1a;
}

.export-log__text {
  flex: 1;
  color: var(--md-sys-color-on-surface, #222);
  line-height: 1.4;
}

/* ---- Footer ---- */
.gtfs-export-view__footer {
  display: none;
}
</style>
