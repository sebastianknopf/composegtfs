<script setup>
/**
 * AppToast — lightweight snackbar for one-off feedback messages.
 *
 * Usage (from any view):
 *   import { toast } from '@/stores/toast.js'
 *   toast.show('Something went wrong', 'error')   // type: 'info' | 'error'
 *
 * Mount once in AppView.vue (or App.vue).
 */
import { toastState } from '@/stores/toast.js'
</script>

<template>
  <Transition name="toast">
    <div
      v-if="toastState.visible"
      :class="['app-toast', `app-toast--${toastState.type}`]"
      role="status"
      aria-live="polite"
    >
      {{ toastState.message }}
    </div>
  </Transition>
</template>

<style scoped>
.app-toast {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  padding: 0.75rem 1.25rem;
  border-radius: 6px;
  font-size: var(--font-size-1, 0.875rem);
  font-weight: 500;
  box-shadow: var(--shadow-3, 0 4px 12px rgba(0,0,0,0.18));
  white-space: nowrap;
  pointer-events: none;
}

.app-toast--info {
  background: #303845;
  color: #ffffff;
}

.app-toast--error {
  background: var(--md-sys-color-error, #ba1a1a);
  color: #ffffff;
}

/* Transition */
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>
