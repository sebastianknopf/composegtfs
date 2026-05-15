<script setup>
/**
 * VersionCopyModal — copy a version with selectable data sections.
 *
 * Props:
 *   modelValue — boolean    — open state (v-model)
 *   version    — object|null — source version to copy from
 *
 * Emits:
 *   update:modelValue
 *   done(version)  — emitted after successful copy/merge; version is the
 *                    newly created or the updated target version object
 */
import { ref, reactive, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/select/outlined-select.js'
import '@material/web/select/select-option.js'
import '@material/web/checkbox/checkbox.js'
import '@material/web/icon/icon.js'
import '@material/web/progress/circular-progress.js'
import { api } from '@/api/client.js'

const { t } = useI18n()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  version:    { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'done'])

const dialogRef = ref(null)

// ---- Target version selection ----
// ''          → nothing selected yet (placeholder shown)
// 'new'       → create a brand-new version (name field is shown)
// <uuid>      → merge into the existing version with that id
const targetMode        = ref('')
const availableVersions = ref([])   // sorted versions excluding source

// ---- Form state ----
const name      = ref('')
const nameError = ref(null)

const checks = reactive({
  agencies:    false,
  day_types:   false,
  stops:       false,
  shapes:      false,
  routes:      false,
  route_bands: false,
  schedule:    false,
})

// ---- Dependency logic ----
const forced = computed(() => {
  const f = new Set()
  if (checks.routes || checks.route_bands || checks.schedule) {
    f.add('agencies')
  }
  if (checks.route_bands || checks.schedule) {
    f.add('routes')
    f.add('stops')
  }
  if (checks.schedule) {
    f.add('route_bands')
    f.add('day_types')
    f.add('shapes')
  }
  return f
})

function isChecked(key) {
  return checks[key] || forced.value.has(key)
}

function isDisabled(key) {
  return isCopying.value || forced.value.has(key)
}

function toggle(key, val) {
  checks[key] = val
}

// ---- Copy / SSE state ----
const isCopying  = ref(false)
const copyError  = ref(null)

// ---- Schema ----
const schema = z.object({
  name: z
    .string()
    .min(1, t('version_copy.validation_name_required'))
    .max(128, t('version_copy.validation_name_too_long')),
})

// ---- Dialog lifecycle ----
watch(() => props.modelValue, async (val) => {
  const el = dialogRef.value
  if (val) {
    name.value            = ''
    nameError.value       = null
    copyError.value       = null
    isCopying.value       = false
    targetMode.value      = ''  // reset to placeholder
    availableVersions.value = []
    Object.keys(checks).forEach(k => { checks[k] = false })

    // Load available target versions (all versions except the source)
    try {
      const all = await api.versions.list()
      availableVersions.value = all
        .filter(v => v.id !== props.version?.id)
        .sort((a, b) => {
          const ao = a.sort_order ?? Infinity
          const bo = b.sort_order ?? Infinity
          if (ao !== bo) return ao - bo
          return a.name.localeCompare(b.name)
        })
    } catch {
      // non-critical — user can still create a new version
    }

    requestAnimationFrame(() => el?.show?.())
  } else {
    el?.close?.()
  }
})

function handleClose() {
  if (isCopying.value) return
  emit('update:modelValue', false)
}

// ---- Validation ----
function validate() {
  nameError.value = null
  if (targetMode.value === '') {
    copyError.value = t('version_copy.error_no_target')
    return false
  }
  if (targetMode.value !== 'new') return true   // no name needed for merge
  const result = schema.safeParse({ name: name.value.trim() })
  if (!result.success) {
    const issues = result.error.flatten().fieldErrors
    nameError.value = issues.name?.[0] ?? null
    return false
  }
  return true
}

// ---- Submit ----
async function handleSubmit() {
  if (!validate()) return

  copyError.value = null
  isCopying.value = true

  const token = localStorage.getItem('access_token')
  const isNewVersion = targetMode.value === 'new'
  const payload = {
    ...(isNewVersion
      ? { name: name.value.trim() }
      : { target_version_id: targetMode.value }),
    include: {
      agencies:    isChecked('agencies'),
      day_types:   isChecked('day_types'),
      stops:       isChecked('stops'),
      shapes:      isChecked('shapes'),
      routes:      isChecked('routes'),
      route_bands: isChecked('route_bands'),
      schedule:    isChecked('schedule'),
    },
  }

  try {
    const response = await fetch(`/api/versions/${props.version.id}/copy`, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    })

    const newToken = response.headers.get('X-New-Token')
    if (newToken) localStorage.setItem('access_token', newToken)

    if (!response.ok) {
      isCopying.value = false
      copyError.value = t('error.server')
      return
    }

    const reader  = response.body.getReader()
    const decoder = new TextDecoder()
    let   buffer  = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        try {
          const event = JSON.parse(trimmed.slice('data:'.length).trim())
          if (event.status === 'done') {
            isCopying.value = false
            emit('update:modelValue', false)
            emit('done', event.version, isNewVersion)
            return
          }
          if (event.status === 'error') {
            isCopying.value = false
            copyError.value = event.message === 'name_conflict'
              ? t('version_copy.error_conflict')
              : t('error.server')
            return
          }
        } catch {
          // ignore malformed SSE lines
        }
      }
    }

    isCopying.value = false
  } catch {
    isCopying.value = false
    copyError.value = t('error.server')
  }
}
</script>

<template>
  <md-dialog ref="dialogRef" class="version-copy-dialog" @closed="handleClose">

    <div slot="headline" class="version-copy-dialog__headline">
      <md-icon class="version-copy-dialog__headline-icon">content_copy</md-icon>
      <span class="version-copy-dialog__title">
        {{ t('version_copy.title', { name: version?.name ?? '' }) }}
      </span>
    </div>

    <form slot="content" class="version-copy-dialog__form" method="dialog">

      <!-- Target version selection -->
      <div class="version-copy-dialog__section">
        <p class="version-copy-dialog__section-label">{{ t('version_copy.section_target') }}</p>
        <md-outlined-select
          class="version-copy-dialog__field"
          :label="t('version_copy.target_label')"
          :disabled="isCopying"
          @change="targetMode = $event.target.value; copyError = null"
        >
          <md-select-option value="" :selected="targetMode === ''" disabled>
            <div slot="headline">{{ t('version_copy.target_placeholder') }}</div>
          </md-select-option>
          <md-select-option value="new" :selected="targetMode === 'new'">
            <div slot="headline">{{ t('version_copy.target_new_option') }}</div>
          </md-select-option>
          <md-select-option
            v-for="v in availableVersions"
            :key="v.id"
            :value="v.id"
            :selected="targetMode === v.id"
          >
            <div slot="headline">{{ v.name }}</div>
          </md-select-option>
        </md-outlined-select>
      </div>

      <!-- Name (only when creating a new version) -->
      <div v-if="targetMode === 'new'" class="version-copy-dialog__section">
        <p class="version-copy-dialog__section-label">{{ t('version_copy.section_name') }}</p>
        <md-outlined-text-field
          class="version-copy-dialog__field"
          :label="t('version_copy.name_label')"
          :placeholder="t('version_copy.name_placeholder')"
          :value="name"
          :error="!!nameError"
          :error-text="nameError ?? ''"
          :disabled="isCopying"
          required
          autofocus
          @input="name = $event.target.value; nameError = null"
          @keydown.enter.prevent="handleSubmit"
        />
      </div>

      <!-- Stammdaten -->
      <div class="version-copy-dialog__section">
        <p class="version-copy-dialog__section-label">{{ t('version_copy.section_masterdata') }}</p>
        <div class="version-copy-dialog__checks">
          <label class="version-copy-dialog__check-item">
            <md-checkbox
              :checked="isChecked('agencies')"
              :disabled="isDisabled('agencies')"
              @change="toggle('agencies', $event.target.checked)"
            />
            <span>{{ t('version_copy.item_agencies') }}</span>
          </label>
          <label class="version-copy-dialog__check-item">
            <md-checkbox
              :checked="isChecked('day_types')"
              :disabled="isDisabled('day_types')"
              @change="toggle('day_types', $event.target.checked)"
            />
            <span>{{ t('version_copy.item_day_types') }}</span>
          </label>
        </div>
      </div>

      <!-- Netz -->
      <div class="version-copy-dialog__section">
        <p class="version-copy-dialog__section-label">{{ t('version_copy.section_network') }}</p>
        <div class="version-copy-dialog__checks">
          <label class="version-copy-dialog__check-item">
            <md-checkbox
              :checked="isChecked('stops')"
              :disabled="isDisabled('stops')"
              @change="toggle('stops', $event.target.checked)"
            />
            <span>{{ t('version_copy.item_stops') }}</span>
          </label>
          <label class="version-copy-dialog__check-item">
            <md-checkbox
              :checked="isChecked('routes')"
              :disabled="isDisabled('routes')"
              @change="toggle('routes', $event.target.checked)"
            />
            <span>{{ t('version_copy.item_routes') }}</span>
          </label>
          <label class="version-copy-dialog__check-item">
            <md-checkbox
              :checked="isChecked('shapes')"
              :disabled="isDisabled('shapes')"
              @change="toggle('shapes', $event.target.checked)"
            />
            <span>{{ t('version_copy.item_shapes') }}</span>
          </label>
        </div>
      </div>

      <!-- Fahrplan -->
      <div class="version-copy-dialog__section">
        <p class="version-copy-dialog__section-label">{{ t('version_copy.section_schedule') }}</p>
        <div class="version-copy-dialog__checks">
          <label class="version-copy-dialog__check-item">
            <md-checkbox
              :checked="isChecked('route_bands')"
              :disabled="isDisabled('route_bands')"
              @change="toggle('route_bands', $event.target.checked)"
            />
            <span>{{ t('version_copy.item_route_bands') }}</span>
          </label>
          <label class="version-copy-dialog__check-item">
            <md-checkbox
              :checked="isChecked('schedule')"
              :disabled="isDisabled('schedule')"
              @change="toggle('schedule', $event.target.checked)"
            />
            <span>{{ t('version_copy.item_schedule') }}</span>
          </label>
        </div>
      </div>

    </form>

    <div slot="actions">
      <p v-if="copyError" class="version-copy-dialog__error">{{ copyError }}</p>
      <md-text-button :disabled="isCopying" @click="handleClose">
        {{ t('common.cancel') }}
      </md-text-button>
      <md-filled-button :disabled="isCopying" @click="handleSubmit">
        <md-circular-progress
          v-if="isCopying"
          slot="icon"
          class="version-copy-dialog__progress"
          indeterminate
        />
        <md-icon v-else slot="icon">content_copy</md-icon>
        {{ isCopying ? t('version_copy.copying') : t('version_copy.copy_button') }}
      </md-filled-button>
    </div>

  </md-dialog>
</template>

<style scoped>
.version-copy-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.version-copy-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.version-copy-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.version-copy-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.version-copy-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 0.5rem;
}

.version-copy-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.version-copy-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.version-copy-dialog__field {
  width: 100%;
}

.version-copy-dialog__checks {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 2rem;
}

.version-copy-dialog__check-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.9375rem;
  color: var(--md-sys-color-on-surface, #222);
  user-select: none;
}

.version-copy-dialog__error {
  margin: 0 auto 0 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}

.version-copy-dialog__progress {
  --md-circular-progress-size: 18px;
  --md-circular-progress-active-indicator-color: currentColor;
}
</style>
