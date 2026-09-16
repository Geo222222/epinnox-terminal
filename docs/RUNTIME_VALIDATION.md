# Epinnox Terminal Runtime Validation

This document defines the runtime verification gate for the Epinnox Terminal frontend and research workspaces. Source-level tests and static asset checks are necessary, but they are not sufficient: the application must also boot as a real FastAPI process and serve the intended pages, API contracts, and final CSS/JavaScript layers from the exact commit under test.

## Validation layers

### 1. Unit and contract tests

Run the Python suite first:

```bash
pytest -q
```

This covers strategy logic, settings, persistence, scanner/session contracts, Universe safety behavior, and visual-asset contracts.

### 2. Frontend syntax and asset contracts

GitHub Actions checks the JavaScript entry points with `node --check` and verifies that the command-center, Universe refinement/safety, and responsive visual-QA assets exist and are wired into the correct shell order.

### 3. Runtime HTTP smoke gate

Run:

```bash
python scripts/runtime_smoke.py
```

The smoke gate launches `uvicorn app.main:app` on a temporary local port and verifies the application through HTTP. It does not request live market data and does not perform PAPER or LIVE mutations.

The gate verifies:

- `/api/health` reports the Epinnox Terminal service as healthy;
- `/api/config` preserves the Epinnox Online account-context contract and keeps LIVE routing unarmed;
- `/`, `/scanner`, `/sessions`, `/research`, and `/strategies` are served by the running application;
- the V4 shell, Universe refinement/safety, responsive visual-QA, product visual-QA, and Research evidence assets are actually reachable through `/static`;
- the persisted scanner-runs API responds without requiring external market data.

The script exits non-zero on any contract failure and prints captured Uvicorn output after shutdown.

## Manual browser visual gate

Automated runtime smoke testing proves that the application boots and that its runtime routes/assets are coherent. It does **not** prove pixel-level visual quality. Before declaring a frontend release visually complete, inspect the running application in a real browser at representative desktop widths.

Use this sequence:

1. Open Chart and verify the market header, session rail, chart controls, inspector, bottom dock, and footer do not overlap or clip.
2. Open Scanner and verify query controls, candidate leaderboard, evidence panels, and vertical scrolling remain usable.
3. Open Universe and verify the research-only chrome is active, execution context is hidden, graph/coverage states remain readable, rejected candidates expose qualification reasons, and Paper preparation stays gated.
4. Open Sessions, Research, and Strategies and verify shared product chrome, navigation, tables/cards, sticky regions, and footer behavior.
5. Repeat at approximately 1700+ px, 1360–1699 px, 981–1279 px, and 821–980 px widths, plus a short-height desktop viewport around 760 px tall.
6. Confirm keyboard focus is visible and reduced-motion behavior remains usable when the operating system requests reduced motion.

## Definition of done

A frontend/runtime change is complete only when all of the following are true:

- the exact candidate commit passes the full automated suite;
- the exact candidate commit passes `scripts/runtime_smoke.py`;
- the branch is reconciled with current `main` before merge;
- canonical `main` passes CI after merge;
- visual browser QA has been performed against the deployed or locally running build when the change affects layout or interaction;
- deployment/runtime state is reported separately from repository and CI state.

A green repository/CI state must never be described as deployed or visually verified unless those additional checks were actually performed.
