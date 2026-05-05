<script setup>
/**
 * AuxCalendarViewModal — read-only view of a Hilfskalender.
 *
 * Props:
 *   modelValue  — boolean      — open state (v-model)
 *   auxCalendar — object|null  — {id, name}
 *   dates       — string[]     — ISO dates ("YYYY-MM-DD") to display
 *
 * Emits:
 *   update:modelValue — close signal
 */
import { ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/icon/icon.js'
import CalendarPicker from './CalendarPicker.vue'

const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  auxCalendar: { type: Object,  default: null },
  dates:       { type: Array,   default: () => [] },
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
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="aux-cal-view-dialog">

    <!-- Headline -->
    <div slot="headline" class="aux-cal-view-dialog__headline">
      <md-icon class="aux-cal-view-dialog__headline-icon">date_range</md-icon>
      <span class="aux-cal-view-dialog__title">
        {{ auxCalendar?.name ?? t('aux_calendar.view_title') }}
      </span>
    </div>

    <!-- Content -->
    <form slot="content" class="aux-cal-view-dialog__form" method="dialog">
      <div class="aux-cal-view-dialog__section">
        <p class="aux-cal-view-dialog__section-label">{{ t('aux_calendar.section_dates') }}</p>
        <CalendarPicker
          ref="calendarPicker"
          :model-value="dates"
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
.aux-cal-view-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
  width: min(1516px, 98vw);
}

.aux-cal-view-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.aux-cal-view-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.aux-cal-view-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.aux-cal-view-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.5rem;
}

.aux-cal-view-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.aux-cal-view-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}
</style>
