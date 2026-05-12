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

  // Silently adopt a refreshed token if the backend issued one
  const newToken = res.headers.get('X-New-Token')
  if (newToken) {
    localStorage.setItem('access_token', newToken)
  }

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

  agencies: {
    list:   (versionId)              => request('GET',    `/versions/${versionId}/agencies`),
    create: (versionId, data)        => request('POST',   `/versions/${versionId}/agencies`, data),
    get:    (versionId, agencyId)    => request('GET',    `/versions/${versionId}/agencies/${agencyId}`),
    update: (versionId, agencyId, data) => request('PUT', `/versions/${versionId}/agencies/${agencyId}`, data),
    delete: (versionId, agencyId)    => request('DELETE', `/versions/${versionId}/agencies/${agencyId}`),
  },

  calendars: {
    list:   (versionId)                        => request('GET',    `/versions/${versionId}/calendars`),
    create: (versionId, data)                  => request('POST',   `/versions/${versionId}/calendars`, data),
    get:    (versionId, serviceId)             => request('GET',    `/versions/${versionId}/calendars/${serviceId}`),
    update: (versionId, serviceId, data)       => request('PUT',    `/versions/${versionId}/calendars/${serviceId}`, data),
    delete: (versionId, serviceId)             => request('DELETE', `/versions/${versionId}/calendars/${serviceId}`),
    listAssignments:  (versionId, serviceId)                    => request('GET',    `/versions/${versionId}/calendars/${serviceId}/aux-calendars`),
    assignAuxCalendar:(versionId, serviceId, data)              => request('POST',   `/versions/${versionId}/calendars/${serviceId}/aux-calendars`, data),
    removeAssignment: (versionId, serviceId, auxCalendarId)     => request('DELETE', `/versions/${versionId}/calendars/${serviceId}/aux-calendars/${auxCalendarId}`),
  },

  routes: {
    list:            (versionId)              => request('GET',    `/versions/${versionId}/routes`),
    create:          (versionId, data)        => request('POST',   `/versions/${versionId}/routes`, data),
    get:             (versionId, routeId)     => request('GET',    `/versions/${versionId}/routes/${routeId}`),
    update:          (versionId, routeId, data) => request('PUT',  `/versions/${versionId}/routes/${routeId}`, data),
    delete:          (versionId, routeId)     => request('DELETE', `/versions/${versionId}/routes/${routeId}`),
    agenciesLookup:  (versionId)             => request('GET',    `/versions/${versionId}/routes/agencies`),
  },

  schedule: {
    routes:    (versionId) => request('GET', `/versions/${versionId}/schedule/routes`),
    platforms: (versionId) => request('GET', `/versions/${versionId}/schedule/platforms`),
    dayTypes:  (versionId) => request('GET', `/versions/${versionId}/schedule/day-types`),
    band: {
      get:    (versionId, routeId, direction)                => request('GET',    `/versions/${versionId}/schedule/${routeId}/band/${direction}`),
      add:    (versionId, routeId, direction, data)          => request('POST',   `/versions/${versionId}/schedule/${routeId}/band/${direction}`, data),
      reorder:(versionId, routeId, direction, entryId, data) => request('PUT',    `/versions/${versionId}/schedule/${routeId}/band/${direction}/${entryId}`, data),
      remove: (versionId, routeId, direction, entryId)       => request('DELETE', `/versions/${versionId}/schedule/${routeId}/band/${direction}/${entryId}`),
    },
    trips: {
      list:   (versionId, routeId, direction)        => request('GET',    `/versions/${versionId}/schedule/${routeId}/trips?direction=${direction}`),
      get:    (versionId, routeId, tripId)            => request('GET',    `/versions/${versionId}/schedule/${routeId}/trips/${encodeURIComponent(tripId)}`),
      create: (versionId, routeId, data)             => request('POST',   `/versions/${versionId}/schedule/${routeId}/trips`, data),
      update: (versionId, routeId, tripId, data)     => request('PUT',    `/versions/${versionId}/schedule/${routeId}/trips/${encodeURIComponent(tripId)}`, data),
      delete: (versionId, routeId, tripId)           => request('DELETE', `/versions/${versionId}/schedule/${routeId}/trips/${encodeURIComponent(tripId)}`),
      batchDelete: (versionId, routeId, tripIds) => request('POST', `/versions/${versionId}/schedule/${routeId}/trips/batch-delete`, { trip_ids: tripIds }),
      batchShift:  (versionId, routeId, tripIds, offsetMinutes, direction) => request('POST', `/versions/${versionId}/schedule/${routeId}/trips/batch-shift`, { trip_ids: tripIds, offset_minutes: offsetMinutes, direction }),
      batchCopy:   (versionId, routeId, body) => request('POST', `/versions/${versionId}/schedule/${routeId}/trips/batch-copy`, body),
    },
    stopTimes: {
      list:   (versionId, routeId, tripId)                        => request('GET',    `/versions/${versionId}/schedule/${routeId}/trips/${encodeURIComponent(tripId)}/stop-times`),
      upsert: (versionId, routeId, tripId, routeBandStopId, data) => request('PUT',    `/versions/${versionId}/schedule/${routeId}/trips/${encodeURIComponent(tripId)}/stop-times/${routeBandStopId}`, data),
      delete: (versionId, routeId, tripId, routeBandStopId)       => request('DELETE', `/versions/${versionId}/schedule/${routeId}/trips/${encodeURIComponent(tripId)}/stop-times/${routeBandStopId}`),
    },
    shapes: {
      search: (versionId, query = '', limit = 50) => request(
        'GET',
        `/versions/${versionId}/schedule/shapes?q=${encodeURIComponent(query)}&limit=${encodeURIComponent(limit)}`,
      ),
      get:    (versionId, shapeId)       => request('GET',    `/versions/${versionId}/schedule/shapes/${encodeURIComponent(shapeId)}`),
      create: (versionId, data)          => request('POST',   `/versions/${versionId}/schedule/shapes`, data),
      update: (versionId, shapeId, data) => request('PUT',    `/versions/${versionId}/schedule/shapes/${encodeURIComponent(shapeId)}`, data),
      delete: (versionId, shapeId)       => request('DELETE', `/versions/${versionId}/schedule/shapes/${encodeURIComponent(shapeId)}`),
    },
  },

  stops: {
    list:               (versionId)                              => request('GET',    `/versions/${versionId}/stops`),
    listAllPlatforms:   (versionId)                              => request('GET',    `/versions/${versionId}/stops/all-platforms`),
    create:             (versionId, data)                        => request('POST',   `/versions/${versionId}/stops`, data),
    get:                (versionId, stopId)                      => request('GET',    `/versions/${versionId}/stops/${stopId}`),
    update:             (versionId, stopId, data)                => request('PUT',    `/versions/${versionId}/stops/${stopId}`, data),
    delete:             (versionId, stopId)                      => request('DELETE', `/versions/${versionId}/stops/${stopId}`),
    listPlatforms:      (versionId, stopId)                      => request('GET',    `/versions/${versionId}/stops/${stopId}/platforms`),
    createPlatform:     (versionId, stopId, data)                => request('POST',   `/versions/${versionId}/stops/${stopId}/platforms`, data),
    getPlatform:        (versionId, stopId, platformId)          => request('GET',    `/versions/${versionId}/stops/${stopId}/platforms/${platformId}`),
    updatePlatform:     (versionId, stopId, platformId, data)    => request('PUT',    `/versions/${versionId}/stops/${stopId}/platforms/${platformId}`, data),
    deletePlatform:     (versionId, stopId, platformId)          => request('DELETE', `/versions/${versionId}/stops/${stopId}/platforms/${platformId}`),
  },

  auxCalendars: {
    list:       (versionId)                        => request('GET',    `/versions/${versionId}/aux-calendars`),
    create:     (versionId, data)                  => request('POST',   `/versions/${versionId}/aux-calendars`, data),
    get:        (versionId, auxCalendarId)         => request('GET',    `/versions/${versionId}/aux-calendars/${auxCalendarId}`),
    update:     (versionId, auxCalendarId, data)   => request('PUT',    `/versions/${versionId}/aux-calendars/${auxCalendarId}`, data),
    delete:     (versionId, auxCalendarId)         => request('DELETE', `/versions/${versionId}/aux-calendars/${auxCalendarId}`),
    listDates:  (versionId, auxCalendarId)         => request('GET',    `/versions/${versionId}/aux-calendars/${auxCalendarId}/dates`),
    addDates:   (versionId, auxCalendarId, data)   => request('POST',   `/versions/${versionId}/aux-calendars/${auxCalendarId}/dates`, data),
    deleteDate: (versionId, auxCalendarId, date)   => request('DELETE', `/versions/${versionId}/aux-calendars/${auxCalendarId}/dates/${date}`),
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
