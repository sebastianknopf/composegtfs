<script setup>
/**
 * TripGlobalIdGeneratorModal — enter a preset template to generate global IDs
 * for selected trips. Placeholder chips insert placeholder tokens at the cursor.
 *
 * Props:
 *   modelValue — boolean — open state (v-model)
 *   count      — number  — number of selected trips (display only)
 *
 * Emits:
 *   update:modelValue
 *   confirm({ preset: string, overwrite: boolean })
 */
import { ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/checkbox/checkbox.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  count:      { type: Number,  default: 0 },
})
const emit = defineEmits(['update:modelValue', 'confirm'])

const { t } = useI18n()

const dialogRef     = ref(null)
const presetFieldRef = ref(null)
const preset        = ref('')
const overwrite     = ref(false)
const submitAttempted = ref(false)
const fieldErrors   = ref({ preset: null })

const PLACEHOLDERS = [
  { key: 'agency_id',        value: '{AgencyId}' },
  { key: 'agency_global_id', value: '{AgencyGlobalId}' },
  { key: 'line_id',          value: '{LineId}' },
  { key: 'line_global_id',   value: '{LineGlobalId}' },
  { key: 'day_type_id',      value: '{DayTypeId}' },
  { key: 'trip_short_name',  value: '{TripShortName}' },
  { key: 'generated_number', value: '{GeneratedNumber}' },
  { key: 'uuid',             value: '{UUID}' },
]

function _getSchema() {
  return z.string()
    .min(1, t('schedule.global_id_generator.validation_preset_required'))
    .max(255, t('schedule.global_id_generator.validation_preset_too_long'))
}

watch(() => props.modelValue, (val) => {
  const el = dialogRef.value
  if (!el) return
  if (val) {
    preset.value = ''
    overwrite.value = false
    submitAttempted.value = false
    fieldErrors.value.preset = null
    el.show?.()
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

function validatePreset() {
  const result = _getSchema().safeParse(preset.value)
  fieldErrors.value.preset = result.success ? null : (result.error.issues[0]?.message ?? null)
  return result.success
}

function _getInput() {
  return presetFieldRef.value?.shadowRoot?.querySelector('input') ?? null
}

/**
 * Insert a placeholder token at the current cursor position.
 * @mousedown.prevent on the chip keeps focus inside the text field, so
 * selectionStart is still valid when this click handler runs.
 */
function insertPlaceholder(placeholder) {
  const input = _getInput()
  const pos = input ? (input.selectionStart ?? preset.value.length) : preset.value.length
  preset.value = preset.value.slice(0, pos) + placeholder + preset.value.slice(pos)
  const newPos = pos + placeholder.length
  clearFieldError('preset')
  nextTick(() => {
    const inp = _getInput()
    if (inp) {
      inp.focus()
      inp.setSelectionRange(newPos, newPos)
    }
  })
}

function handleConfirm() {
  submitAttempted.value = true
  if (!validatePreset()) return
  emit('confirm', { preset: preset.value.trim(), overwrite: overwrite.value })
  emit('update:modelValue', false)
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="global-id-dialog">
    <div slot="headline" class="global-id-dialog__headline">
      <md-icon class="global-id-dialog__headline-icon">badge</md-icon>
      <span class="global-id-dialog__headline-title">{{ t('schedule.global_id_generator.title') }}</span>
    </div>

    <div slot="content" class="global-id-dialog__content">
      <p v-if="count > 0" class="global-id-dialog__description">
        {{ t('schedule.global_id_generator.description', { count }) }}
      </p>

      <div class="global-id-dialog__section">
        <p class="global-id-dialog__section-label">{{ t('schedule.global_id_generator.section_preset') }}</p>
        <md-outlined-text-field
          ref="presetFieldRef"
          class="global-id-dialog__preset-field"
          :label="t('schedule.global_id_generator.preset_label')"
          :value="preset"
          required
          :error="submitAttempted && !!fieldErrors.preset"
          :error-text="fieldErrors.preset ?? ''"
          @input="e => { preset = e.target.value; clearFieldError('preset') }"
          @keyup.enter="handleConfirm"
        />
        <div class="global-id-dialog__chips">
          <button
            v-for="ph in PLACEHOLDERS"
            :key="ph.key"
            class="global-id-dialog__chip"
            type="button"
            @mousedown.prevent
            @click="insertPlaceholder(ph.value)"
          >{{ t('schedule.global_id_generator.placeholder_' + ph.key) }}</button>
        </div>
      </div>

      <div class="global-id-dialog__section">
        <p class="global-id-dialog__section-label">{{ t('schedule.global_id_generator.section_options') }}</p>
        <label class="global-id-dialog__checkbox-label">
          <md-checkbox
            :checked="overwrite"
            @change="overwrite = $event.target.checked"
          />
          <span>{{ t('schedule.global_id_generator.overwrite_label') }}</span>
        </label>
      </div>
    </div>

    <div slot="actions" class="global-id-dialog__actions">
      <span class="global-id-dialog__error-area">
        {{ submitAttempted && fieldErrors.preset ? fieldErrors.preset : '' }}
      </span>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleConfirm">
        {{ t('schedule.global_id_generator.generate_button') }}
      </md-filled-button>
    </div>
  </md-dialog>
</template>

<style scoped>
.global-id-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.global-id-dialog__headline-icon {
  color: var(--md-sys-color-primary);
}

.global-id-dialog__content {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  min-width: 340px;
}

.global-id-dialog__description {
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface-variant);
  margin: 0;
}

.global-id-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.global-id-dialog__section-label {
  font-size: var(--font-size-0, 0.8125rem);
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.global-id-dialog__preset-field {
  width: 100%;
}

.global-id-dialog__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.global-id-dialog__chip {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.625rem;
  border-radius: 1rem;
  border: 1px solid var(--md-sys-color-outline);
  background: transparent;
  cursor: pointer;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface);
  font-family: inherit;
  line-height: 1.5;
  transition: background 100ms;
}

.global-id-dialog__chip:hover {
  background: color-mix(in srgb, var(--md-sys-color-on-surface) 8%, transparent);
}

.global-id-dialog__chip:active {
  background: color-mix(in srgb, var(--md-sys-color-on-surface) 12%, transparent);
}

.global-id-dialog__checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface);
}

.global-id-dialog__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.global-id-dialog__error-area {
  flex: 1;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-error);
}
</style>
