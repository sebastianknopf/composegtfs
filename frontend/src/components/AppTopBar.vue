<script setup>
import { useI18n } from 'vue-i18n'
import LangSwitcher from '@/components/LangSwitcher.vue'
import VersionPicker from '@/components/VersionPicker.vue'
import '@material/web/icon/icon.js'

const { t } = useI18n()

defineProps({
  title: {
    type: String,
    default: 'composegtfs',
  },
  sections: {
    type: Array,
    default: () => [],
  },
  activeSection: {
    type: String,
    default: null,
  },
  exchangeSection: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['section-change', 'logout'])
</script>

<template>
  <header class="app-topbar" role="banner">
    <span class="app-topbar__title">{{ title }}</span>

    <VersionPicker />

    <div class="app-topbar__separator" aria-hidden="true" />

    <nav class="app-topbar__sections" :aria-label="t('topbar.sections')">
      <button
        v-for="section in sections"
        :key="section.id"
        class="app-topbar__section-btn"
        :class="{ 'app-topbar__section-btn--active': section.id === activeSection }"
        @click="emit('section-change', section.id)"
      >
        <md-icon class="app-topbar__section-icon">{{ section.icon }}</md-icon>
        <span>{{ t(section.labelKey) }}</span>
      </button>
    </nav>

    <div class="app-topbar__actions">
      <button
        v-if="exchangeSection"
        class="app-topbar__exchange-btn"
        :class="{ 'app-topbar__exchange-btn--active': exchangeSection.id === activeSection }"
        @click="emit('section-change', exchangeSection.id)"
      >
        {{ t(exchangeSection.labelKey) }}
      </button>

      <LangSwitcher />

      <button
        class="app-topbar__icon-btn"
        :title="t('topbar.logout')"
        :aria-label="t('topbar.logout')"
        @click="emit('logout')"
      >
        <md-icon>logout</md-icon>
      </button>
    </div>
  </header>
</template>
