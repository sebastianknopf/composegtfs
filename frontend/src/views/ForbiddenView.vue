<script setup>
import { useI18n } from 'vue-i18n'
import '@material/web/icon/icon.js'
import '@material/web/button/outlined-button.js'

const { t } = useI18n()

const emit = defineEmits(['back'])
</script>

<template>
  <div class="forbidden-view" role="alert" aria-live="assertive">
    <md-icon class="forbidden-view__icon">lock</md-icon>
    <h2 class="forbidden-view__title">{{ t('error.forbidden_title') }}</h2>
    <p class="forbidden-view__message">{{ t('error.forbidden_message') }}</p>
    <md-outlined-button @click="emit('back')">
      <md-icon slot="icon">arrow_back</md-icon>
      {{ t('error.forbidden_back') }}
    </md-outlined-button>
  </div>
</template>

<style scoped>
.forbidden-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  height: 100%;
  min-height: 320px;
  text-align: center;
  padding: 2rem;
}

.forbidden-view__icon {
  font-size: 3.5rem;
  --md-icon-size: 3.5rem;
  color: var(--md-sys-color-outline, #9e9e9e);
  opacity: 0.5;
}

.forbidden-view__title {
  margin: 0;
  font-size: var(--font-size-3, 1.25rem);
  font-weight: 600;
  color: var(--md-sys-color-on-surface, #222);
}

.forbidden-view__message {
  margin: 0;
  font-size: var(--font-size-1, 0.875rem);
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  max-width: 360px;
}
</style>
