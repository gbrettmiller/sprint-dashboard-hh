## Architecture Audit

**Scope:** Whole project (frontend `public/js`, `public/css`, `public/*.html`; naming across `scripts/`)
**Doctrine source:** ARCHITECTURE.md (last updated 2026-07-02)
**Files scanned:** 12 JS source modules + 2 CSS + 4 HTML + 16 Python (naming only)
**Run date:** 2026-07-02

### Resolved this run (#53)
- **TOKENS** — `public/css/styles.css:267` `margin-bottom: -2px` → `calc(-1 * var(--space-3xs))`. No raw spacing outside `tokens.css` remains.
- **DRIFT** — ARCHITECTURE.md styling rules + token list now document the `--fs-*` / `--fw-*` / `--lh-*` / `--radius-sm` / `--radius-pill` scales (preferred; raw-px typography tolerated during migration).

### Violations

#### SIZE — info
- `public/js/dashboard.js` — 888 lines. Doctrine advisory is ~300; the shared dashboard controller is by far the largest module. Candidate for extracting pure chart-config/data-shaping helpers into `js/core/`.
- `public/js/home.js` — 436 lines. Over the ~300 advisory.
- `public/js/core/calculations.js` — 271 lines. Approaching the ~300 advisory.

### Clean categories
- **LAYER** — All DOM touches in `js/core/` are the documented `utils.js` exceptions (`$`, `getParams`, `downloadDoc`); the other `document.` hits are comments. No business logic in UI-only concerns detected.
- **IMPORT** — No upward imports. Core imports only Core (`holidays`, `utils`, `parsing`); `services/api.js` imports nothing; UI imports Core + Services + same-layer `dashboard.js` controller (permitted).
- **FETCH** — No `fetch()` outside `js/services/api.js`.
- **TOKENS (colors)** — No hardcoded colors in `styles.css` or JS. Chart colors are read from CSS custom properties via `getComputedStyle` (CHART_COLORS). The only raw color is `#999` in the `reports.js` Office-HTML `<style>` block (documented exception).
- **NAMING** — JS `camelCase.js`, Python `snake_case.py`, HTML/CSS lowercase, semantic CSS classes — all compliant.
- **STATE** — Page/controller module-level `let` state; Core functions stateless. Compliant.

### Summary
- High: 0 | Medium: 0 | Low: 0 | Info: 1 (SIZE advisory only, after #53 fixes)
- Architecture health: **CLEAN** — layers, imports, tokens, naming, and state all compliant. Only advisory: three modules over the ~300-line guideline.
