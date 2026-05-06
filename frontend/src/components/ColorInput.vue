<script setup>
/**
 * ColorInput — inline color field: swatch + outlined text field + clear button.
 * Opens ColorPickerModal when the swatch is clicked.
 *
 * Props:
 *   modelValue — string  — 6-char hex without '#', or empty string
 *   label      — string  — field label (shown inside the md-outlined-text-field)
 *   disabled   — boolean — disables all interaction
 *   error      — string  — validation error text shown below the field (null = no error)
 *
 * Emits:
 *   update:modelValue(hex) — new hex value (6-char or '' to clear)
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/icon/icon.js'
import ColorPickerModal from '@/components/ColorPickerModal.vue'

const props = defineProps({
  modelValue: { type: String,  default: '' },
  label:      { type: String,  default: '' },
  disabled:   { type: Boolean, default: false },
  error:      { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const pickerOpen = ref(false)

function onInput(e) {
  emit('update:modelValue', e.target.value.replace(/^#/, '').toUpperCase())
}
</script>

<template>
  <div class="color-input">
    <md-outlined-text-field
      class="color-input__field"
      :label="label"
      :value="modelValue ? modelValue.toUpperCase() : ''"
      maxlength="6"
      :disabled="disabled"
      :error="!!error"
      :error-text="error ?? ''"
      @input="onInput"
    />

    <button
      type="button"
      class="color-input__swatch"
      :class="{ 'color-input__swatch--empty': !modelValue }"
      :style="modelValue ? { background: '#' + modelValue } : {}"
      :disabled="disabled"
      :title="t('color_picker.open')"
      @click="pickerOpen = true"
    />

    <button
      v-if="modelValue && !disabled"
      type="button"
      class="color-input__clear"
      :title="t('color_picker.clear')"
      @click="emit('update:modelValue', '')"
    >
      <md-icon>close</md-icon>
    </button>

    <ColorPickerModal
      :open="pickerOpen"
      :model-value="modelValue"
      :label="label"
      @update:model-value="emit('update:modelValue', $event)"
      @close="pickerOpen = false"
    />
  </div>
</template>

<style scoped>
.color-input {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

/* Swatch button — circle, centered to the 56px text field height */
.color-input__swatch {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid var(--md-sys-color-outline);
  cursor: pointer;
  flex-shrink: 0;
  padding: 0;
  margin-top: 8px; /* (56px field - 40px swatch) / 2 */
  transition: border-color 0.15s;
}
.color-input__swatch:hover:not(:disabled) { border-color: var(--md-sys-color-primary); }
.color-input__swatch:disabled { opacity: 0.5; cursor: not-allowed; }
.color-input__swatch--empty {
  background: repeating-linear-gradient(
    45deg,
    var(--md-sys-color-surface-variant, #e7e8ec) 0px,
    var(--md-sys-color-surface-variant, #e7e8ec) 4px,
    var(--md-sys-color-outline-variant, #c4c6d0) 4px,
    var(--md-sys-color-outline-variant, #c4c6d0) 5px
  );
}

/* Text field fills remaining width */
.color-input__field { flex: 1; }

/* Clear button — icon button, centered to the 56px text field height */
.color-input__clear {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  color: var(--md-sys-color-on-surface-variant);
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 12px; /* (56px field - 32px button) / 2 */
}
.color-input__clear:hover {
  color: var(--md-sys-color-error);
  background: rgba(186, 26, 26, 0.08);
}
</style>
