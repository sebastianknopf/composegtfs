<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import '@material/web/icon/icon.js'

const { t } = useI18n()
const router = useRouter()
const { has } = usePermissions()

// Destructure as local ref so Vue auto-unwraps it in the template
const activeVersion = versionsStore.activeVersion

const canManage = has('versions:read')

const open = ref(false)
const triggerRef  = ref(null)
const dropdownRef = ref(null)
const dropdownStyle = ref({})

const sortedVersions = computed(() =>
  [...versionsStore.state.versions].sort((a, b) => a.name.localeCompare(b.name))
)

function openDropdown() {
  const rect = triggerRef.value.getBoundingClientRect()
  dropdownStyle.value = {
    top:      `${rect.bottom + 4}px`,
    left:     `${rect.left}px`,
    minWidth: `${Math.max(rect.width, 220)}px`,
  }
  open.value = true
}

function closeDropdown() {
  open.value = false
}

function toggleDropdown() {
  if (open.value) closeDropdown()
  else openDropdown()
}

function selectVersion(id) {
  versionsStore.setActive(id)
  closeDropdown()
}

function navigateManage() {
  closeDropdown()
  router.push({ name: 'versions' })
}

function onDocumentMousedown(e) {
  if (!open.value) return
  // Close only when the click is outside both the trigger and the teleported dropdown
  if (
    !triggerRef.value?.contains(e.target) &&
    !dropdownRef.value?.contains(e.target)
  ) {
    closeDropdown()
  }
}

function onKeydown(e) {
  if (e.key === 'Escape' && open.value) closeDropdown()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocumentMousedown)
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocumentMousedown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="triggerRef" class="version-picker">
    <button
      class="version-picker__trigger"
      :aria-expanded="open"
      :aria-haspopup="true"
      :aria-label="t('versions.select_label')"
      @click="toggleDropdown"
    >
      <md-icon class="version-picker__icon">layers</md-icon>
      <span class="version-picker__name">
        {{ activeVersion?.name ?? (versionsStore.state.loading ? '…' : '—') }}
      </span>
      <md-icon class="version-picker__chevron" :class="{ 'version-picker__chevron--open': open }">
        expand_more
      </md-icon>
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="dropdownRef"
        class="version-picker__dropdown"
        :style="dropdownStyle"
        role="listbox"
        :aria-label="t('versions.title')"
      >
        <!-- Version list -->
        <div class="version-picker__list">
          <button
            v-for="v in sortedVersions"
            :key="v.id"
            class="version-picker__item"
            :class="{ 'version-picker__item--active': v.id === versionsStore.state.activeVersionId }"
            role="option"
            :aria-selected="v.id === versionsStore.state.activeVersionId"
            @click="selectVersion(v.id)"
          >
            <md-icon v-if="v.id === versionsStore.state.activeVersionId" class="version-picker__item-check">
              check
            </md-icon>
            <span v-else class="version-picker__item-check-placeholder" />
            <span class="version-picker__item-name">{{ v.name }}</span>
          </button>

          <div v-if="sortedVersions.length === 0" class="version-picker__empty">
            {{ t('versions.no_versions') }}
          </div>
        </div>

        <!-- Manage link -->
        <div v-if="canManage" class="version-picker__footer">
          <button class="version-picker__manage" @click="navigateManage">
            <md-icon class="version-picker__manage-icon">settings</md-icon>
            {{ t('versions.manage') }}
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.version-picker {
  position: relative;
  flex-shrink: 0;
}

/* Trigger button */
.version-picker__trigger {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  color: var(--app-topbar-color, #dde3f5);
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  padding: 0.3rem 0.5rem 0.3rem 0.4rem;
  max-width: 200px;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.version-picker__trigger:hover,
.version-picker__trigger[aria-expanded="true"] {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.25);
}

.version-picker__icon {
  font-size: 16px;
  --md-icon-size: 16px;
  opacity: 0.75;
  flex-shrink: 0;
}

.version-picker__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 140px;
}

.version-picker__chevron {
  font-size: 18px;
  --md-icon-size: 18px;
  opacity: 0.75;
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.version-picker__chevron--open {
  transform: rotate(180deg);
}

/* Dropdown */
.version-picker__dropdown {
  position: fixed;
  z-index: 200;
  background: #fff;
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.version-picker__list {
  overflow-y: auto;
  max-height: 280px;
}

.version-picker__item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  padding: 0.55rem 0.75rem;
  background: none;
  border: none;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-on-surface, #222);
  text-align: left;
  transition: background 0.1s ease;
}

.version-picker__item:hover {
  background: var(--md-sys-color-surface-container-low, #f8f8f8);
}

.version-picker__item--active {
  color: var(--md-sys-color-primary, #1f69e0);
  font-weight: 500;
}

.version-picker__item-check {
  font-size: 16px;
  --md-icon-size: 16px;
  flex-shrink: 0;
  color: var(--md-sys-color-primary, #1f69e0);
}

.version-picker__item-check-placeholder {
  display: inline-block;
  width: 16px;
  flex-shrink: 0;
}

.version-picker__item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-picker__empty {
  padding: 0.75rem;
  font-size: var(--font-size-0, 0.8rem);
  color: var(--md-sys-color-outline, #74777f);
  font-style: italic;
  text-align: center;
}

/* Footer / manage link */
.version-picker__footer {
  border-top: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  padding: 0.25rem 0;
}

.version-picker__manage {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  padding: 0.55rem 0.75rem;
  background: none;
  border: none;
  cursor: pointer;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  text-align: left;
  transition: background 0.1s ease;
}

.version-picker__manage:hover {
  background: var(--md-sys-color-surface-container-low, #f8f8f8);
  color: var(--md-sys-color-on-surface, #222);
}

.version-picker__manage-icon {
  font-size: 16px;
  --md-icon-size: 16px;
  flex-shrink: 0;
}
</style>
