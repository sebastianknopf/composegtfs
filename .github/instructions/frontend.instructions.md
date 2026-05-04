---
description: "Frontend development instructions for Vue 3 application. Use when: modifying Vue components, views, router, stores, API client, styles, or frontend configuration."
applyTo:
  - "frontend/**/*.vue"
  - "frontend/**/*.js"
  - "frontend/**/*.ts"
  - "frontend/index.html"
  - "frontend/vite.config.js"
  - "frontend/package.json"
---

# Frontend Development Instructions

## Technology Stack

- **Vue 3** – Composition API (`<script setup>`) is the required style
- **Vue Router** – client-side routing
- **vue-i18n** – internationalization
- **@material/web** – Google's official Material Design 3 web components (MD3)
- **Open Props** – CSS design token library (spacing, shadows, typography, animations) by Adam Argyle (ex-Google)
- **Vite** – build tool
- **No additional UI frameworks** (no Vuetify, Quasar, PrimeVue, etc.) without explicit approval
- **No CSS frameworks** (no Tailwind, Bootstrap, Pico CSS, etc.) without explicit approval
- **Mapping**: if map rendering is required, use **MapLibre GL JS** (`maplibre-gl`). Any additional MapLibre plugins or related packages still require explicit approval.

## Dependency Management

- **Explicit approval required** before adding new packages to `package.json`
- When suggesting new dependencies, explain why no existing dependency covers the need
- Prefer native browser APIs and Vue built-ins over external libraries

## Component Authoring

### General Rules
- Use `<script setup>` syntax for all components – no Options API
- Keep components focused: one responsibility per component
- Extract reusable logic into composables (`use*.js` in `src/composables/`)
- Props must have explicit types; use `defineProps` with type declarations
- Emit events with `defineEmits`; name events in kebab-case

### Structure Order in SFCs
```vue
<script setup>
// imports, props, emits, composables, state, computed, methods, lifecycle
</script>

<template>
  <!-- markup -->
</template>

<style scoped>
/* component-local overrides only – see Styling section */
</style>
```

### Component Naming
- Component files: PascalCase (`UserCard.vue`)
- In templates: PascalCase for custom components (`<UserCard />`)
- Views (routed pages): suffix `View` (`HomeView.vue`, `ItemsView.vue`)

## Styling

### Approach
Styling is token-based, class-light, and framework-free. It follows a three-layer model:

1. **MD3 design tokens** (`--md-sys-color-*`, `--md-ref-typeface-*`) – theming and interactive component appearance. Always prefer MD3 tokens over custom values for anything an MD3 component consumes.
2. **Open Props tokens** (`--shadow-*`, `--size-*`, `--radius-*`, `--font-size-*`, `--ease-*`, etc.) – structural design primitives for layout, spacing, typography scale, shadows, and animation. Use these instead of hard-coding raw values.
3. **Custom layout CSS** (`src/assets/layout.css`) – structural layout rules and project-specific custom properties (prefixed `--mk-*` to avoid collisions). Only add custom properties here when neither MD3 nor Open Props provides what's needed.

Open Props ships as CSS custom properties only – no HTML classes, no JavaScript, no conflict with MD3 web components (which use Shadow DOM).

### Rules
- **Never add inline styles for layout or theming** – use CSS classes or tokens
- Inline styles are acceptable only for truly one-off values (e.g., `max-width` on a single element) where creating a class would be overkill
- Component-scoped `<style scoped>` blocks are for component-local structural tweaks only, not for overriding global theme or layout
- Do not introduce utility-class frameworks (Tailwind, Bootstrap, etc.) without explicit approval
- Responsive design is achieved with CSS custom properties, `clamp()`, Open Props fluid sizes, flexbox, and grid – no breakpoint framework required
- When a design value is needed (shadow, spacing, radius, easing), check Open Props first before writing a custom value

### MD3 Tokens
- Theme colors are set via `--md-sys-color-*` tokens on `:root`
- Typography typefaces are set via `--md-ref-typeface-brand` and `--md-ref-typeface-plain`
- Use MD3 component variants as intended (e.g., `md-filled-button` for primary actions, `md-text-button` for low-emphasis actions)

### Open Props Tokens
Use Open Props variables for structural primitives instead of hard-coded values:
```css
/* correct */
box-shadow: var(--shadow-2);
border-radius: var(--radius-2);
gap: var(--size-4);
font-size: var(--font-size-fluid-1);
animation-timing-function: var(--ease-3);

/* wrong */
box-shadow: 0 4px 6px -1px rgba(0,0,0,.1);
border-radius: 1rem;
```

### Custom Layout Tokens
Project-specific tokens (prefixed `--mk-*`) in `src/assets/layout.css` are used only for values not covered by MD3 or Open Props. Consume them via variables, never duplicate them inline.

## Using MD3 Components

- Import `@material/web` components at the entry point (`main.js`) or in the relevant component – never duplicate imports
- Use the appropriate component for the semantic intent (buttons, text fields, dialogs, icons, etc.)
- Icon names come from the `@material-symbols/font-400` icon font; use `<md-icon>` to render them
- Do not wrap MD3 components in unnecessary container components just to rename them

## Frontend vs. Backend Responsibility

- **The frontend is UI only.** Its sole responsibility is rendering data and capturing user input.
- **All business logic, calculations, data transformations, and aggregations must run on the backend.** If a computation is not purely presentational (e.g., formatting a date for display), it belongs in the backend.
- Do not replicate backend logic in the frontend. If you need a derived value that isn't returned by the API, extend the API – do not compute it client-side.
- Validation in the frontend is for immediate user feedback only (e.g., required field hints). Authoritative validation always runs on the backend.

## Routing

- All routes are defined in `src/router/index.js`
- Protected routes require authentication; use a navigation guard to enforce this
- Public routes (e.g., login) must be explicitly marked (e.g., `meta: { public: true }`)
- Lazy-load route components with dynamic `import()` to keep the initial bundle small

## State Management

- Use Vue's built-in reactivity (`reactive`, `ref`) for shared state – no external state management library is required
- Shared state is implemented as plain reactive singletons exported from `src/stores/` modules
- Do not put UI state (loading spinners, open dialogs) in shared stores unless it needs to be shared across multiple components; keep it local with `ref`/`reactive`
- Do not introduce Pinia or Vuex without explicit approval

## API Communication

- All HTTP calls go through a central API client (`src/api/client.js`)
- Never call `axios` or `fetch` directly from a component or store – always use the client module
- The client handles base URL, auth headers, and error normalization centrally
- API functions are grouped by domain (e.g., `src/api/items.js`, `src/api/auth.js`)

## Internationalization (i18n)

- All user-facing strings must be externalized into locale files (`src/locales/`)
- Never hard-code display text in components – always use `$t('key')` or `t('key')`
- Locale files are the only place where non-English natural language is permitted
- Add keys to all locale files simultaneously to avoid missing translations

## Code Style

### Language
- All code (variable names, function names, comments) must be written in **English**
- Non-English natural language is only allowed in locale files

### Conventions
- Use `const` by default; `let` only when reassignment is necessary
- Prefer `async/await` over `.then()` chains
- Use destructuring for props and object access where it improves readability
- Keep template expressions simple – move complex logic to computed properties or methods

## Before Committing

- Ensure all new user-facing strings have entries in every locale file
- Check that no new dependencies were added without approval
