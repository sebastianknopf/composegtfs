<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="exchange-view">
    <p class="exchange-view__placeholder">{{ t('sections.exchange') }}</p>
  </div>
</template>

<style scoped>
.exchange-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--md-sys-color-outline, #74777f);
  font-size: var(--font-size-2, 1rem);
}

.exchange-view__placeholder {
  margin: 0;
  opacity: 0.6;
}
</style>
