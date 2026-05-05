<script setup>
/**
 * DayTypeEditModal — create or edit a day type (Tagesart / GTFS calendar entry).
 *
 * Props:
 *   modelValue   — boolean       — open state (v-model)
 *   dayType      — object|null   — pre-filled data when editing; null for create
 *   auxCalendars — object[]      — all aux calendars in this version
 *   assignments  — object[]      — current aux-calendar assignments [{aux_calendar_id, junction_type}]
 *   error        — string|null   — server-side error shown in actions bar
 *
 * Emits:
 *   update:modelValue
 *   save({ service_id, name, monday, ..., start_date, end_date, assignments })
 */
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/checkbox/checkbox.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:   { type: Boolean, default: false },
  dayType:      { type: Object,  default: null },
  auxCalendars: { type: Array,   default: () => [] },
  assignments:  { type: Array,   default: () => [] },
  error:        { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])

const { t } = useI18n()

const isEdit = computed(() => !!props.dayType)

// ---- Form state ----
const DAY_KEYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

const DAY_LABEL_KEYS = {
  monday:    'calendar.day_mon',
  tuesday:   'calendar.day_tue',
  wednesday: 'calendar.day_wed',
  thursday:  'calendar.day_thu',
  friday:    'calendar.day_fri',
  saturday:  'calendar.day_sat',
  sunday:    'calendar.day_sun',
}

const DAY_WEEKEND = { saturday: true, sunday: true }

function emptyForm() {
  return {
    service_id: '',
    name:       '',
    monday:    false,
    tuesday:   false,
    wednesday: false,
    thursday:  false,
    friday:    false,
    saturday:  false,
    sunday:    false,
    start_date: '',
    end_date:   '',
  }
}

const form        = ref(emptyForm())
const fieldErrors = ref({})

function clearFieldError(field) {
  fieldErrors.value[field] = null
}

function createSchema() {
  return z
    .object({
      service_id: z
        .string()
        .min(1, t('day_type.validation_id_required'))
        .max(255, t('day_type.validation_id_too_long'))
        .refine(v => !v.includes(','), t('day_type.validation_id_no_comma')),
      name:       z.string().max(255, t('day_type.validation_name_too_long')),
      start_date: z.string().min(1, t('day_type.validation_start_date_required')),
      end_date:   z.string().min(1, t('day_type.validation_end_date_required')),
    })
    .refine(
      d => !d.start_date || !d.end_date || d.end_date >= d.start_date,
      { message: t('day_type.validation_end_before_start'), path: ['end_date'] },
    )
}

function validateForm() {
  fieldErrors.value = {}
  const result = createSchema().safeParse({
    service_id: form.value.service_id.trim(),
    name:       form.value.name.trim(),
    start_date: form.value.start_date,
    end_date:   form.value.end_date,
  })
  if (result.success) return true
  for (const issue of result.error.issues) {
    const field = issue.path?.[0]
    if (field && !fieldErrors.value[field]) {
      fieldErrors.value[field] = issue.message
    }
  }
  return false
}

// ---- Assignment state: { [aux_calendar_id_string]: 1 | 2 | 3 | null } ----
const assignmentState = ref({})

function handleAssignmentChange(auxCalId, type, checked) {
  const key = String(auxCalId)
  // Selecting a type deselects the others for this aux calendar (mutual exclusion).
  assignmentState.value = {
    ...assignmentState.value,
    [key]: checked ? type : null,
  }
}

// Warn in edit modal when ≥2 "nur" (restrict) assignments are active,
// since actual date conflicts can only be confirmed with dates loaded.
const restrictWarning = computed(() => {
  const onlyCount = Object.values(assignmentState.value).filter(v => v === 3).length
  return onlyCount >= 2
})

// ---- Reset on open ----
watch(
  () => [props.modelValue, props.dayType, props.assignments],
  ([open]) => {
    if (!open) return
    if (props.dayType) {
      form.value = {
        service_id: props.dayType.service_id ?? '',
        name:       props.dayType.name ?? '',
        monday:    !!props.dayType.monday,
        tuesday:   !!props.dayType.tuesday,
        wednesday: !!props.dayType.wednesday,
        thursday:  !!props.dayType.thursday,
        friday:    !!props.dayType.friday,
        saturday:  !!props.dayType.saturday,
        sunday:    !!props.dayType.sunday,
        start_date: props.dayType.start_date ?? '',
        end_date:   props.dayType.end_date ?? '',
      }
    } else {
      form.value = emptyForm()
    }
    fieldErrors.value = {}
    const state = {}
    for (const a of (props.assignments ?? [])) {
      state[String(a.aux_calendar_id)] = a.junction_type
    }
    assignmentState.value = state
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
    service_id: form.value.service_id.trim(),
    name:       form.value.name.trim() || null,
    monday:    form.value.monday    ? 1 : 0,
    tuesday:   form.value.tuesday   ? 1 : 0,
    wednesday: form.value.wednesday ? 1 : 0,
    thursday:  form.value.thursday  ? 1 : 0,
    friday:    form.value.friday    ? 1 : 0,
    saturday:  form.value.saturday  ? 1 : 0,
    sunday:    form.value.sunday    ? 1 : 0,
    start_date: form.value.start_date,
    end_date:   form.value.end_date,
    assignments: Object.entries(assignmentState.value)
      .filter(([, type]) => type !== null && type !== undefined)
      .map(([id, type]) => ({ aux_calendar_id: id, junction_type: type })),
  })
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="day-type-dialog">

    <!-- Headline -->
    <div slot="headline" class="day-type-dialog__headline">
      <md-icon class="day-type-dialog__headline-icon">wb_sunny</md-icon>
      <span>{{ isEdit ? t('day_type.edit_title') : t('day_type.create_title') }}</span>
    </div>

    <!-- Content -->
    <form slot="content" class="day-type-dialog__form" method="dialog">

      <!-- Identifikation -->
      <div class="day-type-dialog__section">
        <p class="day-type-dialog__section-label">{{ t('day_type.section_identification') }}</p>
        <md-outlined-text-field
          class="day-type-dialog__field"
          :label="t('day_type.field_id')"
          :value="form.service_id"
          :required="!isEdit || undefined"
          :disabled="isEdit || undefined"
          :error="!!fieldErrors.service_id"
          :error-text="fieldErrors.service_id ?? ''"
          @input="form.service_id = $event.target.value; clearFieldError('service_id')"
        />
        <md-outlined-text-field
          class="day-type-dialog__field"
          :label="t('day_type.field_name')"
          :value="form.name"
          :error="!!fieldErrors.name"
          :error-text="fieldErrors.name ?? ''"
          @input="form.name = $event.target.value; clearFieldError('name')"
        />
      </div>

      <!-- Betriebstage -->
      <div class="day-type-dialog__section">
        <p class="day-type-dialog__section-label">{{ t('day_type.section_days') }}</p>
        <div class="day-type-dialog__days">
          <label
            v-for="key in DAY_KEYS"
            :key="key"
            :class="['day-type-dialog__day', DAY_WEEKEND[key] ? 'day-type-dialog__day--weekend' : '']"
          >
            <span class="day-type-dialog__day-label">{{ t(DAY_LABEL_KEYS[key]) }}</span>
            <md-checkbox
              :checked="form[key]"
              @change="form[key] = $event.target.checked"
            />
          </label>
        </div>
      </div>

      <!-- Laufzeit -->
      <div class="day-type-dialog__section">
        <p class="day-type-dialog__section-label">{{ t('day_type.section_period') }}</p>
        <div class="day-type-dialog__dates">
          <md-outlined-text-field
            class="day-type-dialog__field"
            type="date"
            :label="t('day_type.field_start_date')"
            :value="form.start_date"
            required
            :error="!!fieldErrors.start_date"
            :error-text="fieldErrors.start_date ?? ''"
            @change="form.start_date = $event.target.value; clearFieldError('start_date')"
          />
          <md-outlined-text-field
            class="day-type-dialog__field"
            type="date"
            :label="t('day_type.field_end_date')"
            :value="form.end_date"
            required
            :error="!!fieldErrors.end_date"
            :error-text="fieldErrors.end_date ?? ''"
            @change="form.end_date = $event.target.value; clearFieldError('end_date')"
          />
        </div>
      </div>

      <!-- Abweichungen -->
      <div class="day-type-dialog__section">
        <p class="day-type-dialog__section-label">{{ t('day_type.section_assignments') }}</p>
        <p v-if="!auxCalendars.length" class="day-type-dialog__no-aux">
          {{ t('day_type.no_aux_calendars') }}
        </p>
        <div v-else class="day-type-dialog__assignments">
          <p v-if="restrictWarning" class="day-type-dialog__restrict-warning">
            <md-icon>warning</md-icon>
            {{ t('day_type.warning_restrict_multiple') }}
          </p>
          <div
            v-for="ac in auxCalendars"
            :key="ac.id"
            class="day-type-dialog__assignment-row"
          >
            <label class="day-type-dialog__assignment-option">
              <md-checkbox
                :checked="assignmentState[String(ac.id)] === 1"
                @change="handleAssignmentChange(ac.id, 1, $event.target.checked)"
              />
              <span>{{ t('day_type.assignment_additional') }}</span>
            </label>
            <label class="day-type-dialog__assignment-option">
              <md-checkbox
                :checked="assignmentState[String(ac.id)] === 2"
                @change="handleAssignmentChange(ac.id, 2, $event.target.checked)"
              />
              <span>{{ t('day_type.assignment_excluded') }}</span>
            </label>
            <label class="day-type-dialog__assignment-option">
              <md-checkbox
                :checked="assignmentState[String(ac.id)] === 3"
                @change="handleAssignmentChange(ac.id, 3, $event.target.checked)"
              />
              <span>{{ t('day_type.assignment_only') }}</span>
            </label>
            <span class="day-type-dialog__assignment-name">{{ ac.name }}</span>
          </div>
        </div>
      </div>

    </form>

    <!-- Actions -->
    <div slot="actions">
      <p v-if="error" class="day-type-dialog__error">{{ error }}</p>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleSave">
        <md-icon slot="icon">save</md-icon>
        {{ t('common.save') }}
      </md-filled-button>
    </div>

  </md-dialog>
</template>

<style scoped>
.day-type-dialog {
  --md-dialog-container-shape: 6px;
}

/* ---- Headline ---- */
.day-type-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.day-type-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

/* ---- Form ---- */
.day-type-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.5rem;
}

.day-type-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.day-type-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.day-type-dialog__field {
  width: 100%;
}

/* ---- Day checkboxes ---- */
.day-type-dialog__days {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.day-type-dialog__day {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.125rem;
  cursor: pointer;
  padding: 0.5rem 0.875rem;
  border-radius: 6px;
  border: 1px solid var(--md-sys-color-outline-variant, #ccc);
  min-width: 56px;
  transition: background 0.15s;
}

.day-type-dialog__day:hover {
  background: var(--md-sys-color-surface-variant, #f5f5f5);
}

.day-type-dialog__day--weekend {
  background: rgba(0, 0, 0, 0.03);
}

.day-type-dialog__day-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #333);
  user-select: none;
}

/* ---- Dates row ---- */
.day-type-dialog__dates {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

/* ---- Actions error ---- */
.day-type-dialog__error {
  margin: 0 auto 0 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}

/* ---- Abweichungen ---- */
.day-type-dialog__no-aux {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-on-surface-variant, #666);
}

.day-type-dialog__assignments {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.day-type-dialog__assignment-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.day-type-dialog__assignment-name {
  padding-left: 0.75rem;
  font-size: 1.0625rem;
  color: var(--md-sys-color-on-surface, #222);
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.day-type-dialog__assignment-option {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  cursor: pointer;
  font-size: 1.0625rem;
  color: var(--md-sys-color-on-surface-variant, #555);
  user-select: none;
  white-space: nowrap;
  border-radius: 4px;
  transition: background 0.12s;
}

.day-type-dialog__restrict-warning {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0;
  padding: 0.625rem 0.875rem;
  background: rgba(234, 179, 8, 0.1);
  border: 1px solid rgba(234, 179, 8, 0.4);
  border-radius: 6px;
  font-size: 0.875rem;
  color: #92400e;
}

.day-type-dialog__restrict-warning md-icon {
  --md-icon-size: 1.1rem;
  font-size: 1.1rem;
  color: #d97706;
  flex-shrink: 0;
  margin-top: 0.05rem;
}

.day-type-dialog__assignment-option:hover {
  background: var(--md-sys-color-surface-variant, #f5f5f5);
}
</style>
