<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import { api } from '@/api/client.js'
import '@material/web/dialog/dialog.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'
import TagSelect from '@/components/TagSelect.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  group: { type: Object, default: null },
  error: { type: String, default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

const isEdit = computed(() => !!props.group)

const form = ref(emptyForm())
const fieldErrors = ref(emptyErrors())

function emptyForm() {
  return {
    name: '',
    description: '',
    permission_codenames: [],
  }
}

// Available permissions loaded from API (flat list for TagSelect)
const availablePerms = ref([])

async function loadPermissions() {
  if (availablePerms.value.length > 0) return
  try {
    const groups = await api.permissions.list()
    availablePerms.value = groups.flatMap(g =>
      g.permissions.map(p => ({ id: p.codename, label: t(p.lang_key) }))
    )
  } catch {
    // non-fatal: TagSelect will just show an empty dropdown
  }
}

function emptyErrors() {
  return {
    name: null,
    description: null,
  }
}

function createSchema() {
  return z.object({
    name: z.string().min(1, t('accounts.validation_group_name_required')),
    description: z.string(),
  })
}

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function validateForm() {
  fieldErrors.value = emptyErrors()
  const result = createSchema().safeParse(form.value)
  if (result.success) return true

  for (const issue of result.error.issues) {
    const field = issue.path?.[0]
    if (field && fieldErrors.value[field] == null) {
      fieldErrors.value[field] = issue.message
    }
  }
  return false
}

watch(
  () => [props.modelValue, props.group],
  ([open]) => {
    if (!open) return
    form.value = props.group
      ? {
          name: props.group.name,
          description: props.group.description ?? '',
          permission_codenames: props.group.permission_codenames ?? [],
        }
      : emptyForm()
    fieldErrors.value = emptyErrors()
    loadPermissions()
  },
  { immediate: true },
)

const dialogRef = ref(null)

watch(() => props.modelValue, (val) => {
  const el = dialogRef.value
  if (!el) return
  if (val) el.show?.()
  else el.close?.()
})

function handleClose() {
  emit('update:modelValue', false)
}

function handleSave() {
  if (!validateForm()) return
  emit('save', { ...form.value })
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="group-edit-dialog">
    <div slot="headline" class="group-edit-dialog__headline">
      <md-icon class="group-edit-dialog__headline-icon">
        {{ isEdit ? 'groups' : 'group_add' }}
      </md-icon>
      <span class="group-edit-dialog__title">
        {{ isEdit ? t('accounts.edit_group') : t('accounts.add_group') }}
      </span>
    </div>

    <form slot="content" class="group-edit-dialog__form" method="dialog">
      <div class="group-edit-dialog__section">
        <p class="group-edit-dialog__section-label">{{ t('accounts.section_group') }}</p>
        <md-outlined-text-field
          class="group-edit-field"
          :label="t('accounts.group_name')"
          :value="form.name"
          :error="!!fieldErrors.name"
          :error-text="fieldErrors.name ?? ''"
          required
          @input="form.name = $event.target.value; clearFieldError('name')"
        />
        <md-outlined-text-field
          class="group-edit-field"
          :label="t('accounts.group_description')"
          type="textarea"
          rows="3"
          :value="form.description"
          :error="!!fieldErrors.description"
          :error-text="fieldErrors.description ?? ''"
          @input="form.description = $event.target.value; clearFieldError('description')"
        />
      </div>

      <!-- Permission assignment -->
      <div class="group-edit-dialog__section">
        <p class="group-edit-dialog__section-label">{{ t('accounts.section_permissions') }}</p>
        <TagSelect
          v-model="form.permission_codenames"
          :options="availablePerms"
          :label="t('accounts.permissions_search')"
          :no-results-text="t('accounts.permissions_no_results')"
        />
      </div>
    </form>

    <div slot="actions">
      <p v-if="error" class="group-edit-dialog__error">{{ error }}</p>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleSave">
        <md-icon slot="icon">save</md-icon>
        {{ t('common.save') }}
      </md-filled-button>
    </div>
  </md-dialog>
</template>

<style scoped>
.group-edit-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.group-edit-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.group-edit-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
}

.group-edit-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.group-edit-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-top: 0.5rem;
}

.group-edit-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.group-edit-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.group-edit-field {
  width: 100%;
}

.group-edit-dialog__error {
  margin: 0 auto 0 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}
</style>
