<script setup>
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ref, onMounted } from 'vue'
import { authStore } from '@/stores/auth.js'
import { settingsStore } from '@/stores/settings.js'
import LangSwitcher from '@/components/LangSwitcher.vue'
import '@material/web/textfield/outlined-text-field.js'
import '@material/web/button/filled-button.js'

const router = useRouter()
const { t } = useI18n()

onMounted(() => settingsStore.load())

const usernameRef = ref(null)
const passwordRef = ref(null)

async function handleLogin(event) {
  event.preventDefault()
  const username = usernameRef.value?.value ?? ''
  const password = passwordRef.value?.value ?? ''

  try {
    await authStore.login(username, password)
    await router.push('/')
  } catch {
    // errorKey is set in the store
  }
}
</script>

<template>
  <div class="login-layout">
    <div class="login-card" role="main">
      <header class="login-card__header">
        <h1 class="login-card__title">{{ settingsStore.state.appTitle }}</h1>
        <p class="login-card__subtitle">{{ t('login.subtitle') }}</p>
      </header>

      <form class="login-card__fields" novalidate @submit="handleLogin" @keydown.enter.prevent="handleLogin">
        <md-outlined-text-field
          ref="usernameRef"
          :label="t('login.username')"
          type="text"
          name="username"
          autocomplete="username"
          required
        />
        <md-outlined-text-field
          ref="passwordRef"
          :label="t('login.password')"
          type="password"
          name="password"
          autocomplete="current-password"
          required
        />

        <p class="login-card__error" role="alert">
          {{ authStore.state.errorKey ? t(authStore.state.errorKey) : '' }}
        </p>

        <div class="login-card__actions">
          <md-filled-button type="submit" :disabled="authStore.state.loading">
            {{ authStore.state.loading ? '…' : t('login.button') }}
          </md-filled-button>
        </div>
        
        <p v-if="settingsStore.state.appVersion" class="login-card__version">
          v{{ settingsStore.state.appVersion }}
        </p>
      </form>

      <div class="login-card__footer">
        <LangSwitcher />
      </div>
    </div>
  </div>
</template>
