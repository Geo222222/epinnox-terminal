(() => {
  'use strict';

  const SCHEMA_VERSION = 1;
  const LOCAL_KEY = 'epinnox.workspace.v1';
  const SESSION_KEY = 'epinnox.session.v1';
  const BACKTEST_META_KEY = 'epinnox.backtest-meta.v1';

  const persistentIds = [
    'symbol','timeframe','backtestProfile','startDate','endDate','strategy','confirm1','confirm2',
    'confirmationPolicy','confirmationRequired','confirmationWindow','direction','bars','balance',
    'leverage','allocation','pyramiding','entryFee','exitFee','extraCost','netTarget','referral',
    'maintenance','maxBars','stopLoss','manualParams'
  ];

  const readJson = (storage, key) => {
    try {
      const value = JSON.parse(storage.getItem(key) || 'null');
      return value && value.schema_version === SCHEMA_VERSION ? value : null;
    } catch {
      return null;
    }
  };

  const writeJson = (storage, key, value) => {
    try { storage.setItem(key, JSON.stringify(value)); } catch { /* storage can be unavailable */ }
  };

  const optionExists = (el, value) => !el.options || [...el.options].some(o => o.value === String(value));

  function setField(id, value, emit = false) {
    const el = document.getElementById(id);
    if (!el || value === undefined || value === null) return false;
    const stringValue = String(value);
    if (el.tagName === 'SELECT' && !optionExists(el, stringValue)) return false;
    if (el.type === 'number' && stringValue !== '' && !Number.isFinite(Number(stringValue))) return false;
    el.value = stringValue;
    if (emit) el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
    return true;
  }

  function collectWorkspace() {
    const values = {};
    for (const id of persistentIds) {
      const el = document.getElementById(id);
      if (el) values[id] = el.value;
    }
    const mode = document.querySelector('.mode.active')?.dataset.mode || 'BACKTEST';
    return {
      schema_version: SCHEMA_VERSION,
      saved_at_ms: Date.now(),
      mode,
      values,
    };
  }

  function collectSessionUi() {
    return {
      schema_version: SCHEMA_VERSION,
      saved_at_ms: Date.now(),
      inspector_tab: document.querySelector('.inspector-tab.active')?.dataset.inspectorTab || 'positionPanel',
      bottom_tab: document.querySelector('.tabbar button.active')?.dataset.tab || 'tester',
      indicator_collapsed: document.getElementById('indicatorPane')?.classList.contains('collapsed') || false,
    };
  }

  function saveWorkspace() { writeJson(localStorage, LOCAL_KEY, collectWorkspace()); }
  function saveSessionUi() { writeJson(sessionStorage, SESSION_KEY, collectSessionUi()); }

  function backendDefaults(config) {
    const d = config?.defaults || {};
    const terminal = d.terminal || {};
    const account = d.account_defaults || {};
    const econ = d.economics_defaults || {};
    const backtest = d.backtest_defaults || {};
    return {
      symbol: terminal.default_symbol,
      timeframe: terminal.default_timeframe,
      backtestProfile: terminal.default_backtest_profile,
      strategy: terminal.default_strategy,
      confirmationPolicy: terminal.default_confirmation_policy,
      balance: account.starting_balance,
      leverage: account.leverage,
      allocation: account.allocation_pct,
      pyramiding: account.pyramiding,
      direction: account.direction,
      entryFee: econ.entry_fee_pct,
      exitFee: econ.exit_fee_pct,
      extraCost: econ.extra_cost_pct,
      netTarget: econ.desired_net_profit_pct,
      referral: econ.referral_share_pct,
      maintenance: econ.maintenance_margin_pct,
      bars: backtest.history_bars,
    };
  }

  function syncTimeframeButtons(value) {
    document.querySelectorAll('.tf').forEach(b => b.classList.toggle('active', b.dataset.tf === value));
  }

  function restoreWorkspace(config) {
    const saved = readJson(localStorage, LOCAL_KEY);
    const values = saved?.values || backendDefaults(config);
    for (const [id, value] of Object.entries(values)) setField(id, value, false);
    if (values.timeframe) syncTimeframeButtons(String(values.timeframe));

    const desiredMode = saved?.mode || config?.defaults?.terminal?.default_mode || 'BACKTEST';
    const modeButton = document.querySelector(`.mode[data-mode="${desiredMode}"]`);
    if (modeButton && !modeButton.classList.contains('active')) modeButton.click();

    // Emit after all fields are hydrated so one final auto-backtest uses a coherent snapshot.
    for (const id of persistentIds) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (id === 'timeframe') continue;
      el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
    }
    const tf = document.getElementById('timeframe')?.value;
    const tfButton = tf && document.querySelector(`.tf[data-tf="${tf}"]`);
    if (tfButton) tfButton.click();
    saveWorkspace();
  }

  function restoreSessionUi() {
    const saved = readJson(sessionStorage, SESSION_KEY);
    if (!saved) return;
    const inspector = saved.inspector_tab && document.querySelector(`.inspector-tab[data-inspector-tab="${saved.inspector_tab}"]`);
    if (inspector) inspector.click();
    const bottom = saved.bottom_tab && document.querySelector(`.tabbar button[data-tab="${saved.bottom_tab}"]`);
    if (bottom) bottom.click();
    const pane = document.getElementById('indicatorPane');
    if (pane && Boolean(saved.indicator_collapsed) !== pane.classList.contains('collapsed')) {
      document.getElementById('toggleIndicator')?.click();
    }
  }

  async function waitForAppReady() {
    for (let i = 0; i < 120; i += 1) {
      const strategyReady = document.querySelectorAll('#strategy option').length > 0;
      const symbolReady = document.querySelectorAll('#symbol option').length > 0;
      if (strategyReady && symbolReady) return true;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    return false;
  }

  async function bootPersistence() {
    const ready = await waitForAppReady();
    if (!ready) return;
    let config = null;
    try { config = await fetch('/api/config').then(r => r.ok ? r.json() : null); } catch { /* defaults remain app defaults */ }
    restoreWorkspace(config);
    restoreSessionUi();

    for (const id of persistentIds) {
      const el = document.getElementById(id);
      if (!el) continue;
      el.addEventListener('input', saveWorkspace);
      el.addEventListener('change', saveWorkspace);
    }
    document.querySelectorAll('.mode,.tf').forEach(el => el.addEventListener('click', saveWorkspace));
    document.querySelectorAll('.inspector-tab,.tabbar button,#toggleIndicator').forEach(el => el.addEventListener('click', saveSessionUi));
    window.addEventListener('beforeunload', () => { saveWorkspace(); saveSessionUi(); });
  }

  // Keep the last experiment identity across reloads without storing the full candle payload.
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    try {
      const target = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      const method = String(args[1]?.method || 'GET').toUpperCase();
      if (target.includes('/api/backtest') && method === 'POST' && response.ok) {
        const data = await response.clone().json();
        writeJson(localStorage, BACKTEST_META_KEY, {
          schema_version: SCHEMA_VERSION,
          saved_at_ms: Date.now(),
          symbol: data.symbol,
          timeframe: data.timeframe,
          strategy: data.strategy,
          entry_model: data.entry_model,
          backtest_profile: data.backtest_profile,
          backtest_window: data.backtest_window,
          metrics: data.metrics,
        });
      }
    } catch { /* diagnostics persistence must never break fetch */ }
    return response;
  };

  window.EpinnoxPersistence = {
    schemaVersion: SCHEMA_VERSION,
    saveWorkspace,
    getWorkspace: () => readJson(localStorage, LOCAL_KEY),
    getLastBacktestMeta: () => readJson(localStorage, BACKTEST_META_KEY),
    clearWorkspace: () => { localStorage.removeItem(LOCAL_KEY); sessionStorage.removeItem(SESSION_KEY); },
    listPresets: async () => fetch('/api/settings/presets').then(r => r.json()),
    savePreset: async (name, payload = collectWorkspace().values) => fetch('/api/settings/presets', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, schema_version: SCHEMA_VERSION, payload }),
    }).then(async r => { const body = await r.json(); if (!r.ok) throw new Error(body.detail || 'Preset save failed'); return body; }),
    deletePreset: async name => fetch(`/api/settings/presets/${encodeURIComponent(name)}`, { method: 'DELETE' }).then(r => r.json()),
    applyPreset: payload => {
      if (!payload || typeof payload !== 'object') return;
      for (const [id, value] of Object.entries(payload)) setField(id, value, true);
      saveWorkspace();
    },
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootPersistence);
  else bootPersistence();
})();
