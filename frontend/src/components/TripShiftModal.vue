<script setup>
/**
 * TripShiftModal — enter a time offset (hh:mm) and direction to shift trips.
 *
 * Props:
 *   modelValue — boolean — open state (v-model)
 *   count      — number  — number of selected trips (display only)
 *
 * Emits:
 *   update:modelValue
 *   confirm({ offsetMinutes: number, direction: 'forward'|'backward' })
 */
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/radio/radio.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  count:      { type: Number,  default: 0 },
})
const emit = defineEmits(['update:modelValue', 'confirm'])

const { t } = useI18n()

const dialogRef = ref(null)
const timeInput = ref('00:00')
const direction = ref('forward')
const submitAttempted = ref(false)
const fieldErrors = ref({
  timeInput: null,
})

const timeSchema = computed(() => z.string()
  .regex(/^\d{2}:\d{2}$/, t('schedule.shift_modal.validation_format'))
  .refine((value) => {
    const minutes = Number(value.slice(3, 5))
    return Number.isInteger(minutes) && minutes >= 0 && minutes <= 59
  }, t('schedule.shift_modal.validation_minutes'))
  .refine((value) => {
    const hours = Number(value.slice(0, 2))
    const minutes = Number(value.slice(3, 5))
    return (hours * 60 + minutes) >= 1
  }, t('schedule.shift_modal.validation_min'))
  .refine((value) => {
    const hours = Number(value.slice(0, 2))
    const minutes = Number(value.slice(3, 5))
    return (hours * 60 + minutes) <= 1439
  }, t('schedule.shift_modal.validation_max')))

const timeError = computed(() => fieldErrors.value.timeInput)

watch(() => props.modelValue, (val) => {
  const el = dialogRef.value
  if (!el) return
  if (val) {
    timeInput.value = '00:00'
    direction.value = 'forward'
    submitAttempted.value = false
    fieldErrors.value.timeInput = null
    el.show?.()
    selectMinutePart()
  } else {
    el.close?.()
  }
})

function handleClose() {
  emit('update:modelValue', false)
}

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function validateTimeField() {
  if (!timeInput.value.trim()) {
    fieldErrors.value.timeInput = t('schedule.shift_modal.validation_required')
    return false
  }
  const result = timeSchema.value.safeParse(timeInput.value.trim())
  fieldErrors.value.timeInput = result.success ? null : result.error.issues[0]?.message ?? null
  return result.success
}

function selectMinutePart() {
  requestAnimationFrame(() => {
    const textField = dialogRef.value?.querySelector('.shift-dialog__time-input')
    const input = textField?.shadowRoot?.querySelector('input')
    input?.focus()
    input?.setSelectionRange(3, 5)
  })
}

function handleConfirm() {
  submitAttempted.value = true
  if (!validateTimeField()) return
  const [h, m] = timeInput.value.trim().split(':').map(Number)
  emit('confirm', { offsetMinutes: h * 60 + m, direction: direction.value })
  emit('update:modelValue', false)
}

function handleInput(e) {
  let v = e.target.value.replace(/[^\d:]/g, '')
  if (v.length > 5) {
    v = v.slice(0, 5)
  }
  if (/^\d{2}$/.test(v)) {
    v = `${v}:`
  } else if (/^\d{3,4}$/.test(v)) {
    v = `${v.slice(0, 2)}:${v.slice(2)}`
  }
  timeInput.value = v
  clearFieldError('timeInput')
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="shift-dialog">
    <div slot="headline" class="shift-dialog__headline">
      <md-icon class="shift-dialog__headline-icon">swap_horiz</md-icon>
      <span class="shift-dialog__headline-title">{{ t('schedule.shift_modal.title') }}</span>
    </div>

    <div slot="content" class="shift-dialog__content">
      <div class="shift-dialog__section">
        <p class="shift-dialog__section-label">{{ t('schedule.shift_modal.section_time') }}</p>
        <md-outlined-text-field
          class="shift-dialog__time-input"
          :label="t('schedule.shift_modal.offset_label')"
          :value="timeInput"
          required
          :error="submitAttempted && !!timeError"
          :error-text="timeError ?? ''"
          placeholder="hh:mm"
          @input="handleInput"
          @keyup.enter="handleConfirm"
        />
        <p class="shift-dialog__hint">{{ t('schedule.shift_modal.offset_hint') }}</p>
      </div>

      <div class="shift-dialog__section">
        <p class="shift-dialog__section-label">{{ t('schedule.shift_modal.section_direction') }}</p>
        <div class="shift-dialog__direction-options">
          <label class="shift-dialog__radio-label">
            <md-radio
              name="shift-direction"
              value="forward"
              :checked="direction === 'forward'"
              @change="direction = 'forward'"
            />
            {{ t('schedule.shift_modal.direction_forward') }}
          </label>
          <label class="shift-dialog__radio-label">
            <md-radio
              name="shift-direction"
              value="backward"
              :checked="direction === 'backward'"
              @change="direction = 'backward'"
            />
            {{ t('schedule.shift_modal.direction_backward') }}
          </label>
        </div>
      </div>
    </div>

    <div slot="actions">
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleConfirm">
        {{ t('schedule.shift_modal.confirm') }}
      </md-filled-button>
    </div>
  </md-dialog>
</template>

<style scoped>
.shift-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.shift-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.shift-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.shift-dialog__headline-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.shift-dialog__content {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.75rem;
}

.shift-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.shift-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.shift-dialog__time-input {
  width: 100%;
}

.shift-dialog__direction-options {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}

.shift-dialog__radio-label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: var(--font-size-1, 0.875rem);
  cursor: pointer;
}

.shift-dialog__hint {
  margin: 0;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}
</style>
