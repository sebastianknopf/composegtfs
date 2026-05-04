<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { settingsStore } from '@/stores/settings.js'
import { usePermissions } from '@/composables/usePermissions.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const { t } = useI18n()
const { has } = usePermissions()
const canSave = has('settings:write')

const appTitle = ref('')
const mapTileUrl = ref('')
const saving = ref(false)
const statusKey = ref(null) // 'settings.saved' | 'settings.error' | null

onMounted(async () => {
  try {
    const data = await api.settings.get()
    appTitle.value = data.app_title
    mapTileUrl.value = data.map_tile_url
  } catch {
    appTitle.value = settingsStore.state.appTitle
    mapTileUrl.value = settingsStore.state.mapTileUrl
  }
})

async function save() {
  saving.value = true
  statusKey.value = null
  try {
    const data = await api.settings.save({
      app_title: appTitle.value,
      map_tile_url: mapTileUrl.value,
    })
    // Apply to global store so all reactive consumers update immediately
    settingsStore.apply(data)
    appTitle.value = data.app_title
    mapTileUrl.value = data.map_tile_url
    statusKey.value = 'settings.saved'
  } catch {
    statusKey.value = 'settings.error'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="settings-view">

    <header class="settings-view__header">
      <md-icon class="settings-view__header-icon">settings</md-icon>
      <h1 class="settings-view__title">{{ t('views.settings') }}</h1>
    </header>

    <!-- Section: Network -->
    <section class="settings-section">
      <h2 class="settings-section__title">
        <md-icon class="settings-section__icon">map</md-icon>
        {{ t('settings.section_network') }}
      </h2>
      <div class="settings-section__fields">
        <md-outlined-text-field
          class="settings-field"
          :label="t('settings.map_tile_url')"
          :supporting-text="t('settings.map_tile_url_hint')"
          :value="mapTileUrl"
          @input="mapTileUrl = $event.target.value"
        />
      </div>
    </section>

    <!-- Section: System -->
    <section class="settings-section">
      <h2 class="settings-section__title">
        <md-icon class="settings-section__icon">computer</md-icon>
        {{ t('settings.section_system') }}
      </h2>
      <div class="settings-section__fields">
        <md-outlined-text-field
          class="settings-field"
          :label="t('settings.app_title')"
          :supporting-text="t('settings.app_title_hint')"
          :value="appTitle"
          @input="appTitle = $event.target.value"
        />
      </div>
    </section>

    <!-- Footer: Save -->
    <div class="settings-footer">
      <span v-if="statusKey" :class="['settings-status', { 'settings-status--error': statusKey === 'settings.error' }]">
        <md-icon class="settings-status__icon">{{ statusKey === 'settings.error' ? 'error' : 'check_circle' }}</md-icon>
        {{ t(statusKey) }}
      </span>
      <md-filled-button v-if="canSave" :disabled="saving" @click="save">
        <md-icon slot="icon">save</md-icon>
        {{ t('settings.save') }}
      </md-filled-button>
    </div>

  </div>
</template>

<style scoped>
.settings-view {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  height: 100%;
}

.settings-view__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-bottom: 1rem;

}

.settings-view__header-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
}

.settings-view__title {
  font-size: var(--font-size-3, 1.25rem);
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
  margin: 0;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.settings-section__title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-1, 0.875rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--md-sys-color-primary, #1f69e0);
  margin: 0;
}

.settings-section__icon {
  font-size: 1rem;
  --md-icon-size: 1rem;
}

.settings-section__fields {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-field {
  width: 100%;
}

.settings-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: auto;
  padding-top: 1rem;
}

.settings-status {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-primary, #1f69e0);
}

.settings-status__icon {
  font-size: 1rem;
  --md-icon-size: 1rem;
}

.settings-status--error {
  color: var(--md-sys-color-error, #b00020);
}
</style>
