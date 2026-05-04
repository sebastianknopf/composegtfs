import { createApp } from 'vue'
import { createI18n } from 'vue-i18n'
import de from './locales/de.js'
import en from './locales/en.js'
import router from './router/index.js'
import App from './App.vue'
import 'material-symbols/outlined.css'
import './assets/theme.css'
import './assets/layout.css'

const _savedLocale = localStorage.getItem('locale') ?? 'de'

const i18n = createI18n({
  legacy: false,
  locale: _savedLocale,
  fallbackLocale: 'de',
  messages: { de, en },
})

createApp(App).use(router).use(i18n).mount('#app')
