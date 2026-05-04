<script setup>
/**
 * DataTable — generic MD3-aligned data table component.
 *
 * Props:
 *   columns    — Array<{ key, label (string|fn), width?, align?, sortable? }>
 *                label can be a plain string or a reactive getter: () => t('key')
 *   rows       — Array<Record<string, any>>
 *   rowKey     — field used as row :key (default 'id')
 *   loading    — show loading skeleton
 *   empty      — override for the empty-state message (falls back to t('table.empty'))
 *   pagination — null (disabled)
 *              | { pageSize, total? }
 *                  total present → server-side: emits page-change, parent fetches each page
 *                                  also provide `page` (current 1-based page number)
 *                  total absent  → client-side: component paginates rows internally
 *   sortMode   — 'client' (default) | 'server'
 *                'client': sorts rows locally; 'server': emits sort-change, parent refetches
 *
 * Emits:
 *   page-change  { page, pageSize }   — user requested a different page or page size
 *   sort-change  { key, direction }   — server-side sort: key=null & direction=null means unsorted
 *
 * Slots:
 *   cell-{key}   — custom cell renderer: <template #cell-name="{ value, row }">
 *   actions      — action buttons appended as last column: <template #actions="{ row }">
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/icon/icon.js'

const { t } = useI18n()

const props = defineProps({
  columns: {
    type: Array,
    required: true,
  },
  rows: {
    type: Array,
    default: () => [],
  },
  rowKey: {
    type: String,
    default: 'id',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  empty: {
    type: String,
    default: null,
  },
  pagination: {
    type: Object,
    default: null,
  },
  sortMode: {
    type: String,
    default: 'client',
  },
})

const emit = defineEmits(['page-change', 'sort-change'])

const slots = defineSlots()
const hasActions = computed(() => !!slots.actions)

// ---- Column resolution ----
// label can be a plain string or a reactive getter function () => t('key')
const resolvedColumns = computed(() =>
  props.columns.map(c => ({ ...c, label: typeof c.label === 'function' ? c.label() : c.label }))
)

// ---- Sorting ----
const sortKey = ref(null)
const sortDir = ref(null) // 'asc' | 'desc' | null

function toggleSort(col) {
  if (!col.sortable) return
  const same = sortKey.value === col.key
  const next = same
    ? (sortDir.value === 'asc' ? 'desc' : sortDir.value === 'desc' ? null : 'asc')
    : 'asc'
  sortKey.value = next ? col.key : null
  sortDir.value = next
  if (props.sortMode === 'server') {
    emit('sort-change', { key: sortKey.value, direction: sortDir.value })
  }
}

const sortedRows = computed(() => {
  if (props.sortMode === 'server' || !sortKey.value || !sortDir.value) return props.rows
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...props.rows].sort((a, b) => {
    const av = a[key] ?? ''
    const bv = b[key] ?? ''
    if (typeof av === 'string') return av.localeCompare(bv, undefined, { sensitivity: 'base' }) * dir
    return (av < bv ? -1 : av > bv ? 1 : 0) * dir
  })
})

// ---- Pagination ----
const hasPagination  = computed(() => props.pagination != null)
const isServerSide   = computed(() => hasPagination.value && props.pagination.total !== undefined)

// Internal page for client-side mode
const clientPage = ref(1)

// Reset to page 1 when the row data changes (client-side only)
watch(() => props.rows, () => {
  if (!isServerSide.value) clientPage.value = 1
}, { deep: false })

const currentPage = computed(() =>
  isServerSide.value ? (props.pagination.page ?? 1) : clientPage.value
)
const pageSize = computed(() => props.pagination?.pageSize ?? 25)

const totalRows = computed(() => {
  if (!hasPagination.value) return props.rows.length
  if (isServerSide.value)   return props.pagination.total
  return sortedRows.value.length
})

const totalPages = computed(() => Math.max(1, Math.ceil(totalRows.value / pageSize.value)))

const displayedRows = computed(() => {
  if (!hasPagination.value || isServerSide.value) return sortedRows.value
  const start = (currentPage.value - 1) * pageSize.value
  return sortedRows.value.slice(start, start + pageSize.value)
})

const rangeStart = computed(() =>
  totalRows.value === 0 ? 0 : (currentPage.value - 1) * pageSize.value + 1
)
const rangeEnd = computed(() => Math.min(currentPage.value * pageSize.value, totalRows.value))

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

function goToPage(page) {
  if (page < 1 || page > totalPages.value || page === currentPage.value) return
  if (isServerSide.value) {
    emit('page-change', { page, pageSize: pageSize.value })
  } else {
    clientPage.value = page
  }
}

function onPageSizeChange(event) {
  const newSize = Number(event.target.value)
  clientPage.value = 1
  emit('page-change', { page: 1, pageSize: newSize })
}

const displayEmpty = computed(() => props.empty ?? t('table.empty'))
</script>

<template>
  <div class="data-table-wrapper" role="region">
    <table class="data-table" :aria-busy="loading">
      <thead class="data-table__head">
        <tr>
          <th
            v-for="col in resolvedColumns"
            :key="col.key"
            class="data-table__th"
            :class="[
              `data-table__th--${col.align ?? 'left'}`,
              { 'data-table__th--sortable': col.sortable },
            ]"
            :style="col.width ? { width: col.width } : {}"
            scope="col"
            :aria-sort="col.sortable
              ? (sortKey === col.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none')
              : undefined"
            @click="toggleSort(col)"
          >
            <span class="data-table__th-inner">
              {{ col.label }}
              <md-icon
                v-if="col.sortable"
                class="data-table__sort-icon"
                :class="{ 'data-table__sort-icon--active': sortKey === col.key }"
                :aria-hidden="true"
              >
                {{ sortKey === col.key ? (sortDir === 'asc' ? 'arrow_upward' : 'arrow_downward') : 'unfold_more' }}
              </md-icon>
            </span>
          </th>
          <th v-if="hasActions" class="data-table__th data-table__th--actions" scope="col" />
        </tr>
      </thead>

      <tbody class="data-table__body">
        <!-- Loading skeleton -->
        <template v-if="loading">
          <tr v-for="n in 4" :key="n" class="data-table__row data-table__row--skeleton">
            <td v-for="col in resolvedColumns" :key="col.key" class="data-table__td">
              <span class="data-table__skeleton" />
            </td>
            <td v-if="hasActions" class="data-table__td data-table__td--actions">
              <span class="data-table__skeleton data-table__skeleton--icon" />
              <span class="data-table__skeleton data-table__skeleton--icon" />
            </td>
          </tr>
        </template>

        <!-- Empty state -->
        <tr v-else-if="displayedRows.length === 0" class="data-table__row data-table__row--empty">
          <td
            :colspan="resolvedColumns.length + (hasActions ? 1 : 0)"
            class="data-table__td data-table__td--empty"
          >
            {{ displayEmpty }}
          </td>
        </tr>

        <!-- Data rows -->
        <template v-else>
          <tr
            v-for="row in displayedRows"
            :key="row[rowKey]"
            class="data-table__row"
          >
            <td
              v-for="col in resolvedColumns"
              :key="col.key"
              class="data-table__td"
              :class="`data-table__td--${col.align ?? 'left'}`"
            >
              <slot :name="`cell-${col.key}`" :value="row[col.key]" :row="row">
                {{ row[col.key] ?? '—' }}
              </slot>
            </td>
            <td v-if="hasActions" class="data-table__td data-table__td--actions">
              <slot name="actions" :row="row" />
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <!-- Pagination footer -->
    <div v-if="hasPagination && !loading" class="data-table-footer">
      <div class="data-table-footer__page-size">
        <span class="data-table-footer__label">{{ t('table.pagination.rows_per_page') }}</span>
        <select
          class="data-table-footer__select"
          :value="pageSize"
          :aria-label="t('table.pagination.rows_per_page')"
          @change="onPageSizeChange"
        >
          <option v-for="opt in PAGE_SIZE_OPTIONS" :key="opt" :value="opt">{{ opt }}</option>
        </select>
      </div>

      <span class="data-table-footer__range">
        {{ t('table.pagination.range_of', { start: rangeStart, end: rangeEnd, total: totalRows }) }}
      </span>

      <div class="data-table-footer__nav" role="group" :aria-label="t('table.pagination.navigation')">
        <button
          class="data-table-footer__nav-btn"
          :disabled="currentPage <= 1"
          :aria-label="t('table.pagination.previous')"
          @click="goToPage(currentPage - 1)"
        >
          <md-icon>chevron_left</md-icon>
        </button>
        <button
          class="data-table-footer__nav-btn"
          :disabled="currentPage >= totalPages"
          :aria-label="t('table.pagination.next')"
          @click="goToPage(currentPage + 1)"
        >
          <md-icon>chevron_right</md-icon>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.data-table-wrapper {
  width: 100%;
  overflow-x: auto;
  border: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  border-radius: 6px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-1, 0.875rem);
  font-family: inherit;
  color: var(--md-sys-color-on-surface, #222);
}

/* Head */
.data-table__head {
  background: var(--md-sys-color-surface-container, #f0f0f0);
}

.data-table__th {
  padding: 0 1rem;
  height: 56px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  white-space: nowrap;
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
}

.data-table__th--left   { text-align: left; }
.data-table__th--center { text-align: center; }
.data-table__th--right  { text-align: right; }
.data-table__th--actions { width: 1px; /* shrink-wrap */ }

.data-table__th--sortable {
  cursor: pointer;
  user-select: none;
}
.data-table__th--sortable:hover {
  background: var(--md-sys-color-surface-container-highest, #e4e4e4);
}

.data-table__th-inner {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.data-table__sort-icon {
  --md-icon-size: 1rem;
  font-size: 1rem;
  opacity: 0.35;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}
.data-table__sort-icon--active {
  opacity: 1;
  color: var(--md-sys-color-primary, #1f69e0);
}

/* Body rows */
.data-table__row {
  transition: background 0.1s ease;
}

.data-table__row:not(.data-table__row--skeleton):not(.data-table__row--empty):hover {
  background: var(--md-sys-color-surface-container-low, #f8f8f8);
}

.data-table__row:not(:last-child) .data-table__td {
  border-bottom: 1px solid var(--md-sys-color-outline-variant, #e8e8e8);
}

.data-table__td {
  padding: 0 1rem;
  height: 52px;
  vertical-align: middle;
}

.data-table__td--left   { text-align: left; }
.data-table__td--center { text-align: center; }
.data-table__td--right  { text-align: right; }

.data-table__td--actions {
  white-space: nowrap;
  padding-right: 0.5rem;
}

.data-table__td--empty {
  text-align: center;
  color: var(--md-sys-color-outline, #74777f);
  font-style: italic;
  padding: 3rem 1rem;
}

/* Skeleton */
@keyframes shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}

.data-table__skeleton {
  display: inline-block;
  width: 60%;
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
  background-size: 800px 100%;
  animation: shimmer 1.4s infinite linear;
}

.data-table__skeleton--icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  margin-left: 0.25rem;
}

/* Action buttons inside cells */
.data-table-wrapper :deep(.table-action-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: none;
  border-radius: 50%;
  cursor: pointer;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  transition: background 0.15s ease, color 0.15s ease;
}

.data-table-wrapper :deep(.table-action-btn:hover) {
  background: rgba(0, 0, 0, 0.08);
}

.data-table-wrapper :deep(.table-action-btn--danger:hover) {
  background: rgba(176, 0, 32, 0.08);
  color: var(--md-sys-color-error, #b00020);
}

/* Pagination footer */
.data-table-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1.5rem;
  padding: 0 0.25rem 0 1rem;
  height: 52px;
  border-top: 1px solid var(--md-sys-color-outline-variant, #e0e0e0);
  font-size: 0.8rem;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  flex-shrink: 0;
}

.data-table-footer__page-size {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.data-table-footer__label {
  white-space: nowrap;
}

.data-table-footer__select {
  appearance: none;
  border: none;
  background: none;
  font-size: 0.8rem;
  font-family: inherit;
  color: inherit;
  cursor: pointer;
  padding: 0.2rem 0.25rem;
  border-radius: 4px;
  font-weight: 500;
}
.data-table-footer__select:hover {
  background: rgba(0, 0, 0, 0.06);
}
.data-table-footer__select:focus {
  outline: 2px solid var(--md-sys-color-primary, #1f69e0);
  outline-offset: 1px;
}

.data-table-footer__range {
  white-space: nowrap;
  min-width: 6rem;
  text-align: right;
}

.data-table-footer__nav {
  display: flex;
  gap: 0;
}

.data-table-footer__nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: none;
  border-radius: 50%;
  cursor: pointer;
  color: var(--md-sys-color-on-surface-variant, #5c5f6a);
  transition: background 0.15s ease;
}
.data-table-footer__nav-btn:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.08);
}
.data-table-footer__nav-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}
</style>
