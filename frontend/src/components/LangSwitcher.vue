<script setup>
import { useI18n } from 'vue-i18n'

const { locale, t, availableLocales } = useI18n()

function setLocale(lang) {
  locale.value = lang
  localStorage.setItem('locale', lang)
}
</script>

<template>
  <div class="lang-switcher" role="group" :aria-label="t('topbar.language')">
    <button
      v-for="lang in availableLocales"
      :key="lang"
      class="lang-switcher__btn"
      :class="{ 'lang-switcher__btn--active': locale === lang }"
      :aria-pressed="locale === lang"
      @click="setLocale(lang)"
    >
      {{ lang.toUpperCase() }}
    </button>
  </div>
</template>

<style scoped>
.lang-switcher {
  display: flex;
  align-items: center;
  gap: 2px;
}

.lang-switcher__btn {
  background: none;
  border: 1px solid transparent;
  cursor: pointer;
  color: inherit;
  padding: 3px 7px;
  border-radius: var(--radius-2, 6px);
  font-size: var(--font-size-0, 0.75rem);
  font-family: inherit;
  font-weight: 500;
  letter-spacing: 0.04em;
  opacity: 0.6;
  transition: opacity 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.lang-switcher__btn:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.1);
}

.lang-switcher__btn--active {
  opacity: 1;
  border-color: rgba(255, 255, 255, 0.35);
}
</style>
