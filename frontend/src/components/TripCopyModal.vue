<script setup>
/**
 * TripCopyModal — copy selected trips with optional time shift or headway generation.
 *
 * Props:
 *   modelValue — boolean       — open state (v-model)
 *   dayTypes   — Array<{service_id, name}> — available day types for override
 *
 * Emits:
 *   update:modelValue
 *   confirm(payload) — { mode, shift?, headway?, short_name_start?, short_name_step, service_id? }
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/select/outlined-select.js'
import '@material/web/select/select-option.js'
import '@material/web/radio/radio.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  dayTypes:   { type: Array,   default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'confirm'])
const { t } = useI18n()

const dialogRef = ref(null)

// ---- form state ----
const mode = ref('shift')  // 'shift' | 'headway'

// shift fields
const shiftTime      = ref('00:00')
const shiftDirection = ref('forward')

// headway fields
const headwayStart    = ref('')
const headwayEnd      = ref('')
const headwayMinutes  = ref('')

// short name fields
const shortNameStart = ref('')
const shortNameStep  = ref('')

// day type override
const selectedServiceId = ref('')

// ---- validation ----
const submitAttempted = ref(false)
const fieldErrors = ref({
  shiftTime:      null,
  headwayStart:   null,
  headwayEnd:     null,
  headwayMinutes: null,
  shortNameStart: null,
  shortNameStep:  null,
})

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

// hh:mm string schema builder
function timeStringSchema(requiredMsg) {
  return z.string()
    .min(1, requiredMsg)
    .regex(/^\d{2}:\d{2}$/, t('schedule.copy_modal.validation_time_format'))
    .refine((v) => Number(v.slice(3, 5)) <= 59, t('schedule.copy_modal.validation_time_minutes'))
}

function validateAll() {
  const errs = {
    shiftTime: null, headwayStart: null, headwayEnd: null,
    headwayMinutes: null, shortNameStart: null, shortNameStep: null,
  }

  if (mode.value === 'shift') {
    const schema = timeStringSchema(t('schedule.copy_modal.validation_offset_required'))
      .refine((v) => {
        const [h, m] = v.split(':').map(Number)
        return h * 60 + m >= 1
      }, t('schedule.copy_modal.validation_offset_min'))
      .refine((v) => {
        const [h, m] = v.split(':').map(Number)
        return h * 60 + m <= 1439
      }, t('schedule.copy_modal.validation_offset_max'))
    const r = schema.safeParse(shiftTime.value.trim())
    if (!r.success) errs.shiftTime = r.error.issues[0]?.message ?? null
  } else {
    const startR = timeStringSchema(t('schedule.copy_modal.validation_start_required')).safeParse(headwayStart.value.trim())
    if (!startR.success) errs.headwayStart = startR.error.issues[0]?.message ?? null

    const endR = timeStringSchema(t('schedule.copy_modal.validation_end_required')).safeParse(headwayEnd.value.trim())
    if (!endR.success) errs.headwayEnd = endR.error.issues[0]?.message ?? null

    const hwSchema = z.string()
      .min(1, t('schedule.copy_modal.validation_headway_required'))
      .refine((v) => /^\d+$/.test(v.trim()), t('schedule.copy_modal.validation_headway_integer'))
      .refine((v) => Number(v) >= 1,    t('schedule.copy_modal.validation_headway_positive'))
      .refine((v) => Number(v) <= 1439, t('schedule.copy_modal.validation_headway_max'))
    const hwR = hwSchema.safeParse(headwayMinutes.value.trim())
    if (!hwR.success) errs.headwayMinutes = hwR.error.issues[0]?.message ?? null
  }

  if (shortNameStart.value.trim() !== '') {
    const r = z.string()
      .refine((v) => /^-?\d+$/.test(v.trim()), t('schedule.copy_modal.validation_short_name_integer'))
      .safeParse(shortNameStart.value.trim())
    if (!r.success) errs.shortNameStart = r.error.issues[0]?.message ?? null
  }

  if (shortNameStep.value.trim() !== '') {
    const r = z.string()
      .refine((v) => /^\d+$/.test(v.trim()) && Number(v) >= 1, t('schedule.copy_modal.validation_short_name_step_positive'))
      .safeParse(shortNameStep.value.trim())
    if (!r.success) errs.shortNameStep = r.error.issues[0]?.message ?? null
  }

  fieldErrors.value = errs
  return Object.values(errs).every((e) => e === null)
}

// ---- dialog open/close ----
watch(() => props.modelValue, (val) => {
  const el = dialogRef.value
  if (!el) return
  if (val) {
    // reset
    mode.value           = 'shift'
    shiftTime.value      = '00:00'
    shiftDirection.value = 'forward'
    headwayStart.value   = ''
    headwayEnd.value     = ''
    headwayMinutes.value = ''
    shortNameStart.value = ''
    shortNameStep.value  = ''
    selectedServiceId.value = ''
    submitAttempted.value = false
    fieldErrors.value = { shiftTime: null, headwayStart: null, headwayEnd: null, headwayMinutes: null, shortNameStart: null, shortNameStep: null }
    el.show?.()
    selectShiftMinutes()
  } else {
    el.close?.()
  }
})

function selectShiftMinutes() {
  requestAnimationFrame(() => {
    const tf = dialogRef.value?.querySelector('.copy-modal__shift-time')
    const input = tf?.shadowRoot?.querySelector('input')
    input?.focus()
    input?.setSelectionRange(3, 5)
  })
}

function handleClose() {
  emit('update:modelValue', false)
}

function handleConfirm() {
  submitAttempted.value = true
  if (!validateAll()) return

  const payload = {
    mode: mode.value,
    short_name_start: shortNameStart.value.trim() !== '' ? shortNameStart.value.trim() : null,
    short_name_step:  shortNameStep.value.trim()  !== '' ? parseInt(shortNameStep.value)  : 1,
    service_id:       selectedServiceId.value !== '' ? selectedServiceId.value : null,
  }

  if (mode.value === 'shift') {
    const [h, m] = shiftTime.value.trim().split(':').map(Number)
    payload.shift = { offset_minutes: h * 60 + m, direction: shiftDirection.value }
  } else {
    payload.headway = {
      start_time:      shiftToGtfs(headwayStart.value.trim()),
      end_time:        shiftToGtfs(headwayEnd.value.trim()),
      headway_minutes: parseInt(headwayMinutes.value.trim()),
    }
  }

  emit('confirm', payload)
  emit('update:modelValue', false)
}

// hh:mm → H:MM:SS (GTFS)
function shiftToGtfs(v) {
  const [h, m] = v.split(':').map(Number)
  return `${h}:${String(m).padStart(2, '0')}:00`
}

// ---- input handlers ----
function handleTimeInput(field, e) {
  let v = e.target.value.replace(/[^\d:]/g, '')
  if (v.length > 5) v = v.slice(0, 5)
  if (/^\d{2}$/.test(v))     v = `${v}:`
  else if (/^\d{3,4}$/.test(v)) v = `${v.slice(0, 2)}:${v.slice(2)}`
  if (field === 'shiftTime')     shiftTime.value      = v
  else if (field === 'start')    headwayStart.value   = v
  else if (field === 'end')      headwayEnd.value     = v
  clearFieldError(field === 'shiftTime' ? 'shiftTime' : field === 'start' ? 'headwayStart' : 'headwayEnd')
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="copy-modal">
    <div slot="headline" class="copy-modal__headline">
      <md-icon class="copy-modal__headline-icon">content_copy</md-icon>
      <span class="copy-modal__headline-title">{{ t('schedule.copy_modal.title') }}</span>
    </div>

    <div slot="content" class="copy-modal__content">

      <!-- Section: Kurzname -->
      <div class="copy-modal__section">
        <p class="copy-modal__section-label">{{ t('schedule.copy_modal.section_short_name') }}</p>
        <div class="copy-modal__row copy-modal__row--2col">
          <md-outlined-text-field
            class="copy-modal__field"
            :label="t('schedule.copy_modal.field_short_name_start')"
            :value="shortNameStart"
            :error="submitAttempted && !!fieldErrors.shortNameStart"
            :error-text="fieldErrors.shortNameStart ?? ''"
            inputmode="numeric"
            @input="shortNameStart = $event.target.value; clearFieldError('shortNameStart')"
          />
          <md-outlined-text-field
            class="copy-modal__field"
            :label="t('schedule.copy_modal.field_short_name_step')"
            :value="shortNameStep"
            :error="submitAttempted && !!fieldErrors.shortNameStep"
            :error-text="fieldErrors.shortNameStep ?? ''"
            inputmode="numeric"
            :placeholder="'1'"
            @input="shortNameStep = $event.target.value; clearFieldError('shortNameStep')"
          />
        </div>
        <p class="copy-modal__hint">{{ t('schedule.copy_modal.short_name_hint') }}</p>
      </div>

      <!-- Section: Modus -->
      <div class="copy-modal__section">
        <p class="copy-modal__section-label">{{ t('schedule.copy_modal.section_mode') }}</p>
        <div class="copy-modal__radios-inline">
          <label class="copy-modal__radio-label">
            <md-radio name="copy-mode" value="shift" :checked="mode === 'shift'" @change="mode = 'shift'" />
            {{ t('schedule.copy_modal.mode_shift') }}
          </label>
          <label class="copy-modal__radio-label">
            <md-radio name="copy-mode" value="headway" :checked="mode === 'headway'" @change="mode = 'headway'" />
            {{ t('schedule.copy_modal.mode_headway') }}
          </label>
        </div>
      </div>

      <!-- Section: Verschieben -->
      <div v-if="mode === 'shift'" class="copy-modal__section">
        <p class="copy-modal__section-label">{{ t('schedule.copy_modal.section_shift') }}</p>
        <md-outlined-text-field
          class="copy-modal__field copy-modal__shift-time"
          :label="t('schedule.copy_modal.field_offset')"
          :value="shiftTime"
          required
          :error="submitAttempted && !!fieldErrors.shiftTime"
          :error-text="fieldErrors.shiftTime ?? ''"
          placeholder="hh:mm"
          @input="handleTimeInput('shiftTime', $event)"
          @keyup.enter="handleConfirm"
        />
        <p class="copy-modal__hint">{{ t('schedule.copy_modal.offset_hint') }}</p>
        <div class="copy-modal__radios-inline">
          <label class="copy-modal__radio-label">
            <md-radio name="copy-direction" value="forward" :checked="shiftDirection === 'forward'" @change="shiftDirection = 'forward'" />
            {{ t('schedule.copy_modal.direction_forward') }}
          </label>
          <label class="copy-modal__radio-label">
            <md-radio name="copy-direction" value="backward" :checked="shiftDirection === 'backward'" @change="shiftDirection = 'backward'" />
            {{ t('schedule.copy_modal.direction_backward') }}
          </label>
        </div>
      </div>

      <!-- Section: Takt -->
      <div v-else class="copy-modal__section">
        <p class="copy-modal__section-label">{{ t('schedule.copy_modal.section_headway') }}</p>
        <div class="copy-modal__row copy-modal__row--3col">
          <md-outlined-text-field
            class="copy-modal__field"
            :label="t('schedule.copy_modal.field_start_time')"
            :value="headwayStart"
            required
            :error="submitAttempted && !!fieldErrors.headwayStart"
            :error-text="fieldErrors.headwayStart ?? ''"
            placeholder="hh:mm"
            @input="handleTimeInput('start', $event)"
            @keyup.enter="handleConfirm"
          />
          <md-outlined-text-field
            class="copy-modal__field"
            :label="t('schedule.copy_modal.field_end_time')"
            :value="headwayEnd"
            required
            :error="submitAttempted && !!fieldErrors.headwayEnd"
            :error-text="fieldErrors.headwayEnd ?? ''"
            placeholder="hh:mm"
            @input="handleTimeInput('end', $event)"
            @keyup.enter="handleConfirm"
          />
          <md-outlined-text-field
            class="copy-modal__field"
            :label="t('schedule.copy_modal.field_headway')"
            :value="headwayMinutes"
            required
            :error="submitAttempted && !!fieldErrors.headwayMinutes"
            :error-text="fieldErrors.headwayMinutes ?? ''"
            inputmode="numeric"
            placeholder="z. B. 30"
            @input="headwayMinutes = $event.target.value; clearFieldError('headwayMinutes')"
            @keyup.enter="handleConfirm"
          />
        </div>
        <p class="copy-modal__hint">{{ t('schedule.copy_modal.time_hint') }}</p>
      </div>

      <!-- Section: Tagesart -->
      <div class="copy-modal__section">
        <p class="copy-modal__section-label">{{ t('schedule.copy_modal.section_day_type') }}</p>
        <md-outlined-select
          class="copy-modal__field"
          :label="t('schedule.copy_modal.field_day_type')"
          @change="selectedServiceId = $event.target.value"
        >
          <md-select-option value="" :selected="selectedServiceId === ''">
            <div slot="headline">{{ t('schedule.copy_modal.day_type_keep') }}</div>
          </md-select-option>
          <md-select-option
            v-for="dt in dayTypes"
            :key="dt.service_id"
            :value="dt.service_id"
            :selected="selectedServiceId === dt.service_id"
          >
            <div slot="headline">{{ dt.name ?? dt.service_id }}</div>
          </md-select-option>
        </md-outlined-select>
      </div>

    </div>

    <div slot="actions">
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleConfirm">
        {{ t('schedule.copy_modal.confirm') }}
      </md-filled-button>
    </div>
  </md-dialog>
</template>

<style scoped>
.copy-modal {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.copy-modal__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.copy-modal__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.copy-modal__headline-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.copy-modal__content {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.25rem;
}

.copy-modal__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.copy-modal__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.copy-modal__row {
  display: flex;
  gap: 1rem;
}

.copy-modal__row--2col > * {
  flex: 1 1 0;
  min-width: 0;
}

.copy-modal__row--3col > * {
  flex: 1 1 0;
  min-width: 0;
}

.copy-modal__field {
  width: 100%;
}

.copy-modal__radios-inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 1rem;
}

.copy-modal__radio-label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: var(--font-size-1, 0.875rem);
  cursor: pointer;
}

.copy-modal__hint {
  margin: 0;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}
</style>
