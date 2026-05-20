<script setup>
/**
 * ShapeEditPanel â€” slide-in panel for viewing or editing a Fahrweg (Shape).
 *
 * Props:
 *   modelValue         — boolean      — visible state (v-model)
 *   shape              — object|null  — shape data to display/edit
 *   loading            — boolean      — disables actions while a request is in flight
 *   serverError        — string|null  — error message to display
 *   canWrite           — boolean      — whether the user can save changes
 *   canDelete          — boolean      — whether the user can delete
 *   readonly           — boolean      — show read-only view (name not editable)
 *   intermediatePoints — array        — current list of intermediate points
 *   selectedPointIndex — number|null  — index of the selected point (for insert-after)
 *
 * Emits:
 *   update:modelValue
 *   save({ shape_name, description, route_type, is_autoroute_active })
 *   delete()
 *   remove-point(index)
 *   select-point(index)
 */
import { ref, watch, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/select/outlined-select.js'
import '@material/web/select/select-option.js'
import '@material/web/checkbox/checkbox.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:         { type: Boolean, default: false },
  shape:              { type: Object,  default: null },
  creating:           { type: Boolean, default: false },
  loading:            { type: Boolean, default: false },
  serverError:        { type: String,  default: null },
  canWrite:           { type: Boolean, default: false },
  canDelete:          { type: Boolean, default: false },
  readonly:           { type: Boolean, default: false },
  intermediatePoints: { type: Array,   default: () => [] },
  selectedPointIndex: { default: null },
})

const emit = defineEmits(['update:modelValue', 'save', 'delete', 'remove-point', 'select-point', 'autoroute-change'])
const { t } = useI18n()

// ---------------------------------------------------------------------------
// Form state
// ---------------------------------------------------------------------------
const nameValue        = ref('')
const descriptionValue = ref('')
const routeTypeValue   = ref('')
const autoRouteActive  = ref(false)
const nameError        = ref(null)

function populateForm(shape) {
  nameValue.value        = shape?.shape_name           ?? ''
  descriptionValue.value = shape?.description          ?? ''
  routeTypeValue.value   = shape?.route_type != null   ? String(shape.route_type) : ''
  autoRouteActive.value  = shape?.is_autoroute_active  ?? false
  nameError.value        = null
}

watch(() => props.shape,      (shape) => { populateForm(shape) }, { immediate: true })
watch(() => props.modelValue, (visible) => { if (visible) populateForm(props.shape) })

// ---------------------------------------------------------------------------
// Routing availability
// ---------------------------------------------------------------------------

const UNSUPPORTED_ROUTE_TYPES = new Set([0, 1, 2, 5, 7, 12])
const routingAvailable = ref(false)

const routingSupported = computed(() => {
  if (!routingAvailable.value) return false
  const rt = routeTypeValue.value.trim()
  if (rt === '') return false
  return !UNSUPPORTED_ROUTE_TYPES.has(parseInt(rt, 10))
})

async function checkRoutingHealth() {
  try {
    const res = await api.routing.health()
    routingAvailable.value = res.available === true
  } catch {
    routingAvailable.value = false
  }
}

onMounted(checkRoutingHealth)

// Notify parent whenever auto-routing or route-type changes, so the map
// can trigger live routing without waiting for a save.
function emitAutoRouteChange(active) {
  const routeType = routeTypeValue.value !== '' ? parseInt(routeTypeValue.value, 10) : null
  emit('autoroute-change', { active, routeType })
}

function onAutoRouteChange(val) {
  autoRouteActive.value = val
  emitAutoRouteChange(val)
}

// Re-trigger routing when route type changes while auto-routing is on.
watch(routeTypeValue, (newVal) => {
  if (autoRouteActive.value) {
    const routeType = newVal !== '' ? parseInt(newVal, 10) : null
    emit('autoroute-change', { active: true, routeType })
  }
})

// ---------------------------------------------------------------------------

const panelTitle = computed(() => {
  if (props.creating) return t('shapes.panel_title_create')
  return props.readonly ? t('shapes.panel_title_view') : t('shapes.panel_title_edit')
})

function handleCancel() {
  emit('update:modelValue', false)
}

function handleSave() {
  if (props.readonly || !props.canWrite) return
  if (!nameValue.value.trim()) {
    nameError.value = t('shapes.validation_name_required')
    return
  }
  nameError.value = null
  const rt = routeTypeValue.value.trim()
  emit('save', {
    shape_name:          nameValue.value.trim()        || null,
    description:         descriptionValue.value.trim() || null,
    route_type:          rt !== '' ? parseInt(rt, 10)  : null,
    is_autoroute_active: autoRouteActive.value,
  })
}

function handleDelete() {
  if (props.readonly || !props.canDelete) return
  emit('delete')
}
</script>

<template>
  <Transition name="panel-slide">
    <aside v-if="modelValue" class="shape-edit-panel">

      <!-- Header -->
      <div class="panel-header">
        <span class="panel-title">{{ panelTitle }}</span>
        <button class="panel-close-btn" @click="handleCancel" :aria-label="t('shapes.cancel')">
          <md-icon>close</md-icon>
        </button>
      </div>

      <!-- Scrollable content -->
      <div class="panel-content">
        <div class="panel-section">
          <span class="panel-section-label">{{ t('shapes.section_properties') }}</span>
          <md-outlined-text-field
            :label="t('shapes.field_name')"
            :value="nameValue"
            :disabled="readonly"
            :error="!!nameError"
            :error-text="nameError ?? ''"
            @input="nameValue = $event.target.value; nameError = null"
          />
          <md-outlined-text-field
            type="textarea"
            rows="2"
            :label="t('shapes.field_description')"
            :value="descriptionValue"
            :disabled="readonly"
            @input="descriptionValue = $event.target.value"
          />
          <md-outlined-select
            :label="t('shapes.field_route_type')"
            :disabled="readonly"
            @change="routeTypeValue = $event.target.value"
          >
            <md-select-option value="" :selected="routeTypeValue === ''">
              <div slot="headline">{{ t('routes.type_empty') }}</div>
            </md-select-option>
            <md-select-option value="0" :selected="routeTypeValue === '0'">
              <div slot="headline">{{ t('routes.type_0') }}</div>
            </md-select-option>
            <md-select-option value="1" :selected="routeTypeValue === '1'">
              <div slot="headline">{{ t('routes.type_1') }}</div>
            </md-select-option>
            <md-select-option value="2" :selected="routeTypeValue === '2'">
              <div slot="headline">{{ t('routes.type_2') }}</div>
            </md-select-option>
            <md-select-option value="3" :selected="routeTypeValue === '3'">
              <div slot="headline">{{ t('routes.type_3') }}</div>
            </md-select-option>
            <md-select-option value="4" :selected="routeTypeValue === '4'">
              <div slot="headline">{{ t('routes.type_4') }}</div>
            </md-select-option>
            <md-select-option value="5" :selected="routeTypeValue === '5'">
              <div slot="headline">{{ t('routes.type_5') }}</div>
            </md-select-option>
            <md-select-option value="6" :selected="routeTypeValue === '6'">
              <div slot="headline">{{ t('routes.type_6') }}</div>
            </md-select-option>
            <md-select-option value="7" :selected="routeTypeValue === '7'">
              <div slot="headline">{{ t('routes.type_7') }}</div>
            </md-select-option>
            <md-select-option value="11" :selected="routeTypeValue === '11'">
              <div slot="headline">{{ t('routes.type_11') }}</div>
            </md-select-option>
            <md-select-option value="12" :selected="routeTypeValue === '12'">
              <div slot="headline">{{ t('routes.type_12') }}</div>
            </md-select-option>
          </md-outlined-select>
          <template v-if="routingAvailable">
            <label v-if="routingSupported" class="shape-checkbox-row">
              <md-checkbox
                touch-target="wrapper"
                :checked="autoRouteActive"
                :disabled="readonly || undefined"
                @change="onAutoRouteChange($event.target.checked)"
              />
              <span class="shape-checkbox-label">{{ t('shapes.field_is_autoroute_active') }}</span>
            </label>
            <span v-else class="shape-routing-unsupported">{{ t('shapes.routing_unsupported_type') }}</span>
          </template>
        </div>

        <!-- Section: Intermediate points (Zwischenpunkte) -->
        <div class="panel-section">
          <span class="panel-section-label">{{ t('shapes.section_intermediate_points') }}</span>
          <div v-if="!intermediatePoints.length" class="panel-section-placeholder">
            {{ t('shapes.intermediate_points_empty') }}
          </div>
          <div v-else class="shape-points-list">
            <div
              v-for="(pt, idx) in intermediatePoints"
              :key="idx"
              class="shape-point-row"
              :class="[
                pt.stop_id ? 'shape-point-row--stop' : 'shape-point-row--coord',
                idx === selectedPointIndex ? 'shape-point-row--selected' : '',
              ]"
              @click="emit('select-point', idx)"
            >
              <md-icon class="shape-point-row__icon">
                {{ pt.stop_id ? 'directions_bus' : 'location_on' }}
              </md-icon>
              <span class="shape-point-row__label">
                <template v-if="pt.stop_id">
                  {{ pt.stop_name || pt.stop_id }}<template v-if="pt.platform_code"> ({{ pt.platform_code }})</template>
                </template>
                <template v-else>
                  {{ pt.lat?.toFixed(5) }}, {{ pt.lon?.toFixed(5) }}
                </template>
              </span>
              <button
                v-if="!readonly && canWrite"
                type="button"
                class="shape-point-row__delete"
                :aria-label="t('shapes.remove_point')"
                @click.stop="emit('remove-point', idx)"
              >
                <md-icon>close</md-icon>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="panel-actions">
        <div class="panel-actions-left">
          <md-filled-button
            v-if="!readonly && canDelete"
            :disabled="loading"
            class="panel-delete-btn"
            @click="handleDelete"
          >
            <md-icon slot="icon">delete</md-icon>
            {{ t('shapes.delete') }}
          </md-filled-button>
          <span v-if="serverError" class="panel-error">{{ serverError }}</span>
        </div>
        <div class="panel-actions-right">
          <md-text-button :disabled="loading" @click="handleCancel">
            {{ t('shapes.cancel') }}
          </md-text-button>
          <md-filled-button v-if="!readonly" :disabled="loading" @click="handleSave">
            {{ t('shapes.save') }}
          </md-filled-button>
        </div>
      </div>

    </aside>
  </Transition>
</template>

<style scoped>
.shape-edit-panel {
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
  z-index: 12;
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

.panel-section md-outlined-text-field {
  width: 100%;
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
}

.panel-actions-right {
  display: flex;
  align-items: center;
  gap: 8px;
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

.panel-error {
  font-size: var(--font-size-0, 0.78rem);
  color: var(--md-sys-color-error, #b3261e);
}

.shape-checkbox-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.shape-checkbox-label {
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #222);
}

.shape-routing-unsupported {
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-error, #b3261e);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0;
}

.panel-section-placeholder {
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-outline, #74777f);
  margin: 0;
}

/* Intermediate points list */
.shape-points-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.shape-point-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.12s;
}

.shape-point-row:hover {
  background: rgba(21, 101, 192, 0.08);
}

.shape-point-row--selected {
  background: #e3f2fd;
}

.shape-point-row__icon {
  flex-shrink: 0;
  font-size: 18px;
  width: 20px;
  height: 20px;
}

.shape-point-row--stop .shape-point-row__icon {
  color: var(--md-sys-color-primary, #1a73e8);
}

.shape-point-row--coord .shape-point-row__icon {
  color: var(--md-sys-color-outline, #74777f);
}

.shape-point-row__label {
  flex: 1;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #222);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shape-point-row__delete {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--md-sys-color-outline, #74777f);
  padding: 2px;
  display: flex;
  align-items: center;
  border-radius: 4px;
}

.shape-point-row__delete:hover {
  color: var(--md-sys-color-error, #b3261e);
  background: var(--md-sys-color-error-container, #ffdad6);
}
</style>
