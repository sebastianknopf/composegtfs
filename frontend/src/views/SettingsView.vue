<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { settingsStore } from '@/stores/settings.js'
import { usePermissions } from '@/composables/usePermissions.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'
import ColorInput from '@/components/ColorInput.vue'

const { t } = useI18n()
const { has } = usePermissions()
const canSave = has('settings:write')

const appTitle = ref('')
const appPrimaryColor = ref('')
const appSecondaryColor = ref('')
const mapTileUrl = ref('')
const saving = ref(false)
const statusKey = ref(null) // 'settings.saved' | 'settings.error' | null

// ---------------------------------------------------------------------------
// Form state
// ---------------------------------------------------------------------------

function emptyErrors() {
  return {
    app_primary_color:      null,
    app_secondary_color:    null,
    map_tile_url:           null
  }
}

const fieldErrors = ref(emptyErrors())

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function isValidHttpUrl(value) {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

function validate() {
  fieldErrors.value = emptyErrors()
  let ok = true

  const url = mapTileUrl.value.trim()
  if (!isValidHttpUrl(url)) {
    fieldErrors.value.map_tile_url = t('settings.validation_url_invalid')
    ok = false
  }
  
  const HEX6_RE = /^[0-9A-Fa-f]{6}$/
  const primaryColor = appPrimaryColor.value.trim()
  if (primaryColor && !HEX6_RE.test(primaryColor)) {
    fieldErrors.value.app_primary_color = t('settings.validation_app_color_error')
    ok = false
  }
  const secondaryColor = appSecondaryColor.value.trim()
  if (secondaryColor && !HEX6_RE.test(secondaryColor)) {
    fieldErrors.value.app_secondary_color = t('settings.validation_app_color_error')
    ok = false
  }

  return ok
}

// ---------------------------------------------------------------------------
// Populate form
// ---------------------------------------------------------------------------

onMounted(async () => {
  try {
    const data = await api.settings.get()
    appTitle.value = data.app_title
    appPrimaryColor.value = data.app_primary_color
    appSecondaryColor.value = data.app_secondary_color
    mapTileUrl.value = data.map_tile_url
  } catch {
    appTitle.value = settingsStore.state.appTitle
    appPrimaryColor.value = settingsStore.state.appPrimaryColor
    appSecondaryColor.value = settingsStore.state.appSecondaryColor
    mapTileUrl.value = settingsStore.state.mapTileUrl
  }
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function save() {
  if (!validate()) return  
  saving.value = true
  statusKey.value = null
  try {
    const data = await api.settings.save({
      app_title: appTitle.value,
      app_primary_color: appPrimaryColor.value,
      app_secondary_color: appSecondaryColor.value,
      map_tile_url: mapTileUrl.value,
    })
    // Apply to global store so all reactive consumers update immediately
    settingsStore.apply(data)
    appTitle.value = data.app_title
    appPrimaryColor.value = data.app_primary_color
    appSecondaryColor.value = data.app_secondary_color
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
          :error="!!fieldErrors.map_tile_url"
          :error-text="fieldErrors.map_tile_url ?? ''"
          :disabled="!canSave"
          @input="mapTileUrl = $event.target.value; clearFieldError('map_tile_url')"
        />
      </div>
    </section>

    <!-- Section: Fahrplan -->
    <section class="settings-section">
      <h2 class="settings-section__title">
        <md-icon class="settings-section__icon">directions_bus</md-icon>
        {{ t('settings.section_schedule') }}
      </h2>
      <div class="settings-section__fields">
        <p class="settings-section__description">{{ t('settings.graphhopper_local_hint') }}</p>
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
          :disabled="!canSave"
          @input="appTitle = $event.target.value"
        />
        <ColorInput
          :model-value="appPrimaryColor"
          :label="t('settings.app_primary_color')"
          :error="fieldErrors.app_primary_color"
          :disabled="!canSave"
          @update:model-value="appPrimaryColor = $event; clearFieldError('app_primary_color')"
        />
        <ColorInput
          :model-value="appSecondaryColor"
          :label="t('settings.app_secondary_color')"
          :error="fieldErrors.app_secondary_color"
          :disabled="!canSave"
          @update:model-value="appSecondaryColor = $event; clearFieldError('app_secondary_color')"
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
