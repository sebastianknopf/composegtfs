<script setup>
/**
 * RouteEditPanel — slide-in panel for creating or editing a GTFS route (Linie).
 *
 * Props:
 *   modelValue  — boolean      — visible state (v-model)
 *   route       — object|null  — pre-filled data when editing; null for a new route
 *   loading     — boolean      — disables actions while a request is in flight
 *   serverError — string|null  — error to show in actions bar
 *   canDelete   — boolean      — show delete button
 *   readonly    — boolean      — view-only mode
 *
 * Emits:
 *   update:modelValue
 *   save(data)   — payload ready to POST/PUT
 *   delete()     — user requested deletion of the current route
 */
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { versionsStore } from '@/stores/versions.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/select/outlined-select.js'
import '@material/web/select/select-option.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'
import ColorInput from '@/components/ColorInput.vue'

const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  route:       { type: Object,  default: null },
  loading:     { type: Boolean, default: false },
  serverError: { type: String,  default: null },
  canDelete:   { type: Boolean, default: false },
  readonly:    { type: Boolean, default: false },
  agencies:    { type: Array,   default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'save', 'delete'])
const { t } = useI18n()

const isEdit     = computed(() => !!props.route)
const isReadonly = computed(() => props.readonly)

// ---------------------------------------------------------------------------
// Form state
// ---------------------------------------------------------------------------

function emptyForm() {
  return {
    route_id:            '',
    agency_id:           '',
    route_short_name:    '',
    route_long_name:     '',
    route_desc:          '',
    route_type:          '',
    route_url:           '',
    route_color:         '',
    route_text_color:    '',
    continuous_pickup:   '',
    continuous_drop_off: '',
    cemv_support:        '',
    global_id:           '',
  }
}

function emptyErrors() {
  return {
    route_id:         null,
    route_short_name: null,
    route_long_name:  null,
    route_type:       null,
    route_url:        null,
    route_color:      null,
    route_text_color: null,
  }
}

// Agencies for dropdown (accept pre-loaded prop; fetch only as fallback)
const agencies = ref([])
async function loadAgencies() {
  if (props.agencies.length > 0) {
    agencies.value = props.agencies
    return
  }
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  try {
    agencies.value = await api.routes.agenciesLookup(versionId)
  } catch {
    agencies.value = []
  }
}

// Sync agencies when prop changes (pre-loaded from parent)
watch(() => props.agencies, (val) => { if (val.length > 0) agencies.value = val }, { immediate: true })

const form        = ref(emptyForm())
const fieldErrors = ref(emptyErrors())

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

const VALID_ROUTE_TYPES = new Set([0, 1, 2, 3, 4, 5, 6, 7, 11, 12])

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function isValidHttpUrl(value) {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

function validate() {
  fieldErrors.value = emptyErrors()
  let ok = true

  const shortName = form.value.route_short_name.trim()
  const longName  = form.value.route_long_name.trim()

  if (!isEdit.value) {
    const id = form.value.route_id.trim()
    if (!id) {
      fieldErrors.value.route_id = t('routes.validation_id_required')
      ok = false
    } else if (id.length > 255) {
      fieldErrors.value.route_id = t('routes.validation_id_too_long')
      ok = false
    }
  }

  if (!shortName && !longName) {
    fieldErrors.value.route_short_name = t('routes.validation_name_required')
    fieldErrors.value.route_long_name  = t('routes.validation_name_required')
    ok = false
  }

  const routeType = form.value.route_type
  if (routeType === '' || routeType === null) {
    fieldErrors.value.route_type = t('routes.validation_type_required')
    ok = false
  } else if (!VALID_ROUTE_TYPES.has(parseInt(routeType, 10))) {
    fieldErrors.value.route_type = t('routes.validation_type_invalid')
    ok = false
  }

  const url = form.value.route_url.trim()
  if (url && !isValidHttpUrl(url)) {
    fieldErrors.value.route_url = t('routes.validation_url_invalid')
    ok = false
  }

  const HEX6_RE = /^[0-9A-Fa-f]{6}$/
  const color = form.value.route_color.trim()
  if (color && !HEX6_RE.test(color)) {
    fieldErrors.value.route_color = t('routes.validation_color_invalid')
    ok = false
  }
  const textColor = form.value.route_text_color.trim()
  if (textColor && !HEX6_RE.test(textColor)) {
    fieldErrors.value.route_text_color = t('routes.validation_color_invalid')
    ok = false
  }

  return ok
}

// ---------------------------------------------------------------------------
// Populate form
// ---------------------------------------------------------------------------

function populateForm() {
  if (props.route) {
    form.value = {
      route_id:            props.route.route_id,
      agency_id:           props.route.agency_id           ?? '',
      route_short_name:    props.route.route_short_name     ?? '',
      route_long_name:     props.route.route_long_name      ?? '',
      route_desc:          props.route.route_desc           ?? '',
      route_type:          props.route.route_type           != null ? String(props.route.route_type) : '',
      route_url:           props.route.route_url            ?? '',
      route_color:         props.route.route_color          ?? '',
      route_text_color:    props.route.route_text_color     ?? '',
      continuous_pickup:   props.route.continuous_pickup    != null ? String(props.route.continuous_pickup) : '',
      continuous_drop_off: props.route.continuous_drop_off  != null ? String(props.route.continuous_drop_off) : '',
      cemv_support:        props.route.cemv_support         != null ? String(props.route.cemv_support) : '',
      global_id:           props.route.global_id            ?? '',
    }
  } else {
    form.value = emptyForm()
  }
  fieldErrors.value = emptyErrors()
}

watch(() => props.modelValue, (val) => { if (val) { populateForm(); loadAgencies() } })
watch(() => props.route,      ()    => { if (props.modelValue) populateForm() })

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function handleCancel() {
  emit('update:modelValue', false)
}

function handleSave() {
  if (!validate()) return
  const str  = (v) => (v ?? '').trim() === '' ? null : v.trim()
  const int_ = (v) => {
    const s = (v ?? '').trim()
    if (s === '') return null
    const n = parseInt(s, 10)
    return isNaN(n) ? null : n
  }
  emit('save', {
    route_id:            form.value.route_id.trim(),
    agency_id:           str(form.value.agency_id),
    route_short_name:    str(form.value.route_short_name),
    route_long_name:     str(form.value.route_long_name),
    route_desc:          str(form.value.route_desc),
    route_type:          parseInt(form.value.route_type, 10),
    route_url:           str(form.value.route_url),
    route_color:         form.value.route_color || null,
    route_text_color:    form.value.route_text_color || null,
    continuous_pickup:   int_(form.value.continuous_pickup),
    continuous_drop_off: int_(form.value.continuous_drop_off),
    cemv_support:        int_(form.value.cemv_support),
    global_id:           str(form.value.global_id),
  })
}

function handleDelete() {
  emit('delete')
}

</script>

<template>
  <Transition name="panel-slide">
    <aside v-if="modelValue" class="route-edit-panel">
      <!-- Header -->
      <div class="panel-header">
        <span class="panel-title">
          {{ isReadonly ? t('routes.panel_title_view') : isEdit ? t('routes.panel_title_edit') : t('routes.panel_title_create') }}
        </span>
        <button class="panel-close-btn" :aria-label="t('routes.cancel')" @click="handleCancel">
          <md-icon>close</md-icon>
        </button>
      </div>

      <!-- Scrollable content -->
      <div class="panel-content">

        <!-- Section: Identification -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('routes.section_identification') }}</span>

          <md-outlined-text-field
            :label="t('routes.field_route_id')"
            :value="form.route_id"
            :disabled="isEdit || isReadonly"
            required
            :error="!!fieldErrors.route_id"
            :error-text="fieldErrors.route_id ?? ''"
            @input="form.route_id = $event.target.value; clearFieldError('route_id')"
          />

          <md-outlined-text-field
            :label="t('routes.field_route_short_name')"
            :value="form.route_short_name"
            :disabled="isReadonly"
            :error="!!fieldErrors.route_short_name"
            :error-text="fieldErrors.route_short_name ?? ''"
            @input="form.route_short_name = $event.target.value; clearFieldError('route_short_name'); clearFieldError('route_long_name')"
          />

          <md-outlined-text-field
            :label="t('routes.field_route_long_name')"
            :value="form.route_long_name"
            :disabled="isReadonly"
            :error="!!fieldErrors.route_long_name"
            :error-text="fieldErrors.route_long_name ?? ''"
            @input="form.route_long_name = $event.target.value; clearFieldError('route_short_name'); clearFieldError('route_long_name')"
          />

          <md-outlined-select
            :label="t('routes.field_agency_id')"
            :disabled="isReadonly"
            @change="form.agency_id = $event.target.value"
          >
            <md-select-option value="" :selected="form.agency_id === ''">
              <div slot="headline">{{ t('routes.agency_empty') }}</div>
            </md-select-option>
            <md-select-option
              v-for="agency in agencies"
              :key="agency.agency_id"
              :value="agency.agency_id"
              :selected="form.agency_id === agency.agency_id"
            >
              <div slot="headline">{{ agency.agency_name }} ({{ agency.agency_id }})</div>
            </md-select-option>
          </md-outlined-select>

          <md-outlined-text-field
            :label="t('routes.field_global_id')"
            :value="form.global_id"
            :disabled="isReadonly"
            @input="form.global_id = $event.target.value"
          />
        </div>

        <!-- Section: Description & Type -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('routes.section_details') }}</span>

          <md-outlined-select
            :label="t('routes.field_route_type')"
            :disabled="isReadonly"
            :error="!!fieldErrors.route_type"
            :error-text="fieldErrors.route_type ?? ''"
            @change="form.route_type = $event.target.value; clearFieldError('route_type')"
          >
            <md-select-option value="" :selected="form.route_type === ''">
              <div slot="headline">{{ t('routes.type_empty') }}</div>
            </md-select-option>
            <md-select-option value="0" :selected="form.route_type === '0'">
              <div slot="headline">{{ t('routes.type_0') }}</div>
            </md-select-option>
            <md-select-option value="1" :selected="form.route_type === '1'">
              <div slot="headline">{{ t('routes.type_1') }}</div>
            </md-select-option>
            <md-select-option value="2" :selected="form.route_type === '2'">
              <div slot="headline">{{ t('routes.type_2') }}</div>
            </md-select-option>
            <md-select-option value="3" :selected="form.route_type === '3'">
              <div slot="headline">{{ t('routes.type_3') }}</div>
            </md-select-option>
            <md-select-option value="4" :selected="form.route_type === '4'">
              <div slot="headline">{{ t('routes.type_4') }}</div>
            </md-select-option>
            <md-select-option value="5" :selected="form.route_type === '5'">
              <div slot="headline">{{ t('routes.type_5') }}</div>
            </md-select-option>
            <md-select-option value="6" :selected="form.route_type === '6'">
              <div slot="headline">{{ t('routes.type_6') }}</div>
            </md-select-option>
            <md-select-option value="7" :selected="form.route_type === '7'">
              <div slot="headline">{{ t('routes.type_7') }}</div>
            </md-select-option>
            <md-select-option value="11" :selected="form.route_type === '11'">
              <div slot="headline">{{ t('routes.type_11') }}</div>
            </md-select-option>
            <md-select-option value="12" :selected="form.route_type === '12'">
              <div slot="headline">{{ t('routes.type_12') }}</div>
            </md-select-option>
          </md-outlined-select>

          <md-outlined-text-field
            type="textarea"
            rows="2"
            :label="t('routes.field_route_desc')"
            :value="form.route_desc"
            :disabled="isReadonly"
            @input="form.route_desc = $event.target.value"
          />

          <md-outlined-text-field
            :label="t('routes.field_route_url')"
            :value="form.route_url"
            :disabled="isReadonly"
            :error="!!fieldErrors.route_url"
            :error-text="fieldErrors.route_url ?? ''"
            @input="form.route_url = $event.target.value; clearFieldError('route_url')"
          />
        </div>

        <!-- Section: Appearance -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('routes.section_appearance') }}</span>

          <ColorInput
            :model-value="form.route_color"
            :label="t('routes.field_route_color')"
            :disabled="isReadonly"
            :error="fieldErrors.route_color"
            @update:model-value="form.route_color = $event; clearFieldError('route_color')"
          />

          <ColorInput
            :model-value="form.route_text_color"
            :label="t('routes.field_route_text_color')"
            :disabled="isReadonly"
            :error="fieldErrors.route_text_color"
            @update:model-value="form.route_text_color = $event; clearFieldError('route_text_color')"
          />
        </div>

        <!-- Section: Service (Continuous pickup/drop-off) -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('routes.section_service') }}</span>

          <md-outlined-select
            :label="t('routes.field_continuous_pickup')"
            :disabled="isReadonly"
            @change="form.continuous_pickup = $event.target.value"
          >
            <md-select-option value="" :selected="form.continuous_pickup === ''">
              <div slot="headline">{{ t('routes.continuous_empty') }}</div>
            </md-select-option>
            <md-select-option value="0" :selected="form.continuous_pickup === '0'">
              <div slot="headline">{{ t('routes.continuous_0') }}</div>
            </md-select-option>
            <md-select-option value="1" :selected="form.continuous_pickup === '1'">
              <div slot="headline">{{ t('routes.continuous_1') }}</div>
            </md-select-option>
            <md-select-option value="2" :selected="form.continuous_pickup === '2'">
              <div slot="headline">{{ t('routes.continuous_2') }}</div>
            </md-select-option>
            <md-select-option value="3" :selected="form.continuous_pickup === '3'">
              <div slot="headline">{{ t('routes.continuous_3') }}</div>
            </md-select-option>
          </md-outlined-select>

          <md-outlined-select
            :label="t('routes.field_continuous_drop_off')"
            :disabled="isReadonly"
            @change="form.continuous_drop_off = $event.target.value"
          >
            <md-select-option value="" :selected="form.continuous_drop_off === ''">
              <div slot="headline">{{ t('routes.continuous_empty') }}</div>
            </md-select-option>
            <md-select-option value="0" :selected="form.continuous_drop_off === '0'">
              <div slot="headline">{{ t('routes.continuous_0') }}</div>
            </md-select-option>
            <md-select-option value="1" :selected="form.continuous_drop_off === '1'">
              <div slot="headline">{{ t('routes.continuous_1') }}</div>
            </md-select-option>
            <md-select-option value="2" :selected="form.continuous_drop_off === '2'">
              <div slot="headline">{{ t('routes.continuous_2') }}</div>
            </md-select-option>
            <md-select-option value="3" :selected="form.continuous_drop_off === '3'">
              <div slot="headline">{{ t('routes.continuous_3') }}</div>
            </md-select-option>
          </md-outlined-select>
        </div>

        <!-- Section: Other -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('routes.section_other') }}</span>

          <md-outlined-select
            :label="t('routes.field_cemv_support')"
            :disabled="isReadonly"
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
            {{ t('routes.delete') }}
          </md-filled-button>
          <span v-if="serverError" class="panel-error">{{ serverError }}</span>
        </div>
        <div class="panel-actions-right">
          <md-text-button :disabled="loading" @click="handleCancel">
            {{ t('routes.cancel') }}
          </md-text-button>
          <md-filled-button v-if="!isReadonly" :disabled="loading" @click="handleSave">
            {{ t('routes.save') }}
          </md-filled-button>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.route-edit-panel {
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
