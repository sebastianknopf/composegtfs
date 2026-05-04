# Create View Prompt

Erstelle eine neue Ansicht für dieses Projekt und halte dich strikt an diese Vorgaben.

## Projektkontext
- Frontend: Vue 3 mit `<script setup>`, keine Options API
- UI-Komponenten: `@material/web` (MD3)
- I18n: `vue-i18n` (Composition API, `const { t } = useI18n()`)
- Berechtigungen: `usePermissions()` aus `@/composables/usePermissions.js`
- Routing: Vue Router, Routen in `frontend/src/router/index.js`
- API-Client: `api` aus `@/api/client.js`

## Pflichtfragen vor der Implementierung

Frage folgendes ab, bevor du anfängst:

1. **Name der Ansicht** — z. B. `StopsView`, Dateiname `StopsView.vue`
2. **Bereich (Section)** — in welchem TopBar-Bereich liegt die Ansicht? (`masterdata`, `network`, `schedule`)
3. **Permission** — welche Permission braucht der User, um die Ansicht sehen zu dürfen?
   - Vorhandene Permissions siehe `backend/src/app/permissions.py`
   - Falls keine passende existiert: vor Implementierung nachfragen
4. **Sub-Perspektiven?** — Hat die Ansicht mehrere Tabs (ähnlich wie Accounts → Accounts/Gruppen)?
   - Falls ja: wie heißen die Perspektiven, welche Spalten/Daten haben sie jeweils?
5. **Tabellenspalten** — Welche Felder sollen in der Haupttabelle erscheinen?
6. **CRUD-Operationen** — Welche Aktionen braucht die Ansicht? (Erstellen, Bearbeiten, Löschen)

## Dateistruktur

- Neue Ansichtsdatei: `frontend/src/views/{Name}View.vue`
- Route eintragen in: `frontend/src/router/index.js`
- Ansicht als `views`-Eintrag in `AppView.vue` bei der passenden Section registrieren — mit `permission`-Feld
- Neue I18n-Schlüssel in `frontend/src/locales/de.js` und `en.js`

## Ansicht in AppView registrieren

Jede Ansicht wird in `frontend/src/views/AppView.vue` im `sections`-Array eingetragen:

```js
{ id: 'stops', labelKey: 'views.stops', icon: 'location_on', position: 'top', permission: 'network:read' }
```

Das `permission`-Feld steuert, ob der Sidebar-Eintrag angezeigt wird. Ist es nicht gesetzt, ist der Eintrag für alle sichtbar. Wird ein `permission`-Feld gesetzt, taucht der Eintrag nur auf, wenn der User das Recht hat.

Die Route erhält dasselbe Permission-Feld als `meta.permission`:

```js
{
  path: 'stops',
  name: 'stops',
  component: StopsView,
  meta: { section: 'network', permission: 'network:read' },
}
```

## Grundstruktur einer Ansicht

```vue
<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client.js'
import { usePermissions } from '@/composables/usePermissions.js'
import DataTable from '@/components/DataTable.vue'
import '@material/web/icon/icon.js'
import '@material/web/button/filled-button.js'

const { t } = useI18n()
const { has } = usePermissions()

// Berechtigungen für Actions
const canWrite  = has('resource:write')
const canDelete = has('resource:delete')

// Daten
const items   = ref([])
const loading = ref(false)

const columns = [
  { key: 'name',  label: () => t('resource.name') },
  { key: 'field', label: () => t('resource.field') },
]

async function loadItems() {
  loading.value = true
  try {
    items.value = await api.resource.list()
  } finally {
    loading.value = false
  }
}

onMounted(loadItems)
</script>

<template>
  <div class="resource-view">

    <header class="view-header">
      <md-icon class="view-header__icon">icon_name</md-icon>
      <h1 class="view-header__title">{{ t('views.resource') }}</h1>
      <div class="view-header__actions">
        <md-filled-button v-if="canWrite" @click="openCreate">
          <md-icon slot="icon">add</md-icon>
          {{ t('resource.add') }}
        </md-filled-button>
      </div>
    </header>

    <DataTable
      :columns="columns"
      :rows="items"
      :loading="loading"
      :empty="t('resource.no_items')"
      :pagination="{ pageSize: 25 }"
    >
      <template #actions="{ row }">
        <button v-if="canWrite"  class="table-action-btn" :title="t('common.edit')"   @click="openEdit(row)">
          <md-icon>edit</md-icon>
        </button>
        <button v-if="canDelete" class="table-action-btn table-action-btn--danger" :title="t('common.delete')" @click="requestDelete(row)">
          <md-icon>delete</md-icon>
        </button>
      </template>
    </DataTable>

  </div>
</template>

<style scoped>
.resource-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  height: 100%;
}
</style>
```

## Grundstruktur mit Sub-Perspektiven

Wenn die Ansicht mehrere Tabs hat, wird ein Tab-Control analog zur `AccountsView` verwendet:

```vue
<script setup>
const PERSPECTIVES = ['items', 'subitems']
const activePerspective = ref('items')

const itemColumns    = [ /* Spalten für Perspektive 1 */ ]
const subitemColumns = [ /* Spalten für Perspektive 2 */ ]
</script>

<template>
  <!-- Perspective tabs -->
  <div class="perspective-tabs" role="tablist">
    <button
      v-for="p in PERSPECTIVES"
      :key="p"
      role="tab"
      :aria-selected="activePerspective === p"
      :class="['perspective-tab', { 'perspective-tab--active': activePerspective === p }]"
      @click="activePerspective = p"
    >
      <md-icon class="perspective-tab__icon">{{ p === 'items' ? 'list' : 'category' }}</md-icon>
      {{ t(`resource.tab_${p}`) }}
    </button>
  </div>

  <DataTable v-if="activePerspective === 'items'"    ... />
  <DataTable v-if="activePerspective === 'subitems'" ... />
</template>
```

## Berechtigungen für UI-Controls

**Wichtig:** Buttons und andere schreibende/löschende Controls dürfen nur angezeigt werden, wenn der User die entsprechende Permission hat. Dazu immer `usePermissions()` verwenden:

```js
const { has } = usePermissions()
const canWrite  = has('resource:write')
const canDelete = has('resource:delete')
```

Im Template:
```html
<md-filled-button v-if="canWrite" ...>Anlegen</md-filled-button>
<button v-if="canWrite"  class="table-action-btn" ...>edit</button>
<button v-if="canDelete" class="table-action-btn table-action-btn--danger" ...>delete</button>
```

Superuser sehen immer alle Controls — das ergibt sich automatisch aus `permissionsStore`, der für Superuser alle Codenames enthält.

## DataTable — Vollständige API

Die `DataTable`-Komponente (`@/components/DataTable.vue`) ist die einzige zu verwendende Tabellenkomponente.

### Spalten (`columns`)
```js
const columns = [
  { key: 'name',   label: () => t('resource.name'), sortable: true },
  { key: 'status', label: () => t('resource.status'), align: 'center', width: '120px' },
]
```
- `label` kann ein String oder eine Getter-Funktion `() => t('...')` sein — die Komponente löst sie intern auf, kein `resolvedColumns()`-Helper nötig.
- `sortable: true` aktiviert die Sortierung für diese Spalte.
- `align`: `'left'` (Standard) | `'center'` | `'right'`
- `width`: optional, z. B. `'140px'`

### Pagination
```html
<!-- Client-seitig (Tabelle paginiert selbst) -->
<DataTable :columns="columns" :rows="items" :pagination="{ pageSize: 25 }" />

<!-- Server-seitig (Backend liefert Seiten, Parent steuert) -->
<DataTable
  :columns="columns"
  :rows="items"
  :pagination="{ page: currentPage, pageSize: pageSize, total: totalCount }"
  @page-change="({ page, pageSize }) => { currentPage = page; loadData() }"
/>
```
- Ohne `pagination`-Prop: keine Pagination, alle Zeilen werden angezeigt.
- `total` fehlt → client-seitig (Tabelle teilt `rows` selbst auf)
- `total` vorhanden → server-seitig (Tabelle gibt nur Steuerelemente aus, emittet `page-change`)

### Sortierung
```html
<!-- Client-seitig (Standard) -->
<DataTable :columns="columns" :rows="items" />

<!-- Server-seitig -->
<DataTable
  :columns="columns"
  :rows="items"
  sort-mode="server"
  @sort-change="({ key, direction }) => { sortKey = key; sortDir = direction; loadData() }"
/>
```
- `sortMode="client"` (Standard): Tabelle sortiert `rows` intern.
- `sortMode="server"`: Tabelle emittet `sort-change` und erwartet, dass der Parent neue Daten liefert.
- Sortierbare Spalten erhalten `sortable: true` im Columns-Array.

### Slots
```html
<!-- Benutzerdefinierter Zelleninhalt -->
<template #cell-status="{ value, row }">
  <span class="badge">{{ value }}</span>
</template>

<!-- Aktions-Spalte -->
<template #actions="{ row }">
  <button v-if="canWrite"  class="table-action-btn" @click="openEdit(row)"><md-icon>edit</md-icon></button>
  <button v-if="canDelete" class="table-action-btn table-action-btn--danger" @click="requestDelete(row)"><md-icon>delete</md-icon></button>
</template>
```

## Berechtigungen für UI-Controls

Jede neue Ansicht braucht mindestens:
- `views.{name}` — Label in Sidebar und TopBar
- `{resource}.add` — Label des "Anlegen"-Buttons
- `{resource}.no_items` — Leertext der Tabelle
- Spaltenbezeichnungen für alle definierten `columns`
- Validierungsfehlermeldungen (falls Modal vorhanden)

Alle Schlüssel müssen in **beiden** Locale-Dateien angelegt werden:
- `frontend/src/locales/de.js`
- `frontend/src/locales/en.js`

## Styling-Konventionen
- Globale Stile in `frontend/src/assets/layout.css` — insbesondere `.view-header`, `.perspective-tab`, `.table-action-btn` sind bereits global definiert und dürfen direkt verwendet werden.
- Komponentenspezifische Stile im `<style scoped>` Block der Ansicht.
- `border-radius` maximal `6px` (außer `50%`).
- Keine Inline-Styles verwenden.
