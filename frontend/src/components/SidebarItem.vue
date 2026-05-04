<script setup>
import '@material/web/icon/icon.js'

/**
 * SidebarItem — a single navigation entry in an AppSideBar.
 *
 * Props:
 *   icon      — Material Symbols ligature name
 *   label     — resolved (translated) label string
 *   active    — whether this item is the currently active view
 *   collapsed — whether the parent sidebar is in collapsed mode
 *               (switches from text label to title tooltip)
 */
defineProps({
  icon:      { type: String,  required: true },
  label:     { type: String,  required: true },
  active:    { type: Boolean, default: false },
  collapsed: { type: Boolean, default: false },
})

defineEmits(['click'])
</script>

<template>
  <button
    class="sidebar-item"
    :class="{ 'sidebar-item--active': active }"
    :title="collapsed ? label : undefined"
    :aria-label="label"
    @click="$emit('click')"
  >
    <md-icon class="sidebar-item__icon">{{ icon }}</md-icon>
    <span class="sidebar-item__label">{{ label }}</span>
  </button>
</template>
