<script setup>
/**
 * ShapeEditPanel â€” slide-in panel for viewing or editing a Fahrweg (Shape).
 *
 * Props:
 *   modelValue  â€” boolean      â€” visible state (v-model)
 *   shape       â€” object|null  â€” shape data to display/edit
 *   loading     â€” boolean      â€” disables actions while a request is in flight
 *   serverError â€” string|null  â€” error message to display
 *   canWrite    â€” boolean      â€” whether the user can save changes
 *   canDelete   â€” boolean      â€” whether the user can delete
 *   readonly    â€” boolean      â€” show read-only view (name not editable)
 *
 * Emits:
 *   update:modelValue
 *   save({ shape_name })
 *   delete()
 */
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  shape:       { type: Object,  default: null },
  loading:     { type: Boolean, default: false },
  serverError: { type: String,  default: null },
  canWrite:    { type: Boolean, default: false },
  canDelete:   { type: Boolean, default: false },
  readonly:    { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'save', 'delete'])
const { t } = useI18n()

const nameValue = ref('')

watch(
  () => props.shape,
  (shape) => { nameValue.value = shape?.shape_name ?? '' },
  { immediate: true },
)

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) nameValue.value = props.shape?.shape_name ?? ''
  },
)

const panelTitle = computed(() =>
  props.readonly ? t('shapes.panel_title_view') : t('shapes.panel_title_edit'),
)

function handleCancel() {
  emit('update:modelValue', false)
}

function handleSave() {
  if (props.readonly || !props.canWrite) return
  emit('save', { shape_name: nameValue.value.trim() || null })
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
            @input="nameValue = $event.target.value"
          />
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
</style>
