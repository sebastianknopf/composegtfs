/**
 * Thin API client. All requests go through /api (proxied to the backend).
 * The auth token is read from localStorage on every call so the store
 * doesn't need to be imported here (avoids circular deps).
 *
 * Errors thrown by this client always have:
 *   err.status  – HTTP status code
 *   err.code    – normalized error code string (see _errorCode below)
 */

const BASE = '/api'

/**
 * Optional callback invoked when any authenticated request returns 401.
 * Register this from the router or app bootstrap to trigger auto-logout.
 */
let _unauthorizedHandler = null
export function setUnauthorizedHandler(fn) {
  _unauthorizedHandler = fn
}

/**
 * Optional callback invoked when any authenticated request returns 403.
 * Register this from the router to show the forbidden view.
 */
let _forbiddenHandler = null
export function setForbiddenHandler(fn) {
  _forbiddenHandler = fn
}

function authHeaders() {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * Derive a stable error code from an HTTP response.
 * FastAPI may return detail as a string (our own errors) or as an array
 * of validation objects (422 Unprocessable Entity from Pydantic).
 */
function _errorCode(status, detail) {
  if (status === 401) return 'error.invalid_credentials'
  if (status === 403) return 'error.forbidden'
  if (status === 422 || Array.isArray(detail)) return 'error.validation'
  if (status >= 500) return 'error.server'
  return 'error.unknown'
}

async function _parseError(res) {
  let detail = null
  try {
    const data = await res.json()
    detail = data.detail ?? null
  } catch {
    // ignore
  }
  const code = _errorCode(res.status, detail)
  const err = new Error(code)
  err.status = res.status
  err.code = code
  return err
}

async function request(method, path, body) {
  const options = {
    method,
    headers: {
      ...authHeaders(),
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  }

  const res = await fetch(`${BASE}${path}`, options)

  if (!res.ok) {
    const err = await _parseError(res)
    if (res.status === 401 && localStorage.getItem('access_token')) {
      _unauthorizedHandler?.()
    }
    if (res.status === 403) {
      _forbiddenHandler?.()
    }
    throw err
  }

  // 204 must not be parsed as JSON, even if a JSON content-type header is present.
  if (res.status === 204) {
    return null
  }

  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    return res.json()
  }
  return null
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  delete: (path) => request('DELETE', path),

  settings: {
    get: () => request('GET', '/settings'),
    save: (data) => request('PUT', '/settings', data),
  },

  users: {
    list:   ()           => request('GET',    '/users'),
    create: (data)       => request('POST',   '/users', data),
    update: (id, data)   => request('PUT',    `/users/${id}`, data),
    delete: (id)         => request('DELETE', `/users/${id}`),
  },

  groups: {
    list:   ()           => request('GET',    '/groups'),
    create: (data)       => request('POST',   '/groups', data),
    update: (id, data)   => request('PUT',    `/groups/${id}`, data),
    delete: (id)         => request('DELETE', `/groups/${id}`),
  },

  permissions: {
    list: () => request('GET', '/permissions'),
  },

  versions: {
    list:   ()           => request('GET',    '/versions'),
    create: (data)       => request('POST',   '/versions', data),
    get:    (id)         => request('GET',    `/versions/${id}`),
    rename: (id, data)   => request('PATCH',  `/versions/${id}`, data),
    delete: (id)         => request('DELETE', `/versions/${id}`),
  },

  /**
   * Login via OAuth2 password flow (application/x-www-form-urlencoded).
   * Returns { access_token, token_type }.
   */
  async login(username, password) {
    const body = new URLSearchParams({ username, password, grant_type: 'password' })
    const res = await fetch(`${BASE}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    })
    if (!res.ok) throw await _parseError(res)
    return res.json()
  },

  /**
   * Refresh the current access token. Requires a valid bearer token.
   * Returns { access_token, token_type }.
   */
  refresh: () => request('POST', '/auth/refresh'),

  /**
   * Returns the current user's username, is_superuser flag, and the union
   * of all effective permission_codenames across all their groups.
   */
  me: () => request('GET', '/auth/me'),
}
