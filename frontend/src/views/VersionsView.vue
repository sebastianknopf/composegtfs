<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import DataTable from '@/components/DataTable.vue'
import VersionEditModal from '@/components/VersionEditModal.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-button.js'

const { t } = useI18n()
const { has } = usePermissions()

const canWrite  = has('versions:write')
const canDelete = has('versions:delete')

// ---- Table ----
const versions = ref([])
const loading  = ref(false)

const columns = [
  { key: 'name',       label: () => t('versions.column_name'), sortable: true },
  { key: 'created_at', label: () => t('versions.column_created_at'), sortable: true, width: '200px' },
]

async function loadVersions() {
  loading.value = true
  try {
    versions.value = await api.versions.list()
    versionsStore.state.versions = versions.value
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(loadVersions)

// ---- Create / Edit modal ----
const modalOpen   = ref(false)
const editVersion = ref(null)
const saveError   = ref(null)

function openCreate() {
  editVersion.value = null
  saveError.value   = null
  modalOpen.value   = true
}

function openEdit(version) {
  editVersion.value = version
  saveError.value   = null
  modalOpen.value   = true
}

async function handleSave(data) {
  saveError.value = null
  try {
    if (editVersion.value) {
      const updated = await api.versions.rename(editVersion.value.id, data)
      const idx = versions.value.findIndex(v => v.id === updated.id)
      if (idx !== -1) versions.value[idx] = updated
      const storeIdx = versionsStore.state.versions.findIndex(v => v.id === updated.id)
      if (storeIdx !== -1) versionsStore.state.versions[storeIdx] = updated
    } else {
      const created = await api.versions.create(data)
      versions.value.push(created)
      versionsStore.state.versions.push(created)
      if (!versionsStore.state.activeVersionId) {
        versionsStore.setActive(created.id)
      }
    }
    modalOpen.value = false
  } catch (err) {
    saveError.value = err.status === 409
      ? t('versions.error_conflict')
      : t('error.server')
  }
}

// ---- Confirm delete ----
const confirmOpen   = ref(false)
const pendingDelete = ref(null)

function requestDelete(version) {
  pendingDelete.value = version
  confirmOpen.value   = true
}

async function handleConfirmDelete() {
  if (!pendingDelete.value) return
  const target = pendingDelete.value
  pendingDelete.value = null
  try {
    await api.versions.delete(target.id)
    versions.value = versions.value.filter(v => v.id !== target.id)
    versionsStore.state.versions = versionsStore.state.versions.filter(v => v.id !== target.id)
    if (versionsStore.state.activeVersionId === target.id) {
      const sorted = [...versionsStore.state.versions].sort((a, b) => a.name.localeCompare(b.name))
      versionsStore.setActive(sorted[0]?.id ?? null)
    }
  } catch (err) {
    const msg = err.status === 409
      ? t('versions.error_last_version')
      : err.status === 404
        ? t('versions.error_not_found')
        : t('error.server')
    toast.show(msg, 'error')
    await loadVersions()
  }
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit',
  })
}
</script>

<template>
  <div class="versions-view">

    <header class="view-header">
      <md-icon class="view-header__icon">layers</md-icon>
      <h1 class="view-header__title">{{ t('versions.title') }}</h1>
      <div class="view-header__actions">
        <md-filled-button v-if="canWrite" @click="openCreate">
          <md-icon slot="icon">add</md-icon>
          {{ t('versions.add') }}
        </md-filled-button>
      </div>
    </header>

    <DataTable
      :columns="columns"
      :rows="versions"
      :loading="loading"
      :empty="t('versions.no_versions')"
      :pagination="{ pageSize: 25 }"
    >
      <template #cell-created_at="{ value }">
        {{ formatDate(value) }}
      </template>
      <template #actions="{ row }">
        <button
          v-if="canWrite"
          class="table-action-btn"
          :title="t('common.edit')"
          @click="openEdit(row)"
        >
          <md-icon>edit</md-icon>
        </button>
        <button
          v-if="canDelete && versions.length > 1"
          class="table-action-btn table-action-btn--danger"
          :title="t('common.delete')"
          @click="requestDelete(row)"
        >
          <md-icon>delete</md-icon>
        </button>
      </template>
    </DataTable>

  </div>

  <VersionEditModal
    v-model="modalOpen"
    :version="editVersion"
    :error="saveError"
    @save="handleSave"
  />

  <ConfirmDialog
    v-model="confirmOpen"
    :title="t('versions.delete_confirm_title')"
    :message="t('versions.delete_confirm_message', { name: pendingDelete?.name ?? '' })"
    :confirm-label="t('common.delete')"
    :cancel-label="t('common.cancel')"
    :danger="true"
    @confirm="handleConfirmDelete"
  />
</template>

<style scoped>
.versions-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  height: 100%;
  padding: var(--size-6, 1.5rem);
  overflow-y: auto;
  box-sizing: border-box;
}


</style>
