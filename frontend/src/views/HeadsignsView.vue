<script setup>
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import DataTable from '@/components/DataTable.vue'
import HeadsignEditModal from '@/components/HeadsignEditModal.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-button.js'

const { t } = useI18n()
const { has } = usePermissions()

const canWrite  = has('headsigns:write')
const canDelete = has('headsigns:delete')

// ---- Table ----
const headsigns = ref([])
const loading   = ref(false)

const columns = [
  { key: 'number',      label: () => t('headsigns.column_number'),      sortable: true, width: '120px' },
  { key: 'name',        label: () => t('headsigns.column_name'),        sortable: true },
  { key: 'destination', label: () => t('headsigns.column_destination'), sortable: true },
]

async function loadHeadsigns() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) {
    headsigns.value = []
    return
  }
  loading.value = true
  try {
    headsigns.value = await api.headsigns.list(versionId)
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(loadHeadsigns)
watch(() => versionsStore.state.activeVersionId, loadHeadsigns)

// ---- Create / Edit modal ----
const modalOpen    = ref(false)
const editHeadsign = ref(null)
const saveError    = ref(null)

function openCreate() {
  editHeadsign.value = null
  saveError.value    = null
  modalOpen.value    = true
}

function openEdit(headsign) {
  editHeadsign.value = headsign
  saveError.value    = null
  modalOpen.value    = true
}

async function handleSave(data) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  saveError.value = null
  try {
    if (editHeadsign.value) {
      const updated = await api.headsigns.update(versionId, editHeadsign.value.id, data)
      const idx = headsigns.value.findIndex(h => h.id === updated.id)
      if (idx !== -1) headsigns.value[idx] = updated
    } else {
      const created = await api.headsigns.create(versionId, data)
      headsigns.value.push(created)
    }
    modalOpen.value = false
  } catch (err) {
    saveError.value = err.status === 409
      ? t('headsigns.error_conflict')
      : t('error.server')
  }
}

// ---- Confirm delete ----
const confirmOpen   = ref(false)
const pendingDelete = ref(null)

function requestDelete(headsign) {
  pendingDelete.value = headsign
  confirmOpen.value   = true
}

async function handleConfirmDelete() {
  if (!pendingDelete.value) return
  const versionId = versionsStore.state.activeVersionId
  const target = pendingDelete.value
  pendingDelete.value = null
  try {
    await api.headsigns.delete(versionId, target.id)
    headsigns.value = headsigns.value.filter(h => h.id !== target.id)
  } catch (err) {
    const msg = err.status === 404
      ? t('headsigns.error_not_found')
      : t('error.server')
    toast.show(msg, 'error')
    await loadHeadsigns()
  }
}
</script>

<template>
  <div class="headsigns-view">

    <header class="view-header">
      <md-icon class="view-header__icon">directions_bus</md-icon>
      <h1 class="view-header__title">{{ t('views.headsigns') }}</h1>
      <div class="view-header__actions">
        <md-filled-button
          v-if="canWrite && versionsStore.state.activeVersionId"
          @click="openCreate"
        >
          <md-icon slot="icon">add</md-icon>
          {{ t('headsigns.add') }}
        </md-filled-button>
      </div>
    </header>

    <div v-if="!versionsStore.state.activeVersionId" class="headsigns-view__no-version">
      <md-icon>info</md-icon>
      <span>{{ t('headsigns.no_version_selected') }}</span>
    </div>

    <DataTable
      v-else
      :columns="columns"
      :rows="headsigns"
      :loading="loading"
      :empty="t('headsigns.no_items')"
      :pagination="{ pageSize: 25 }"
    >
      <template #cell-number="{ value }">
        <span>{{ value ?? '—' }}</span>
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
          v-if="canDelete"
          class="table-action-btn table-action-btn--danger"
          :title="t('common.delete')"
          @click="requestDelete(row)"
        >
          <md-icon>delete</md-icon>
        </button>
      </template>
    </DataTable>

  </div>

  <HeadsignEditModal
    v-model="modalOpen"
    :headsign="editHeadsign"
    :error="saveError"
    @save="handleSave"
  />

  <ConfirmDialog
    v-model="confirmOpen"
    :title="t('headsigns.delete_confirm_title')"
    :message="t('headsigns.delete_confirm_message', { name: pendingDelete?.name ?? '' })"
    :confirm-label="t('common.delete')"
    :cancel-label="t('common.cancel')"
    :danger="true"
    @confirm="handleConfirmDelete"
  />
</template>

<style scoped>
.headsigns-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  height: 100%;
}

.headsigns-view__no-version {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--md-sys-color-on-surface-variant);
  padding: 1rem 0;
}
</style>
