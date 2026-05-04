<script setup>
/**
 * AgencyEditModal — dialog for creating or editing a GTFS agency.
 *
 * Props:
 *   modelValue — boolean     — open state (v-model)
 *   agency     — object|null — pre-filled data when editing; null for new agency
 *   error      — string|null — server-level error message
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
import '@material/web/select/outlined-select.js'
import '@material/web/select/select-option.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  agency:     { type: Object,  default: null },
  error:      { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

const isEdit = computed(() => !!props.agency)

// ---- Form state ----
function emptyForm() {
  return {
    agency_id:       '',
    agency_name:     '',
    agency_url:      '',
    agency_timezone: '',
    agency_lang:     '',
    agency_phone:    '',
    agency_fare_url: '',
    agency_email:    '',
    cemv_support:    '',
  }
}

function emptyErrors() {
  return {
    agency_id:       null,
    agency_name:     null,
    agency_url:      null,
    agency_timezone: null,
    agency_lang:     null,
    agency_email:    null,
    agency_fare_url: null,
  }
}

const form        = ref(emptyForm())
const fieldErrors = ref(emptyErrors())
const dialogRef   = ref(null)

// ---- Validation ----

/** IANA timezone names supported by this browser. */
const IANA_TIMEZONES = new Set(Intl.supportedValuesOf('timeZone'))
const TIMEZONE_OPTIONS = [...IANA_TIMEZONES].sort()

const LANG_OPTIONS = [
  { value: 'de', label: 'Deutsch (de)' },
  { value: 'en', label: 'English (en)' },
]
const LANG_VALUES = new Set(LANG_OPTIONS.map(l => l.value))

/** Returns true if value is a reachable http(s) URL. */
function isValidHttpUrl(value) {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

/** Returns true if value looks like a valid e-mail address. */
function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

/** GTFS: agency_id must not contain commas (CSV field separator). */
function isValidGtfsId(value) {
  return value.trim().length > 0 && !value.includes(',')
}

function buildSchema() {
  return z.object({
    agency_id: z
      .string()
      .min(1, t('agency.validation_id_required'))
      .max(255, t('agency.validation_id_too_long'))
      .refine(v => !v.includes(','), t('agency.validation_id_no_comma')),
    agency_name: z
      .string()
      .min(1, t('agency.validation_name_required'))
      .max(255, t('agency.validation_name_too_long')),
    agency_url: z
      .string()
      .min(1, t('agency.validation_url_required'))
      .refine(isValidHttpUrl, t('agency.validation_url_invalid')),
    agency_timezone: z
      .string()
      .min(1, t('agency.validation_timezone_required'))
      .refine(v => IANA_TIMEZONES.has(v.trim()), t('agency.validation_timezone_invalid')),
    agency_lang: z
      .string()
      .optional()
      .refine(v => !v || LANG_VALUES.has(v), t('agency.validation_lang_invalid')),
    agency_email: z
      .string()
      .optional()
      .refine(v => !v || isValidEmail(v), t('agency.validation_email_invalid')),
    agency_fare_url: z
      .string()
      .optional()
      .refine(v => !v || isValidHttpUrl(v), t('agency.validation_fare_url_invalid')),
  })
}

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function validate() {
  fieldErrors.value = emptyErrors()
  const nullable = (v) => v.trim() === '' ? undefined : v.trim()
  const result = buildSchema().safeParse({
    agency_id:       form.value.agency_id.trim(),
    agency_name:     form.value.agency_name.trim(),
    agency_url:      form.value.agency_url.trim(),
    agency_timezone: form.value.agency_timezone.trim(),
    agency_lang:     nullable(form.value.agency_lang),
    agency_email:    nullable(form.value.agency_email),
    agency_fare_url: nullable(form.value.agency_fare_url),
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
    form.value = props.agency
      ? {
          agency_id:       props.agency.agency_id,
          agency_name:     props.agency.agency_name,
          agency_url:      props.agency.agency_url,
          agency_timezone: props.agency.agency_timezone,
          agency_lang:     props.agency.agency_lang     ?? '',
          agency_phone:    props.agency.agency_phone    ?? '',
          agency_fare_url: props.agency.agency_fare_url ?? '',
          agency_email:    props.agency.agency_email    ?? '',
          cemv_support:    props.agency.cemv_support != null
            ? String(props.agency.cemv_support) : '',
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
  emit('save', {
    agency_id:       form.value.agency_id.trim(),
    agency_name:     form.value.agency_name.trim(),
    agency_url:      form.value.agency_url.trim(),
    agency_timezone: form.value.agency_timezone.trim(),
    agency_lang:     nullable(form.value.agency_lang),
    agency_phone:    nullable(form.value.agency_phone),
    agency_fare_url: nullable(form.value.agency_fare_url),
    agency_email:    nullable(form.value.agency_email),
    cemv_support:    form.value.cemv_support === '' ? null : parseInt(form.value.cemv_support, 10),
  })
}
</script>

<template>
  <md-dialog ref="dialogRef" class="agency-edit-dialog" @closed="handleClose">

    <div slot="headline" class="agency-edit-dialog__headline">
      <md-icon class="agency-edit-dialog__headline-icon">business</md-icon>
      <span class="agency-edit-dialog__title">
        {{ isEdit ? t('agency.edit_title_edit') : t('agency.edit_title_create') }}
      </span>
    </div>

    <form slot="content" class="agency-edit-dialog__form" method="dialog">

      <!-- Identification -->
      <div class="agency-edit-dialog__section">
        <p class="agency-edit-dialog__section-label">{{ t('agency.section_identification') }}</p>
        <md-outlined-text-field
          class="agency-edit-field"
          :label="t('agency.field_id')"
          :value="form.agency_id"
          :error="!!fieldErrors.agency_id"
          :error-text="fieldErrors.agency_id ?? ''"
          :disabled="isEdit || undefined"
          autocomplete="off"
          required
          @input="form.agency_id = $event.target.value; clearFieldError('agency_id')"
        />
        <md-outlined-text-field
          class="agency-edit-field"
          :label="t('agency.field_name')"
          :value="form.agency_name"
          :error="!!fieldErrors.agency_name"
          :error-text="fieldErrors.agency_name ?? ''"
          autocomplete="off"
          required
          @input="form.agency_name = $event.target.value; clearFieldError('agency_name')"
        />
      </div>

      <!-- Contact & URLs -->
      <div class="agency-edit-dialog__section">
        <p class="agency-edit-dialog__section-label">{{ t('agency.section_contact') }}</p>
        <md-outlined-text-field
          class="agency-edit-field"
          :label="t('agency.field_url')"
          type="url"
          :value="form.agency_url"
          :error="!!fieldErrors.agency_url"
          :error-text="fieldErrors.agency_url ?? ''"
          autocomplete="off"
          required
          @input="form.agency_url = $event.target.value; clearFieldError('agency_url')"
        />
        <md-outlined-text-field
          class="agency-edit-field"
          :label="t('agency.field_phone')"
          type="tel"
          :value="form.agency_phone"
          autocomplete="off"
          @input="form.agency_phone = $event.target.value"
        />
        <md-outlined-text-field
          class="agency-edit-field"
          :label="t('agency.field_email')"
          type="email"
          :value="form.agency_email"
          :error="!!fieldErrors.agency_email"
          :error-text="fieldErrors.agency_email ?? ''"
          autocomplete="off"
          @input="form.agency_email = $event.target.value; clearFieldError('agency_email')"
        />
        <md-outlined-text-field
          class="agency-edit-field"
          :label="t('agency.field_fare_url')"
          type="url"
          :value="form.agency_fare_url"
          :error="!!fieldErrors.agency_fare_url"
          :error-text="fieldErrors.agency_fare_url ?? ''"
          autocomplete="off"
          @input="form.agency_fare_url = $event.target.value; clearFieldError('agency_fare_url')"
        />
      </div>

      <!-- Regional settings -->
      <div class="agency-edit-dialog__section">
        <p class="agency-edit-dialog__section-label">{{ t('agency.section_regional') }}</p>
        <md-outlined-select
          class="agency-edit-field"
          :label="t('agency.field_timezone')"
          :error="!!fieldErrors.agency_timezone"
          :error-text="fieldErrors.agency_timezone ?? ''"
          required
          @change="form.agency_timezone = $event.target.value; clearFieldError('agency_timezone')"
        >
          <md-select-option
            v-for="tz in TIMEZONE_OPTIONS"
            :key="tz"
            :value="tz"
            :selected="form.agency_timezone === tz"
          >
            <div slot="headline">{{ tz }}</div>
          </md-select-option>
        </md-outlined-select>
        <md-outlined-select
          class="agency-edit-field"
          :label="t('agency.field_lang')"
          :error="!!fieldErrors.agency_lang"
          :error-text="fieldErrors.agency_lang ?? ''"
          @change="form.agency_lang = $event.target.value; clearFieldError('agency_lang')"
        >
          <md-select-option value="" :selected="form.agency_lang === ''">
            <div slot="headline">—</div>
          </md-select-option>
          <md-select-option
            v-for="opt in LANG_OPTIONS"
            :key="opt.value"
            :value="opt.value"
            :selected="form.agency_lang === opt.value"
          >
            <div slot="headline">{{ opt.label }}</div>
          </md-select-option>
        </md-outlined-select>
      </div>

      <!-- Other -->
      <div class="agency-edit-dialog__section">
        <p class="agency-edit-dialog__section-label">{{ t('agency.section_other') }}</p>
        <md-outlined-select
          class="agency-edit-field"
          :label="t('agency.field_cemv')"
          @change="form.cemv_support = $event.target.value"
        >
          <md-select-option value="" :selected="form.cemv_support === ''">
            <div slot="headline">{{ t('agency.cemv_empty') }}</div>
          </md-select-option>
          <md-select-option value="0" :selected="form.cemv_support === '0'">
            <div slot="headline">{{ t('agency.cemv_0') }}</div>
          </md-select-option>
          <md-select-option value="1" :selected="form.cemv_support === '1'">
            <div slot="headline">{{ t('agency.cemv_1') }}</div>
          </md-select-option>
          <md-select-option value="2" :selected="form.cemv_support === '2'">
            <div slot="headline">{{ t('agency.cemv_2') }}</div>
          </md-select-option>
        </md-outlined-select>
      </div>

    </form>

    <div slot="actions">
      <p v-if="error" class="agency-edit-dialog__error">{{ error }}</p>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleSave">
        <md-icon slot="icon">save</md-icon>
        {{ t('common.save') }}
      </md-filled-button>
    </div>

  </md-dialog>
</template>

<style scoped>
.agency-edit-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.agency-edit-dialog__error {
  margin: 0 auto 0 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}

.agency-edit-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.agency-edit-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.agency-edit-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.agency-edit-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.5rem;
}

.agency-edit-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.agency-edit-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.agency-edit-field {
  width: 100%;
}
</style>
