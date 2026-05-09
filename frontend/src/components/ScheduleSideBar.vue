<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/icon/icon.js'

const { t } = useI18n()

/**
 * ScheduleSideBar — collapsible sidebar listing routes for the schedule view.
 * Fully independent from routesStore; selection state is managed locally.
 *
 * Props:
 *   routes    — array of route objects (route_id, route_short_name, route_long_name,
 *               route_color, route_text_color, route_sort_order)
 *   sectionId — localStorage key namespace for collapse state
 *
 * Emits:
 *   route-select — user clicked a route item (emits route object)
 */
const props = defineProps({
  routes:    { type: Array,  default: () => [] },
  sectionId: { type: String, default: 'schedule-routes' },
})

const emit = defineEmits(['route-select'])

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

// ---- Routes — sorted by route_sort_order, then route_id ----
const orderedRoutes = ref([])

function _sortRoutes(routes) {
  return [...routes].sort((a, b) => {
    const aOrder = a.route_sort_order ?? Infinity
    const bOrder = b.route_sort_order ?? Infinity
    if (aOrder !== bOrder) return aOrder - bOrder
    return (a.route_id ?? '').localeCompare(b.route_id ?? '')
  })
}

watch(() => props.routes, (routes) => {
  orderedRoutes.value = _sortRoutes(routes ?? [])
}, { immediate: true })

// ---- Local selection state (independent of routesStore) ----
const selectedRouteId = ref(null)

function isSelected(route) {
  return selectedRouteId.value === route.route_id
}

function selectRoute(route) {
  selectedRouteId.value = route.route_id
  emit('route-select', route)
}

// ---- Display helpers ----
function routeLabel(route) {
  return route.route_short_name?.trim() || route.route_long_name?.trim() || route.route_id
}

function routeColor(route) {
  return route.route_color ? `#${route.route_color}` : 'var(--md-sys-color-outline, #74777f)'
}
</script>

<template>
  <nav
    :class="['schedule-sidebar', { 'schedule-sidebar--collapsed': collapsed }]"
    :aria-label="t('routes.sidebar_label')"
  >
    <!-- Collapse toggle -->
    <div class="schedule-sidebar__collapse">
      <button
        class="sidebar-collapse-btn"
        :title="collapsed ? t('sidebar.expand') : t('sidebar.collapse')"
        :aria-label="collapsed ? t('sidebar.expand') : t('sidebar.collapse')"
        @click="toggleCollapse"
      >
        <md-icon>{{ collapsed ? 'chevron_right' : 'chevron_left' }}</md-icon>
      </button>
    </div>

    <!-- Route list -->
    <div class="schedule-sidebar__list">
      <div
        v-for="route in orderedRoutes"
        :key="route.route_id"
        :class="[
          'route-item',
          { 'route-item--active': isSelected(route) },
        ]"
        :title="collapsed ? routeLabel(route) : undefined"
        role="button"
        tabindex="0"
        @click="selectRoute(route)"
        @keydown.enter="selectRoute(route)"
        @keydown.space.prevent="selectRoute(route)"
      >
        <!-- Colored bar -->
        <span
          class="route-item__bar"
          :style="{ backgroundColor: routeColor(route) }"
        />

        <!-- Collapsed: short name or first letter of long name -->
        <span
          v-if="collapsed"
          class="route-item__short route-item__short--always"
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

      <p v-if="orderedRoutes.length === 0" class="schedule-sidebar__empty">
        <span v-if="!collapsed">{{ t('routes.no_routes') }}</span>
      </p>
    </div>
  </nav>
</template>

<style scoped>
.schedule-sidebar {
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

.schedule-sidebar--collapsed {
  width: 56px;
}

/* Collapse toggle */
.schedule-sidebar__collapse {
  display: flex;
  justify-content: flex-end;
  padding: var(--size-1, 0.25rem) var(--size-2, 0.5rem) var(--size-2, 0.5rem);
  flex-shrink: 0;
}

.schedule-sidebar--collapsed .schedule-sidebar__collapse {
  justify-content: center;
}

/* Route list */
.schedule-sidebar__list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 4px;
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

/* Colored bar */
.route-item__bar {
  display: block;
  flex-shrink: 0;
  width: 5px;
  height: 100%;
  border-radius: 3px 0 0 3px;
  margin-right: var(--size-2, 0.5rem);
  align-self: stretch;
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

/* Collapsed state */
.schedule-sidebar--collapsed .route-item {
  justify-content: center;
  padding: 0;
}

.schedule-sidebar--collapsed .route-item__bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  height: 100%;
  margin-right: 0;
  border-radius: 2px 0 0 2px;
}

.schedule-sidebar--collapsed .route-item__short {
  flex: 0 1 auto;
  text-align: center;
  max-width: 100%;
  padding: 0;
}

.schedule-sidebar--collapsed .route-item__long {
  opacity: 0;
  width: 0;
  padding: 0;
  pointer-events: none;
}

/* Empty message */
.schedule-sidebar__empty {
  padding: var(--size-4, 1rem) var(--size-3, 0.75rem);
  font-size: var(--font-size-0, 0.8rem);
  color: var(--md-sys-color-outline, #74777f);
  text-align: center;
  margin: 0;
}
</style>
