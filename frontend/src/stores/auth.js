import { reactive } from 'vue'
import { api } from '@/api/client.js'

const _TOKEN_KEY = 'access_token'

/**
 * Decode the payload of a JWT without verifying the signature.
 * Returns null if the token is malformed.
 */
function _decodePayload(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(base64))
  } catch {
    return null
  }
}

function _isExpired(token) {
  const payload = _decodePayload(token)
  if (!payload?.exp) return true
  // exp is in seconds; add 5 s clock-skew tolerance
  return Date.now() / 1000 > payload.exp - 5
}

/**
 * Minimal reactive auth state.
 */
const state = reactive({
  token: localStorage.getItem(_TOKEN_KEY) ?? null,
  loading: false,
  errorKey: null,
})

function _storeToken(token) {
  state.token = token
  localStorage.setItem(_TOKEN_KEY, token)
}

// ---- Public API ----

function isAuthenticated() {
  if (!state.token) return false
  if (_isExpired(state.token)) {
    state.token = null
    localStorage.removeItem(_TOKEN_KEY)
    return false
  }
  return true
}

async function login(username, password) {
  state.loading = true
  state.errorKey = null
  try {
    const data = await api.login(username, password)
    _storeToken(data.access_token)
  } catch (err) {
    state.errorKey = err.code ?? 'error.unknown'
    throw err
  } finally {
    state.loading = false
  }
}

function logout() {
  state.token = null
  localStorage.removeItem(_TOKEN_KEY)
}

export const authStore = { state, isAuthenticated, login, logout }
