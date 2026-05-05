<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { toast } from '@/stores/toast.js'
import { permissionsStore } from '@/stores/permissions.js'
import { usePermissions } from '@/composables/usePermissions.js'
import DataTable from '@/components/DataTable.vue'
import UserEditModal from '@/components/UserEditModal.vue'
import GroupEditModal from '@/components/GroupEditModal.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-button.js'

const { t } = useI18n()
const { has } = usePermissions()

const canWriteUsers  = has('accounts:write')
const canDeleteUsers = has('accounts:delete')
const canReadGroups   = has('groups:read')
const canWriteGroups  = has('groups:write')
const canDeleteGroups = has('groups:delete')

// ---- Perspectives ----
const canSeeGroups = computed(() => canReadGroups.value || canWriteGroups.value || canDeleteGroups.value)
const PERSPECTIVES = computed(() => canSeeGroups.value ? ['users', 'groups'] : ['users'])
const activePerspective = ref('users')

// Reset to users tab if groups tab becomes unavailable
watch(canSeeGroups, (visible) => {
  if (!visible && activePerspective.value === 'groups') {
    activePerspective.value = 'users'
  }
})

// ---- User table ----
const userColumns = computed(() => [
  { key: 'username',     label: () => t('accounts.username'),     sortable: true },
  { key: 'email',        label: () => t('accounts.email'),        sortable: true },
  ...(canSeeGroups.value ? [{ key: 'groups', label: () => t('accounts.groups') }] : []),
  { key: 'is_superuser', label: () => 'Superuser', align: 'center', width: '100px', sortable: true },
])

const users       = ref([])
const usersLoading = ref(false)
const usersError   = ref(null)

const currentUsername = computed(() => {
  try {
    const token = localStorage.getItem('access_token')
    if (!token) return null
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload?.sub ?? null
  } catch {
    return null
  }
})

function canDeleteUser(row) {
  return row.username !== currentUsername.value && !row.is_superuser
}

async function loadUsers() {
  usersLoading.value = true
  usersError.value   = null
  try {
    users.value = await api.users.list()
  } catch {
    usersError.value = t('error.server')
  } finally {
    usersLoading.value = false
  }
}

onMounted(() => {
  loadUsers()
  if (canSeeGroups.value) loadGroups()
})

// ---- Group table ----
const groupColumns = [
  { key: 'name',        label: () => t('accounts.group_name'),        sortable: true },
  { key: 'description', label: () => t('accounts.group_description'), sortable: true },
]

const groups = ref([])
const groupsLoading = ref(false)

async function loadGroups() {
  groupsLoading.value = true
  try {
    groups.value = await api.groups.list()
  } catch {
    toast.show(t('error.server'), 'error')
  } finally {
    groupsLoading.value = false
  }
}

const groupModalOpen = ref(false)
const editGroup = ref(null)
const groupSaveError = ref(null)

function openGroupCreate() {
  editGroup.value = null
  groupSaveError.value = null
  groupModalOpen.value = true
}

function openGroupEdit(group) {
  editGroup.value = group
  groupSaveError.value = null
  groupModalOpen.value = true
}

async function handleGroupSave(data) {
  groupSaveError.value = null
  try {
    if (editGroup.value) {
      const updated = await api.groups.update(editGroup.value.id, data)
      const idx = groups.value.findIndex(g => g.id === updated.id)
      if (idx !== -1) groups.value[idx] = updated
    } else {
      const created = await api.groups.create(data)
      groups.value.push(created)
    }
    groupModalOpen.value = false
    // Permissions may have changed — reload for current user
    permissionsStore.load(true)
  } catch (err) {
    groupSaveError.value = err.status === 409
      ? t('accounts.error_group_conflict')
      : t('error.server')
  }
}

// ---- Edit modal ----
const modalOpen = ref(false)
const editUser  = ref(null)
const saveError = ref(null)

function openCreate() {
  editUser.value  = null
  saveError.value = null
  modalOpen.value = true
}

function openEdit(user) {
  editUser.value  = user
  saveError.value = null
  modalOpen.value = true
}

async function handleSave(data) {
  saveError.value = null
  try {
    if (editUser.value) {
      const payload = {
        username:     data.username,
        email:        data.email,
        is_active:    data.is_active,
        is_superuser: data.is_superuser,
        group_ids:    data.group_ids ?? [],
        ...(data.password ? { password: data.password } : {}),
      }
      const updated = await api.users.update(editUser.value.id, payload)
      const idx = users.value.findIndex(u => u.id === updated.id)
      if (idx !== -1) users.value[idx] = updated
    } else {
      const created = await api.users.create(data)
      users.value.push(created)
    }
    modalOpen.value = false
  } catch (err) {
    if (err.status === 409) {
      saveError.value = t('accounts.error_conflict')
    } else if (err.status === 403) {
      saveError.value = t('accounts.error_self_demote')
    } else {
      saveError.value = t('error.server')
    }
  }
}

// ---- Confirm delete ----
const confirmOpen   = ref(false)
const pendingDelete = ref(null)
const pendingDeleteType = ref('user')

function requestDelete(user) {
  if (!canDeleteUser(user)) return
  pendingDeleteType.value = 'user'
  pendingDelete.value = user
  confirmOpen.value   = true
}

function requestGroupDelete(group) {
  pendingDeleteType.value = 'group'
  pendingDelete.value = group
  confirmOpen.value = true
}

async function handleConfirmDelete() {
  if (!pendingDelete.value) return
  const target = pendingDelete.value
  const targetType = pendingDeleteType.value
  pendingDelete.value = null
  try {
    if (targetType === 'group') {
      await api.groups.delete(target.id)
      groups.value = groups.value.filter(g => g.id !== target.id)
    } else {
      await api.users.delete(target.id)
      users.value = users.value.filter(u => u.id !== target.id)
    }
  } catch (err) {
    const msg = err.status === 400 && targetType === 'user'
      ? t('accounts.error_delete_self')
      : err.status === 403 && targetType === 'user'
        ? t('accounts.error_delete_superuser')
        : err.status === 404 && targetType === 'group'
        ? t('accounts.error_group_not_found')
        : t('error.server')
    toast.show(msg, 'error')
    if (targetType === 'group') {
      await loadGroups()
    } else {
      await loadUsers()
    }
  }
}

// Resolve reactive column labels at render time
// Not needed — DataTable handles label functions internally.
</script>

<template>
  <div class="accounts-view">

    <!-- View header -->
    <header class="view-header">
      <md-icon class="view-header__icon">group</md-icon>
      <h1 class="view-header__title">{{ t('views.accounts') }}</h1>
      <div class="view-header__actions">
        <md-filled-button v-if="activePerspective === 'users' && canWriteUsers" @click="openCreate">
          <md-icon slot="icon">person_add</md-icon>
          {{ t('accounts.add_user') }}
        </md-filled-button>
        <md-filled-button v-if="activePerspective === 'groups' && canWriteGroups" @click="openGroupCreate">
          <md-icon slot="icon">group_add</md-icon>
          {{ t('accounts.add_group') }}
        </md-filled-button>
      </div>
    </header>

    <!-- Perspective tabs — custom lightweight segmented control -->
    <div class="perspective-tabs" role="tablist">
      <button
        v-for="p in PERSPECTIVES"
        :key="p"
        role="tab"
        :aria-selected="activePerspective === p"
        :class="['perspective-tab', { 'perspective-tab--active': activePerspective === p }]"
        @click="activePerspective = p"
      >
        <md-icon class="perspective-tab__icon">{{ p === 'users' ? 'manage_accounts' : 'group_work' }}</md-icon>
        {{ p === 'users' ? t('accounts.tab_users') : t('accounts.tab_groups') }}
      </button>
    </div>

    <!-- Users table -->
    <DataTable
      v-if="activePerspective === 'users'"
      :columns="userColumns"
      :rows="users"
      :loading="usersLoading"
      :empty="t('accounts.no_users')"
      :pagination="{ pageSize: 25 }"
    >
      <template #cell-groups="{ row }">
        <div class="group-badges">
          <span
            v-for="gid in row.group_ids"
            :key="gid"
            class="group-badge"
          >
            {{ groups.find(g => g.id === gid)?.name ?? gid }}
          </span>
          <span v-if="!row.group_ids?.length" class="group-badge-empty">—</span>
        </div>
      </template>
      <template #cell-is_superuser="{ value }">
        <md-icon v-if="value" class="superuser-icon">shield_person</md-icon>
        <span v-else class="group-badge-empty">—</span>
      </template>
      <template #actions="{ row }">
        <button v-if="canWriteUsers" class="table-action-btn" :title="t('common.edit')" @click="openEdit(row)">
          <md-icon>edit</md-icon>
        </button>
        <button
          v-if="canDeleteUsers && canDeleteUser(row)"
          class="table-action-btn table-action-btn--danger"
          :title="t('common.delete')"
          @click="requestDelete(row)"
        >
          <md-icon>delete</md-icon>
        </button>
      </template>
    </DataTable>

    <!-- Groups table -->
    <DataTable
      v-if="activePerspective === 'groups'"
      :columns="groupColumns"
      :rows="groups"
      :loading="groupsLoading"
      :empty="t('accounts.no_groups')"
      :pagination="{ pageSize: 25 }"
    >
      <template #actions="{ row }">
        <button v-if="canWriteGroups" class="table-action-btn" :title="t('common.edit')" @click="openGroupEdit(row)">
          <md-icon>edit</md-icon>
        </button>
        <button v-if="canDeleteGroups" class="table-action-btn table-action-btn--danger" :title="t('common.delete')" @click="requestGroupDelete(row)">
          <md-icon>delete</md-icon>
        </button>
      </template>
    </DataTable>

  </div>

  <!-- Edit / Create modal -->
  <UserEditModal v-model="modalOpen" :user="editUser" :error="saveError" :groups="groups" :is-self="editUser?.username === currentUsername" @save="handleSave" />

  <!-- Group Edit / Create modal -->
  <GroupEditModal
    v-model="groupModalOpen"
    :group="editGroup"
    :error="groupSaveError"
    @save="handleGroupSave"
  />

  <!-- Confirm delete -->
  <ConfirmDialog
    v-model="confirmOpen"
    :title="pendingDeleteType === 'group' ? t('accounts.group_delete_confirm_title') : t('accounts.delete_confirm_title')"
    :message="pendingDeleteType === 'group'
      ? t('accounts.group_delete_confirm_message', { name: pendingDelete?.name ?? '' })
      : t('accounts.delete_confirm_message', { name: pendingDelete?.username ?? '' })"
    :confirm-label="t('common.delete')"
    :cancel-label="t('common.cancel')"
    :danger="true"
    @confirm="handleConfirmDelete"
  />
</template>

<style scoped>
.accounts-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  height: 100%;
}

/* Status badges */
.status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  --md-icon-size: 1.1rem;
}

.status-badge--active   { color: #2a7a3b; }
.status-badge--inactive { color: var(--md-sys-color-outline, #9e9e9e); }
.status-badge--super    { color: var(--md-sys-color-primary, #1f69e0); }
.status-badge--none     { color: var(--md-sys-color-outline, #bbb); }

/* Group badges in user table */
.group-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.group-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 500;
  background: rgba(31, 105, 224, 0.12);
  color: #1f69e0;
  white-space: nowrap;
}

.group-badge-empty {
  color: var(--md-sys-color-outline, #bbb);
}

.superuser-icon {
  font-size: 1.1rem;
  --md-icon-size: 1.1rem;
  color: #2a7a3b;
}
</style>
