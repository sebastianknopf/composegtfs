<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import ScheduleSideBar from '@/components/ScheduleSideBar.vue'
import ScheduleTable from '@/components/ScheduleTable.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import TripShiftModal from '@/components/TripShiftModal.vue'
import TripCopyModal from '@/components/TripCopyModal.vue'
import TripGlobalIdGeneratorModal from '@/components/TripGlobalIdGeneratorModal.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/outlined-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/menu/menu.js'
import '@material/web/menu/menu-item.js'
import '@material/web/divider/divider.js'

const { t } = useI18n()
const { has } = usePermissions()

const canReadSchedule   = has('schedule:read')
const canWriteSchedule  = has('schedule:write')
const canDeleteSchedule = has('schedule:delete')

const versionId = computed(() => versionsStore.state.activeVersionId)

// ---- Routes ----
const scheduleRoutes = ref([])
const routesLoading  = ref(false)

async function loadRoutes() {
  const vid = versionId.value
  if (!vid || !canReadSchedule.value) { scheduleRoutes.value = []; return }
  routesLoading.value = true
  try { scheduleRoutes.value = await api.schedule.routes(vid) }
  catch { scheduleRoutes.value = [] }
  finally { routesLoading.value = false }
}

watch(versionId, loadRoutes, { immediate: true })

// ---- Platforms ----
const platforms = ref([])

async function loadPlatforms() {
  const vid = versionId.value
  if (!vid || !canReadSchedule.value) { platforms.value = []; return }
  try { platforms.value = await api.schedule.platforms(vid) }
  catch { platforms.value = [] }
}

watch(versionId, loadPlatforms, { immediate: true })

// ---- Day types ----
const dayTypes = ref([])

async function loadDayTypes() {
  const vid = versionId.value
  if (!vid || !canReadSchedule.value) { dayTypes.value = []; return }
  try { dayTypes.value = await api.schedule.dayTypes(vid) }
  catch { dayTypes.value = [] }
}

watch(versionId, loadDayTypes, { immediate: true })

// ---- Direction / Route selection ----
const selectedRoute     = ref(null)
const direction         = ref(0)
const scheduleTableRef  = ref(null)
const selectionMenuOpen = ref(false)

function handleRouteSelect(route) {
  selectedRoute.value = route
  direction.value = 0
}

function setDirection(dir) {
  direction.value = dir
}

// ---- Selection state ----
const selectedTripsCount = computed(() => {
  if (!scheduleTableRef.value) return 0
  return scheduleTableRef.value.visibleTrips?.filter(t => t.selected).length ?? 0
})

const canSelectWithSamePath = computed(() => selectedTripsCount.value === 1)

function handleSelectAll() {
  scheduleTableRef.value?.selectAllTrips?.()
  selectionMenuOpen.value = false
}

function handleSelectSamePath() {
  scheduleTableRef.value?.selectTripsWithSamePath?.()
  selectionMenuOpen.value = false
}

function handleDeselectAll() {
  scheduleTableRef.value?.deselectAllTrips?.()
  selectionMenuOpen.value = false
}

// ---- Filter ----
const filterServiceIds = ref([])
const filterOpen       = ref(false)
const filterRef        = ref(null)

const availableFilterDayTypes = computed(() => {
  const ids = scheduleTableRef.value?.availableServiceIds ?? []
  return ids.map(id => {
    const dt = dayTypes.value.find(d => d.service_id === id)
    return { service_id: id, name: dt?.name ?? id }
  })
})

const filterChipLabel = computed(() => {
  if (!filterServiceIds.value.length) return t('schedule.filter_day_type')
  if (filterServiceIds.value.length === 1) {
    const id = filterServiceIds.value[0]
    const dt = availableFilterDayTypes.value.find(d => d.service_id === id)
    return dt?.name ?? id
  }
  return t('schedule.filter_day_type')
})

const visibleTripsCount = computed(() => scheduleTableRef.value?.visibleTrips?.length ?? 0)

function toggleFilterServiceId(id) {
  const idx = filterServiceIds.value.indexOf(id)
  if (idx === -1) {
    filterServiceIds.value = [...filterServiceIds.value, id]
  } else {
    filterServiceIds.value = filterServiceIds.value.filter(s => s !== id)
  }
}

function clearFilter() {
  filterServiceIds.value = []
}

watch(filterServiceIds, () => {
  scheduleTableRef.value?.deselectAllTrips?.()
})

watch([selectedRoute, direction], () => {
  filterServiceIds.value = []
  filterOpen.value = false
})

function _onFilterClickOutside(e) {
  if (!filterRef.value?.contains(e.target)) filterOpen.value = false
}

watch(filterOpen, (open) => {
  if (open) {
    document.addEventListener('click', _onFilterClickOutside, true)
  } else {
    document.removeEventListener('click', _onFilterClickOutside, true)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', _onFilterClickOutside, true)
})

// ---- Move ----
const shiftModalOpen = ref(false)

function onMoveTrips() {
  if (!canWriteSchedule.value) return
  shiftModalOpen.value = true
}

async function confirmShiftTrips({ offsetMinutes, direction }) {
  if (!canWriteSchedule.value) return
  const trips = scheduleTableRef.value?.trips ?? []
  const selected = trips.filter(t => t.selected)
  if (!selected.length) return
  const tripIds = selected.map(t => t.tripId)
  try {
    await api.schedule.trips.batchShift(versionId.value, selectedRoute.value.route_id, tripIds, offsetMinutes, direction)
    // Reload the table to reflect updated times
    await scheduleTableRef.value?.loadTrips?.()
  } catch {
    // TODO: Fehler per Toast anzeigen
  }
}

// ---- Copy ----
const copyModalOpen = ref(false)

function onCopyTrips() {
  if (!canWriteSchedule.value || selectedTripsCount.value !== 1) return
  copyModalOpen.value = true
}

async function confirmCopyTrips(payload) {
  if (!canWriteSchedule.value) return
  const trips = scheduleTableRef.value?.trips ?? []
  const selected = trips.filter(t => t.selected)
  if (!selected.length) return
  const tripIds = selected.map(t => t.tripId)
  try {
    await api.schedule.trips.batchCopy(versionId.value, selectedRoute.value.route_id, {
      trip_ids: tripIds,
      ...payload,
    })
    await scheduleTableRef.value?.loadTrips?.()
  } catch {
    // TODO: Fehler per Toast anzeigen
  }
}

// ---- Delete ----
const confirmDeleteOpen = ref(false)
const deleteCount = computed(() => selectedTripsCount.value)

function onDeleteTrips() {
  if (!canDeleteSchedule.value) return
  confirmDeleteOpen.value = true
}

async function confirmDeleteTrips() {
  if (!canDeleteSchedule.value) return
  confirmDeleteOpen.value = false
  const trips = scheduleTableRef.value?.trips ?? []
  const selected = trips.filter(t => t.selected)
  if (!selected.length) return
  const tripIds = selected.map(t => t.tripId)
  try {
    await api.schedule.trips.batchDelete(versionId.value, selectedRoute.value.route_id, tripIds)
    scheduleTableRef.value.trips = trips.filter(t => !tripIds.includes(t.tripId))
  } catch {
    // TODO: Fehler per Toast anzeigen
  }
}

// ---- Wizard ----
const wizardMenuOpen        = ref(false)
const wizardLoading         = ref(false)
const globalIdGeneratorOpen = ref(false)
// Close the menu whenever the selection changes so it doesn't auto-open
// when the wizard button appears after a trip is selected.
watch(selectedTripsCount, () => { wizardMenuOpen.value = false })

async function onWizardAssignShapes() {
  wizardMenuOpen.value = false
  if (!canWriteSchedule.value) return
  const trips = scheduleTableRef.value?.trips ?? []
  const selected = trips.filter(t => t.selected)
  if (!selected.length) return
  const tripIds = selected.map(t => t.tripId)
  wizardLoading.value = true
  try {
    const result = await api.schedule.trips.wizardAssignShapes(
      versionId.value,
      selectedRoute.value.route_id,
      tripIds,
    )
    const parts = []
    if (result.updated        > 0) parts.push(t('schedule.wizard_result_updated',  { count: result.updated }))
    if (result.already_assigned > 0) parts.push(t('schedule.wizard_result_already',  { count: result.already_assigned }))
    if (result.no_match       > 0) parts.push(t('schedule.wizard_result_no_match', { count: result.no_match }))
    const type = result.updated > 0 ? 'info' : 'error'
    toast.show(parts.length ? parts.join(' ') : t('schedule.wizard_result_no_match', { count: 0 }), type)
    if (result.updated > 0) {
      await scheduleTableRef.value?.loadTrips?.()
    }
  } catch {
    toast.show(t('schedule.wizard_assign_shapes_error'), 'error')
  } finally {
    wizardLoading.value = false
  }
}

function onWizardGenerateGlobalIds() {
  wizardMenuOpen.value = false
  if (!canWriteSchedule.value) return
  globalIdGeneratorOpen.value = true
}

async function confirmGenerateGlobalIds({ preset, overwrite }) {
  globalIdGeneratorOpen.value = false
  const trips = scheduleTableRef.value?.trips ?? []
  const selected = trips.filter(t => t.selected)
  if (!selected.length) return
  const tripIds = selected.map(t => t.tripId)
  wizardLoading.value = true
  try {
    const result = await api.schedule.trips.wizardGenerateGlobalIds(
      versionId.value,
      selectedRoute.value.route_id,
      { trip_ids: tripIds, preset, overwrite },
    )
    const parts = []
    if (result.updated > 0) parts.push(t('schedule.wizard_global_id_updated', { count: result.updated }))
    if (result.skipped > 0) parts.push(t('schedule.wizard_global_id_skipped', { count: result.skipped }))
    const msg = parts.join(' ') || t('schedule.wizard_global_id_none')
    toast.show(msg, result.updated > 0 ? 'info' : 'error')
    if (result.updated > 0) {
      await scheduleTableRef.value?.loadTrips?.()
    }
  } catch (err) {
    const detail = err?.detail
    let msg
    if (detail && typeof detail === 'object' && detail.error_code) {
      const params = Object.fromEntries(Object.entries(detail).filter(([k]) => k !== 'error_code'))
      msg = t(`schedule.global_id_errors.${detail.error_code}`, params)
    }
    if (!msg) msg = t('schedule.wizard_global_id_error')
    toast.show(msg, 'error')
  } finally {
    wizardLoading.value = false
  }
}
</script>

<template>
  <div class="schedule-view">

    <ScheduleSideBar
      :routes="scheduleRoutes"
      section-id="schedule-routes"
      @route-select="handleRouteSelect"
    />

    <div class="schedule-content">

      <header class="view-header">
        <md-icon class="view-header__icon">table_view</md-icon>
        <h1 class="view-header__title">{{ t("views.schedule") }}</h1>
        <div class="view-header__actions schedule-view__dir-toggle" v-if="selectedRoute">
          <div v-if="availableFilterDayTypes.length" ref="filterRef" class="schedule-filter">
            <button
              class="schedule-filter__chip"
              :class="{ 'schedule-filter__chip--active': filterServiceIds.length }"
              @click="filterOpen = !filterOpen"
            >
              <span class="schedule-filter__icon-wrap">
                <md-icon class="schedule-filter__icon">filter_list</md-icon>
                <span v-if="filterServiceIds.length > 1" class="schedule-filter__badge">{{ filterServiceIds.length }}</span>
              </span>
              <span class="schedule-filter__label">{{ filterChipLabel }}</span>
              <span v-if="filterServiceIds.length" class="schedule-filter__clear" @click.stop="clearFilter">
                <md-icon>close</md-icon>
              </span>
            </button>
            <div v-if="filterOpen" class="schedule-filter__dropdown">
              <label
                v-for="dt in availableFilterDayTypes"
                :key="dt.service_id"
                class="schedule-filter__option"
              >
                <input
                  type="checkbox"
                  class="schedule-filter__checkbox"
                  :checked="filterServiceIds.includes(dt.service_id)"
                  @change="toggleFilterServiceId(dt.service_id)"
                />
                <span>{{ dt.name || dt.service_id }}</span>
              </label>
            </div>
          </div>
          <template v-for="[dir, label] in [[0, t('schedule.direction_outbound')], [1, t('schedule.direction_inbound')]]" :key="dir">
            <md-filled-button v-if="direction === dir" class="dir-toggle-btn" @click="setDirection(dir)">{{ label }}</md-filled-button>
            <md-outlined-button v-else class="dir-toggle-btn" @click="setDirection(dir)">{{ label }}</md-outlined-button>
          </template>
        </div>
      </header>

      <div v-if="!versionId" class="schedule-content__placeholder">
        <md-icon>info</md-icon>
        <span>{{ t("schedule.no_version") }}</span>
      </div>

      <div v-else-if="!selectedRoute" class="schedule-content__placeholder">
        <md-icon>info</md-icon>
        <span>{{ t("schedule.no_route") }}</span>
      </div>

      <template v-else>
        <div class="schedule-toolbar">
          <div v-if="canWriteSchedule || canDeleteSchedule" class="schedule-toolbar__selection">
            <md-filled-button
              id="selection-menu-btn"
              class="schedule-toolbar__btn"
              @click="selectionMenuOpen = !selectionMenuOpen"
            >
              <md-icon slot="icon">unfold_more</md-icon>
              {{ t("schedule.selection_button") }}
            </md-filled-button>
            <md-menu
              anchor="selection-menu-btn"
              :open="selectionMenuOpen"
              @close="selectionMenuOpen = false"
              class="schedule-toolbar__menu"
            >
              <md-menu-item class="toolbar-menu-item" @click="handleSelectAll">
                <div slot="headline">{{ t("schedule.select_all_trips") }}</div>
              </md-menu-item>
              <md-menu-item
                class="toolbar-menu-item"
                :disabled="!canSelectWithSamePath"
                @click="canSelectWithSamePath && handleSelectSamePath()"
              >
                <div slot="headline" class="menu-item-nowrap">{{ t("schedule.select_same_path") }}</div>
              </md-menu-item>
              <md-divider />
              <md-menu-item class="toolbar-menu-item" @click="handleDeselectAll">
                <div slot="headline">{{ t("schedule.deselect_all") }}</div>
              </md-menu-item>
            </md-menu>
          </div>

          <span class="schedule-toolbar__count">{{ selectedTripsCount }}/{{ visibleTripsCount }}</span>

          <div v-if="canWriteSchedule && selectedTripsCount > 0" class="schedule-toolbar__wizard">
            <md-outlined-button
              id="wizard-menu-btn"
              class="schedule-toolbar__btn"
              :disabled="wizardLoading"
              @click="wizardMenuOpen = !wizardMenuOpen"
            >
              <md-icon slot="icon">auto_fix_high</md-icon>
              {{ t('schedule.wizard_button') }}
            </md-outlined-button>
            <md-menu
              anchor="wizard-menu-btn"
              :open="wizardMenuOpen"
              @close="wizardMenuOpen = false"
              class="schedule-toolbar__menu"
            >
              <md-menu-item class="toolbar-menu-item" @click="onWizardAssignShapes">
                <div slot="headline">{{ t('schedule.wizard_assign_shapes') }}</div>
              </md-menu-item>
              <md-menu-item class="toolbar-menu-item" @click="onWizardGenerateGlobalIds">
                <div slot="headline">{{ t('schedule.wizard_generate_global_ids') }}</div>
              </md-menu-item>
            </md-menu>
          </div>

          <template v-if="selectedTripsCount > 0">
            <md-outlined-button v-if="canWriteSchedule && selectedTripsCount === 1" class="schedule-toolbar__btn" @click="onCopyTrips">
              <md-icon slot="icon">content_copy</md-icon>
              {{ t("common.copy") }}
            </md-outlined-button>
            <md-outlined-button v-if="canWriteSchedule" class="schedule-toolbar__btn" @click="onMoveTrips">
              <md-icon slot="icon">swap_horiz</md-icon>
              {{ t("common.move") }}
            </md-outlined-button>
            <md-outlined-button v-if="canDeleteSchedule" class="schedule-toolbar__btn schedule-toolbar__btn--danger" @click="onDeleteTrips">
              <md-icon slot="icon">delete</md-icon>
              {{ t("common.delete") }}
            </md-outlined-button>
          </template>
        </div>

        <ScheduleTable
          ref="scheduleTableRef"
          :version-id="versionId"
          :route-id="selectedRoute.route_id"
          :route-type="selectedRoute.route_type ?? null"
          :direction="direction"
          :platforms="platforms"
          :can-read="canReadSchedule"
          :can-write="canWriteSchedule"
          :can-delete="canDeleteSchedule"
          :filter-service-ids="filterServiceIds"
        />
      </template>

    </div>

    <ConfirmDialog
      v-model="confirmDeleteOpen"
      :title="t('common.delete')"
      :message="t('schedule.delete_trips_confirm', { count: deleteCount })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      :danger="true"
      @confirm="confirmDeleteTrips"
    />

    <TripShiftModal
      v-model="shiftModalOpen"
      :count="selectedTripsCount"
      @confirm="confirmShiftTrips"
    />

    <TripCopyModal
      v-model="copyModalOpen"
      :day-types="dayTypes"
      @confirm="confirmCopyTrips"
    />

    <TripGlobalIdGeneratorModal
      v-model="globalIdGeneratorOpen"
      :count="selectedTripsCount"
      @confirm="confirmGenerateGlobalIds"
    />

  </div>
</template>

<style scoped>
.schedule-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
}

.schedule-content {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 1rem 1.25rem 0;
  overflow: hidden;
}

.schedule-view__dir-toggle {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.dir-toggle-btn {
  min-width: 7.5rem;
}

.schedule-content__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 3rem 1rem;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  font-size: var(--font-size-1, 0.875rem);
}

.schedule-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0 0.5rem 0;
  margin-bottom: 0.75rem;
  flex-shrink: 0;
}

.schedule-toolbar__selection {
  position: relative;
}

.schedule-toolbar__wizard {
  position: relative;
}

.schedule-toolbar__count {
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  white-space: nowrap;
  line-height: 1;
}

.schedule-toolbar__btn--danger {
  --md-outlined-button-label-text-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-hover-label-text-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-pressed-label-text-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-focus-label-text-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-outline-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-hover-outline-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-pressed-outline-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-focus-outline-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-hover-state-layer-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-pressed-state-layer-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-focus-state-layer-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-icon-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-hover-icon-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-pressed-icon-color: var(--md-sys-color-error, #b00020);
  --md-outlined-button-focus-icon-color: var(--md-sys-color-error, #b00020);
}

.schedule-toolbar__menu {
  min-width: 280px;
}

.toolbar-menu-item {
  --md-menu-item-top-space: 6px;
  --md-menu-item-bottom-space: 6px;
  --md-menu-item-one-line-container-height: 36px;
}

.menu-item-nowrap {
  white-space: nowrap;
}

/* ---- Day-type filter chip ---- */

.schedule-filter {
  position: relative;
}

.schedule-filter__chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0 0.625rem 0 0.75rem;
  height: 2.5rem;
  border-radius: 1.25rem;
  border: 1px solid var(--md-sys-color-outline, #79747e);
  background: transparent;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #1c1b1f);
  transition: background 120ms, border-color 120ms;
  white-space: nowrap;
  font-family: inherit;
}

.schedule-filter__chip:hover {
  background: color-mix(in srgb, var(--md-sys-color-on-surface, #1c1b1f) 8%, transparent);
}

.schedule-filter__chip--active {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 12%, transparent);
  border-color: var(--md-sys-color-primary, #1f69e0);
  color: var(--md-sys-color-primary, #1f69e0);
}

.schedule-filter__chip--active:hover {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 18%, transparent);
}

.schedule-filter__icon-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.schedule-filter__icon {
  font-size: 1.125rem;
  width: 1.125rem;
  height: 1.125rem;
}

.schedule-filter__badge {
  position: absolute;
  bottom: -0.3rem;
  right: -0.45rem;
  min-width: 1rem;
  height: 1rem;
  padding: 0 0.2rem;
  border-radius: 0.5rem;
  background: var(--md-sys-color-primary, #1f69e0);
  color: var(--md-sys-color-on-primary, #ffffff);
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1rem;
  text-align: center;
  pointer-events: none;
}

.schedule-filter__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 14rem;
}

.schedule-filter__clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 100ms;
}

.schedule-filter__clear:hover {
  background: color-mix(in srgb, currentColor 12%, transparent);
}

.schedule-filter__clear md-icon {
  font-size: 1rem;
  width: 1rem;
  height: 1rem;
}

.schedule-filter__dropdown {
  position: absolute;
  top: calc(100% + 0.375rem);
  left: 0;
  z-index: 200;
  background: var(--md-sys-color-surface-container, #f3edf7);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15), 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: 0.375rem 0;
  min-width: 10rem;
  max-height: 16rem;
  overflow-y: auto;
}

.schedule-filter__option {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 1rem;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #1c1b1f);
  transition: background 80ms;
  user-select: none;
}

.schedule-filter__option:hover {
  background: color-mix(in srgb, var(--md-sys-color-on-surface, #1c1b1f) 8%, transparent);
}

.schedule-filter__checkbox {
  accent-color: var(--md-sys-color-primary, #1f69e0);
  width: 1rem;
  height: 1rem;
  cursor: pointer;
  flex-shrink: 0;
}
</style>
