<script setup>
/**
 * ConfirmDialog — generic confirmation dialog.
 *
 * Props:
 *   modelValue   — boolean   — open state (v-model)
 *   title        — string    — dialog headline
 *   message      — string    — body text
 *   confirmLabel — string    — confirm button label (default 'Confirm')
 *   cancelLabel  — string    — cancel button label  (default 'Cancel')
 *   danger       — boolean   — use error color for confirm button
 *
 * Emits:
 *   update:modelValue — close signal
 *   confirm           — user confirmed
 */
import { ref, watch } from 'vue'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const props = defineProps({
  modelValue:   { type: Boolean, default: false },
  title:        { type: String,  default: 'Bestätigen' },
  message:      { type: String,  default: '' },
  confirmLabel: { type: String,  default: 'Bestätigen' },
  cancelLabel:  { type: String,  default: 'Abbrechen' },
  danger:       { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

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

function handleConfirm() {
  emit('confirm')
  emit('update:modelValue', false)
}
</script>

<template>
  <md-dialog ref="dialogRef" @closed="handleClose" class="confirm-dialog">
    <div slot="headline" class="confirm-dialog__headline">
      <md-icon :class="['confirm-dialog__icon', { 'confirm-dialog__icon--danger': danger }]">
        {{ danger ? 'warning' : 'help' }}
      </md-icon>
      {{ title }}
    </div>

    <div slot="content" class="confirm-dialog__message">
      {{ message }}
    </div>

    <div slot="actions">
      <md-text-button @click="handleClose">{{ cancelLabel }}</md-text-button>
      <md-filled-button
        :class="{ 'confirm-dialog__btn--danger': danger }"
        @click="handleConfirm"
      >
        {{ confirmLabel }}
      </md-filled-button>
    </div>
  </md-dialog>
</template>

<style scoped>
.confirm-dialog {
  --md-dialog-container-shape: 6px;
  --md-dialog-container-color: #ffffff;
}

.confirm-dialog__headline {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.confirm-dialog__icon {
  color: var(--md-sys-color-primary, #1f69e0);
}

.confirm-dialog__icon--danger {
  color: var(--md-sys-color-error, #b00020);
}

.confirm-dialog__message {
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  font-size: var(--font-size-1, 0.875rem);
  line-height: 1.5;
}

.confirm-dialog__btn--danger {
  --md-filled-button-container-color: var(--md-sys-color-error, #b00020);
}
</style>
