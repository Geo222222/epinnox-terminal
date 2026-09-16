# Epinnox Terminal — Frontend Product Surface

Epinnox Terminal is not a generic exchange dashboard. Its frontend exists to move a trading idea through a controlled lifecycle:

**discover → synthesize evidence → inspect → compare → paper qualify → eventually execute live**

The application already has distinct backend responsibilities, so the interface exposes them as distinct workspaces rather than crowding every control around one chart.

## Canonical pages

| Page | Route | Purpose | Primary question |
| --- | --- | --- | --- |
| Terminal | `/` | Chart-first strategy research and account-aware Backtest/Paper/Live context | “What does this strategy do on this market, and what is happening now?” |
| Scanner | `/scanner` | Deterministic candidate discovery and walk-forward qualification | “Where is there evidence worth investigating?” |
| Sessions | `/sessions` | Durable PAPER runtime operations and recovery | “What is currently operating, on whose account, and is it healthy?” |
| Research | `/research` | Evidence library across saved Universe candidates, pinned backtests, scans and presets | “What have we learned and what deserves promotion?” |
| Strategies | `/strategies` | Model catalog, preset sources and saved configurations | “What logic is available and how is it configured?” |

The Terminal also contains a first-class **Universe** research workspace. It is embedded in `/` because it shares the command-center shell, but it is not a chart overlay and it is not an execution surface.

LIVE execution remains intentionally locked. Account selection can be visible in the Terminal when Paper/Live context is relevant, but research-only workspaces must not imply that an execution account is active or that real order routing is armed.

## Information architecture

### Terminal / Chart

The chart is the center of gravity for single-market inspection. Global application navigation is not chart tooling. Scanner links, strategy-library navigation and session management therefore live outside the chart toolbar. The chart toolbar is reserved for chart identity, profile, fit, indicators and drawing behavior.

The right inspector is contextual:

- **Position** = current position, account context, current backtest window and paper runtime state.
- **Strategy** = reusable preset, entry model, backtest model, capital/sizing and exit engine.

### Scanner

Scanner V2 is a three-pane research workstation:

1. **Query Builder** — universe, objective, target economics and qualification rules.
2. **Candidate Leaderboard** — ranked evidence rows with a direct Load action into Terminal.
3. **Evidence Inspector** — top qualified candidate and durable recent scan history.

Scanner creates qualification evidence. It intentionally does not look like an order-entry page and does not submit execution mutations.

### Universe

Universe synthesizes persisted Scanner evidence across markets. It answers a different question from Scanner: **“Across the evidence we have already collected, what structure is visible and which candidates deserve inspection?”**

Universe therefore:

- aggregates recent persisted scanner runs instead of treating the latest run as the whole market;
- shows evidence coverage and makes under-covered states explicit;
- groups symbols by observed best strategy family and exposes strategy/timeframe filters;
- derives relationship edges only from common scanner response vectors with enough overlapping dimensions;
- labels those edges as response correlation or strategy similarity, never as raw-price correlation or causal structure;
- treats its composite evidence score as a visualization aid, never as a replacement for scanner qualification;
- blocks Paper preparation for rejected candidates;
- allows qualified candidates to be prepared for Paper without starting a strategy or bypassing account selection;
- keeps unsupported concepts, such as an unqualified regime classifier, out of the active interface.

Universe always runs in research/Backtest context. Single-market symbol price/timeframe chrome and execution-account chrome are hidden while Universe is active because they would misrepresent its multi-market scope.

### Sessions

The session registry is an operations surface, not another chart. It shows durable session identity, account/instrument ownership, runtime state, last processed bar, recovery requirements and checkpoint evidence. Recover and Stop actions remain explicit and scoped to the selected session.

### Research

The research page joins distinct evidence layers without pretending they are the same persistence mechanism:

- browser-local saved Universe candidates;
- browser-local pinned backtests;
- SQLite-persisted scanner experiments;
- server-side named workstation presets;
- PAPER session outcomes as forward-qualification evidence.

The page makes the intended qualification flow visible so evidence does not disappear into disconnected UI features.

### Strategies

The model library is a reference and configuration surface. It exposes all deterministic strategies, the parameter presets for 1m/5m/15m/30m, and the explicit preset-source mapping for longer chart intervals. Longer intervals must visibly identify their 30m source until they have independently qualified presets.

## Design rules

1. **Context before action.** The user should always know market, environment and account before an execution mutation is possible.
2. **Research and execution stay visually distinct.** Scanner and Universe cannot look like order-entry pages; PAPER/LIVE cannot look like synthetic backtest state.
3. **Qualification is a gate, not decoration.** A visually attractive candidate, high composite score or positive P&L does not override a failed scanner qualification contract.
4. **Evidence stays inspectable.** Candidate qualification, saved Universe evidence, backtest comparison and runtime events must remain navigable after the immediate action is complete.
5. **Coverage must be visible.** A graph with one symbol or insufficient common dimensions must say so rather than imply market-wide structure.
6. **Dense, not crowded.** Epinnox is a workstation. High information density is appropriate, but unrelated controls cannot compete for the same visual region.
7. **Fail-closed states must look intentional.** Recovery required, unconfigured upstream execution, rejected Paper candidates and LIVE-not-armed are explicit product states, not generic errors.
8. **One visual language.** Dark neutral surfaces, restrained Epinnox green, tabular numeric values and compact typography are shared across every workspace.

## Definition of done

The frontend product surface is considered coherent when:

- all five canonical pages are directly navigable;
- the embedded Universe workspace is directly discoverable from the Terminal rail;
- each page/workspace maps to one clear operational purpose;
- Terminal remains chart-first for single-market inspection;
- Scanner has query/leaderboard/evidence hierarchy;
- Universe aggregates persisted evidence, exposes coverage, and cannot bypass qualification into Paper;
- Sessions exposes durable runtime lifecycle and scoped recovery/stop actions;
- Research makes saved candidates and persisted evidence discoverable;
- Strategies makes model/preset provenance discoverable;
- LIVE remains visibly unarmed;
- frontend JavaScript syntax and asset-route checks run in CI.
