<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { routesStore } from '@/stores/routes.js'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-tonal-button.js'

const { t } = useI18n()

/**
 * RoutesSideBar — collapsible sidebar listing routes for the active version.
 *
 * Props:
 *   canWrite — whether the current user may create/edit routes
 *   sectionId — localStorage key namespace for collapse state
 *
 * Emits:
 *   add-route     — user clicked "Linie hinzufügen"
 *   route-select  — user clicked a route item (emits route object)
 */
const props = defineProps({
  canWrite:   { type: Boolean, default: false },
  canRead:    { type: Boolean, default: false },
  sectionId:  { type: String,  default: 'routes' },
  showTitle:  { type: Boolean, default: true },
  /** When provided, use these routes instead of the global routesStore. */
  routes:     { type: Array,   default: null },
})

const emit = defineEmits(['add-route', 'route-select', 'reorder'])

// ---- Collapse state ----
function _storageKey(id) {
  return `sidebar-collapsed:${id}`
}

const collapsed = ref(localStorage.getItem(_storageKey(props.sectionId)) === 'true')

watch(() => props.sectionId, (id) => {
  collapsed.value = localStorage.getItem(_storageKey(id)) === 'true'
})

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(_storageKey(props.sectionId), String(collapsed.value))
}

// ---- Routes — local ordered list ----
// When the `routes` prop is provided, use it directly (read-only, no reorder).
// Otherwise, drive from the global routesStore with drag-and-drop reorder support.
const orderedRoutes = ref([])

function _sortRoutes(routes) {
  return [...routes].sort((a, b) => {
    const aOrder = a.route_sort_order ?? Infinity
    const bOrder = b.route_sort_order ?? Infinity
    if (aOrder !== bOrder) return aOrder - bOrder
    return (a.route_id ?? '').localeCompare(b.route_id ?? '')
  })
}

watch(() => props.routes ?? routesStore.state.routes, (routes) => {
  orderedRoutes.value = _sortRoutes(routes ?? [])
}, { immediate: true })

// ---- Drag-and-drop ----
const dragSrcIndex  = ref(null)
const dragOverIndex = ref(null)

function onDragStart(event, index) {
  dragSrcIndex.value = index
  event.dataTransfer.effectAllowed = 'move'
}

function onDragOver(event, index) {
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dragOverIndex.value = index
}

function onDragEnd() {
  dragSrcIndex.value  = null
  dragOverIndex.value = null
}

function onDrop(event, index) {
  event.preventDefault()
  const src = dragSrcIndex.value
  onDragEnd()
  if (src === null || src === index) return
  // Reorder only supported when driven by the store (no routes prop)
  if (props.routes !== null) return
  const items = [...orderedRoutes.value]
  const [moved] = items.splice(src, 1)
  items.splice(index, 0, moved)
  orderedRoutes.value = items
  emit('reorder', items)
}

function routeLabel(route) {
  return route.route_short_name?.trim() || route.route_long_name?.trim() || route.route_id
}

function routeColor(route) {
  return route.route_color ? `#${route.route_color}` : 'var(--md-sys-color-outline, #74777f)'
}

function routeTextColor(route) {
  return route.route_text_color ? `#${route.route_text_color}` : null
}

function isSelected(route) {
  return routesStore.state.selectedRouteId === route.route_id
}

function selectRoute(route) {
  routesStore.select(route.route_id)
  emit('route-select', route)
}
</script>

<template>
  <nav
    :class="['routes-sidebar', { 'routes-sidebar--collapsed': collapsed }]"
    :aria-label="t('routes.sidebar_label')"
  >
    <!-- Collapse toggle -->
    <div class="routes-sidebar__collapse">
      <button
        class="sidebar-collapse-btn"
        :title="collapsed ? t('sidebar.expand') : t('sidebar.collapse')"
        :aria-label="collapsed ? t('sidebar.expand') : t('sidebar.collapse')"
        @click="toggleCollapse"
      >
        <md-icon>{{ collapsed ? 'chevron_right' : 'chevron_left' }}</md-icon>
      </button>
    </div>

    <!-- Section title (only when readable and showTitle is true, hidden when collapsed) -->
    <div v-if="canRead && showTitle" class="routes-sidebar__section-title" aria-hidden="true">{{ t('routes.sidebar_label') }}</div>

    <!-- "Linie hinzufügen" button -->
    <div v-if="canWrite" class="routes-sidebar__add">
      <button
        class="routes-sidebar__add-btn"
        :title="collapsed ? t('routes.add_route') : undefined"
        @click="emit('add-route')"
      >
        <md-icon class="routes-sidebar__add-icon">add</md-icon>
        <span class="routes-sidebar__add-label">{{ t('routes.add_route') }}</span>
      </button>
    </div>

    <!-- Route list -->
    <div class="routes-sidebar__list">
      <div
        v-for="(route, index) in orderedRoutes"
        :key="route.route_id"
        :class="[
          'route-item',
          { 'route-item--active': isSelected(route) },
          { 'route-item--drag-over': dragOverIndex === index && dragSrcIndex !== index },
        ]"
        :draggable="canWrite && !collapsed && routes === null ? 'true' : 'false'"
        :title="collapsed ? routeLabel(route) : undefined"
        role="button"
        tabindex="0"
        @click="selectRoute(route)"
        @keydown.enter="selectRoute(route)"
        @keydown.space.prevent="selectRoute(route)"
        @dragstart="onDragStart($event, index)"
        @dragover="onDragOver($event, index)"
        @dragend="onDragEnd"
        @drop="onDrop($event, index)"
      >
        <!-- Colored bar -->
        <span
          class="route-item__bar"
          :style="{ backgroundColor: routeColor(route) }"
        />
        <!-- Collapsed: short name or first letter of long name -->
        <span
          v-if="collapsed"
          :class="['route-item__short', 'route-item__short--always']"
        >
          {{ route.route_short_name?.trim() || route.route_long_name?.trim()[0]?.toUpperCase() || route.route_id }}
        </span>

        <!-- Expanded: short name with prefix, OR long name, OR id -->
        <template v-if="!collapsed">
          <span v-if="route.route_short_name?.trim()" class="route-item__short">
            {{ t('routes.route_prefix') }} {{ route.route_short_name.trim() }}
          </span>
          <span v-else-if="route.route_long_name?.trim()" class="route-item__long">
            {{ route.route_long_name.trim() }}
          </span>
          <span v-else class="route-item__long">{{ route.route_id }}</span>
        </template>
      </div>

      <p v-if="orderedRoutes.length === 0 && !routesStore.state.loading" class="routes-sidebar__empty">
        <span v-if="!collapsed">{{ t('routes.no_routes') }}</span>
      </p>
    </div>
  </nav>
</template>

<style scoped>
.routes-sidebar {
  width: var(--app-sidebar-width, 240px);
  flex-shrink: 0;
  background: var(--app-sidebar-bg, #f5f6fa);
  border-right: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
  display: flex;
  flex-direction: column;
  padding: var(--size-2, 0.5rem) 0;
  transition: width 0.2s ease;
  overflow: hidden;
  height: 100%;
}

.routes-sidebar--collapsed {
  width: 56px;
}

/* Collapse toggle */
.routes-sidebar__collapse {
  display: flex;
  justify-content: flex-end;
  padding: var(--size-1, 0.25rem) var(--size-2, 0.5rem) var(--size-2, 0.5rem);
  flex-shrink: 0;
}

.routes-sidebar--collapsed .routes-sidebar__collapse {
  justify-content: center;
}

/* Add button */
.routes-sidebar__add {
  padding: 0 var(--size-2, 0.5rem) var(--size-2, 0.5rem);
  flex-shrink: 0;
}

.routes-sidebar--collapsed .routes-sidebar__add {
  padding: 0 0 var(--size-2, 0.5rem);
  display: flex;
  justify-content: center;
  align-items: center;
}

.routes-sidebar__add-btn {
  display: flex;
  align-items: center;
  gap: var(--size-2, 0.5rem);
  width: 100%;
  background: var(--md-sys-color-primary-container, #d8e2ff);
  color: var(--md-sys-color-on-primary-container, #001a42);
  border: none;
  border-radius: 6px;
  padding: var(--size-2, 0.5rem) var(--size-3, 0.75rem);
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  transition: background 0.15s ease, color 0.15s ease;
}

.routes-sidebar__add-btn:hover {
  background: var(--md-sys-color-primary, #1f69e0);
  color: #ffffff;
}

.routes-sidebar__add-icon {
  flex-shrink: 0;
  font-size: 18px;
  --md-icon-size: 18px;
}

.routes-sidebar__add-label {
  overflow: hidden;
  text-overflow: ellipsis;
  transition: opacity 0.15s ease, width 0.2s ease;
}

.routes-sidebar--collapsed .routes-sidebar__add-label {
  opacity: 0;
  width: 0;
  pointer-events: none;
}

.routes-sidebar--collapsed .routes-sidebar__add-btn {
  width: 36px;
  height: 36px;
  min-width: 36px;
  padding: 0;
  justify-content: center;
  border-radius: 50%;
  gap: 0;
}

/* Route list */
.routes-sidebar__list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 var(--size-1, 0.25rem);
}

.routes-sidebar--collapsed .routes-sidebar__list {
  padding: 0 var(--size-1, 0.25rem);
}

/* Route item */
.route-item {
  display: flex;
  align-items: center;
  min-height: 40px;
  height: 40px;
  border-radius: 6px;
  cursor: pointer;
  overflow: hidden;
  position: relative;
  user-select: none;
  transition: background 0.12s ease;
}

.route-item:hover {
  background: rgba(0, 0, 0, 0.05);
}

.route-item--active {
  background: rgba(31, 105, 224, 0.12);
}

.route-item--active .route-item__short,
.route-item--active .route-item__long {
  color: #1f69e0;
  font-weight: 600;
}

/* The colored bar */
.route-item__bar {
  display: block;
  flex-shrink: 0;
  width: 5px;
  height: 100%;
  border-radius: 3px 0 0 3px;
  margin-right: var(--size-2, 0.5rem);
  align-self: stretch;
}

/* Drag feedback */
.route-item--drag-over {
  outline: 2px solid var(--md-sys-color-primary, #1f69e0);
  outline-offset: -2px;
  border-radius: 6px;
}

.route-item[draggable="true"] {
  cursor: grab;
}

.route-item[draggable="true"]:active {
  cursor: grabbing;
  opacity: 0.7;
}

/* Labels */
.route-item__short {
  font-size: var(--font-size-1, 0.875rem);
  font-weight: 500;
  color: var(--app-sidebar-color, #1a1c2e);
  align-self: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  padding: var(--size-2, 0.5rem) var(--size-2, 0.5rem) var(--size-2, 0.5rem) 0;
  transition: opacity 0.15s ease;
}

/* Short name is always shown — even collapsed — because it's compact */
.routes-sidebar--collapsed .route-item__short {
  /* still visible but width-constrained; let the sidebar width clip it */
}

.route-item__long {
  font-size: var(--font-size-1, 0.875rem);
  color: var(--app-sidebar-color, #1a1c2e);
  align-self: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  padding: var(--size-2, 0.5rem) var(--size-2, 0.5rem) var(--size-2, 0.5rem) 0;
  transition: opacity 0.15s ease;
}

/* Long name is hidden when collapsed */
.routes-sidebar--collapsed .route-item__long {
  opacity: 0;
  width: 0;
  padding: 0;
  pointer-events: none;
}

/* Collapsed: center the bar inside the narrow sidebar and center short name text */
.routes-sidebar--collapsed .route-item {
  justify-content: center;
  padding: 0;
  height: 40px;
  min-height: 40px;
  position: relative;
}

.routes-sidebar--collapsed .route-item__bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  height: 100%;
  margin-right: 0;
  border-radius: 2px 0 0 2px;
}

.routes-sidebar--collapsed .route-item__short {
  flex: 0 1 auto;
  text-align: center;
  max-width: 100%;
  padding: 0;
}

/* Section title */
.routes-sidebar__section-title {
  padding: 0 var(--size-2, 0.5rem) var(--size-3, 0.75rem) var(--size-2, 0.5rem);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
  white-space: nowrap;
  overflow: hidden;
}

.routes-sidebar--collapsed .routes-sidebar__section-title {
  display: none;
}

/* Empty message */
.routes-sidebar__empty {
  padding: var(--size-4, 1rem) var(--size-3, 0.75rem);
  font-size: var(--font-size-0, 0.8rem);
  color: var(--md-sys-color-outline, #74777f);
  text-align: center;
  margin: 0;
}
</style>
