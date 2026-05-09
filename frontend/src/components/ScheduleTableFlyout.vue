<script setup>
/**
 * ScheduleTableFlyout — generic searchable dropdown flyout for table header cells.
 *
 * Props:
 *   modelValue   — the currently selected id (stored value)
 *   items        — Array<{ id: string, label: string, sublabel?: string }>
 *   placeholder  — placeholder for the trigger when nothing is selected
 *   searchPlaceholder — placeholder for the search field
 *   open         — boolean — controls whether the flyout is shown
 *
 * Emits:
 *   update:modelValue  — emitted when a new item is selected (passes id)
 *   open               — emitted when the trigger is activated
 *   close              — emitted when the flyout should close
 */
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue:        { type: String,  default: '' },
  items:             { type: Array,   default: () => [] },
  placeholder:       { type: String,  default: '—' },
  searchPlaceholder: { type: String,  default: 'Suchen …' },
  open:              { type: Boolean, default: false },
  isGhost:           { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'open', 'close'])

const searchQuery = ref('')

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return props.items
  return props.items.filter(item =>
    item.id.toLowerCase().includes(q) ||
    item.label.toLowerCase().includes(q) ||
    (item.sublabel && item.sublabel.toLowerCase().includes(q))
  )
})

const selectedLabel = computed(() => {
  if (!props.modelValue) return ''
  const found = props.items.find(i => i.id === props.modelValue)
  return found ? found.label : props.modelValue
})

function onTriggerActivate() {
  searchQuery.value = ''
  emit('open')
}

function onSelect(item) {
  emit('update:modelValue', item.id)
  emit('close')
}

function onFocusOut(e) {
  // Only close if focus leaves the entire flyout wrapper
  if (!e.currentTarget.contains(e.relatedTarget)) {
    emit('close')
  }
}
</script>

<template>
  <div
    class="sft-wrap"
    @focusout="onFocusOut"
  >
    <!-- Trigger -->
    <div
      class="sft-trigger"
      :class="{
        'sft-trigger--empty': !modelValue,
        'sft-trigger--ghost': isGhost,
      }"
      tabindex="0"
      @click="onTriggerActivate"
      @keydown.space.prevent="onTriggerActivate"
      @keydown.enter.prevent="onTriggerActivate"
      @keydown.escape="$emit('close')"
    >
      <template v-if="modelValue">{{ selectedLabel }}</template>
      <span v-else class="sft-trigger__placeholder">{{ placeholder }}</span>
    </div>

    <!-- Flyout -->
    <div v-if="open" class="sft-flyout">
      <input
        class="sft-search"
        v-model="searchQuery"
        :placeholder="searchPlaceholder"
        @click.stop
        @keydown.escape="$emit('close')"
      />
      <ul class="sft-list" role="listbox">
        <li v-if="filteredItems.length === 0" class="sft-empty">
          <slot name="empty">–</slot>
        </li>
        <li
          v-for="item in filteredItems"
          :key="item.id"
          class="sft-item"
          :class="{ 'sft-item--selected': item.id === modelValue }"
          role="option"
          :aria-selected="item.id === modelValue"
          @mousedown.prevent="onSelect(item)"
        >
          <span class="sft-item__label">{{ item.label }}</span>
          <span v-if="item.sublabel" class="sft-item__sublabel">{{ item.sublabel }}</span>
        </li>
      </ul>
      <div v-if="$slots.footer" class="sft-footer">
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.sft-wrap {
  position: relative;
}

.sft-trigger {
  display: block;
  width: 100%;
  padding: 0 0.25rem;
  min-height: 1.25rem;
  line-height: 1.25rem;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-on-surface, #222);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  outline: none;
  border-radius: 2px;
}

.sft-trigger:focus {
  box-shadow: 0 0 0 2px var(--md-sys-color-primary, #1f69e0);
}

.sft-trigger--empty {
  color: var(--md-sys-color-outline, #bbb);
}

.sft-trigger--ghost .sft-trigger__placeholder,
.sft-trigger--ghost.sft-trigger--empty {
  font-style: italic;
}

.sft-trigger__placeholder {
  font-style: normal;
}

.sft-flyout {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 200;
  min-width: 220px;
  background: #fff;
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.sft-search {
  display: block;
  width: 100%;
  padding: 0.375rem 0.625rem;
  border: none;
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  background: transparent;
  color: var(--md-sys-color-on-surface, #222);
  outline: none;
  box-sizing: border-box;
}

.sft-search:focus {
  border-bottom-color: var(--md-sys-color-primary, #1f69e0);
}

.sft-list {
  list-style: none;
  padding: 0.25rem 0;
  margin: 0;
  max-height: 200px;
  overflow-y: auto;
}

.sft-empty {
  padding: 0.375rem 0.625rem;
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-outline, #aaa);
}

.sft-footer {
  border-top: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  padding: 0.25rem 0;
}

.sft-item {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.325rem 0.625rem;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  transition: background 0.1s;
}

.sft-item:hover,
.sft-item--selected {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
}

.sft-item__label {
  color: var(--md-sys-color-on-surface, #222);
}

.sft-item__sublabel {
  font-size: var(--font-size-0, 0.8125rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  flex-shrink: 0;
}
</style>
