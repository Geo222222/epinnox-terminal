# Epinnox Terminal — Senior Engineer Instructions

## Mission

Complete the Epinnox Terminal frontend so all 5 canonical pages render consistently, function correctly, and share a unified shell. The backend is done. The frontend has been through several refactors and has accumulated inconsistencies. Your job is to audit, fix, and finish.

---

## Architecture Overview

### What Exists

- **Backend:** FastAPI (`app/main.py`) serving 5 HTML pages + REST API
- **Frontend:** Vanilla JS (no framework), multiple CSS files, dynamic DOM construction via `product-chrome.js`
- **Shell system:** `product-chrome.js` builds a canonical header, sidebar, and footer that replace the per-page HTML chrome on load

### The 5 Canonical Pages

| Page | Route | HTML File | JS Entry | CSS Files |
|------|-------|-----------|----------|-----------|
| Terminal | `/` | `index.html` | `app.js` (module) | `styles.css`, `workstation.css`, `v4-shell.css`, `v4-workbench.css`, `v4-universe.css`, `v5-chart-workspace.css`, `product-chrome.css` |
| Scanner | `/scanner` | `scanner.html` | `scanner.js` (module) | `product-pages.css`, `scanner.css`, `product-chrome.css` |
| Sessions | `/sessions` | `sessions.html` | `sessions.js` (module) | `product-pages.css`, `sessions.css`, `product-chrome.css` |
| Research | `/research` | `research.html` | `research.js` (module) | `product-pages.css`, `research.css`, `product-chrome.css` |
| Strategies | `/strategies` | `strategies.html` | `strategies.js` (module) | `product-pages.css`, `strategies.css`, `product-chrome.css` |

Plus an embedded **Universe** workspace accessible from Terminal via `?universe=1`.

### Script Execution Order (Terminal page)

1. `persistence.js` (sync) — creates `#sessionRail` if missing, loads v4-shell.js
2. `product-chrome.js` (defer) — builds canonical header/sidebar/footer, replaces page chrome
3. `v4-shell.js` (defer) — loads additional v4 scripts (workbench, universe, etc.)
4. `v4-workbench.js` (defer) — chart workbench features
5. `v4-universe.js` (defer) — universe workspace
6. `v5-chart-workspace.js` (defer) — v5 chart features (drawing icons, strategy modal, dock controls)
7. `app.js` (module) — main chart logic, creates drawing toolbar, binds events

### Script Execution Order (Product pages)

1. `product-chrome.js` (defer) — builds canonical header/sidebar/footer
2. Page-specific JS (module) — scanner.js, sessions.js, research.js, or strategies.js

---

## What To Fix

### 1. Canonical Shell Consistency

`product-chrome.js` builds the shell. Verify on every page:

**Header** (`#epGlobalHeader`):
- Brand mark + "EPINNOX TERMINAL" + "Capital intelligence · Serving Benjamin"
- Ticker deck: BTC, ETH, SOL, XRP with live prices
- Search input with symbol autocomplete
- System status button (◌) — shows runtime status popover
- Settings button (⚙) — links to `/?open=strategy`
- Mode selector (Backtest/Paper/Live)

**Sidebar** (`#epGlobalNav`):
- Title: "COMMAND CENTER"
- 6 nav items with icons: ⌁ Terminal, ⌘ Scanner, ⌬ Universe, ▣ Sessions, ◇ Research, ◈ Strategies
- Active state: emerald left border + glow icon
- Paper Sessions section with count + list
- "DISCIPLINE BUILDS FREEDOM" art at bottom

**Footer** (`#epGlobalFooter`):
- Clock (live updating)
- Current page name
- Ticker tape (BTC/ETH/SOL/XRP changes)
- Cues: "◇ Evidence First · ★ No Assumptions · Serve Benjamin ↗"

### 2. Terminal Page (`/`)

The Terminal is the most complex page. It must:

- Show the chart as the primary workspace
- Have a drawing toolbar with SVG icons (not Unicode text)
- Have a right inspector with Position and Strategy tabs
- Have a bottom dock with Overview, Trades, Economics, Paper Events tabs
- Support Backtest/Paper/Live mode switching
- Show account selector when in Paper/Live mode
- Have the quick strategy selector in the chart toolbar
- Support the strategy modal (click ⚙ or "Strategy configuration")
- Support dock resize (drag grip) and collapse
- Support Universe workspace via `?universe=1`

**Drawing Toolbar Issues:**
- `app.js` creates the toolbar with Unicode text icons
- `v5-chart-workspace.js` replaces them with SVGs via `installDrawingIcons()`
- Verify the timing: `app.js` must call `window.EpinnoxV5Chart?.installDrawingIcons?.()` after toolbar creation
- Verify the MutationObserver in `v5-chart-workspace.js` catches late toolbar insertion

**Rail Navigation:**
- The old `#sessionRail` is replaced by `product-chrome.js` with `#epGlobalNav`
- Verify all 6 nav items render correctly
- Verify the Universe link triggers the universe workspace on Terminal page

### 3. Scanner Page (`/scanner`)

Scanner is a continuous live scanner (not the old batch scanner). It must:

- Show runtime strip: STATE, CYCLE, ACTIVE BATCH, MARKETS, COVERED, UNSCANNED, STALE, LAST COMMIT
- Show Scanner/Universe toggle switches
- Show Scanner Mandate panel (query builder) with Edit/Apply/Cancel
- Show Live Candidate Leaderboard with qualification columns
- Show Operations panel, Top Evidence panel, Runtime Events panel
- Connect to WebSocket or polling for live updates
- Handle connection state (CONNECTING → RUNNING)

### 4. Sessions Page (`/sessions`)

Sessions shows durable paper runtime operations. It must:

- Show session registry with state filtering (All, Active, Recovery Required, Stopped)
- Show session detail panel with evidence, position, events
- Support Recover and Stop actions scoped to selected session
- Show KPIs: Active sessions, Running now, Recovery required, Execution authority
- Refresh automatically

### 5. Research Page (`/research`)

Research is the evidence library. It must:

- Show saved Universe candidates (browser localStorage)
- Show pinned backtests (browser localStorage)
- Show scanner experiments (SQLite-persisted)
- Show named presets (server-side)
- Show paper session outcomes
- Show qualification flow visualization (Discover → Inspect → Compare → Paper qualify)
- KPIs: Saved candidates, Pinned backtests, Scanner experiments, Named presets, Paper sessions

### 6. Strategies Page (`/strategies`)

Strategies is the model catalog. It must:

- Show all 15 deterministic strategies with descriptions
- Show parameter presets for 1m/5m/15m/30m
- Show preset source mapping (longer intervals inherit from 30m)
- Show saved configurations (named presets)
- Support search and category filtering
- KPIs: Strategies, Native preset bands, Composite policies, Named presets

### 7. Universe Workspace (embedded in Terminal)

Universe synthesizes persisted Scanner evidence. It must:

- Aggregate recent persisted scanner runs
- Show evidence coverage per symbol
- Group symbols by best strategy family
- Expose strategy/timeframe filters
- Derive relationship edges from common scanner response vectors
- Label edges as "response correlation" or "strategy similarity" (never "price correlation")
- Block Paper preparation for rejected candidates
- Allow qualified candidates to be prepared for Paper
- Hide single-market chrome (symbol select, timeframe) when active

---

## Design Rules

From `docs/BRAND.md` and `docs/FRONTEND_PRODUCT_SURFACE.md`:

1. **Context before action** — user must know market, environment, and account before execution
2. **Research and execution stay visually distinct** — Scanner/Universe cannot look like order entry
3. **Qualification is a gate** — positive P&L does not override failed qualification
4. **Evidence stays inspectable** — qualification, backtests, and events remain navigable
5. **Coverage must be visible** — insufficient data must say so
6. **Dense, not crowded** — high information density, no competing controls
7. **Fail-closed states look intentional** — recovery required, unconfigured, LIVE-not-armed are explicit states
8. **One visual language** — dark surfaces, restrained emerald, tabular numerics, compact type

### Typography Scale

- Eyebrow labels: 7px, uppercase, letter-spacing 0.12-0.16em
- Panel titles: 10-11px, bold
- Body text: 8-9px
- Monospace numerals: `ui-monospace, SFMono-Regular, Consolas, monospace`
- Status pills: 8px

### Color Palette

- Background: `#020403` / `#030605`
- Panel: `#050906` / `#040806`
- Border: `#17221c` / `#15231c`
- Text primary: `#edf6f1`
- Text muted: `#66786e` / `#56685f`
- Emerald: `#10ff8b` (active, qualified, connected only)
- Negative: `#ff7373`
- Monospace: `#cad7d0`

---

## File-by-File Audit

For each file, read it and verify it does what it should:

### HTML Files

| File | What to verify |
|------|---------------|
| `web/index.html` | Has `.app-shell` layout, chart workspace, inspector, bottom dock, statusbar. Loads all required CSS/JS. |
| `web/scanner.html` | Has `.product-shell` layout, `.product-sidebar` (replaced by canonical shell), scanner workbench panels. |
| `web/sessions.html` | Has `.product-shell` layout, session registry, session detail panel. |
| `web/research.html` | Has `.product-shell` layout, evidence library sections, qualification flow. |
| `web/strategies.html` | Has `.product-shell` layout, model catalog, preset source, saved configurations. |

### JS Files

| File | What to verify |
|------|---------------|
| `web/product-chrome.js` | Builds canonical header/sidebar/footer. Handles nav active state. Refreshes market data and sessions. |
| `web/app.js` | Creates drawing toolbar, initializes charts, binds all Terminal events, handles backtest/paper/live modes. |
| `web/v5-chart-workspace.js` | Installs drawing SVG icons, quick strategy selector, strategy modal, dock controls, position dock. |
| `web/v4-shell.js` | Loads additional v4 scripts, handles session rail, binds mode buttons. |
| `web/v4-workbench.js` | Chart workbench features (if still needed). |
| `web/v4-universe.js` | Universe workspace logic. |
| `web/scanner.js` | Scanner page logic — live scanning, mandate editing, leaderboard rendering. |
| `web/sessions.js` | Sessions page logic — session list, detail, actions. |
| `web/research.js` | Research page logic — evidence loading, display. |
| `web/strategies.js` | Strategies page logic — catalog, presets, search. |
| `web/persistence.js` | Workspace persistence, preset management, rail creation. |
| `web/position-lifecycle.js` | Position lifecycle management (if still needed). |

### CSS Files

| File | What to verify |
|------|---------------|
| `web/product-chrome.css` | Canonical shell styles — header, nav, footer, responsive breakpoints. |
| `web/product-pages.css` | Base product page styles — panels, KPIs, forms. |
| `web/workstation.css` | Terminal workstation styles — drawing toolbar, market strip. |
| `web/v4-shell.css` | Legacy shell styles (may be partially superseded by product-chrome.css). |
| `web/v5-chart-workspace.css` | v5 chart overrides — compact rail, drawing toolbar sizing, modal. |
| `web/scanner.css` | Scanner-specific styles. |
| `web/sessions.css` | Sessions-specific styles. |
| `web/research.css` | Research-specific styles. |
| `web/strategies.css` | Strategies-specific styles. |
| `web/styles.css` | Base global styles. |

---

## Known Issues to Fix

### Race Conditions

1. **Drawing toolbar SVG timing:** `app.js` creates toolbar after CDN fetch. `v5-chart-workspace.js` runs `installDrawingIcons()` before toolbar exists. Fix: `app.js` calls `window.EpinnoxV5Chart?.installDrawingIcons?.()` after creation, AND `v5-chart-workspace.js` has MutationObserver as fallback.

2. **Canonical shell vs page HTML:** `product-chrome.js` replaces the page's header/sidebar/footer with canonical versions. The original HTML in each page file still has the old chrome. This is intentional (the JS replaces it), but verify no flicker or double-render occurs.

### Layout Inconsistencies

3. **Product page panels:** Scanner, Sessions, Research, and Strategies pages may have different panel padding, border styles, or background gradients. Audit `.panel` class usage across all product page CSS files.

4. **Sidebar width:** The canonical nav uses `--ep-nav: 232px`. Verify this works on all pages, including Terminal where the sidebar replaces `#sessionRail`.

5. **Terminal grid:** Terminal uses `.app-shell` with grid rows. Verify the canonical shell's footer doesn't break the grid.

### Missing Features

6. **Universe nav link:** The Universe nav item in the canonical shell must trigger the universe workspace on Terminal page. Verify `product-chrome.js` handles this correctly.

7. **Scanner live connection:** The new scanner is a continuous runtime. Verify it connects to the backend WebSocket/polling endpoint and shows live state.

8. **Research evidence loading:** Verify Research page loads evidence from all sources (localStorage candidates, pinned backtests, SQLite scanner experiments, server presets, paper sessions).

9. **Strategies catalog:** Verify Strategies page loads all 15 strategies from the API and shows preset sources correctly.

---

## Verification Checklist

After making changes, verify:

- [ ] Navigate all 5 pages — no layout jumps, consistent shell
- [ ] Sidebar nav works on all pages — correct active state, links work
- [ ] Header renders identically on all pages — brand, tickers, search, tools
- [ ] Footer renders identically on all pages — clock, tape, cues
- [ ] Terminal: chart loads, drawing toolbar has SVG icons, inspector tabs work
- [ ] Terminal: mode switching (Backtest/Paper/Live) works
- [ ] Terminal: strategy modal opens/closes
- [ ] Terminal: dock resize and collapse work
- [ ] Terminal: Universe workspace opens from sidebar
- [ ] Scanner: live state updates, mandate editing works
- [ ] Sessions: session list loads, detail shows, actions work
- [ ] Research: all evidence sections load data
- [ ] Strategies: catalog loads, search/filter works
- [ ] Run `python scripts/runtime_smoke.py` — all pages load, assets resolve
- [ ] Run `pytest -q` — all tests pass

---

## Running the App

```bash
cd epinnox-terminal
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Open `http://localhost:8010`.

---

## References

- `docs/FRONTEND_PRODUCT_SURFACE.md` — complete page specs and design rules
- `docs/BRAND.md` — visual identity
- `docs/SESSION_ARCHITECTURE.md` — session runtime
- `docs/SCANNER_V2.md` — scanner details
- `docs/RUNTIME_VALIDATION.md` — automated validation

---

## Questions to Answer Before Signing Off

1. Does the drawing toolbar show SVG icons on first load without requiring a page refresh?
2. Does navigating from Terminal to Scanner and back cause any layout jump?
3. Does the canonical sidebar show all 6 nav items with correct active states on every page?
4. Does the Universe workspace open correctly from the Terminal sidebar?
5. Does the Scanner show live state updates from the backend?
6. Does the Research page load evidence from all 5 sources?
7. Does the Strategies page show all 15 strategies with correct preset sources?
8. Does `runtime_smoke.py` pass?
9. Does `pytest -q` pass?
10. Is LIVE mode visibly unarmed on all pages?
