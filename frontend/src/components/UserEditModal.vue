<script setup>
/**
 * UserEditModal — dialog for creating or editing a user account.
 *
 * Props:
 *   modelValue — boolean    — whether the dialog is open (v-model)
 *   user       — object|null — pre-filled data when editing; null for new user
 *
 * Emits:
 *   update:modelValue   — close signal
 *   save(user)          — emitted with the form data when the user confirms
 */
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import { permissionsStore } from '@/stores/permissions.js'
import '@material/web/dialog/dialog.js'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/checkbox/checkbox.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'
import TagSelect from '@/components/TagSelect.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  user:       { type: Object,  default: null },
  error:      { type: String,  default: null },
  groups:     { type: Array,   default: () => [] },
  isSelf:     { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

const isEdit = computed(() => !!props.user)

const form = ref(emptyForm())
const fieldErrors = ref(emptyErrors())

function emptyErrors() {
  return {
    username: null,
    email: null,
    password: null,
    password2: null,
  }
}

function createSchema() {
  return z
    .object({
      username: z.string().min(1, t('accounts.validation_username_required')),
      email: z
        .string()
        .min(1, t('accounts.validation_email_required'))
        .email(t('accounts.validation_email_invalid')),
      password: z.string(),
      password2: z.string(),
      is_active: z.boolean(),
      is_superuser: z.boolean(),
    })
    .superRefine((data, ctx) => {
      const hasPassword = data.password.length > 0
      const hasPassword2 = data.password2.length > 0

      if (!isEdit.value) {
        if (!hasPassword) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['password'],
            message: t('accounts.validation_password_required'),
          })
        }
        if (!hasPassword2) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['password2'],
            message: t('accounts.validation_password_confirm_required'),
          })
        }
      } else {
        if (hasPassword && !hasPassword2) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['password2'],
            message: t('accounts.validation_password_confirm_required'),
          })
        }
        if (hasPassword2 && !hasPassword) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['password'],
            message: t('accounts.validation_password_required'),
          })
        }
      }

      if ((hasPassword || hasPassword2) && data.password !== data.password2) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['password2'],
          message: t('accounts.password_mismatch'),
        })
      }
    })
}

function emptyForm() {
  return { username: '', email: '', password: '', password2: '', is_active: true, is_superuser: false, group_ids: [] }
}

const groupOptions = computed(() =>
  props.groups.map(g => ({ id: g.id, label: g.name }))
)

function clearFieldError(name) {
  fieldErrors.value[name] = null
}

function validateForm() {
  fieldErrors.value = emptyErrors()
  const result = createSchema().safeParse(form.value)
  if (result.success) {
    return true
  }
  for (const issue of result.error.issues) {
    const field = issue.path?.[0]
    if (field && fieldErrors.value[field] == null) {
      fieldErrors.value[field] = issue.message
    }
  }
  return false
}

watch(
  () => [props.modelValue, props.user],
  ([open]) => {
    if (open) {
      form.value = props.user
        ? {
            username:     props.user.username,
            email:        props.user.email,
            password:     '',
            password2:    '',
            is_active:    props.user.is_active,
            is_superuser: props.user.is_superuser,
            group_ids:    props.user.group_ids ?? [],
          }
        : emptyForm()
      fieldErrors.value = emptyErrors()
    }
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
  if (!validateForm()) {
    return
  }
  const { password2, ...data } = form.value
  emit('save', data)
  // Modal stays open — parent closes it after successful API call
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="user-edit-dialog">

    <div slot="headline" class="user-edit-dialog__headline">
      <md-icon class="user-edit-dialog__headline-icon">
        {{ isEdit ? 'manage_accounts' : 'person_add' }}
      </md-icon>
      <div class="user-edit-dialog__headline-text">
        <span class="user-edit-dialog__title">
          {{ isEdit ? t('accounts.edit_user') : t('accounts.add_user') }}
        </span>
      </div>
    </div>

    <form slot="content" class="user-edit-dialog__form" method="dialog">

      <!-- Login credentials -->
      <div class="user-edit-dialog__section">
        <p class="user-edit-dialog__section-label">{{ t('accounts.section_credentials') }}</p>
        <div class="user-edit-dialog__row">
          <md-outlined-text-field
            class="user-edit-field"
            :label="t('accounts.username')"
            :value="form.username"
            :error="!!fieldErrors.username"
            :error-text="fieldErrors.username ?? ''"
            autocomplete="off"
            required
            @input="form.username = $event.target.value; clearFieldError('username')"
          />
          <md-outlined-text-field
            class="user-edit-field"
            :label="t('accounts.email')"
            type="email"
            :value="form.email"
            :error="!!fieldErrors.email"
            :error-text="fieldErrors.email ?? ''"
            autocomplete="off"
            required
            @input="form.email = $event.target.value; clearFieldError('email')"
          />
        </div>
        <div class="user-edit-dialog__row">
          <md-outlined-text-field
            class="user-edit-field"
            :label="isEdit ? t('accounts.password_change_hint') : t('accounts.password')"
            type="password"
            :value="form.password"
            :error="!!fieldErrors.password"
            :error-text="fieldErrors.password ?? ''"
            autocomplete="new-password"
            :required="!isEdit"
            @input="form.password = $event.target.value; clearFieldError('password'); clearFieldError('password2')"
          />
          <md-outlined-text-field
            class="user-edit-field"
            :label="t('accounts.password_confirm')"
            type="password"
            :value="form.password2"
            :error="!!fieldErrors.password2"
            :error-text="fieldErrors.password2 ?? ''"
            autocomplete="new-password"
            :required="!isEdit"
            @input="form.password2 = $event.target.value; clearFieldError('password2'); clearFieldError('password')"
          />
        </div>
      </div>

      <!-- Group assignment -->
      <div class="user-edit-dialog__section">
        <p class="user-edit-dialog__section-label">{{ t('accounts.section_groups') }}</p>
        <TagSelect
          v-model="form.group_ids"
          :options="groupOptions"
          :label="t('accounts.groups_search')"
          :no-results-text="t('accounts.groups_no_results')"
        />
      </div>

      <!-- Misc / permissions -->
      <div class="user-edit-dialog__section">
        <p class="user-edit-dialog__section-label">{{ t('accounts.section_misc') }}</p>
        <div class="user-edit-dialog__checks">
          <label class="user-edit-checkbox" :class="{ 'user-edit-checkbox--disabled': isSelf }">
            <md-checkbox
              touch-target="wrapper"
              :checked="form.is_active"
              :disabled="isSelf || undefined"
              @change="form.is_active = $event.target.checked"
            />
            <span class="user-edit-checkbox__label">{{ t('accounts.active') }}</span>
          </label>
          <label v-if="permissionsStore.state.isSuperuser" class="user-edit-checkbox" :class="{ 'user-edit-checkbox--disabled': isSelf }">
            <md-checkbox
              touch-target="wrapper"
              :checked="form.is_superuser"
              :disabled="isSelf || undefined"
              @change="form.is_superuser = $event.target.checked"
            />
            <span class="user-edit-checkbox__label">{{ t('accounts.superuser') }}</span>
          </label>
        </div>
      </div>

    </form>

    <div slot="actions">
      <p v-if="error" class="user-edit-dialog__error">{{ error }}</p>
      <md-text-button @click="handleClose">{{ t('common.cancel') }}</md-text-button>
      <md-filled-button @click="handleSave">
        <md-icon slot="icon">save</md-icon>
        {{ t('common.save') }}
      </md-filled-button>
    </div>

  </md-dialog>
</template>

<style scoped>
.user-edit-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.user-edit-dialog__error {
  margin: 0 auto 0 0;
  font-size: 0.8125rem;
  color: var(--md-sys-color-error, #ba1a1a);
}

.user-edit-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.user-edit-dialog__headline-icon {
  font-size: 1.5rem;
  --md-icon-size: 1.5rem;
  color: var(--md-sys-color-primary, #1f69e0);
  flex-shrink: 0;
}

.user-edit-dialog__headline-text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.user-edit-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.user-edit-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding-top: 0.5rem;
}

.user-edit-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.user-edit-dialog__section-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--md-sys-color-primary, #1f69e0);
}

.user-edit-dialog__row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.875rem;
}

.user-edit-field {
  width: 100%;
}

.user-edit-dialog__checks {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.user-edit-checkbox {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
}

.user-edit-checkbox__label {
  font-size: var(--font-size-1, 0.875rem);
  font-weight: 500;
  color: var(--md-sys-color-on-surface, #222);
}

.user-edit-checkbox--disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}
</style>
