<script setup>
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import { versionsStore } from '@/stores/versions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import DataTable from '@/components/DataTable.vue'
import AgencyEditModal from '@/components/AgencyEditModal.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-button.js'

const { t } = useI18n()
const { has } = usePermissions()

const canWrite  = has('agency:write')
const canDelete = has('agency:delete')

// ---- Table ----
const agencies = ref([])
const loading  = ref(false)

const CEMV_LABEL = { '0': () => t('agency.cemv_0'), '1': () => t('agency.cemv_1'), '2': () => t('agency.cemv_2') }

const columns = [
  { key: 'agency_id',       label: () => t('agency.column_id'),        sortable: true, width: '140px' },
  { key: 'global_id',       label: () => t('agency.column_global_id'), sortable: true, width: '160px' },
  { key: 'agency_name',     label: () => t('agency.column_name'),      sortable: true },
  { key: 'agency_url',      label: () => t('agency.column_url'),      sortable: false },
  { key: 'agency_timezone', label: () => t('agency.column_timezone'), sortable: true, width: '160px' },
  { key: 'agency_lang',     label: () => t('agency.column_lang'),     sortable: true, width: '90px',  align: 'center' },
  { key: 'agency_phone',    label: () => t('agency.column_phone'),    sortable: false, width: '160px' },
  { key: 'agency_email',    label: () => t('agency.column_email'),    sortable: false },
  { key: 'agency_fare_url', label: () => t('agency.column_fare_url'), sortable: false },
  { key: 'cemv_support',    label: () => t('agency.column_cemv'),     sortable: true,  width: '130px', align: 'center' },
]

async function loadAgencies() {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) {
    agencies.value = []
    return
  }
  loading.value = true
  try {
    agencies.value = await api.agencies.list(versionId)
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(loadAgencies)

watch(() => versionsStore.state.activeVersionId, loadAgencies)

// ---- Create / Edit modal ----
const modalOpen  = ref(false)
const editAgency = ref(null)
const saveError  = ref(null)

function openCreate() {
  editAgency.value = null
  saveError.value  = null
  modalOpen.value  = true
}

function openEdit(agency) {
  editAgency.value = agency
  saveError.value  = null
  modalOpen.value  = true
}

async function handleSave(data) {
  const versionId = versionsStore.state.activeVersionId
  if (!versionId) return
  saveError.value = null
  try {
    if (editAgency.value) {
      const { agency_id, ...updateData } = data
      const updated = await api.agencies.update(versionId, editAgency.value.agency_id, updateData)
      const idx = agencies.value.findIndex(a => a.agency_id === updated.agency_id)
      if (idx !== -1) agencies.value[idx] = updated
    } else {
      const created = await api.agencies.create(versionId, data)
      agencies.value.push(created)
    }
    modalOpen.value = false
  } catch (err) {
    saveError.value = err.status === 409
      ? t('agency.error_conflict')
      : t('error.server')
  }
}

// ---- Confirm delete ----
const confirmOpen   = ref(false)
const pendingDelete = ref(null)

function requestDelete(agency) {
  pendingDelete.value = agency
  confirmOpen.value   = true
}

async function handleConfirmDelete() {
  if (!pendingDelete.value) return
  const versionId = versionsStore.state.activeVersionId
  const target = pendingDelete.value
  pendingDelete.value = null
  try {
    await api.agencies.delete(versionId, target.agency_id)
    agencies.value = agencies.value.filter(a => a.agency_id !== target.agency_id)
  } catch (err) {
    const msg = err.status === 404
      ? t('agency.error_not_found')
      : t('error.server')
    toast.show(msg, 'error')
    await loadAgencies()
  }
}

function cemvLabel(val) {
  if (val == null) return '—'
  const fn = CEMV_LABEL[String(val)]
  return fn ? fn() : '—'
}
</script>

<template>
  <div class="agency-view">

    <header class="view-header">
      <md-icon class="view-header__icon">business</md-icon>
      <h1 class="view-header__title">{{ t('views.agency') }}</h1>
      <div class="view-header__actions">
        <md-filled-button
          v-if="canWrite && versionsStore.state.activeVersionId"
          @click="openCreate"
        >
          <md-icon slot="icon">add</md-icon>
          {{ t('agency.add') }}
        </md-filled-button>
      </div>
    </header>

    <div v-if="!versionsStore.state.activeVersionId" class="agency-view__no-version">
      <md-icon>info</md-icon>
      <span>{{ t('agency.no_version_selected') }}</span>
    </div>

    <DataTable
      v-else
      :columns="columns"
      :rows="agencies"
      :loading="loading"
      :empty="t('agency.no_items')"
      :pagination="{ pageSize: 25 }"
    >
      <template #cell-agency_url="{ value }">
        <a v-if="value" :href="value" target="_blank" rel="noopener noreferrer" class="agency-link" :title="value">
          {{ value }}
        </a>
        <span v-else>—</span>
      </template>

      <template #cell-global_id="{ value }">
        <span>{{ value ?? '—' }}</span>
      </template>

      <template #cell-agency_email="{ value }">
        <a v-if="value" :href="`mailto:${value}`" class="agency-link" :title="value">
          {{ value }}
        </a>
        <span v-else>—</span>
      </template>

      <template #cell-agency_fare_url="{ value }">
        <a v-if="value" :href="value" target="_blank" rel="noopener noreferrer" class="agency-link" :title="value">
          {{ value }}
        </a>
        <span v-else>—</span>
      </template>

      <template #cell-agency_lang="{ value }">
        <span>{{ value ?? '—' }}</span>
      </template>

      <template #cell-agency_phone="{ value }">
        <span>{{ value ?? '—' }}</span>
      </template>

      <template #cell-cemv_support="{ value }">
        <span>{{ cemvLabel(value) }}</span>
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

  <AgencyEditModal
    v-model="modalOpen"
    :agency="editAgency"
    :error="saveError"
    @save="handleSave"
  />

  <ConfirmDialog
    v-model="confirmOpen"
    :title="t('agency.delete_confirm_title')"
    :message="t('agency.delete_confirm_message', { name: pendingDelete?.agency_name ?? '' })"
    :confirm-label="t('common.delete')"
    :cancel-label="t('common.cancel')"
    :danger="true"
    @confirm="handleConfirmDelete"
  />

</template>

<style scoped>
.agency-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  height: 100%;
}

.agency-view__no-version {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--md-sys-color-on-surface-variant, #444);
  font-size: 0.9375rem;
  padding: 1rem 0;
}

.agency-link {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
  color: var(--md-sys-color-primary, #1f69e0);
  text-decoration: none;
}

.agency-link:hover {
  text-decoration: underline;
}
</style>

