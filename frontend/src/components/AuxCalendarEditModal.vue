<script setup>
/**
 * AuxCalendarEditModal — create or edit an aux calendar (Hilfskalender).
 *
 * Props:
 *   modelValue   — boolean       — open state (v-model)
 *   auxCalendar  — object|null   — {id, name} when editing; null when creating
 *   dates        — string[]      — pre-loaded ISO dates ("YYYY-MM-DD") when editing
 *   error        — string|null   — server-side error message shown in actions bar
 *
 * Emits:
 *   update:modelValue     — close signal
 *   save({ name, dates }) — confirmed, parent handles API
 */
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'
import CalendarPicker from './CalendarPicker.vue'

const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  auxCalendar: { type: Object,  default: null },
  dates:       { type: Array,   default: () => [] },
  error:       { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])

const { t } = useI18n()

const isEdit = computed(() => !!props.auxCalendar)

// ---- Form state ----
const name = ref('')
const fieldErrors = ref({ name: null })

function clearFieldError(field) {
  fieldErrors.value[field] = null
}

function createSchema() {
  return z.object({
    name: z
      .string()
      .min(1, t('aux_calendar.validation_name_required'))
      .max(255, t('aux_calendar.validation_name_too_long')),
  })
}

function validateForm() {
  fieldErrors.value = { name: null }
  const result = createSchema().safeParse({ name: name.value.trim() })
  if (result.success) return true
  for (const issue of result.error.issues) {
    const field = issue.path?.[0]
    if (field && fieldErrors.value[field] == null) {
      fieldErrors.value[field] = issue.message
    }
  }
  return false
}

// ---- Calendar state ----
const selectedDates  = ref([])        // string[] of ISO dates
const calendarPicker = ref(null)      // template ref to CalendarPicker

// ---- Reset on open ----
watch(
  () => [props.modelValue, props.auxCalendar, props.dates],
  ([open]) => {
    if (!open) return
    name.value = props.auxCalendar?.name ?? ''
    fieldErrors.value = { name: null }
    selectedDates.value = [...(props.dates ?? [])].sort()
    calendarPicker.value?.resetYear()
  },
  { immediate: true },
)

// ---- Dialog ref ----
const dialogRef = ref(null)

watch(() => props.modelValue, (val) => {
  const el = dialogRef.value
  if (!el) return
  if (val) el.show?.()
  else el.close?.()
})

function handleClose() {
  emit('update:modelValue', false)
}

function handleSave() {
  if (!validateForm()) return
  emit('save', {
    name:  name.value.trim(),
    dates: selectedDates.value,
  })
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="aux-cal-dialog">

    <!-- Headline -->
    <div slot="headline" class="aux-cal-dialog__headline">
      <md-icon class="aux-cal-dialog__headline-icon">date_range</md-icon>
      <span class="aux-cal-dialog__title">
        {{ isEdit ? t('aux_calendar.edit_title') : t('aux_calendar.create_title') }}
      </span>
    </div>

    <!-- Content -->
    <form slot="content" class="aux-cal-dialog__form" method="dialog">

      <!-- Name section -->
      <div class="aux-cal-dialog__section">
        <p class="aux-cal-dialog__section-label">{{ t('aux_calendar.section_name') }}</p>
        <md-outlined-text-field
          class="aux-cal-dialog__name-field"
          :label="t('aux_calendar.field_name')"
          :value="name"
          :error="!!fieldErrors.name"
          :error-text="fieldErrors.name ?? ''"
          required
          @input="name = $event.target.value; clearFieldError('name')"
        />
      </div>

      <!-- Calendar section -->
      <div class="aux-cal-dialog__section">
        <p class="aux-cal-dialog__section-label">{{ t('aux_calendar.section_dates') }}</p>
        <CalendarPicker
          ref="calendarPicker"
          v-model="selectedDates"
        />
      </div>

    </form>

    <!-- Actions -->
    <div slot="actions">
      <p v-if="error" class="aux-cal-dialog__error">{{ error }}</p>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleSave">
        <md-icon slot="icon">save</md-icon>
        {{ t('common.save') }}
      </md-filled-button>
    </div>

  </md-dialog>
</template>

<style scoped>
.aux-cal-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
  width: min(1516px, 98vw);
}

/* ---- Headline ---- */
.aux-cal-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.aux-cal-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.aux-cal-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

/* ---- Form ---- */
.aux-cal-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.5rem;
}

.aux-cal-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.aux-cal-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.aux-cal-dialog__name-field {
  width: 100%;
}

/* ---- Actions error ---- */
.aux-cal-dialog__error {
  margin: 0 auto 0 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}
</style>
