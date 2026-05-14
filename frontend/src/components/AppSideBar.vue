<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import SidebarItem from '@/components/SidebarItem.vue'
import '@material/web/icon/icon.js'

const { t } = useI18n()

/**
 * AppSideBar — generic, self-contained sidebar.
 *
 * Props:
 *   items      — Array<{ id, labelKey, icon, position? }>
 *                Items with position === 'bottom' are pinned at the bottom.
 *   activeItem — id of the currently active item
 *   sectionId  — unique identifier for this sidebar context, used as the
 *                localStorage key so the collapsed state is remembered
 *                separately for each app section.
 *
 * Emits:
 *   item-select — emitted with the item id when a navigation item is clicked
 */
const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  activeItem: {
    type: String,
    default: null,
  },
  sectionId: {
    type: String,
    default: 'default',
  },
})

const emit = defineEmits(['item-select'])

// ---- Collapsed state — managed internally, persisted per sectionId ----
function _storageKey(id) {
  return `sidebar-collapsed:${id}`
}

function _loadCollapsed(id) {
  return localStorage.getItem(_storageKey(id)) === 'true'
}

const collapsed = ref(_loadCollapsed(props.sectionId))

// Reload collapsed state when the sectionId changes (user switches section)
watch(() => props.sectionId, (id) => {
  collapsed.value = _loadCollapsed(id)
})

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(_storageKey(props.sectionId), String(collapsed.value))
}

// ---- Item groups ----
const topItems    = computed(() => props.items.filter(i => i.position !== 'bottom'))
const bottomItems = computed(() => props.items.filter(i => i.position === 'bottom'))
</script>

<template>
  <nav
    :class="['app-sidebar', { 'app-sidebar--collapsed': collapsed }]"
    role="navigation"
    :aria-label="t('sidebar.label')"
  >
    <!-- Collapse toggle -->
    <div class="app-sidebar__collapse">
      <button
        class="sidebar-collapse-btn"
        :title="collapsed ? t('sidebar.expand') : t('sidebar.collapse')"
        :aria-label="collapsed ? t('sidebar.expand') : t('sidebar.collapse')"
        @click="toggleCollapse"
      >
        <md-icon>{{ collapsed ? 'chevron_right' : 'chevron_left' }}</md-icon>
      </button>
    </div>

    <!-- Top items -->
    <div class="app-sidebar__group app-sidebar__group--top">
      <SidebarItem
        v-for="item in topItems"
        :key="item.id"
        :icon="item.icon"
        :label="t(item.labelKey)"
        :active="item.id === activeItem"
        :collapsed="collapsed"
        @click="emit('item-select', item.id)"
      />
    </div>

    <!-- Bottom items -->
    <div v-if="bottomItems.length" class="app-sidebar__group app-sidebar__group--bottom">
      <SidebarItem
        v-for="item in bottomItems"
        :key="item.id"
        :icon="item.icon"
        :label="t(item.labelKey)"
        :active="item.id === activeItem"
        :collapsed="collapsed"
        @click="emit('item-select', item.id)"
      />
    </div>
  </nav>
</template>

