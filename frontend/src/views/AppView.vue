<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { authStore } from '@/stores/auth.js'
import { permissionsStore } from '@/stores/permissions.js'
import { forbiddenState } from '@/stores/forbidden.js'
import { settingsStore } from '@/stores/settings.js'
import { versionsStore } from '@/stores/versions.js'
import AppTopBar from '@/components/AppTopBar.vue'
import AppSideBar from '@/components/AppSideBar.vue'
import AppToast from '@/components/AppToast.vue'
import ForbiddenView from '@/views/ForbiddenView.vue'
import '@material/web/icon/icon.js'

const router = useRouter()
const route = useRoute()

onMounted(() => {
  settingsStore.load()
  // Always force-reload so a different user logging in gets fresh permissions
  permissionsStore.load(true)
  versionsStore.load()
})

/**
 * Application sections displayed in the TopBar.
 * Each section owns its sidebar views (position 'top' or 'bottom').
 * 'icon' is a Material Symbols ligature name.
 * Sections with no views hide the sidebar automatically.
 */
const sections = [
  {
    id: 'masterdata',
    labelKey: 'sections.masterdata',
    icon: 'storage',
    defaultView: 'agency',
    views: [
      { id: 'agency',    labelKey: 'views.agency',    icon: 'business',      position: 'top' },
      { id: 'calendar',  labelKey: 'views.calendar',  icon: 'calendar_month', position: 'top' },
      { id: 'accounts', labelKey: 'views.accounts', icon: 'group',     position: 'bottom', permission: 'accounts:read' },
      { id: 'settings', labelKey: 'views.settings', icon: 'settings',  position: 'bottom', permission: 'settings:read' },
    ],
  },
  {
    id: 'network',
    labelKey: 'sections.network',
    icon: 'map',
    defaultView: 'network',
    permission: 'network:read',
    views: [],
  },
  {
    id: 'schedule',
    labelKey: 'sections.schedule',
    icon: 'calendar_month',
    defaultView: 'schedule',
    permission: 'schedule:read',
    views: [],
  },
]

/**
 * The exchange section is rendered separately in the TopBar (right-aligned, blue button).
 */
const exchangeSection = {
  id: 'exchange',
  labelKey: 'sections.exchange',
  defaultView: 'gtfs-export',
  views: [
    { id: 'gtfs-export', labelKey: 'views.gtfs_export', icon: 'file_download', position: 'top', permission: 'gtfs:export' },
  ],
}

const visibleExchangeSection = computed(() =>
  exchangeSection.views.some(v => canSeeEntry(v)) ? exchangeSection : null
)

/** Returns true if the current user may see a view or section entry. */
function canSeeEntry(entry) {
  if (!entry.permission) return true
  return permissionsStore.state.isSuperuser || permissionsStore.has(entry.permission)
}

/** Sections visible to the current user (at least one visible view, or no views defined). */
const visibleSections = computed(() =>
  sections.filter(s => {
    if (s.permission && !canSeeEntry(s)) return false
    if (s.views.length === 0) return true
    return s.views.some(v => canSeeEntry(v))
  })
)

// Derive the active section from the current route meta.
// Routes without a section meta (e.g. /versions) return null so no section
// tab stays highlighted in the TopBar.
const activeSection = computed(() => route.meta?.section ?? null)

// Derive the active view from the current route name
const activeView = computed(() => route.name ?? null)

// Whether the current route fills the whole content area (no sidebar)
const isFullscreen = computed(() => !!route.meta?.fullscreen)

// The sidebar items for the active section — filtered by permission
const sidebarItems = computed(() => {
  const allSections = [...sections, exchangeSection]
  const section = allSections.find(s => s.id === activeSection.value)
  return (section?.views ?? []).filter(v => canSeeEntry(v))
})

// Per-section collapsed state is managed inside AppSideBar itself.
// AppView only needs to know the active section to pass as sectionId.

function onSectionChange(id) {
  const allSections = [...sections, exchangeSection]
  const section = allSections.find(s => s.id === id)
  const target = section?.defaultView ?? section?.views[0]?.id
  if (target) router.push({ name: target })
}

function onViewSelect(id) {
  router.push({ name: id })
}

function onLogout() {
  authStore.logout()
  permissionsStore.reset()
  versionsStore.reset()
  router.push('/login')
}
</script>

<template>
  <div class="app-layout">
    <AppTopBar
      :title="settingsStore.state.appTitle"
      :app-version="settingsStore.state.appVersion"
      :sections="visibleSections"
      :active-section="activeSection"
      :exchange-section="visibleExchangeSection"
      @section-change="onSectionChange"
      @logout="onLogout"
    />
    <div class="app-body">
      <AppSideBar
        v-if="!isFullscreen"
        :items="sidebarItems"
        :active-item="activeView"
        :section-id="activeSection"
        @item-select="onViewSelect"
      />
      <main :class="['app-main', { 'app-main--fullscreen': isFullscreen }]">
        <ForbiddenView v-if="forbiddenState" @back="router.back()" />
        <RouterView v-show="!forbiddenState" v-slot="{ Component }">
          <KeepAlive>
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
      </main>
    </div>
  </div>
  <AppToast />
</template>
