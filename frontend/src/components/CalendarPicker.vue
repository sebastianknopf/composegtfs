<script setup>
/**
 * CalendarPicker — reusable year-calendar picker component.
 *
 * Props:
 *   modelValue  — string[]  — selected ISO dates ("YYYY-MM-DD")
 *   readonly    — boolean   — if true, days/months cannot be toggled,
 *                             but the year can still be navigated freely
 *
 * Emits:
 *   update:modelValue — string[] — emitted only when not readonly
 *
 * Exposed:
 *   resetYear() — resets the visible year to the current calendar year
 */
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: { type: Array,   default: () => [] },
  readonly:   { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const { t, locale } = useI18n()

// ---- Year navigation ----
const displayYear = ref(new Date().getFullYear())
function prevYear() { displayYear.value-- }
function nextYear() { displayYear.value++ }

/** Resets the visible year to the current calendar year. Call via template ref. */
function resetYear() { displayYear.value = new Date().getFullYear() }
defineExpose({ resetYear })

// ---- Derived counts ----
const countInYear = computed(() => {
  const prefix = String(displayYear.value) + '-'
  return props.modelValue.filter(d => d.startsWith(prefix)).length
})
const totalCount = computed(() => props.modelValue.length)

// ---- Calendar helpers ----
const MONTH_INDICES = Array.from({ length: 12 }, (_, i) => i)

// Weekday names Mon–Sun, localized, trailing dots stripped
const weekdayNames = computed(() =>
  Array.from({ length: 7 }, (_, i) => {
    const d = new Date(2000, 0, 3 + i) // Jan 3 2000 is Monday
    return new Intl.DateTimeFormat(locale.value, { weekday: 'short' }).format(d).replace(/\.$/, '')
  })
)

// Month abbreviations, localized
const monthAbbrs = computed(() =>
  Array.from({ length: 12 }, (_, i) =>
    new Intl.DateTimeFormat(locale.value, { month: 'short' }).format(new Date(2000, i, 1))
  )
)

function firstWeekdayOffset(year, monthIndex) {
  return (new Date(year, monthIndex, 1).getDay() + 6) % 7
}

function daysInMonth(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0).getDate()
}

// Dynamic: compute the maximum number of weeks needed by any month in the year,
// so that no trailing-empty columns are wasted.
const weekCols = computed(() => {
  const maxWeeks = Math.max(...MONTH_INDICES.map(mi => {
    const offset = firstWeekdayOffset(displayYear.value, mi)
    const count  = daysInMonth(displayYear.value, mi)
    return Math.ceil((offset + count) / 7)
  }))
  return maxWeeks * 7
})

// Grid style — reactive so it updates when weekCols changes (year navigation).
const gridStyle = computed(() => ({
  gridTemplateColumns: `36px repeat(${weekCols.value}, 32px)`,
}))

// Returns exactly weekCols.value items per month row.
function monthCells(year, monthIndex) {
  const cols   = weekCols.value
  const offset = firstWeekdayOffset(year, monthIndex)
  const count  = daysInMonth(year, monthIndex)
  return Array.from({ length: cols }, (_, i) => {
    const day = i - offset + 1
    return (day >= 1 && day <= count) ? day : null
  })
}

function dateKey(year, monthIndex, day) {
  const m = String(monthIndex + 1).padStart(2, '0')
  const d = String(day).padStart(2, '0')
  return `${year}-${m}-${d}`
}

// O(1) lookup set derived from modelValue
const selectedSet = computed(() => new Set(props.modelValue))

function isSelected(monthIndex, day) {
  return selectedSet.value.has(dateKey(displayYear.value, monthIndex, day))
}

function toggleDay(monthIndex, day) {
  if (props.readonly) return
  const key  = dateKey(displayYear.value, monthIndex, day)
  const next = new Set(selectedSet.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  emit('update:modelValue', [...next].sort())
}

function toggleMonth(monthIndex) {
  if (props.readonly) return
  const cells      = monthCells(displayYear.value, monthIndex)
  const validDays  = cells.filter(d => d !== null)
  const allSelected = validDays.every(d => isSelected(monthIndex, d))
  const next = new Set(selectedSet.value)
  for (const day of validDays) {
    const key = dateKey(displayYear.value, monthIndex, day)
    if (allSelected) next.delete(key)
    else next.add(key)
  }
  emit('update:modelValue', [...next].sort())
}
</script>

<template>
  <div class="cal-picker">

    <!-- Year navigator -->
    <div class="cal-picker__year-nav">
      <button type="button" class="cal-picker__year-btn" :title="t('aux_calendar.prev_year')" @click="prevYear">
        <md-icon>chevron_left</md-icon>
      </button>
      <span class="cal-picker__year-label">{{ displayYear }}</span>
      <button type="button" class="cal-picker__year-btn" :title="t('aux_calendar.next_year')" @click="nextYear">
        <md-icon>chevron_right</md-icon>
      </button>
      <span class="cal-picker__year-count">
        {{ t('aux_calendar.year_count', { count: countInYear }) }}
      </span>
      <span v-if="totalCount !== countInYear" class="cal-picker__total-count">
        {{ t('aux_calendar.total_count', { count: totalCount }) }}
      </span>
    </div>

    <!-- Calendar grid: rows=months, columns=weekdays (Mo–So × dynamic weeks) -->
    <div class="cal-picker__scroll">
      <div class="cal-picker__grid" :style="gridStyle" role="grid" :aria-label="t('aux_calendar.grid_label')">

        <!-- Header row: corner + weekday-name headers -->
        <div class="cal-picker__corner" aria-hidden="true"></div>
        <div
          v-for="col in weekCols"
          :key="`h-${col}`"
          :class="[
            'cal-picker__day-header',
            (col - 1) % 7 >= 5 ? 'cal-picker__day-header--weekend' : '',
          ]"
          aria-hidden="true"
        >{{ weekdayNames[(col - 1) % 7] }}</div>

        <!-- Month rows -->
        <template v-for="mi in MONTH_INDICES" :key="mi">
          <button
            type="button"
            class="cal-picker__month-label"
            :class="{ 'cal-picker__month-label--readonly': readonly }"
            :title="monthAbbrs[mi]"
            @click="toggleMonth(mi)"
          >
            {{ monthAbbrs[mi] }}
          </button>
          <button
            v-for="(day, ci) in monthCells(displayYear, mi)"
            :key="`${mi}-${ci}`"
            type="button"
            :disabled="day === null || readonly || undefined"
            :class="[
              'cal-picker__cell',
              ci % 7 >= 5 ? 'cal-picker__cell--weekend-col' : '',
              day === null
                ? 'cal-picker__cell--empty'
                : isSelected(mi, day)
                  ? 'cal-picker__cell--selected'
                  : 'cal-picker__cell--valid',
              readonly ? 'cal-picker__cell--readonly' : '',
            ]"
            :aria-pressed="day !== null && isSelected(mi, day) ? 'true' : undefined"
            :aria-label="day !== null ? `${monthAbbrs[mi]} ${day}` : undefined"
            @click="day !== null && toggleDay(mi, day)"
          >{{ day !== null ? day : '' }}</button>
        </template>

      </div>
    </div>
  </div>
</template>

<style scoped>
.cal-picker {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

/* ---- Year navigator ---- */
.cal-picker__year-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.cal-picker__year-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: none;
  border: 1px solid var(--md-sys-color-outline-variant, #ccc);
  border-radius: 4px;
  cursor: pointer;
  color: var(--md-sys-color-on-surface, #222);
  transition: background 0.15s;
}
.cal-picker__year-btn:hover {
  background: var(--md-sys-color-surface-variant, #f0f0f0);
}
.cal-picker__year-btn md-icon {
  --md-icon-size: 1.1rem;
  font-size: 1.1rem;
}

.cal-picker__year-label {
  font-size: 1rem;
  font-weight: 600;
  min-width: 3rem;
  text-align: center;
  color: var(--md-sys-color-on-surface, #222);
}

.cal-picker__year-count {
  margin-left: 0.75rem;
  font-size: 0.8125rem;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}

.cal-picker__total-count {
  font-size: 0.8125rem;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}
.cal-picker__total-count::before {
  content: '·';
  margin-right: 0.5rem;
}

/* ---- Calendar grid ---- */
/* Outer scroll wrapper enables horizontal scrolling on narrow screens */
.cal-picker__scroll {
  overflow-x: auto;
}

/* Grid columns are set dynamically via inline style */
.cal-picker__grid {
  display: grid;
  gap: 2px;
  width: max-content;
}

/* Header cells */
.cal-picker__corner {
  height: 20px;
}

.cal-picker__day-header {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  font-size: 0.5625rem;
  font-weight: 700;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  border-radius: 2px;
}

.cal-picker__day-header--weekend {
  background: rgba(0, 0, 0, 0.045);
  color: var(--md-sys-color-on-surface-variant, #666);
}

/* Month label column */
.cal-picker__month-label {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  height: 32px;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  white-space: nowrap;
  overflow: hidden;
  background: none;
  border: none;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s;
}
.cal-picker__month-label:not(.cal-picker__month-label--readonly):hover {
  background: var(--md-sys-color-surface-variant, #e8eaf0);
  color: var(--md-sys-color-primary, #1f69e0);
}
.cal-picker__month-label--readonly {
  cursor: default;
  pointer-events: none;
}

/* Day cells */
.cal-picker__cell {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 3px;
  border: none;
  padding: 0;
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  transition: background 0.1s;
}

.cal-picker__cell--valid {
  background: var(--md-sys-color-surface-variant, #f0f2f8);
  color: var(--md-sys-color-on-surface, #333);
}
.cal-picker__cell--valid:not(.cal-picker__cell--readonly):hover {
  background: rgba(31, 105, 224, 0.18);
}

/* Weekend tint on non-selected valid cells */
.cal-picker__cell--weekend-col.cal-picker__cell--valid {
  background: rgba(0, 0, 0, 0.055);
}
.cal-picker__cell--weekend-col.cal-picker__cell--valid:not(.cal-picker__cell--readonly):hover {
  background: rgba(31, 105, 224, 0.18);
}

.cal-picker__cell--selected {
  background: var(--md-sys-color-primary, #1f69e0);
  color: #fff;
  font-weight: 700;
}
.cal-picker__cell--selected:not(.cal-picker__cell--readonly):hover {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 85%, #000);
}

.cal-picker__cell--empty {
  background: transparent;
  cursor: default;
  pointer-events: none;
  color: transparent;
}
/* Weekend tint on empty cells */
.cal-picker__cell--weekend-col.cal-picker__cell--empty {
  background: rgba(0, 0, 0, 0.025);
}

/* Readonly: selected cells keep highlight but no hover effect */
.cal-picker__cell--readonly:not(.cal-picker__cell--empty) {
  cursor: default;
}
</style>
