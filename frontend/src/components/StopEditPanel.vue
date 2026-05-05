<script setup>
/**
 * StopEditPanel — slide-in panel for creating or editing a GTFS stop (Haltestelle).
 *
 * Props:
 *   modelValue — boolean      — visible state (v-model)
 *   stop       — object|null  — pre-filled data when editing; null for a new stop
 *   initLat    — number|null  — initial latitude (from map right-click)
 *   initLon    — number|null  — initial longitude (from map right-click)
 *   loading    — boolean      — disables actions while a request is in flight
 *   serverError — string|null — error to show in actions bar
 *
 * Emits:
 *   update:modelValue
 *   save(data)   — payload ready to POST/PUT
 *   delete()     — user requested deletion of the current stop
 */
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/select/outlined-select.js'
import '@material/web/select/select-option.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/button/outlined-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  stop:        { type: Object,  default: null },
  initLat:     { type: Number,  default: null },
  initLon:     { type: Number,  default: null },
  loading:     { type: Boolean, default: false },
  serverError: { type: String,  default: null },
  canDelete:   { type: Boolean, default: false },
  platforms:   { type: Array,   default: () => [] },
  readonly:    { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'save', 'delete', 'add-platform', 'edit-platform'])
const { t } = useI18n()

// IANA timezone list (browser-provided)
const TIMEZONE_OPTIONS = Intl.supportedValuesOf('timeZone').sort()

const isEdit = computed(() => !!props.stop)
const isReadonly = computed(() => props.readonly)

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
  }
}

function emptyErrors() {
  return {
    stop_id:             null,
    stop_name:           null,
    stop_lat:            null,
    stop_lon:            null,
    stop_url:            null,
  }
}

const form        = ref(emptyForm())
const fieldErrors = ref(emptyErrors())

// ---------------------------------------------------------------------------
// Validation helpers
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
// Populate form when panel becomes visible or stop changes
// ---------------------------------------------------------------------------

function populateForm() {
  if (props.stop) {
    form.value = {
      stop_id:             props.stop.stop_id,
      stop_code:           props.stop.stop_code           ?? '',
      stop_name:           props.stop.stop_name           ?? '',
      tts_stop_name:       props.stop.tts_stop_name       ?? '',
      stop_desc:           props.stop.stop_desc           ?? '',
      stop_lat:            props.stop.stop_lat            != null ? String(props.stop.stop_lat) : '',
      stop_lon:            props.stop.stop_lon            != null ? String(props.stop.stop_lon) : '',
      zone_id:             props.stop.zone_id             ?? '',
      stop_url:            props.stop.stop_url            ?? '',
      stop_timezone:       props.stop.stop_timezone       ?? '',
      wheelchair_boarding: props.stop.wheelchair_boarding != null ? String(props.stop.wheelchair_boarding) : '',
      platform_code:       props.stop.platform_code       ?? '',
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

watch(() => props.stop, () => {
  if (props.modelValue) populateForm()
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function handleCancel() {
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
        <span class="panel-title">
          {{ isReadonly ? t('stops.panel_title_view') : isEdit ? t('stops.panel_title_edit') : t('stops.panel_title_create') }}
        </span>
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

        </div>

        <!-- Section: Platforms (Steige) -->
        <div v-if="isEdit" class="panel-section">
          <div class="panel-section-header">
            <span class="panel-section-label">{{ t('stops.section_platforms') }}</span>
            <md-text-button v-if="!isReadonly" @click="$emit('add-platform')">
              <md-icon slot="icon">add</md-icon>
              {{ t('stops.add_platform') }}
            </md-text-button>
          </div>
          <div v-if="platforms.length === 0" class="panel-empty-hint">{{ t('stops.platforms_empty') }}</div>
          <div v-else class="platform-list">
            <button
              v-for="p in platforms"
              :key="p.stop_id"
              class="platform-list-item"
              :class="{ 'platform-list-item--readonly': isReadonly }"
              @click="$emit('edit-platform', p)"
            >
              <span class="platform-list-item__dot" />
              <span class="platform-list-item__name">{{ p.stop_name || p.stop_id }}</span>
              <span v-if="p.platform_code" class="platform-list-item__code">{{ p.platform_code }}</span>
              <md-icon v-if="!isReadonly" class="platform-list-item__arrow">chevron_right</md-icon>
            </button>
          </div>
        </div>

      </div>

      <!-- Actions -->
      <div class="panel-actions">
        <div class="panel-actions-left">
          <md-filled-button
            v-if="!isReadonly && isEdit && canDelete"
            :disabled="loading"
            class="panel-delete-btn"
            @click="handleDelete"
          >
            <md-icon slot="icon">delete</md-icon>
            {{ t('stops.delete') }}
          </md-filled-button>
          <span v-if="serverError" class="panel-error">{{ serverError }}</span>
        </div>
        <div class="panel-actions-right">
          <md-text-button :disabled="loading" @click="handleCancel">
            {{ t('stops.cancel') }}
          </md-text-button>
          <md-filled-button v-if="!isReadonly" :disabled="loading" @click="handleSave">
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
  z-index: 10;
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

.panel-title {
  font-size: var(--font-size-2, 1rem);
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
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

/* Full-width text fields and selects */
.panel-section md-outlined-text-field,
.panel-section md-outlined-select {
  width: 100%;
}

/* Two-column coordinate row */
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

.panel-delete-btn {
  --md-filled-button-container-color:         var(--md-sys-color-error, #ba1a1a);
  --md-filled-button-hover-container-color:   #a31717;
  --md-filled-button-pressed-container-color: #8c1313;
  --md-filled-button-label-text-color:        #ffffff;
  --md-filled-button-hover-label-text-color:  #ffffff;
  --md-filled-button-icon-color:              #ffffff;
  --md-filled-button-hover-icon-color:        #ffffff;
}

/* ---- Platform section header (label + add button side by side) ---- */
.panel-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-empty-hint {
  margin: 0;
  font-size: var(--font-size-0, 0.78rem);
  color: var(--md-sys-color-outline, #74777f);
  font-style: italic;
}

/* ---- Platform list ---- */
.platform-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.platform-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--md-sys-color-surface-container-low, #f7f7fb);
  border: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
  width: 100%;
  transition: background 0.12s;
}

.platform-list-item:hover {
  background: var(--md-sys-color-surface-container, #ededf4);
}

.platform-list-item--readonly {
  cursor: default;
}

.platform-list-item__dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #ffffff;
  border: 3px solid var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.platform-list-item__name {
  flex: 1;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #222);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-list-item__code {
  font-size: var(--font-size-0, 0.78rem);
  font-weight: 600;
  color: var(--md-sys-color-primary, #1f69e0);
  background: var(--md-sys-color-primary-container, #d8e2ff);
  border-radius: 4px;
  padding: 2px 6px;
  flex-shrink: 0;
}

.platform-list-item__arrow {
  color: var(--md-sys-color-outline, #74777f);
  font-size: 18px;
  flex-shrink: 0;
}
</style>
