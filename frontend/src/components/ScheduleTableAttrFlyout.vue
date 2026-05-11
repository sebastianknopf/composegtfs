<script setup>
/**
 * ScheduleTableAttrFlyout — attribute flyout for schedule trip columns.
 *
 * Each attribute has three states: null (unset), true (yes), false (no).
 * The trigger shows:
 *   null  → icon not rendered
 *   true  → icon rendered normally
 *   false → icon rendered with a diagonal strikethrough
 *
 * Props:
 *   modelValue  — { wheelchair_accessible: null|true|false, bikes_allowed: null|true|false, cars_allowed: null|true|false }
 *   open        — boolean — controls flyout visibility
 *   isGhost     — boolean — ghost (dummy) styling
 *   readonly    — boolean — show value only, no dropdown allowed
 *   disabled    — boolean — disable all interactions
 *
 * Emits:
 *   update:modelValue  — emitted on every checkbox toggle (passes updated object)
 *   open               — emitted when trigger is activated
 *   close              — emitted when flyout should close
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue: {
    type:    Object,
    default: () => ({ wheelchair_accessible: null, bikes_allowed: null, cars_allowed: null }),
  },
  open:      { type: Boolean, default: false },
  isGhost:   { type: Boolean, default: false },
  readonly:  { type: Boolean, default: false },
  disabled:  { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'open', 'close'])
const { t } = useI18n()

const ATTRS = [
  { key: 'wheelchair_accessible', icon: 'accessible',      labelKey: 'schedule.attr_barrier_free' },
  { key: 'bikes_allowed',         icon: 'directions_bike', labelKey: 'schedule.attr_bikes'        },
  { key: 'cars_allowed',          icon: 'directions_car',  labelKey: 'schedule.attr_cars'         },
]

// Only attrs with a non-null value are shown in the trigger
const visibleAttrs = computed(() =>
  ATTRS.filter(a => props.modelValue?.[a.key] !== null && props.modelValue?.[a.key] !== undefined)
)

const hasAny = computed(() => visibleAttrs.value.length > 0)

/**
 * Toggle logic for a single Ja/Nein checkbox.
 * - Clicking the already-checked checkbox → resets to null
 * - Clicking the other checkbox → sets the new value
 */
function toggle(key, value) {
  if (props.disabled || props.readonly) return
  const current = props.modelValue?.[key] ?? null
  const next = current === value ? null : value
  emit('update:modelValue', { ...props.modelValue, [key]: next })
}

function onTriggerActivate() {
  if (props.disabled || props.readonly) return
  emit('open')
}

function onFocusOut(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    emit('close')
  }
}
</script>

<template>
  <div class="saf-wrap" @focusout="onFocusOut">
    <!-- Trigger: shows icons for set attributes -->
    <div
      class="saf-trigger"
      :class="{ 'saf-trigger--empty': !hasAny, 'saf-trigger--ghost': isGhost, 'saf-trigger--disabled': disabled || readonly }"
      :tabindex="disabled || readonly ? -1 : 0"
      @click="onTriggerActivate"
      @keydown.space.prevent="onTriggerActivate"
      @keydown.enter.prevent="onTriggerActivate"
      @keydown.escape="$emit('close')"
    >
      <template v-if="hasAny">
        <span
          v-for="a in visibleAttrs"
          :key="a.key"
          class="saf-trigger__icon-wrap"
          :class="{ 'saf-trigger__icon-wrap--no': modelValue[a.key] === false }"
        >
          <md-icon class="saf-trigger__icon">{{ a.icon }}</md-icon>
        </span>
      </template>
      <span v-else class="saf-trigger__placeholder">—</span>
    </div>

    <!-- Flyout: Ja / Nein checkboxes per attribute -->
    <div v-if="open && !disabled && !readonly" class="saf-flyout">
      <div
        v-for="attr in ATTRS"
        :key="attr.key"
        class="saf-row"
      >
        <md-icon class="saf-row__icon">{{ attr.icon }}</md-icon>
        <span class="saf-row__label">{{ t(attr.labelKey) }}</span>
        <label class="saf-check">
          <input
            type="checkbox"
            class="saf-checkbox"
            :checked="modelValue?.[attr.key] === true"
            @change="toggle(attr.key, true)"
          />
          <span class="saf-check__label">{{ t('common.yes') }}</span>
        </label>
        <label class="saf-check">
          <input
            type="checkbox"
            class="saf-checkbox"
            :checked="modelValue?.[attr.key] === false"
            @change="toggle(attr.key, false)"
          />
          <span class="saf-check__label">{{ t('common.no') }}</span>
        </label>
      </div>
    </div>
  </div>
</template>

<style scoped>
.saf-wrap {
  position: relative;
}

/* ---- Trigger ---- */
.saf-trigger {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  width: 100%;
  min-height: 1.25rem;
  padding: 0 0.25rem;
  cursor: pointer;
  outline: none;
  border-radius: 2px;
}

.saf-trigger:focus {
  box-shadow: 0 0 0 2px var(--md-sys-color-primary, #1f69e0);
}

.saf-trigger--disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.saf-trigger--disabled:focus {
  box-shadow: none;
}

/* Icon wrapper in trigger — enables strikethrough overlay */
.saf-trigger__icon-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

/* Diagonal strikethrough line for "Nein" state */
.saf-trigger__icon-wrap--no::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top right,
    transparent calc(50% - 1px),
    var(--md-sys-color-error, #b00020) calc(50% - 1px),
    var(--md-sys-color-error, #b00020) calc(50% + 1px),
    transparent calc(50% + 1px)
  );
  border-radius: 1px;
}

.saf-trigger__icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}

.saf-trigger__icon-wrap--no .saf-trigger__icon {
  color: var(--md-sys-color-error, #b00020);
  opacity: 0.6;
}

.saf-trigger--empty .saf-trigger__placeholder {
  color: var(--md-sys-color-outline, #bbb);
  font-size: var(--font-size-1, 0.875rem);
}

.saf-trigger--ghost .saf-trigger__placeholder {
  font-style: italic;
}

/* ---- Flyout ---- */
.saf-flyout {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 200;
  min-width: 220px;
  background: #fff;
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  padding: 0.375rem 0;
}

/* ---- Attribute row ---- */
.saf-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.625rem;
}

.saf-row__icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  flex-shrink: 0;
}

.saf-row__label {
  flex: 1;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface, #222);
  white-space: nowrap;
}

/* ---- Ja / Nein checkbox pairs ---- */
.saf-check {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}

.saf-check:hover .saf-check__label {
  color: var(--md-sys-color-primary, #1f69e0);
}

.saf-checkbox {
  width: 0.875rem;
  height: 0.875rem;
  cursor: pointer;
  accent-color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.saf-check__label {
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
}
</style>
