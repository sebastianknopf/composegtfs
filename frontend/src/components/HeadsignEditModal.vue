<script setup>
/**
 * HeadsignEditModal — dialog for creating or editing a headsign.
 *
 * Props:
 *   modelValue — boolean      — open state (v-model)
 *   headsign   — object|null  — pre-filled data when editing; null for new entry
 *   error      — string|null  — server-level error message
 *
 * Emits:
 *   update:modelValue
 *   save(data)  — emits the form data when the user confirms
 */
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  headsign:   { type: Object,  default: null },
  error:      { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

const isEdit = computed(() => !!props.headsign)

// ---- Form state ----
function emptyForm() {
  return { name: '', number: '', destination: '' }
}

function emptyErrors() {
  return { name: null, number: null, destination: null }
}

const form        = ref(emptyForm())
const fieldErrors = ref(emptyErrors())
const dialogRef   = ref(null)

// ---- Validation schema ----
function buildSchema() {
  return z.object({
    name: z
      .string()
      .min(1, t('headsigns.validation_name_required'))
      .max(255, t('headsigns.validation_name_too_long')),
    number: z
      .string()
      .regex(/^\d*$/, t('headsigns.validation_number_not_numeric'))
      .max(10, t('headsigns.validation_number_too_long'))
      .optional(),
    destination: z
      .string()
      .min(1, t('headsigns.validation_destination_required'))
      .max(255, t('headsigns.validation_destination_too_long')),
  })
}

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function validate() {
  fieldErrors.value = emptyErrors()
  const result = buildSchema().safeParse({
    name:        form.value.name.trim(),
    number:      form.value.number.trim() || undefined,
    destination: form.value.destination.trim(),
  })
  if (result.success) return true
  for (const issue of result.error.issues) {
    const field = issue.path?.[0]
    if (field && fieldErrors.value[field] == null) {
      fieldErrors.value[field] = issue.message
    }
  }
  return false
}

// ---- Dialog open/close ----
watch(() => props.modelValue, (val) => {
  const el = dialogRef.value
  if (val) {
    form.value = props.headsign
      ? {
          name:        props.headsign.name        ?? '',
          number:      props.headsign.number?.toString() ?? '',
          destination: props.headsign.destination  ?? '',
        }
      : emptyForm()
    fieldErrors.value = emptyErrors()
    requestAnimationFrame(() => el?.show?.())
  } else {
    el?.close?.()
  }
})

function handleClose() {
  emit('update:modelValue', false)
}

function handleSave() {
  if (!validate()) return
  const nullable = (v) => v.trim() === '' ? null : v.trim()
  const toInt    = (v) => { const n = nullable(v); return n !== null ? parseInt(n, 10) : null }
  emit('save', {
    name:        form.value.name.trim(),
    number:      toInt(form.value.number),
    destination: form.value.destination.trim(),
  })
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose">
    <div slot="headline" class="headsign-edit-dialog__headline">
      <md-icon class="headsign-edit-dialog__headline-icon">directions_bus</md-icon>
      {{ isEdit ? t('headsigns.edit_title_edit') : t('headsigns.edit_title_create') }}
    </div>

    <form slot="content" class="headsign-form" @submit.prevent="handleSave">
      <!-- Identification -->
      <p class="form-section-label">{{ t('headsigns.section_identification') }}</p>

      <md-outlined-text-field
        :label="t('headsigns.field_name')"
        :value="form.name"
        :error="!!fieldErrors.name"
        :error-text="fieldErrors.name ?? ''"
        required
        @input="form.name = $event.target.value; clearFieldError('name')"
      />

      <md-outlined-text-field
        :label="t('headsigns.field_number')"
        :value="form.number"
        :error="!!fieldErrors.number"
        :error-text="fieldErrors.number ?? ''"
        inputmode="numeric"
        pattern="[0-9]*"
        @input="form.number = $event.target.value; clearFieldError('number')"
      />

      <!-- Display text -->
      <p class="form-section-label">{{ t('headsigns.section_display') }}</p>

      <md-outlined-text-field
        :label="t('headsigns.field_destination')"
        :value="form.destination"
        :error="!!fieldErrors.destination"
        :error-text="fieldErrors.destination ?? ''"
        required
        @input="form.destination = $event.target.value; clearFieldError('destination')"
      />
    </form>

    <div slot="actions" class="dialog-actions">
      <span v-if="error" class="dialog-error">{{ error }}</span>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleSave">{{ t('common.save') }}</md-filled-button>
    </div>
  </md-dialog>
</template>

<style scoped>
.headsign-edit-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.headsign-edit-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.headsign-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--md-sys-color-on-surface-variant);
}

.dialog-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.dialog-error {
  flex: 1;
  font-size: 0.875rem;
  color: var(--md-sys-color-error);
}
</style>
