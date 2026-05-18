<script setup>
/**
 * PlatformEditPanel — slide-in panel for creating or editing a GTFS platform (Steig, location_type=0).
 *
 * Props:
 *   modelValue     — boolean      — visible state (v-model)
 *   platform       — object|null  — pre-filled data when editing; null for a new platform
 *   initLat        — number|null  — initial latitude (from map crosshair pick)
 *   initLon        — number|null  — initial longitude (from map crosshair pick)
 *   loading        — boolean      — disables actions while a request is in flight
 *   serverError    — string|null  — error to show in actions bar
 *   canDelete      — boolean      — show delete button
 *   parentStopName — string|null  — displayed as subtitle to give context
 *
 * Emits:
 *   update:modelValue
 *   save(data)   — payload ready to POST/PUT
 *   delete()     — user requested deletion
 */
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/select/outlined-select.js'
import '@material/web/select/select-option.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:     { type: Boolean, default: false },
  platform:       { type: Object,  default: null },
  initLat:        { type: Number,  default: null },
  initLon:        { type: Number,  default: null },
  loading:        { type: Boolean, default: false },
  serverError:    { type: String,  default: null },
  canDelete:      { type: Boolean, default: false },
  parentStopName: { type: String,  default: null },
  readonly:       { type: Boolean, default: false },
  rerouting:      { type: Boolean, default: false },
  reroutingMessage: { type: String, default: null },
})

const emit = defineEmits(['update:modelValue', 'save', 'delete', 'cancel'])
const { t } = useI18n()

const TIMEZONE_OPTIONS = Intl.supportedValuesOf('timeZone').sort()

const isEdit = computed(() => !!props.platform)
const isReadonly = computed(() => props.readonly || props.rerouting)

// ---------------------------------------------------------------------------
// Form state
// ---------------------------------------------------------------------------

function emptyForm() {
  return {
    stop_id:             '',
    stop_code:           '',
    stop_name:           '',
    tts_stop_name:       '',
    stop_desc:           '',
    stop_lat:            '',
    stop_lon:            '',
    zone_id:             '',
    stop_url:            '',
    stop_timezone:       '',
    wheelchair_boarding: '',
    platform_code:       '',
    stop_access:         '',
  }
}

function emptyErrors() {
  return {
    stop_id:   null,
    stop_name: null,
    stop_lat:  null,
    stop_lon:  null,
    stop_url:  null,
  }
}

const form        = ref(emptyForm())
const fieldErrors = ref(emptyErrors())

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function isValidHttpUrl(value) {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

function buildSchema() {
  return z.object({
    stop_id: z
      .string()
      .min(1, t('stops.validation_id_required'))
      .max(255, t('stops.validation_id_too_long'))
      .refine(v => !v.includes(','), t('stops.validation_id_no_comma')),
    stop_name: z
      .string()
      .max(255, t('stops.validation_name_too_long'))
      .optional(),
    stop_lat: z
      .number()
      .min(-90, t('stops.validation_lat_invalid'))
      .max(90,  t('stops.validation_lat_invalid'))
      .nullable()
      .optional(),
    stop_lon: z
      .number()
      .min(-180, t('stops.validation_lon_invalid'))
      .max(180,  t('stops.validation_lon_invalid'))
      .nullable()
      .optional(),
    stop_url: z
      .string()
      .refine(v => !v || isValidHttpUrl(v), t('stops.validation_url_invalid'))
      .optional(),
  })
}

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function validate() {
  fieldErrors.value = emptyErrors()
  const parseFloat_ = (v) => {
    const trimmed = typeof v === 'string' ? v.trim() : String(v ?? '')
    if (trimmed === '') return undefined
    const n = parseFloat(trimmed)
    return isNaN(n) ? trimmed : n
  }
  const result = buildSchema().safeParse({
    stop_id:   form.value.stop_id.trim(),
    stop_name: form.value.stop_name.trim() || undefined,
    stop_lat:  parseFloat_(form.value.stop_lat),
    stop_lon:  parseFloat_(form.value.stop_lon),
    stop_url:  form.value.stop_url.trim() || undefined,
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

// ---------------------------------------------------------------------------
// Populate form
// ---------------------------------------------------------------------------

function populateForm() {
  if (props.platform) {
    form.value = {
      stop_id:             props.platform.stop_id,
      stop_code:           props.platform.stop_code           ?? '',
      stop_name:           props.platform.stop_name           ?? '',
      tts_stop_name:       props.platform.tts_stop_name       ?? '',
      stop_desc:           props.platform.stop_desc           ?? '',
      stop_lat:            props.platform.stop_lat            != null ? String(props.platform.stop_lat) : '',
      stop_lon:            props.platform.stop_lon            != null ? String(props.platform.stop_lon) : '',
      zone_id:             props.platform.zone_id             ?? '',
      stop_url:            props.platform.stop_url            ?? '',
      stop_timezone:       props.platform.stop_timezone       ?? '',
      wheelchair_boarding: props.platform.wheelchair_boarding != null ? String(props.platform.wheelchair_boarding) : '',
      platform_code:       props.platform.platform_code       ?? '',
      stop_access:         props.platform.stop_access         != null ? String(props.platform.stop_access)         : '',
    }
  } else {
    form.value = {
      ...emptyForm(),
      stop_lat: props.initLat != null ? String(props.initLat) : '',
      stop_lon: props.initLon != null ? String(props.initLon) : '',
    }
  }
  fieldErrors.value = emptyErrors()
}

watch(() => props.modelValue, (val) => {
  if (val) populateForm()
})

watch(() => props.platform, () => {
  if (props.modelValue) populateForm()
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function handleCancel() {
  emit('cancel')
  emit('update:modelValue', false)
}

function handleSave() {
  if (!validate()) return
  const str  = (v) => v.trim() === '' ? null : v.trim()
  const num  = (v) => {
    const s = typeof v === 'string' ? v.trim() : ''
    if (s === '') return null
    const n = parseFloat(s)
    return isNaN(n) ? null : n
  }
  const int_ = (v) => {
    const s = typeof v === 'string' ? v.trim() : ''
    if (s === '') return null
    const n = parseInt(s, 10)
    return isNaN(n) ? null : n
  }
  emit('save', {
    stop_id:             form.value.stop_id.trim(),
    stop_code:           str(form.value.stop_code),
    stop_name:           str(form.value.stop_name),
    tts_stop_name:       str(form.value.tts_stop_name),
    stop_desc:           str(form.value.stop_desc),
    stop_lat:            num(form.value.stop_lat),
    stop_lon:            num(form.value.stop_lon),
    zone_id:             str(form.value.zone_id),
    stop_url:            str(form.value.stop_url),
    stop_timezone:       str(form.value.stop_timezone),
    wheelchair_boarding: int_(form.value.wheelchair_boarding),
    platform_code:       str(form.value.platform_code),
    stop_access:         int_(form.value.stop_access),
  })
}

function handleDelete() {
  emit('delete')
}
</script>

<template>
  <Transition name="panel-slide">
    <aside v-if="modelValue" class="stop-edit-panel">
      <!-- Header -->
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-title">
            {{ isReadonly ? t('platforms.panel_title_view') : isEdit ? t('platforms.panel_title_edit') : t('platforms.panel_title_create') }}
          </span>
          <span v-if="parentStopName" class="panel-subtitle">{{ parentStopName }}</span>
        </div>
        <button class="panel-close-btn" @click="handleCancel" :aria-label="t('stops.cancel')">
          <md-icon>close</md-icon>
        </button>
      </div>

      <!-- Scrollable content -->
      <div class="panel-content">

        <!-- Section: Identification -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('stops.section_identification') }}</span>

          <md-outlined-text-field
            :label="t('stops.field_stop_id')"
            :value="form.stop_id"
            :disabled="isEdit || isReadonly"
            required
            :error="!!fieldErrors.stop_id"
            :error-text="fieldErrors.stop_id ?? ''"
            @input="form.stop_id = $event.target.value; clearFieldError('stop_id')"
          />

          <md-outlined-text-field
            :label="t('stops.field_stop_name')"
            :value="form.stop_name"
            :disabled="isReadonly"
            :error="!!fieldErrors.stop_name"
            :error-text="fieldErrors.stop_name ?? ''"
            @input="form.stop_name = $event.target.value; clearFieldError('stop_name')"
          />

          <md-outlined-text-field
            :label="t('stops.field_tts_stop_name')"
            :value="form.tts_stop_name"
            :disabled="isReadonly"
            @input="form.tts_stop_name = $event.target.value"
          />

          <md-outlined-text-field
            :label="t('stops.field_stop_code')"
            :value="form.stop_code"
            :disabled="isReadonly"
            @input="form.stop_code = $event.target.value"
          />
        </div>

        <!-- Section: Location -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('stops.section_location') }}</span>

          <div class="panel-row">
            <md-outlined-text-field
              :label="t('stops.field_stop_lat')"
              :value="form.stop_lat"
              type="number"
              step="any"
              :disabled="isReadonly"
              :error="!!fieldErrors.stop_lat"
              :error-text="fieldErrors.stop_lat ?? ''"
              @input="form.stop_lat = $event.target.value; clearFieldError('stop_lat')"
            />
            <md-outlined-text-field
              :label="t('stops.field_stop_lon')"
              :value="form.stop_lon"
              type="number"
              step="any"
              :disabled="isReadonly"
              :error="!!fieldErrors.stop_lon"
              :error-text="fieldErrors.stop_lon ?? ''"
              @input="form.stop_lon = $event.target.value; clearFieldError('stop_lon')"
            />
          </div>
        </div>

        <!-- Section: Details -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('stops.section_details') }}</span>

          <md-outlined-text-field
            :label="t('stops.field_platform_code')"
            :value="form.platform_code"
            :disabled="isReadonly"
            @input="form.platform_code = $event.target.value"
          />

          <md-outlined-text-field
            :label="t('stops.field_stop_desc')"
            type="textarea"
            rows="2"
            :value="form.stop_desc"
            :disabled="isReadonly"
            @input="form.stop_desc = $event.target.value"
          />

          <md-outlined-text-field
            :label="t('stops.field_stop_url')"
            :value="form.stop_url"
            :disabled="isReadonly"
            :error="!!fieldErrors.stop_url"
            :error-text="fieldErrors.stop_url ?? ''"
            @input="form.stop_url = $event.target.value; clearFieldError('stop_url')"
          />

          <md-outlined-select
            :label="t('stops.field_stop_timezone')"
            :disabled="isReadonly"
            @change="form.stop_timezone = $event.target.value"
          >
            <md-select-option value="" :selected="form.stop_timezone === ''">
              <div slot="headline">— {{ t('stops.timezone_empty') }}</div>
            </md-select-option>
            <md-select-option
              v-for="tz in TIMEZONE_OPTIONS"
              :key="tz"
              :value="tz"
              :selected="form.stop_timezone === tz"
            >
              <div slot="headline">{{ tz }}</div>
            </md-select-option>
          </md-outlined-select>

          <md-outlined-text-field
            :label="t('stops.field_zone_id')"
            :value="form.zone_id"
            :disabled="isReadonly"
            @input="form.zone_id = $event.target.value"
          />
        </div>

        <!-- Section: Accessibility -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('stops.section_accessibility') }}</span>

          <md-outlined-select
            :label="t('stops.field_wheelchair_boarding')"
            :value="form.wheelchair_boarding"
            :disabled="isReadonly"
            @change="form.wheelchair_boarding = $event.target.value"
          >
            <md-select-option value="">{{ t('stops.wheelchair_empty') }}</md-select-option>
            <md-select-option value="0">{{ t('stops.wheelchair_0') }}</md-select-option>
            <md-select-option value="1">{{ t('stops.wheelchair_1') }}</md-select-option>
            <md-select-option value="2">{{ t('stops.wheelchair_2') }}</md-select-option>
          </md-outlined-select>

          <md-outlined-select
            :label="t('stops.field_stop_access')"
            :disabled="isReadonly"
            @change="form.stop_access = $event.target.value"
          >
            <md-select-option value="" :selected="form.stop_access === ''">
              {{ t('stops.stop_access_empty') }}
            </md-select-option>
            <md-select-option value="0" :selected="form.stop_access === '0'">
              {{ t('stops.stop_access_0') }}
            </md-select-option>
            <md-select-option value="1" :selected="form.stop_access === '1'">
              {{ t('stops.stop_access_1') }}
            </md-select-option>
          </md-outlined-select>
        </div>

      </div>

      <!-- Actions -->
      <div class="panel-actions">
        <div class="panel-actions-left">
          <md-filled-button
            v-if="!isReadonly && isEdit && canDelete"
            :disabled="loading || rerouting"
            class="panel-delete-btn"
            @click="handleDelete"
          >
            <md-icon slot="icon">delete</md-icon>
            {{ t('stops.delete') }}
          </md-filled-button>
          <span v-if="reroutingMessage" class="panel-rerouting-msg">{{ reroutingMessage }}</span>
          <span v-else-if="serverError" class="panel-error">{{ serverError }}</span>
        </div>
        <div class="panel-actions-right">
          <md-text-button :disabled="loading || rerouting" @click="handleCancel">
            {{ t('stops.cancel') }}
          </md-text-button>
          <md-filled-button v-if="!props.readonly" :disabled="loading || rerouting" @click="handleSave">
            {{ t('stops.save') }}
          </md-filled-button>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.stop-edit-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 480px;
  max-width: 96vw;
  background: #ffffff;
  border-left: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
  display: flex;
  flex-direction: column;
  z-index: 11;
  box-shadow: var(--shadow-3);
}

/* ---- Transition ---- */
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: transform 0.22s var(--ease-3, ease), opacity 0.18s ease;
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* ---- Header ---- */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
  flex-shrink: 0;
}

.panel-title-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.panel-title {
  font-size: var(--font-size-2, 1rem);
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.panel-subtitle {
  font-size: var(--font-size-0, 0.78rem);
  color: var(--md-sys-color-outline, #74777f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-close-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  color: var(--md-sys-color-on-surface-variant, #444);
  transition: background 0.15s;
  flex-shrink: 0;
}
.panel-close-btn:hover {
  background: rgba(0, 0, 0, 0.06);
}

/* ---- Scrollable content ---- */
.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ---- Sections ---- */
.panel-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-section-label {
  font-size: var(--font-size-0, 0.78rem);
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--md-sys-color-outline, #74777f);
}

.panel-section md-outlined-text-field,
.panel-section md-outlined-select {
  width: 100%;
}

.panel-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* ---- Actions bar ---- */
.panel-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
  flex-shrink: 0;
  gap: 8px;
}

.panel-actions-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.panel-actions-right {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.panel-error {
  font-size: var(--font-size-0, 0.78rem);
  color: var(--md-sys-color-error, #ba1a1a);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-rerouting-msg {
  font-size: var(--font-size-0, 0.78rem);
  color: var(--md-sys-color-on-surface-variant, #44474f);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-delete-btn {
  --md-filled-button-container-color:         var(--md-sys-color-error, #ba1a1a);
  --md-filled-button-hover-container-color:   #a31717;
  --md-filled-button-pressed-container-color: #8c1313;
  --md-filled-button-label-text-color:        #ffffff;
  --md-filled-button-hover-label-text-color:  #ffffff;
  --md-filled-button-icon-color:              #ffffff;
  --md-filled-button-hover-icon-color:        #ffffff;
}
</style>
