<script setup>
/**
 * DayTypeViewModal — read-only view of a Tagesart with computed effective dates.
 *
 * The effective dates are pre-computed by the parent by:
 *   1. Generating all dates in [start_date, end_date] matching the weekday pattern.
 *   2. Applying each aux-calendar assignment:
 *      - junction_type 1 (zusätzlich): union dates
 *      - junction_type 2 (nicht):      subtract dates
 *      - junction_type 3 (nur):        restrict to intersection of all "nur" date sets
 *
 * Props:
 *   modelValue     — boolean     — open state (v-model)
 *   dayType        — object|null — {service_id, name, monday…sunday, start_date, end_date}
 *   effectiveDates — string[]    — pre-computed ISO dates ("YYYY-MM-DD") to display
 *   warning        — string|null — optional warning message (e.g. restrict conflict)
 *
 * Emits:
 *   update:modelValue — close signal
 */
import { ref, watch, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/icon/icon.js'
import CalendarPicker from './CalendarPicker.vue'

const props = defineProps({
  modelValue:     { type: Boolean, default: false },
  dayType:        { type: Object,  default: null },
  effectiveDates: { type: Array,   default: () => [] },
  warning:        { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()

const dialogRef      = ref(null)
const calendarPicker = ref(null)

watch(() => props.modelValue, async (val) => {
  const el = dialogRef.value
  if (!el) return
  if (val) {
    el.show?.()
    await nextTick()
    calendarPicker.value?.resetYear()
  } else {
    el.close?.()
  }
})

function handleClose() {
  emit('update:modelValue', false)
}

// ---- Weekday display ----
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

const activeDays = computed(() =>
  DAY_KEYS.filter(k => props.dayType?.[k] === 1)
)

function formatDate(iso) {
  if (!iso) return '—'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="day-type-view-dialog">

    <!-- Headline -->
    <div slot="headline" class="day-type-view-dialog__headline">
      <md-icon class="day-type-view-dialog__headline-icon">wb_sunny</md-icon>
      <span class="day-type-view-dialog__title">
        {{ dayType?.name || dayType?.service_id || t('day_type.view_title') }}
      </span>
    </div>

    <!-- Content -->
    <form slot="content" class="day-type-view-dialog__form" method="dialog">

      <!-- Betriebstage + Laufzeit info -->
      <div class="day-type-view-dialog__section">
        <p class="day-type-view-dialog__section-label">{{ t('day_type.section_info') }}</p>
        <div class="day-type-view-dialog__info-row">
          <!-- Weekday badges -->
          <div class="day-type-view-dialog__day-badges">
            <span
              v-for="key in DAY_KEYS"
              :key="key"
              :class="[
                'day-type-view-dialog__day-badge',
                DAY_WEEKEND[key]
                  ? 'day-type-view-dialog__day-badge--weekend'
                  : 'day-type-view-dialog__day-badge--weekday',
                activeDays.includes(key)
                  ? ''
                  : 'day-type-view-dialog__day-badge--inactive',
              ]"
            >{{ DAY_LABEL[key]() }}</span>
          </div>
          <!-- Date range -->
          <span class="day-type-view-dialog__date-range">
            {{ formatDate(dayType?.start_date) }}
            <md-icon class="day-type-view-dialog__date-range-arrow">arrow_forward</md-icon>
            {{ formatDate(dayType?.end_date) }}
          </span>
        </div>
      </div>

      <!-- Effective calendar -->
      <div class="day-type-view-dialog__section">
        <p class="day-type-view-dialog__section-label">{{ t('day_type.section_calendar') }}</p>
        <div v-if="warning" class="day-type-view-dialog__warning">
          <md-icon>warning</md-icon>
          <span>{{ warning }}</span>
        </div>
        <CalendarPicker
          ref="calendarPicker"
          :model-value="effectiveDates"
          :readonly="true"
        />
      </div>

    </form>

    <!-- Actions -->
    <div slot="actions">
      <md-text-button @click="handleClose">{{ t('common.close') }}</md-text-button>
    </div>

  </md-dialog>
</template>

<style scoped>
.day-type-view-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
  width: min(1516px, 98vw);
}

.day-type-view-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.day-type-view-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.day-type-view-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.day-type-view-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.5rem;
}

.day-type-view-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.day-type-view-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.day-type-view-dialog__info-row {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  flex-wrap: wrap;
}

.day-type-view-dialog__day-badges {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.day-type-view-dialog__day-badge {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.4;
}

.day-type-view-dialog__day-badge--weekday {
  background: rgba(31, 105, 224, 0.12);
  color: #1f69e0;
}

.day-type-view-dialog__day-badge--weekend {
  background: rgba(180, 80, 20, 0.12);
  color: #b45014;
}

.day-type-view-dialog__day-badge--inactive {
  background: rgba(0, 0, 0, 0.05);
  color: var(--md-sys-color-outline, #999);
  opacity: 0.45;
}

.day-type-view-dialog__date-range {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--md-sys-color-on-surface-variant, #555);
  white-space: nowrap;
}

.day-type-view-dialog__date-range-arrow {
  --md-icon-size: 1rem;
  font-size: 1rem;
  color: var(--md-sys-color-outline, #999);
}

.day-type-view-dialog__warning {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.625rem 0.875rem;
  background: rgba(234, 179, 8, 0.1);
  border: 1px solid rgba(234, 179, 8, 0.4);
  border-radius: 6px;
  font-size: 0.875rem;
  color: #92400e;
}

.day-type-view-dialog__warning md-icon {
  --md-icon-size: 1.1rem;
  font-size: 1.1rem;
  color: #d97706;
  flex-shrink: 0;
  margin-top: 0.05rem;
}
</style>
