<script setup>
/**
 * TagSelect — a multi-select component with chip-style tags and a search dropdown.
 *
 * Props:
 *   modelValue    — Array<id>          — IDs of currently selected options (v-model)
 *   options       — Array<{id, label}> — all available options to choose from
 *   label         — string             — floating label on the search input
 *   noResultsText — string             — text shown when search yields no matches
 *
 * Emits:
 *   update:modelValue — emitted with the new array of selected IDs on each change
 */
import { ref, computed, nextTick } from 'vue'
import '@material/web/chips/chip-set.js'
import '@material/web/chips/input-chip.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:    { type: Array,  default: () => [] },
  options:       { type: Array,  default: () => [] },
  label:         { type: String, default: '' },
  noResultsText: { type: String, default: 'No results' },
})

const emit = defineEmits(['update:modelValue'])

const searchQuery  = ref('')
const dropdownOpen = ref(false)
const wrapRef      = ref(null)
const dropdownStyle = ref({})

function recalcDropdownPosition() {
  if (!wrapRef.value) return
  const rect = wrapRef.value.getBoundingClientRect()
  dropdownStyle.value = {
    top:   `${rect.bottom + 2}px`,
    left:  `${rect.left}px`,
    width: `${rect.width}px`,
  }
}

const selectedOptions = computed(() =>
  props.options.filter(o => props.modelValue.includes(o.id))
)

const filteredOptions = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  return props.options.filter(
    o => !props.modelValue.includes(o.id) &&
         (q === '' || o.label.toLowerCase().includes(q))
  )
})

function select(option) {
  emit('update:modelValue', [...props.modelValue, option.id])
  searchQuery.value = ''
}

function remove(id) {
  emit('update:modelValue', props.modelValue.filter(x => x !== id))
}

function openDropdown() {
  dropdownOpen.value = true
  nextTick(recalcDropdownPosition)
}

function closeDropdown() {
  dropdownOpen.value = false
  searchQuery.value = ''
}
</script>

<template>
  <div class="tag-select">

    <!-- Search input + dropdown -->
    <div ref="wrapRef" class="tag-select__wrap">
      <md-outlined-text-field
        class="tag-select__field"
        :label="label"
        :value="searchQuery"
        autocomplete="off"
        @input="searchQuery = $event.target.value; dropdownOpen = true"
        @focus="openDropdown"
        @blur="closeDropdown"
      >
        <md-icon slot="leading-icon">search</md-icon>
      </md-outlined-text-field>

      <!-- Dropdown list -->
      <ul
        v-if="dropdownOpen && filteredOptions.length > 0"
        class="tag-select__dropdown"
        :style="dropdownStyle"
        role="listbox"
      >
        <li
          v-for="opt in filteredOptions"
          :key="opt.id"
          class="tag-select__option"
          role="option"
          @mousedown.prevent="select(opt)"
        >
          {{ opt.label }}
        </li>
      </ul>

      <!-- No results -->
      <div
        v-if="dropdownOpen && filteredOptions.length === 0 && searchQuery.length > 0"
        class="tag-select__dropdown tag-select__dropdown--empty"
        :style="dropdownStyle"
      >
        {{ noResultsText }}
      </div>
    </div>

    <!-- Selected chips -->
    <md-chip-set v-if="selectedOptions.length > 0" class="tag-select__chips">
      <md-input-chip
        v-for="opt in selectedOptions"
        :key="opt.id"
        :label="opt.label"
        remove-only
        @remove="remove(opt.id)"
      />
    </md-chip-set>

  </div>
</template>

<style scoped>
.tag-select {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.tag-select__chips {
  --md-input-chip-container-shape: 6px;
  flex-wrap: wrap;
}

.tag-select__wrap {
  position: relative;
}

.tag-select__field {
  width: 100%;
}

.tag-select__dropdown {
  position: fixed;
  z-index: 9999;
  margin: 0;
  padding: 0.25rem 0;
  list-style: none;
  background: #ffffff;
  border: 1px solid var(--md-sys-color-outline-variant, #cac4d0);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  max-height: 220px;
  overflow-y: auto;
}

.tag-select__dropdown--empty {
  padding: 0.625rem 1rem;
  font-size: 0.875rem;
  color: var(--md-sys-color-on-surface-variant, #49454f);
  cursor: default;
}

.tag-select__option {
  padding: 0.5rem 1rem;
  font-size: 0.9375rem;
  cursor: pointer;
  color: var(--md-sys-color-on-surface, #1c1b1f);
  transition: background 0.1s;
}

.tag-select__option:hover {
  background: color-mix(in srgb, var(--md-sys-color-primary, #1f69e0) 8%, transparent);
}
</style>
