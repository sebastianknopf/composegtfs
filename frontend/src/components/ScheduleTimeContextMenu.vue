<script setup>
/**
 * ScheduleTimeContextMenu — right-click context menu for time matrix cells.
 *
 * Provides:
 *   - Arrival time (defaults to departure; must not exceed departure)
 *   - Pickup type  (Einstieg):   null | 0 = normal | 1 = kein Einstieg | 2 = bei Bestellung | 3 = bei Bedarf
 *   - Drop-off type (Ausstieg):  null | 0 = normal | 1 = kein Ausstieg  | 2 = bei Bestellung | 3 = bei Bedarf
 *
 * Props:
 *   modelValue    — { arrival_time: string|null, pickup_type: null|0|1|2|3, drop_off_type: null|0|1|2|3 }
 *   departureTime — string — the departure time of this cell (used to validate arrival)
 *   open          — boolean
 *   disabled      — boolean — readonly mode, menu shown but no edits allowed
 *
 * Emits:
 *   update:modelValue
 *   close
 */
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: {
    type:    Object,
    default: () => ({ arrival_time: null, pickup_type: null, drop_off_type: null, stop_headsign_id: null }),
  },
  departureTime: { type: String, default: '' },
  open:          { type: Boolean, default: false },
  disabled:      { type: Boolean, default: false },
  headsigns:     { type: Array,   default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'close'])
const { t } = useI18n()

// ---- Arrival time local editing ----
const arrivalInput = ref('')
const arrivalError = ref(false)

// Sync local input when menu opens or modelValue changes
watch(
  () => [props.open, props.modelValue?.arrival_time],
  () => {
    if (props.open) {
      arrivalInput.value = props.modelValue?.arrival_time ?? props.departureTime ?? ''
      arrivalError.value = false
    }
  },
  { immediate: true },
)

// Parse "H+:MM" → total minutes
function toMinutes(t) {
  if (!t || !/^\d+:\d{2}$/.test(t)) return null
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

const departureMinutes = computed(() => toMinutes(props.departureTime))

function onArrivalInput(event) {
  let val = event.target.value.replace(/[^\d:]/g, '')
  if (
    val.length >= 2 &&
    !val.includes(':') &&
    event.inputType !== 'deleteContentBackward' &&
    event.inputType !== 'deleteContentForward'
  ) {
    val = val.slice(0, 2) + ':' + val.slice(2)
  }
  const colonIdx = val.indexOf(':')
  if (colonIdx !== -1) {
    const mm = val.slice(colonIdx + 1).replace(/\D/g, '').slice(0, 2)
    val = val.slice(0, colonIdx + 1) + mm
  }
  arrivalInput.value = val
  event.target.value = val
}

function onArrivalBlur() {
  const val = arrivalInput.value.trim()
  if (!val) {
    // Clear → inherit departure
    arrivalError.value = false
    emit('update:modelValue', { ...props.modelValue, arrival_time: null })
    return
  }
  if (!/^\d+:\d{2}$/.test(val)) {
    arrivalError.value = true
    return
  }
  const mm = parseInt(val.split(':')[1], 10)
  if (mm > 59) { arrivalError.value = true; return }
  const arrMins = toMinutes(val)
  const depMins = departureMinutes.value
  if (depMins !== null && arrMins > depMins) {
    arrivalError.value = true
    return
  }
  arrivalError.value = false
  emit('update:modelValue', { ...props.modelValue, arrival_time: val })
}

function clearArrivalToDeparture() {
  arrivalInput.value = props.departureTime ?? ''
  arrivalError.value = false
  // Null means: inherit departure time.
  emit('update:modelValue', { ...props.modelValue, arrival_time: null })
}

// ---- Pickup / drop-off type ----
// Options displayed (GTFS values):
//   1 = Kein Einstieg / Kein Ausstieg
//   3 = Bei Bedarf
//   2 = Bei Bestellung
// null = not set (inherit default = normaler Halt)
const PICKUP_OPTIONS = [
  { value: 1, labelKey: 'schedule.stop_type_no_pickup'  },
  { value: 3, labelKey: 'schedule.stop_type_request' },
  { value: 2, labelKey: 'schedule.stop_type_order'   },
]

const DROPOFF_OPTIONS = [
  { value: 1, labelKey: 'schedule.stop_type_no_dropoff' },
  { value: 3, labelKey: 'schedule.stop_type_request' },
  { value: 2, labelKey: 'schedule.stop_type_order'   },
]

function togglePickup(value) {
  const current = props.modelValue?.pickup_type ?? null
  const next = current === value ? null : value
  emit('update:modelValue', { ...props.modelValue, pickup_type: next })
}

function toggleDropOff(value) {
  const current = props.modelValue?.drop_off_type ?? null
  const next = current === value ? null : value
  emit('update:modelValue', { ...props.modelValue, drop_off_type: next })
}

function onFocusOut(e) {
  // Only close if focus leaves the entire wrapper
  if (!e.currentTarget.contains(e.relatedTarget)) {
    emit('close')
  }
}

// ---- Headsign selection ----
const headsignSearch = ref('')

const filteredHeadsigns = computed(() => {
  const q = headsignSearch.value.trim().toLowerCase()
  const list = q
    ? props.headsigns.filter(h => h.name.toLowerCase().includes(q))
    : props.headsigns
  return list.slice(0, 8)
})

function selectHeadsign(id) {
  emit('update:modelValue', { ...props.modelValue, stop_headsign_id: id })
}

function clearHeadsign() {
  emit('update:modelValue', { ...props.modelValue, stop_headsign_id: null })
}
</script>

<template>
  <div
    v-if="open"
    class="stcm"
    tabindex="-1"
    @focusout="onFocusOut"
    @mousedown.stop
    @keydown.escape="$emit('close')"
  >
    <div class="stcm__columns">
      <!-- ============ Left column: time + pickup + dropoff ============ -->
      <div class="stcm__col-left">
        <!-- ---- Arrival time ---- -->
        <div class="stcm__section">
          <div class="stcm__section-label">{{ t('schedule.arrival_time') }}</div>
          <div class="stcm__arrival-row">
            <input
              class="stcm__arrival-input"
              :class="{ 'stcm__arrival-input--error': arrivalError }"
              :value="arrivalInput"
              :disabled="disabled"
              type="text"
              inputmode="numeric"
              autocomplete="off"
              maxlength="6"
              :placeholder="departureTime || 'HH:MM'"
              @input="onArrivalInput"
              @blur="onArrivalBlur"
              @keydown.enter.prevent="onArrivalBlur"
              @keydown.escape="$emit('close')"
            />
            <button
              class="stcm__arrival-clear"
              :disabled="disabled"
              :title="t('common.delete')"
              @mousedown.prevent
              @click="clearArrivalToDeparture"
            >
              <md-icon>close</md-icon>
            </button>
            <span v-if="arrivalError" class="stcm__arrival-error-icon" :title="t('schedule.arrival_time_error')">
              <md-icon>error_outline</md-icon>
            </span>
          </div>
          <div v-if="arrivalError" class="stcm__arrival-error-msg">{{ t('schedule.arrival_time_error') }}</div>
        </div>

        <div class="stcm__divider" />

        <!-- ---- Einstieg (Pickup type) ---- -->
        <div class="stcm__section">
          <div class="stcm__section-label">
            <md-icon class="stcm__section-icon">arrow_upward</md-icon>
            {{ t('schedule.pickup_type') }}
          </div>
          <div class="stcm__options">
            <label
              v-for="opt in PICKUP_OPTIONS"
              :key="'pu-' + opt.value"
              class="stcm__option"
              :class="{ 'stcm__option--disabled': disabled }"
            >
              <input
                type="checkbox"
                class="stcm__checkbox"
                :disabled="disabled"
                :checked="(modelValue?.pickup_type ?? null) === opt.value"
                @change="!disabled && togglePickup(opt.value)"
              />
              <span class="stcm__option-label">{{ t(opt.labelKey) }}</span>
            </label>
          </div>
        </div>

        <div class="stcm__divider" />

        <!-- ---- Ausstieg (Drop-off type) ---- -->
        <div class="stcm__section">
          <div class="stcm__section-label">
            <md-icon class="stcm__section-icon">arrow_downward</md-icon>
            {{ t('schedule.drop_off_type') }}
          </div>
          <div class="stcm__options">
            <label
              v-for="opt in DROPOFF_OPTIONS"
              :key="'do-' + opt.value"
              class="stcm__option"
              :class="{ 'stcm__option--disabled': disabled }"
            >
              <input
                type="checkbox"
                class="stcm__checkbox"
                :disabled="disabled"
                :checked="(modelValue?.drop_off_type ?? null) === opt.value"
                @change="!disabled && toggleDropOff(opt.value)"
              />
              <span class="stcm__option-label">{{ t(opt.labelKey) }}</span>
            </label>
          </div>
        </div>
      </div><!-- /col-left -->

      <!-- vertical separator -->
      <div class="stcm__col-divider" />

      <!-- ============ Right column: headsign ============ -->
      <div class="stcm__col-right">
        <div class="stcm__section stcm__section--headsign">
          <div class="stcm__section-label">
            <md-icon class="stcm__section-icon">directions_bus</md-icon>
            {{ t('schedule.trip_headsign') }}
          </div>
          <div v-if="modelValue?.stop_headsign_id" class="stcm__hs-selected">
            {{ headsigns.find(h => h.id === modelValue.stop_headsign_id)?.name ?? '—' }}
          </div>
          <div class="stcm__hs-content">
            <input
              class="stcm__hs-search"
              v-model="headsignSearch"
              :placeholder="t('schedule.headsign_search')"
              :disabled="disabled"
              @click.stop
              @keydown.escape="$emit('close')"
            />
            <ul class="stcm__hs-list" role="listbox">
              <li v-if="filteredHeadsigns.length === 0" class="stcm__hs-empty">
                {{ t('schedule.add_stop_no_results') }}
              </li>
              <li
                v-for="h in filteredHeadsigns"
                :key="h.id"
                class="stcm__hs-item"
                :class="{ 'stcm__hs-item--selected': modelValue?.stop_headsign_id === h.id }"
                role="option"
                @mousedown.prevent="!disabled && selectHeadsign(h.id)"
              >
                {{ h.name }}
              </li>
            </ul>
            <button
              v-if="!disabled"
              class="stcm__hs-clear"
              type="button"
              @mousedown.prevent
              @click="clearHeadsign"
            >
              <md-icon>delete</md-icon>
              {{ t('schedule.headsign_delete') }}
            </button>
          </div>
        </div>
      </div><!-- /col-right -->
    </div><!-- /columns -->
  </div>
</template>

<style scoped>
.stcm {
  position: absolute;
  z-index: 300;
  background: #fff;
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 6px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
  padding: 0.25rem 0;
  outline: none;
}

/* ---- Two-column layout ---- */
.stcm__columns {
  display: flex;
  align-items: stretch;
}

.stcm__col-left {
  flex: 0 0 auto;
  min-width: 210px;
}

.stcm__col-divider {
  width: 1px;
  background: var(--md-sys-color-outline-variant, #e0e0e0);
  align-self: stretch;
  flex-shrink: 0;
}

.stcm__col-right {
  flex: 1 1 auto;
  min-width: 220px;
  display: flex;
  flex-direction: column;
}

/* ---- Sections ---- */
.stcm__section {
  padding: 0.375rem 0.625rem 0.4rem;
}

.stcm__section-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: var(--font-size-0, 0.8125rem);
  font-weight: 600;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  margin-bottom: 0.3rem;
  white-space: nowrap;
}

.stcm__section-icon {
  --md-icon-size: 0.9rem;
  font-size: 0.9rem;
  color: var(--md-sys-color-primary, #1f69e0);
}

.stcm__divider {
  height: 1px;
  background: var(--md-sys-color-outline-variant, #e0e0e0);
  margin: 0.1rem 0;
}

/* ---- Arrival input ---- */
.stcm__arrival-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.stcm__arrival-input {
  width: 80px;
  padding: 0.25rem 0.375rem;
  border: 1px solid var(--md-sys-color-outline, #bbb);
  border-radius: 4px;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-on-surface, #222);
  background: var(--md-sys-color-surface, #fff);
  outline: none;
  transition: border-color 0.15s;
  user-select: text;
  -webkit-user-select: text;
  cursor: text;
}

.stcm__arrival-input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
  background: var(--md-sys-color-surface-dim, #f5f5f5);
}

.stcm__arrival-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  background: none;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  color: var(--md-sys-color-error, #b00020);
  opacity: 0.7;
  transition: opacity 0.15s;
}

.stcm__arrival-clear:hover:not(:disabled) {
  opacity: 1;
}

.stcm__arrival-clear:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.stcm__arrival-clear md-icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
}

.stcm__arrival-input:focus {
  border-color: var(--md-sys-color-primary, #1f69e0);
}

.stcm__arrival-input--error {
  border-color: var(--md-sys-color-error, #b00020);
}

.stcm__arrival-error-icon {
  color: var(--md-sys-color-error, #b00020);
  display: inline-flex;
}

.stcm__arrival-error-icon md-icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
}

.stcm__arrival-error-msg {
  margin-top: 0.2rem;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-error, #b00020);
}

/* ---- Options (pickup/drop-off) ---- */
.stcm__options {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.stcm__option {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.2rem 0.125rem;
  cursor: pointer;
  border-radius: 3px;
  transition: background 0.1s;
  user-select: none;
}

.stcm__option--disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.stcm__option:not(.stcm__option--disabled):hover {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
}

.stcm__checkbox {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
  cursor: pointer;
  accent-color: var(--md-sys-color-primary, #1f69e0);
}

.stcm__option-label {
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #222);
}

/* ---- Headsign section ---- */
.stcm__section--headsign {
  padding: 0.375rem 0 0.25rem;
}

.stcm__section--headsign .stcm__section-label {
  padding: 0 0.625rem;
}

.stcm__section--headsign .stcm__hs-selected {
  margin-left: 0.625rem;
  margin-right: 0.625rem;
}

/* 4px side-padding wrapper for search / list / clear */
.stcm__hs-content {
  padding: 0 4px;
}

.stcm__hs-selected {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: var(--font-size-1, 0.875rem);
  font-weight: 600;
  color: var(--md-sys-color-primary, #1f69e0);
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
  border-radius: 4px;
  padding: 0.4rem 0.5rem;
  margin-top: 0.2rem;
  margin-bottom: 0.5rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stcm__hs-search {
  display: block;
  width: 100%;
  padding: 0.375rem 0.625rem;
  margin-bottom: 0;
  border: none;
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  background: transparent;
  color: var(--md-sys-color-on-surface, #222);
  outline: none;
  box-sizing: border-box;
}

.stcm__hs-search:focus {
  border-bottom-color: var(--md-sys-color-primary, #1f69e0);
}

.stcm__hs-search:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.stcm__hs-list {
  list-style: none;
  padding: 0.25rem 0;
  margin: 0;
  max-height: 200px;
  overflow-y: auto;
}

.stcm__hs-empty {
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-outline, #aaa);
  padding: 0.375rem 0.625rem;
}

.stcm__hs-item {
  padding: 0.325rem 0.625rem;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #222);
  border-radius: 0;
  transition: background 0.1s;
}

.stcm__hs-item:hover,
.stcm__hs-item--selected {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
}

.stcm__hs-clear {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  width: 100%;
  margin-top: 0;
  padding: 0.325rem 0.625rem;
  background: none;
  border: none;
  border-top: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-error, #b00020);
  cursor: pointer;
  transition: background 0.1s;
}

.stcm__hs-clear:hover {
  background: color-mix(in srgb, var(--md-sys-color-error, #b00020) 8%, transparent);
}

.stcm__hs-clear md-icon {
  --md-icon-size: 0.95rem;
  font-size: 0.95rem;
}
</style>
