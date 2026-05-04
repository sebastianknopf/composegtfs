<script setup>
/**
 * VersionEditModal — create or rename a version.
 *
 * Props:
 *   modelValue — boolean    — open state (v-model)
 *   version    — object|null — null = create mode, object = rename mode
 *   error      — string|null — server-level error (e.g. 409 conflict)
 *
 * Emits:
 *   update:modelValue
 *   save({ name })
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/textfield/outlined-text-field.js'

const { t } = useI18n()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  version:    { type: Object,  default: null },
  error:      { type: String,  default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])

const dialogRef = ref(null)

// ---- Form state ----
const name       = ref('')
const nameError  = ref(null)

function buildSchema() {
  return z.object({
    name: z
      .string()
      .min(1, t('versions.validation_name_required'))
      .max(128, t('versions.validation_name_too_long')),
  })
}

watch(() => props.modelValue, (val) => {
  const el = dialogRef.value
  if (val) {
    name.value      = props.version?.name ?? ''
    nameError.value = null
    requestAnimationFrame(() => el?.show?.())
  } else {
    el?.close?.()
  }
})

function handleClose() {
  emit('update:modelValue', false)
}

function validate() {
  nameError.value = null
  const result = buildSchema().safeParse({ name: name.value.trim() })
  if (!result.success) {
    const issues = result.error.flatten().fieldErrors
    nameError.value = issues.name?.[0] ?? null
    return false
  }
  return true
}

function handleSubmit() {
  if (!validate()) return
  emit('save', { name: name.value.trim() })
}


</script>

<template>
  <md-dialog ref="dialogRef" class="version-edit-dialog" @closed="handleClose">

    <div slot="headline" class="version-edit-dialog__headline">
      <md-icon class="version-edit-dialog__headline-icon">layers</md-icon>
      <span class="version-edit-dialog__title">
        {{ version ? t('versions.edit_title_edit') : t('versions.edit_title_create') }}
      </span>
    </div>

    <form slot="content" class="version-edit-dialog__form" method="dialog">
      <div class="version-edit-dialog__section">
        <p class="version-edit-dialog__section-label">{{ t('versions.name') }}</p>
        <md-outlined-text-field
          class="version-edit-field"
          :label="t('versions.name')"
          :placeholder="t('versions.name_placeholder')"
          :value="name"
          :error="!!nameError"
          :error-text="nameError ?? ''"
          required
          autofocus
          @input="name = $event.target.value"
          @keydown.enter="handleSubmit"
        />
      </div>
    </form>

    <div slot="actions">
      <p v-if="error" class="version-edit-dialog__error">{{ error }}</p>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleSubmit">
        <md-icon slot="icon">save</md-icon>
        {{ t('common.save') }}
      </md-filled-button>
    </div>

  </md-dialog>
</template>

<style scoped>
.version-edit-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.version-edit-dialog__error {
  margin: 0 auto 0 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}

.version-edit-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.version-edit-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.version-edit-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.version-edit-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding-top: 0.5rem;
}

.version-edit-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.version-edit-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.version-edit-field {
  width: 100%;
}
</style>
