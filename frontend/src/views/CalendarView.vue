<script setup>
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import DataTable from '@/components/DataTable.vue'
import AuxCalendarEditModal from '@/components/AuxCalendarEditModal.vue'
import AuxCalendarViewModal from '@/components/AuxCalendarViewModal.vue'
import DayTypeEditModal from '@/components/DayTypeEditModal.vue'
import DayTypeViewModal from '@/components/DayTypeViewModal.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-button.js'

const { t } = useI18n()
const { has } = usePermissions()

const canWrite  = has('calendar:write')
const canDelete = has('calendar:delete')
const canRead   = has('calendar:read')

// ---- Perspectives ----
const PERSPECTIVES = ['day_types', 'aux_calendars']
const activePerspective = ref('day_types')

const PERSPECTIVE_LABELS = {
  day_types:     () => t('calendar.tab_day_types'),
  aux_calendars: () => t('calendar.tab_aux_calendars'),
}
const PERSPECTIVE_ICONS = {
  day_types:     'wb_sunny',
  aux_calendars: 'date_range',
}

// ---- Day-of-week config ----
const DAY_KEYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const DAY_LABEL = {
  monday:    () => t('calendar.day_mon'),
  tuesday:   () => t('calendar.day_tue'),
  wednesday: () => t('calendar.day_wed'),
  thursday:  () => t('calendar.day_thu'),
  friday:    () => t('calendar.day_fri'),
  saturday:  () => t('calendar.day_sat'),
  sunday:    () => t('calendar.day_sun'),
}
const DAY_WEEKEND = { saturday: true, sunday: true }

// ---- Columns ----
const dayTypeColumns = [
  { key: 'service_id',  label: () => t('calendar.column_id'),         sortable: true,  width: '160px' },
  { key: 'name',        label: () => t('calendar.column_name'),       sortable: true },
  { key: '_days',       label: () => t('calendar.column_days'),       sortable: false, width: '290px' },
  { key: 'start_date',  label: () => t('calendar.column_start_date'), sortable: true,  width: '110px', align: 'center' },
  { key: 'end_date',    label: () => t('calendar.column_end_date'),   sortable: true,  width: '110px', align: 'center' },
]

const auxCalendarColumns = [
  { key: 'name',        label: () => t('calendar.column_name'),       sortable: true },
  { key: '_date_count', label: () => t('calendar.column_date_count'), sortable: false, width: '140px', align: 'center' },
]

// ---- Data ----
const dayTypes     = ref([])
const auxCalendars = ref([])
const loading      = ref(false)

async function loadData() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) {
    dayTypes.value     = []
    auxCalendars.value = []
    return
  }
  loading.value = true
  try {
    const [dt, ac] = await Promise.all([
      api.calendars.list(versionId),
      api.auxCalendars.list(versionId),
    ])
    dayTypes.value = dt
    const withCounts = await Promise.all(
      ac.map(async (auxCal) => {
        try {
          const dates = await api.auxCalendars.listDates(versionId, auxCal.id)
          return { ...auxCal, _date_count: dates.length }
        } catch {
          return { ...auxCal, _date_count: null }
        }
      })
    )
    auxCalendars.value = withCounts
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
watch(() => versionsStore.state.activeVersionId, loadData)

// ---- Helpers ----
function formatDate(iso) {
  if (!iso) return '—'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

/**
 * Compute the effective set of service dates for a day type by:
 * 1. Enumerating all dates in [start_date, end_date] that match the weekday flags.
 * 2. Applying aux-calendar assignments:
 *    - junction_type 1 (zusätzlich): add those dates
 *    - junction_type 2 (nicht):      remove those dates
 *    - junction_type 3 (nur):        restrict base to intersection of all "nur" date sets
 *
 * Returns { dates: string[], conflict: boolean }
 * conflict is true when ≥2 "nur" aux-calendars have no common dates.
 *
 * assignmentsWithDates: [{ junction_type, dates: string[] }]
 */
function computeEffectiveDates(dayType, assignmentsWithDates) {
  const WEEKDAY_KEYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
  const baseDates = new Set()

  if (dayType.start_date && dayType.end_date) {
    const [sy, sm, sd] = dayType.start_date.split('-').map(Number)
    const [ey, em, ed] = dayType.end_date.split('-').map(Number)
    const end = new Date(ey, em - 1, ed)
    for (let cur = new Date(sy, sm - 1, sd); cur <= end; cur.setDate(cur.getDate() + 1)) {
      const weekdayKey = WEEKDAY_KEYS[cur.getDay()]
      if (dayType[weekdayKey] === 1) {
        const y2 = cur.getFullYear()
        const m2 = String(cur.getMonth() + 1).padStart(2, '0')
        const d2 = String(cur.getDate()).padStart(2, '0')
        baseDates.add(`${y2}-${m2}-${d2}`)
      }
    }
  }

  // --- junction_type 3: restrict (nur) ---
  const onlyAssignments = assignmentsWithDates.filter(a => a.junction_type === 3)
  let conflict = false
  if (onlyAssignments.length > 0) {
    const sets = onlyAssignments.map(a => new Set(a.dates))
    // Intersection of all "nur" date sets
    let restrictSet = new Set(sets[0])
    for (let i = 1; i < sets.length; i++) {
      restrictSet = new Set([...restrictSet].filter(d => sets[i].has(d)))
    }
    if (restrictSet.size === 0 && onlyAssignments.length >= 2) conflict = true
    // Effective set becomes the intersection itself:
    // (base ∩ restrictSet) ∪ (restrictSet − base) = restrictSet
    // This mirrors the backend logic and ensures "nur" calendars can add dates
    // not covered by the weekday pattern (e.g. when base is empty).
    baseDates.clear()
    for (const d of restrictSet) baseDates.add(d)
  }

  // --- junction_type 1 (zusätzlich) and 2 (nicht) ---
  for (const { junction_type, dates } of assignmentsWithDates) {
    if (junction_type === 1) {
      for (const d of dates) baseDates.add(d)
    } else if (junction_type === 2) {
      for (const d of dates) baseDates.delete(d)
    }
  }

  return { dates: [...baseDates].sort(), conflict }
}

// ---- Day type view modal ----
const dayTypeViewModalOpen = ref(false)
const viewingDayType       = ref(null)
const dayTypeViewDates     = ref([])
const dayTypeViewConflict  = ref(false)
const dayTypeViewLoading   = ref(false)

async function openViewDayType(row) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  dayTypeViewLoading.value = true
  try {
    const assignments = await api.calendars.listAssignments(versionId, row.service_id)
    const assignmentsWithDates = await Promise.all(
      assignments.map(async (a) => {
        try {
          const dates = await api.auxCalendars.listDates(versionId, a.aux_calendar_id)
          return { ...a, dates: dates.map(d => d.date) }
        } catch {
          return { ...a, dates: [] }
        }
      })
    )
    const { dates, conflict } = computeEffectiveDates(row, assignmentsWithDates)
    dayTypeViewDates.value     = dates
    dayTypeViewConflict.value  = conflict
    viewingDayType.value       = row
    dayTypeViewModalOpen.value = true
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    dayTypeViewLoading.value = false
  }
}

// ---- Day type modal ----
const dayTypeModalOpen    = ref(false)
const editingDayType      = ref(null)
const dayTypeModalError   = ref(null)
const dayTypeLoading      = ref(false)
const dayTypeAssignments  = ref([]) // current assignments when editing

function openCreateDayType() {
  editingDayType.value     = null
  dayTypeAssignments.value = []
  dayTypeModalError.value  = null
  dayTypeModalOpen.value   = true
}

async function openEditDayType(row) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  dayTypeLoading.value = true
  try {
    const assignments = await api.calendars.listAssignments(versionId, row.service_id)
    dayTypeAssignments.value = assignments
  } catch {
    dayTypeAssignments.value = []
  } finally {
    dayTypeLoading.value = false
  }
  editingDayType.value    = row
  dayTypeModalError.value = null
  dayTypeModalOpen.value  = true
}

async function handleDayTypeSave({ assignments: newAssignments, ...calendarData }) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  dayTypeModalError.value = null
  try {
    let actualServiceId
    if (editingDayType.value) {
      const { service_id: _sid, ...updateData } = calendarData
      await api.calendars.update(versionId, editingDayType.value.service_id, updateData)
      actualServiceId = editingDayType.value.service_id
    } else {
      await api.calendars.create(versionId, calendarData)
      actualServiceId = calendarData.service_id
    }
    // Diff and apply assignment changes
    const oldMap = Object.fromEntries(
      (dayTypeAssignments.value ?? []).map(a => [String(a.aux_calendar_id), a.junction_type])
    )
    const newMap = Object.fromEntries(
      (newAssignments ?? []).map(a => [String(a.aux_calendar_id), a.junction_type])
    )
    const allIds = new Set([...Object.keys(oldMap), ...Object.keys(newMap)])
    for (const id of allIds) {
      const oldType = oldMap[id] ?? null
      const newType = newMap[id] ?? null
      if (oldType === newType) continue
      if (oldType !== null) await api.calendars.removeAssignment(versionId, actualServiceId, id)
      if (newType !== null) await api.calendars.assignAuxCalendar(versionId, actualServiceId, { aux_calendar_id: id, junction_type: newType })
    }
    dayTypeModalOpen.value = false
    await loadData()
  } catch (err) {
    dayTypeModalError.value = err?.status === 409
      ? t('day_type.error_conflict')
      : t('error.server')
  }
}

// ---- Day type delete ----
const confirmDeleteDayTypeOpen = ref(false)
const pendingDeleteDayType     = ref(null)

function requestDeleteDayType(row) {
  pendingDeleteDayType.value = row
  confirmDeleteDayTypeOpen.value = true
}

async function handleConfirmDeleteDayType() {
  const versionId = versionsStore.state.activeVersionId
  const target = pendingDeleteDayType.value
  pendingDeleteDayType.value = null
  if (!versionId || !target) return
  try {
    await api.calendars.delete(versionId, target.service_id)
    dayTypes.value = dayTypes.value.filter(d => d.service_id !== target.service_id)
  } catch (err) {
    const msg = err?.status === 404 ? t('day_type.error_not_found') : t('error.server')
    toast.show(msg, 'error')
    await loadData()
  }
}

// ---- Aux Calendar view modal ----
const auxCalViewModalOpen  = ref(false)
const viewingAuxCal        = ref(null)
const auxCalViewDates      = ref([])
const auxCalViewLoading    = ref(false)

async function openViewAuxCalendar(row) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  auxCalViewLoading.value = true
  try {
    const dates = await api.auxCalendars.listDates(versionId, row.id)
    viewingAuxCal.value      = row
    auxCalViewDates.value    = dates.map(d => d.date)
    auxCalViewModalOpen.value = true
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    auxCalViewLoading.value = false
  }
}

// ---- Aux Calendar modal ----
const auxCalModalOpen  = ref(false)
const editingAuxCal    = ref(null)   // null = create
const auxCalModalDates = ref([])
const auxCalModalError = ref(null)
const auxCalLoading    = ref(false)

function openCreateAuxCalendar() {
  editingAuxCal.value    = null
  auxCalModalDates.value = []
  auxCalModalError.value = null
  auxCalModalOpen.value  = true
}

async function openEditAuxCalendar(row) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  auxCalLoading.value = true
  try {
    const dates = await api.auxCalendars.listDates(versionId, row.id)
    editingAuxCal.value    = row
    auxCalModalDates.value = dates.map(d => d.date)
    auxCalModalError.value = null
    auxCalModalOpen.value  = true
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    auxCalLoading.value = false
  }
}

async function handleAuxCalendarSave({ name, dates }) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  auxCalModalError.value = null
  try {
    if (editingAuxCal.value) {
      // Update name if changed
      if (name !== editingAuxCal.value.name) {
        await api.auxCalendars.update(versionId, editingAuxCal.value.id, { name })
      }
      // Compute diff for dates
      const existing = new Set(auxCalModalDates.value)
      const next     = new Set(dates)
      const toAdd    = dates.filter(d => !existing.has(d))
      const toDelete = [...existing].filter(d => !next.has(d))
      if (toAdd.length)    await api.auxCalendars.addDates(versionId, editingAuxCal.value.id, { dates: toAdd })
      if (toDelete.length) await Promise.all(toDelete.map(d => api.auxCalendars.deleteDate(versionId, editingAuxCal.value.id, d)))
    } else {
      const created = await api.auxCalendars.create(versionId, { name })
      if (dates.length) {
        await api.auxCalendars.addDates(versionId, created.id, { dates })
      }
    }
    auxCalModalOpen.value = false
    await loadData()
  } catch (err) {
    auxCalModalError.value = err?.status === 409
      ? t('aux_calendar.error_conflict')
      : t('error.server')
  }
}

// ---- Aux Calendar delete ----
const confirmDeleteOpen      = ref(false)
const pendingDeleteAuxCal    = ref(null)

function requestDeleteAuxCalendar(row) {
  pendingDeleteAuxCal.value = row
  confirmDeleteOpen.value   = true
}

async function handleConfirmDeleteAuxCalendar() {
  const versionId = versionsStore.state.activeVersionId
  const target = pendingDeleteAuxCal.value
  pendingDeleteAuxCal.value = null
  if (!versionId || !target) return
  try {
    await api.auxCalendars.delete(versionId, target.id)
    auxCalendars.value = auxCalendars.value.filter(a => a.id !== target.id)
  } catch (err) {
    const msg = err?.status === 404 ? t('aux_calendar.error_not_found') : t('error.server')
    toast.show(msg, 'error')
    await loadData()
  }
}
</script>

<template>
  <div class="calendar-view">

    <header class="view-header">
      <md-icon class="view-header__icon">calendar_month</md-icon>
      <h1 class="view-header__title">{{ t('views.calendar') }}</h1>
      <div class="view-header__actions">
        <md-filled-button
          v-if="canWrite && versionsStore.state.activeVersionId && activePerspective === 'day_types'"
          @click="openCreateDayType"
        >
          <md-icon slot="icon">add</md-icon>
          {{ t('calendar.add_day_type') }}
        </md-filled-button>
        <md-filled-button
          v-if="canWrite && versionsStore.state.activeVersionId && activePerspective === 'aux_calendars'"
          :disabled="auxCalLoading || undefined"
          @click="openCreateAuxCalendar"
        >
          <md-icon slot="icon">add</md-icon>
          {{ t('calendar.add_aux_calendar') }}
        </md-filled-button>
      </div>
    </header>

    <div class="perspective-tabs" role="tablist">
      <button
        v-for="p in PERSPECTIVES"
        :key="p"
        role="tab"
        :aria-selected="activePerspective === p"
        :class="['perspective-tab', { 'perspective-tab--active': activePerspective === p }]"
        @click="activePerspective = p"
      >
        <md-icon class="perspective-tab__icon">{{ PERSPECTIVE_ICONS[p] }}</md-icon>
        {{ PERSPECTIVE_LABELS[p]() }}
      </button>
    </div>

    <div v-if="!versionsStore.state.activeVersionId" class="calendar-view__no-version">
      <md-icon>info</md-icon>
      <span>{{ t('calendar.no_version_selected') }}</span>
    </div>

    <template v-else>
      <!-- Tagesarten -->
      <DataTable
        v-if="activePerspective === 'day_types'"
        :columns="dayTypeColumns"
        :rows="dayTypes"
        row-key="service_id"
        :loading="loading"
        :empty="t('calendar.no_day_types')"
        :pagination="{ pageSize: 25 }"
      >
        <template #cell-name="{ value }">
          <span>{{ value ?? '—' }}</span>
        </template>

        <template #cell-start_date="{ value }">
          <span>{{ formatDate(value) }}</span>
        </template>

        <template #cell-end_date="{ value }">
          <span>{{ formatDate(value) }}</span>
        </template>

        <template #cell-_days="{ row }">
          <div class="day-badges">
            <span
              v-for="key in DAY_KEYS"
              :key="key"
              v-show="row[key] === 1"
              :class="['day-badge', DAY_WEEKEND[key] ? 'day-badge--weekend' : 'day-badge--weekday']"
            >{{ DAY_LABEL[key]() }}</span>
          </div>
        </template>

        <template #actions="{ row }">
          <button
            v-if="canRead"
            class="table-action-btn"
            :title="t('common.view')"
            :disabled="dayTypeViewLoading || undefined"
            @click="openViewDayType(row)"
          >
            <md-icon>visibility</md-icon>
          </button>
          <button
            v-if="canWrite"
            class="table-action-btn"
            :title="t('common.edit')"
            :disabled="dayTypeLoading || undefined"
            @click="openEditDayType(row)"
          >
            <md-icon>edit</md-icon>
          </button>
          <button
            v-if="canDelete"
            class="table-action-btn table-action-btn--danger"
            :title="t('common.delete')"
            @click="requestDeleteDayType(row)"
          >
            <md-icon>delete</md-icon>
          </button>
        </template>
      </DataTable>

      <!-- Hilfskalender -->
      <DataTable
        v-if="activePerspective === 'aux_calendars'"
        :columns="auxCalendarColumns"
        :rows="auxCalendars"
        row-key="id"
        :loading="loading"
        :empty="t('calendar.no_aux_calendars')"
        :pagination="{ pageSize: 25 }"
      >
        <template #cell-_date_count="{ row }">
          <span>{{ row._date_count ?? '—' }}</span>
        </template>

        <template #actions="{ row }">
          <button
            v-if="canRead"
            class="table-action-btn"
            :title="t('common.view')"
            :disabled="auxCalViewLoading || undefined"
            @click="openViewAuxCalendar(row)"
          >
            <md-icon>visibility</md-icon>
          </button>
          <button
            v-if="canWrite"
            class="table-action-btn"
            :title="t('common.edit')"
            :disabled="auxCalLoading || undefined"
            @click="openEditAuxCalendar(row)"
          >
            <md-icon>edit</md-icon>
          </button>
          <button
            v-if="canDelete"
            class="table-action-btn table-action-btn--danger"
            :title="t('common.delete')"
            @click="requestDeleteAuxCalendar(row)"
          >
            <md-icon>delete</md-icon>
          </button>
        </template>
      </DataTable>
    </template>

    <!-- Day type view modal -->
    <DayTypeViewModal
      v-model="dayTypeViewModalOpen"
      :day-type="viewingDayType"
      :effective-dates="dayTypeViewDates"
      :warning="dayTypeViewConflict ? t('day_type.warning_restrict_conflict') : null"
    />

    <!-- Day type modal -->
    <DayTypeEditModal
      v-model="dayTypeModalOpen"
      :day-type="editingDayType"
      :aux-calendars="auxCalendars"
      :assignments="dayTypeAssignments"
      :error="dayTypeModalError"
      @save="handleDayTypeSave"
    />

    <!-- Day type delete confirmation -->
    <ConfirmDialog
      v-model="confirmDeleteDayTypeOpen"
      :title="t('day_type.delete_confirm_title')"
      :message="t('day_type.delete_confirm_message', { name: pendingDeleteDayType?.name || pendingDeleteDayType?.service_id || '' })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      danger
      @confirm="handleConfirmDeleteDayType"
    />

    <!-- Aux Calendar view modal -->
    <AuxCalendarViewModal
      v-model="auxCalViewModalOpen"
      :aux-calendar="viewingAuxCal"
      :dates="auxCalViewDates"
    />

    <!-- Aux Calendar modal -->
    <AuxCalendarEditModal
      v-model="auxCalModalOpen"
      :aux-calendar="editingAuxCal"
      :dates="auxCalModalDates"
      :error="auxCalModalError"
      @save="handleAuxCalendarSave"
    />

    <!-- Delete confirmation -->
    <ConfirmDialog
      v-model="confirmDeleteOpen"
      :title="t('aux_calendar.delete_confirm_title')"
      :message="t('aux_calendar.delete_confirm_message', { name: pendingDeleteAuxCal?.name ?? '' })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      danger
      @confirm="handleConfirmDeleteAuxCalendar"
    />

  </div>
</template>

<style scoped>
.calendar-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  height: 100%;
}

.calendar-view__no-version {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--md-sys-color-outline, #9e9e9e);
  padding: 1rem 0;
}

/* Day-of-week badges */
.day-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.day-badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.4;
}

.day-badge--weekday {
  background: rgba(31, 105, 224, 0.12);
  color: #1f69e0;
}

.day-badge--weekend {
  background: rgba(180, 80, 20, 0.12);
  color: #b45014;
}
</style>
