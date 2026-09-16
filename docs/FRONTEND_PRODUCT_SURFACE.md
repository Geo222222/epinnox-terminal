# Epinnox Terminal — Frontend Product Surface

Epinnox Terminal is not a generic exchange dashboard. Its frontend exists to move a trading idea through a controlled lifecycle:

**discover → inspect → compare → paper qualify → eventually execute live**

The application already has distinct backend responsibilities, so the interface should expose them as distinct workspaces rather than crowd every control around one chart.

## Canonical pages

| Page | Route | Purpose | Primary question |
| --- | --- | --- | --- |
| Terminal | `/` | Chart-first strategy research and account-aware Backtest/Paper/Live context | “What does this strategy do on this market, and what is happening now?” |
| Scanner | `/scanner` | Deterministic candidate discovery and walk-forward qualification | “Where is there evidence worth investigating?” |
| Sessions | `/sessions` | Durable PAPER runtime operations and recovery | “What is currently operating, on whose account, and is it healthy?” |
| Research | `/research` | Evidence library across pinned backtests, scans and presets | “What have we learned and what deserves promotion?” |
| Strategies | `/strategies` | Model catalog, preset sources and saved configurations | “What logic is available and how is it configured?” |

LIVE execution remains intentionally locked. Account selection can be visible in the Terminal because account context is real, but the interface must not imply that real order routing is armed.

## Information architecture

### Terminal

The chart is the center of gravity. Global application navigation is not chart tooling. Scanner links, strategy-library navigation and session management therefore live outside the chart toolbar. The chart toolbar is reserved for chart identity, profile, fit, indicators and drawing behavior.

The right inspector is contextual:

- **Position** = current position, account context, current backtest window and paper runtime state.
- **Strategy** = reusable preset, entry model, backtest model, capital/sizing and exit engine.

### Scanner

Scanner V2 is a three-pane research workstation:

1. **Query Builder** — universe, objective, target economics and qualification rules.
2. **Candidate Leaderboard** — ranked evidence rows with a direct Load action into Terminal.
3. **Evidence Inspector** — top qualified candidate and durable recent scan history.

It intentionally removes the old marketing-style hero block. Scanner is an operating tool, not a landing page.

### Sessions

The session registry is an operations surface, not another chart. It shows durable session identity, account/instrument ownership, runtime state, last processed bar, recovery requirements and checkpoint evidence. Recover and Stop actions remain explicit and scoped to the selected session.

### Research

The research page joins three persistence layers without pretending they are the same thing:

- browser-local pinned backtests;
- SQLite-persisted scanner experiments;
- server-side named workstation presets.

The page also makes the intended qualification flow visible so evidence does not disappear into disconnected UI features.

### Strategies

The model library is a reference and configuration surface. It exposes all deterministic strategies, the parameter presets for 1m/5m/15m/30m, and the explicit preset-source mapping for longer chart intervals. Longer intervals must visibly identify their 30m source until they have independently qualified presets.

## Design rules

1. **Context before action.** The user should always know market, environment and account before a mutation is possible.
2. **Research and execution stay visually distinct.** Scanner cannot look like an order-entry page; PAPER/LIVE cannot look like synthetic backtest state.
3. **Evidence stays inspectable.** Candidate qualification, backtest comparison and runtime events must remain navigable after the immediate action is complete.
4. **Dense, not crowded.** Epinnox is a workstation. High information density is appropriate, but unrelated controls cannot compete for the same visual region.
5. **Fail-closed states must look intentional.** Recovery required, unconfigured upstream execution and LIVE-not-armed are explicit product states, not generic errors.
6. **One visual language.** Dark neutral surfaces, restrained Epinnox green, tabular numeric values and compact typography are shared across every workspace.

## Definition of done

The frontend product surface is considered coherent when:

- all five canonical pages are directly navigable;
- each page maps to one clear operational purpose;
- Terminal remains chart-first;
- Scanner has query/leaderboard/evidence hierarchy;
- Sessions exposes durable runtime lifecycle and scoped recovery/stop actions;
- Research makes persisted evidence discoverable;
- Strategies makes model/preset provenance discoverable;
- LIVE remains visibly unarmed;
- frontend JavaScript syntax and asset-route checks run in CI.
