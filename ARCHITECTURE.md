# ARCHITECTURE.md — GitLab Sprint Dashboard

This file is the technical specification. When in doubt about how to build something, this
file decides. Project intent and product framing lives in `PROJECT.md`.

---

## Layers

The frontend follows a strict four-layer architecture. Dependencies flow **downward only**. A lower layer never imports from a higher layer.

| Layer | Location | Purpose | Rules |
|-------|----------|---------|-------|
| **Design System** | `public/css/tokens.css` | CSS custom properties — all colors, radii, focus rings | No hardcoded values in `styles.css` or JS. All visual constants live here. |
| **Core** | `public/js/core/` | Pure business logic — calculations, parsing, utilities, holidays, report/document builders | No DOM access. No `fetch()`. No side effects. Testable without a browser. **Exception:** `utils.js` exports thin DOM helpers (`$`, `getParams`) shared by all UI modules and a DOM-based file download trigger (`downloadDoc`). These are the only permitted DOM touches in Core. |
| **Services** | `public/js/services/api.js` | Data fetching and path resolution | No DOM manipulation. No rendering. Stateless functions. |
| **UI** | `public/js/*.js` (page modules + shared controllers) | DOM rendering, event handlers, page-scoped state | Imports from Core + Services (and, for a shared controller, from another UI module). One page module per page. UI logic shared by multiple pages lives in a **shared controller** module (e.g. `dashboard.js`, mounted + rendered by `group.js` and `home.js`). |

### Import Direction

```
UI page modules (js/home.js, js/group.js, js/milestone.js, js/releases.js)
     ↓ imports from                    ↘ imports from
Shared UI controller (js/dashboard.js)  → (same layer; downward-only otherwise)
     ↓ imports from
Services (js/services/api.js)
     ↓ imports from
   Core (js/core/utils.js, calculations.js, holidays.js, parsing.js, reports.js, dashboardShell.js)
     ↓ uses tokens from
Design System (css/tokens.css)
```

A shared controller sits in the UI layer and may be imported by page modules (same-layer import). The downward-only rule still holds: no UI module (page or controller) is imported by Services or Core.

**The single exception:** Chart.js is loaded as a classic `<script>` in `group.html` (sets `window.Chart`). It is vendored and not an ES module. All other JS files use native ES modules with relative paths and `.js` extensions.

---

## Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Vanilla JavaScript (ES modules), HTML5, CSS3 | No build step, no framework dependency, direct deployment as a static site |
| Charts | Chart.js v4.4.7 (vendored at `js/chart.min.js`) | Mature library; vendored to avoid a CDN dependency |
| Styling | CSS custom properties (`tokens.css` + `styles.css`) | Centralized design tokens with no preprocessor |
| Build | None | Static site; `public/` deploys directly as-is |
| Data | Static JSON in `public/data/`, maintained by hand | Interim data layer — see `README.md` for the planned SQLite/Supabase migration |
| Deployment | Netlify or Vercel | Static hosting with git-based deploys; either works since there's no server code |

---

## Project Structure

```
sprint-metrics-dashboard/
├── .gitlab-ci.yml               # CI: runs the test suite
├── .gitignore
├── ARCHITECTURE.md              # This file — technical specification
├── PROJECT.md                   # Project intent, audience, constraints
├── README.md                    # User-facing documentation
├── package.json                 # Vitest dev dependency; "type": "module"
├── package-lock.json
├── vitest.config.js             # Vitest config — scoped to public/js/core/**/*.test.js
├── netlify.toml                 # Netlify static deploy config
├── vercel.json                  # Vercel static deploy config
├── docs/
│   └── MULTI_GROUP_SUPPORT.md   # Multi-group feature design doc
└── public/                      # Static site root — deployed as-is
    ├── index.html               # Home page (group/project cards with filter)
    ├── group.html               # Sprint dashboard (?group={slug}&project={slug})
    ├── milestone.html           # Milestone detail page
    ├── releases.html            # Releases index page
    ├── css/
    │   ├── tokens.css           # [Design System] CSS custom properties
    │   └── styles.css           # [Design System] Imports tokens.css; all component styles
    ├── img/                     # Logos: favicon.svg, group and project logos
    ├── js/
    │   ├── core/                # [Core] Pure logic — no DOM, no fetch, no side effects
    │   │   ├── utils.js         # $(), esc(), slugify(), getParams(), formatText(), officeHtml(), downloadDoc()
    │   │   ├── holidays.js      # US federal holidays, isWorkingDay(), generateDateRange()
    │   │   ├── calculations.js  # calculateProgress(), burndown, velocity, type breakdown, filtering
    │   │   ├── parsing.js       # parseSection()
    │   │   ├── reports.js       # Word/Office-HTML doc builders, sprint/month predicates
    │   │   └── dashboardShell.js # Pure HTML-string builder for the shared dashboard markup
    │   ├── services/            # [Services] External data only
    │   │   └── api.js           # fetchJSON(), dataPath(), resolveGroupAndProject(), loadFY(), discoverFYs()
    │   ├── dashboard.js         # [UI] Shared sprint-dashboard controller — mountDashboard(), renderDashboard()
    │   ├── home.js              # [UI] Home page rendering and filter chips
    │   ├── group.js             # [UI] Group dashboard page — resolves URL, mounts + renders dashboard.js
    │   ├── milestone.js         # [UI] Milestone detail — issues, dialogs
    │   ├── releases.js          # [UI] Releases index — milestone list with expand/collapse
    │   └── chart.min.js         # Chart.js v4.4.7 (vendored, classic script — sets window.Chart)
    └── data/                    # Static JSON, hand-maintained
        ├── groups.json          # Group + project configuration (IDs, slugs, logos, mode)
        └── {group-slug}/
            ├── current-sprint.json     # Active sprint data or `null` sentinel
            ├── fy{YYYY}/
            │   └── {MM}-{mon}-{YYYY}.json   # All sprints ending in that month
            ├── {project-slug}/              # project-mode groups only
            │   ├── current-sprint.json
            │   ├── fy{YYYY}/
            │   └── reports/                 # Report content (rendered to Word client-side)
            │       ├── sprints/{milestone-slug}.json   # test plan + sprint report
            │       └── months/{YYYY-MM}.json           # monthly report
            └── milestones/
                ├── index.json               # All milestones sorted by due_date descending
                └── {project-slug}/
                    └── {milestone-slug}.json
```

---

## Naming Conventions

| File Type | Convention | Example |
|-----------|-----------|---------|
| JS source files | `camelCase.js` | `utils.js`, `calculations.js` |
| HTML pages | `lowercase.html` | `index.html`, `group.html` |
| CSS files | `lowercase.css` | `tokens.css`, `styles.css` |
| Data directories | `kebab-case` | `public/data/cloud-services/` |
| Data files | `{MM}-{mon}-{YYYY}.json` | `04-apr-2026.json` |
| CSS classes | Semantic, no utility prefix | `.group-card`, `.skip-link`, `.home-filter` |
| JS exports | `camelCase` functions; `UPPER_SNAKE` constants | `fetchJSON`, `EARLIEST_FY` |

---

## Styling

All CSS custom properties are declared in `public/css/tokens.css` on `:root`. `public/css/styles.css` imports `tokens.css` and contains all component styles.

**Rules:**
- New colors and spacing values go in `tokens.css` before `styles.css`. Never hardcode a **color** (hex, `rgb()`, `rgba()`) or a **spacing value** (`margin`, `padding`, `gap`) outside of `tokens.css` — spacing uses the `--space-*` scale.
- **Typography & radii (token scales exist; prefer them):** `font-size` uses the `--fs-*` scale, `font-weight` the `--fw-*` scale, `line-height` the `--lh-*` scale, and `border-radius` the `--radius` / `--radius-sm` / `--radius-pill` tokens. Use these tokens for new or changed styles. Raw `px` typography still present in `styles.css` is being migrated and is **not** flagged in the interim.
- **Not tokenized (raw `px` is allowed):** border widths (`1px`/`2px`), fixed layout dimensions (`max-width`, `width`/`height`, `minmax()`), positioning offsets (`top`/`left`), and media-query breakpoints. Two negative spacing offsets remain raw as documented idioms: the `.visually-hidden` `-1px` clip and the `.sprint-goal` `-8px` pull-up.
- Class names are semantic — they describe the component, not its visual appearance.
- No utility class frameworks (Tailwind, Bootstrap). No CSS modules. No CSS-in-JS.

**Documented exception — generated Word documents:** `js/core/reports.js` builds downloadable MS Word files via the Office-HTML approach. That HTML carries its own inline `<style>` block, rendered by Word in isolation from `tokens.css`, so CSS custom properties are unavailable there. Hardcoded values inside those Office-HTML strings (e.g. the `#999` table border) are the one permitted place for raw colors/spacing in JS.

Current design tokens:
- **Color:** `--purple`, `--purple-light`, `--purple-dark`, `--purple-faint`, `--purple-overlay`, `--purple-glow`, `--bg`, `--bg-hover`, `--card`, `--white`, `--text`, `--text-muted`, `--border`, `--green`, `--green-light`, `--red`, `--blue`, `--orange`, `--gray`, `--gray-light`, `--backdrop`
- **Radius / focus:** `--radius`, `--radius-sm`, `--radius-pill`, `--focus-ring`
- **Typography:** `--fs-2xs` … `--fs-5xl` (font-size scale), `--fw-normal`/`--fw-medium`/`--fw-semibold`/`--fw-bold` (weights), `--lh-tight`/`--lh-normal`/`--lh-relaxed` (line heights)
- **Spacing (4px base):** `--space-3xs` (2px), `--space-2xs` (4px), `--space-xs` (8px), `--space-sm` (12px), `--space-md` (16px), `--space-lg` (20px), `--space-xl` (24px), `--space-2xl` (32px), `--space-3xl` (48px), `--space-4xl` (64px)

---

## State Management

There is no shared state library. Each page module (`js/*.js`) manages its own module-level state.

**Conventions:**
- Module-level `let` variables hold page state (e.g., `let currentSprint = null`, `let burndownChart = null`).
- State is initialized on page load and mutated in response to user events or data loads.
- Core functions are stateless — they take data in and return results. They do not read module-level state from other files.
- State does not cross page boundaries. Each page is a full load.

---

## API / Data Pattern

Data flows in one direction: **static JSON files → browser fetch → rendering**.

1. **Data:** `public/data/` holds pre-generated, hand-maintained JSON — sprint records, milestones, and report content. There is no collection pipeline right now; a future iteration may reintroduce automated collection and/or move this data into a real database (see `README.md`).
2. **Serve:** The host serves `public/` as static files. No server-side computation at read time.
3. **Fetch:** The browser fetches JSON via `fetchJSON()` in `js/services/api.js`. All network access goes through this function. It returns `null` on non-OK responses, preventing thrown errors from missing data files.
4. **Render:** UI page modules receive fetched data and call Core functions to compute metrics, then render to the DOM.

**Data path resolution:** `dataPath(activeGroup, activeProject, relativePath)` in `api.js` scopes all fetches to the active group and project. UI modules never construct data paths directly.

**Null sentinel:** When no active sprint exists, `current-sprint.json` holds `null` (valid JSON) rather than being deleted. This prevents 404 errors in the browser console; `fetchJSON` returns `null`, and UI modules display "No active sprint."

**Data source (`source`):** Each group in `groups.json` can declare a `source` (`"gitlab"` by default, or `"jira"`), which only affects how the JSON was originally produced — the frontend schema is identical either way and does not branch on it.

---

## Testing

**Framework:** Vitest
**Scope:** All pure functions in `js/core/` — `utils.js`, `holidays.js`, `calculations.js`, `parsing.js`, `reports.js`, `dashboardShell.js`

The Core layer is the natural testing boundary. Core functions are pure (data in, result out) with no network calls. The DOM helpers declared as exceptions (`$`, `esc`, `getParams`, and the `downloadDoc` file download trigger in `utils.js`) are excluded — they are thin wrappers with no logic to test.

All existing Core functions are being backfilled with tests. New Core functions must include tests before merge.

**File convention:** `*.test.js` alongside source (e.g., `public/js/core/utils.test.js`)

**Run:** `npm test` or `npx vitest run`

---

## Development Principles

Inferred from observed patterns across the codebase. These describe the architectural beliefs behind the conventions — the "why" that guides edge-case decisions.

**Data is pre-computed, not computed at request time.** Sprint metrics, burndown arrays, and type breakdowns are stored as JSON. The browser does display logic only. Nothing is calculated server-side at page load.

**Layer boundaries are enforced by convention, not tooling.** There is no bundler or linter enforcing the four-layer rule. It is enforced by code review and this document. Every contributor is responsible for placing new code in the correct layer.

**Static over dynamic.** Every feature is done at data-preparation time or at client render time (JS). There is no application server, no API gateway, no database query at page load.

**Accessibility is structural, not cosmetic.** Semantic HTML, ARIA attributes, keyboard navigation, and skip links are part of the markup spec, not retrofitted. A feature that breaks keyboard navigation is not done.

---

## What Not to Do

- **No hardcoded colors or spacing (`margin`/`padding`/`gap`) in `styles.css` or JS.** Colors and spacing belong in `css/tokens.css` (`--space-*` for spacing). Raw `px` is fine for borders, font sizes, radii, fixed dimensions, and breakpoints. The sole exception for raw colors/spacing in JS is the Office-HTML `<style>` block in `reports.js`, which Word renders without access to `tokens.css`.
- **No DOM access in `js/core/` — except the documented exceptions.** `utils.js` may export thin DOM helpers (`$`, `esc`, `getParams`) and a DOM-based file download trigger (`downloadDoc`). Everything else that touches `document` or `window` belongs in a UI module.
- **No `fetch()` calls outside `js/services/api.js`.** All network access goes through the Services layer.
- **No DOM manipulation in `js/services/api.js`.** Services fetch and return data. They do not touch the DOM.
- **No upward imports.** Core does not import from Services or UI. Services do not import from UI.
- **No build tools.** No webpack, Vite, Rollup, Babel, or TypeScript compilation. Import paths must use `.js` extensions for native ES module resolution.
- **No framework dependencies.** Vanilla JS only. No React, Vue, Angular, or Svelte.
- **Files approaching 300 lines — consider splitting.** If a module is growing, look for a pure function to extract into `js/core/`.

---

## How to Add a Feature

Follow this order. Do not skip steps.

1. **Design tokens first.** New colors or spacing go in `css/tokens.css` before anywhere else.
2. **Core logic second.** Write pure functions in the appropriate `js/core/` module. If it has no DOM dependency and no network call, it is Core.
3. **Services third.** If the feature needs new data fetching or a new data path, add it to `js/services/api.js`.
4. **UI last.** Wire rendering and event handling in the relevant page module (`js/home.js`, `js/group.js`, `js/milestone.js`, or `js/releases.js`), or the shared dashboard controller (`js/dashboard.js`) if it applies to the dashboard shown on multiple pages.
5. **Data if needed.** If the feature requires new fields, extend the JSON schema by hand — keeping backward compatibility with existing files.

**Before shipping:**
- Test with `cd public && python -m http.server 8000`
- Verify keyboard navigation works on all interactive elements
- Verify ARIA attributes are present where needed
- Run `npm test`

---

## Flexible Preferences

These are preferences, not rules. They can be overridden with good reason.

- Prefer `async/await` over raw Promise chains.
- Prefer named exports over default exports (matches the existing codebase).
- Prefer template literals for HTML string construction over concatenation.

---

## Decisions

Notable decisions that shaped this architecture:

| Decision | Status |
|----------|--------|
| Four-layer JS architecture with no build step | Accepted |
| Fiscal year data cutoff at October 2025 (FY2026) | Accepted |
| Null sentinel for `current-sprint.json` instead of file deletion | Accepted |
| Vendor Chart.js rather than load from CDN | Accepted |
| Per-project sprint tracking via Milestones (filtered by `transition_date`) for `mode: "projects"` groups | Accepted |
| Deploy as a static site to Netlify/Vercel instead of GitLab Pages | Accepted |
| Data collection removed for now; `public/data/` is static and hand-maintained until a future DB migration | Accepted |
