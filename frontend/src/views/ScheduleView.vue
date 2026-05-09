<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import { api } from '@/api/client.js'
import ScheduleSideBar from '@/components/ScheduleSideBar.vue'
import ScheduleTable from '@/components/ScheduleTable.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/outlined-button.js'
import '@material/web/button/filled-button.js'

const { t } = useI18n()
const { has } = usePermissions()

const canReadSchedule  = has('schedule:read')
const canWriteSchedule = has('schedule:write')
const canDeleteSchedule = has('schedule:delete')

const versionId = computed(() => versionsStore.state.activeVersionId)

// ---- Routes (via schedule endpoint, independent of routes:read) ----
const scheduleRoutes = ref([])
const routesLoading  = ref(false)

async function loadRoutes() {
  const vid = versionId.value
  if (!vid || !canReadSchedule.value) {
    scheduleRoutes.value = []
    return
  }
  routesLoading.value = true
  try {
    scheduleRoutes.value = await api.schedule.routes(vid)
  } catch {
    scheduleRoutes.value = []
  } finally {
    routesLoading.value = false
  }
}

watch(versionId, loadRoutes, { immediate: true })

// ---- Platforms (version-scoped, loaded once per version) ----
const platforms = ref([])

async function loadPlatforms() {
  const vid = versionId.value
  if (!vid || !canReadSchedule.value) {
    platforms.value = []
    return
  }
  try {
    platforms.value = await api.schedule.platforms(vid)
  } catch {
    platforms.value = []
  }
}

watch(versionId, loadPlatforms, { immediate: true })

// ---- Selection ----
const selectedRoute = ref(null)
const direction     = ref(0)   // 0 = Hinfahrt, 1 = Rückfahrt

function handleRouteSelect(route) {
  selectedRoute.value = route
  direction.value = 0           // reset direction on new route
}

function setDirection(dir) {
  direction.value = dir
}
</script>

<template>
  <div class="schedule-view">

    <!-- Routes sidebar (left) -->
    <ScheduleSideBar
      :routes="scheduleRoutes"
      section-id="schedule-routes"
      @route-select="handleRouteSelect"
    />

    <!-- Content area -->
    <div class="schedule-content">

      <header class="view-header">
        <md-icon class="view-header__icon">table_view</md-icon>
        <h1 class="view-header__title">{{ t('views.schedule') }}</h1>
        <div class="view-header__actions schedule-view__dir-toggle" v-if="selectedRoute">
          <template v-for="[dir, label] in [[0, t('schedule.direction_outbound')], [1, t('schedule.direction_inbound')]]" :key="dir">
            <md-filled-button v-if="direction === dir" class="dir-toggle-btn" @click="setDirection(dir)">{{ label }}</md-filled-button>
            <md-outlined-button v-else class="dir-toggle-btn" @click="setDirection(dir)">{{ label }}</md-outlined-button>
          </template>
        </div>
      </header>

      <!-- No version selected -->
      <div v-if="!versionId" class="schedule-content__placeholder">
        <md-icon>info</md-icon>
        <span>{{ t('schedule.no_version') }}</span>
      </div>

      <!-- No route selected -->
      <div v-else-if="!selectedRoute" class="schedule-content__placeholder">
        <md-icon>info</md-icon>
        <span>{{ t('schedule.no_route') }}</span>
      </div>

      <!-- Timetable -->
      <ScheduleTable
        v-else
        :version-id="versionId"
        :route-id="selectedRoute.route_id"
        :direction="direction"
        :platforms="platforms"
        :can-read="canReadSchedule"
        :can-write="canWriteSchedule"
        :can-delete="canDeleteSchedule"
      />

    </div>
  </div>
</template>

<style scoped>
.schedule-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
}

.schedule-content {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 1rem 1.25rem 0;
  overflow: hidden;
}

/* Direction toggle — filled = active, outlined = inactive */
.schedule-view__dir-toggle {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.dir-toggle-btn {
  min-width: 7.5rem;
}

/* Placeholder messages */
.schedule-content__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 3rem 1rem;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  font-size: var(--font-size-1, 0.875rem);
}
</style>

