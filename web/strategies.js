const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let config=null;

const catalog={
  'RSI Mean Reversion':['MEAN_REVERSION','Looks for stretched RSI conditions and a reversal back from oversold or overbought extremes.'],
  'RSI Momentum':['MOMENTUM','Uses RSI state as directional momentum confirmation rather than a reversal trigger.'],
  'EMA Crossover':['TREND','Tracks fast-versus-slow exponential moving-average transitions as trend events.'],
  'SMA Crossover':['TREND','Uses simple moving-average crossovers for slower, transparent trend confirmation.'],
  'MACD':['MOMENTUM','Measures fast/slow momentum spread and signal-line transitions.'],
  'Bollinger Mean Reversion':['MEAN_REVERSION','Treats movement outside the Bollinger envelope as a candidate reversion event.'],
  'Bollinger Breakout':['BREAKOUT','Treats expansion through a Bollinger boundary as directional breakout evidence.'],
  'Donchian Breakout':['BREAKOUT','Uses recent range highs and lows as explicit breakout boundaries.'],
  'Supertrend':['TREND','ATR-scaled trend state that flips direction when price crosses the adaptive band.'],
  'Stochastic Reversal':['MEAN_REVERSION','Looks for stochastic reversals from defined oversold and overbought zones.'],
  'ADX Trend':['TREND','Combines directional movement with ADX strength to qualify trend state.'],
  'ATR Breakout':['BREAKOUT','Uses ATR-scaled price expansion to identify volatility-adjusted breakout events.'],
  'VWAP Deviation':['MEAN_REVERSION','Measures percentage deviation from VWAP as a reversion-oriented signal.'],
  'Momentum ROC':['MOMENTUM','Uses rate of change over a configured lookback as directional momentum evidence.'],
  'Price Channel Trend':['TREND','Uses channel structure over a rolling lookback to express directional trend state.'],
};
const familyLabel=x=>({TREND:'Trend',MOMENTUM:'Momentum',MEAN_REVERSION:'Mean reversion',BREAKOUT:'Breakout'})[x]||x;
const fmtParams=p=>Object.entries(p||{}).map(([k,v])=>`${k}=${v}`).join(' · ')||'—';

function render(){if(!config)return;const q=$('strategySearch').value.trim().toLowerCase(),family=$('strategyCategory').value;const rows=(config.strategies||[]).filter(name=>{const f=catalog[name]?.[0]||'OTHER';return(!q||name.toLowerCase().includes(q))&&(family==='ALL'||family===f)});$('catalogMeta').textContent=`${rows.length} of ${config.strategies.length} models`;$('strategyCatalog').innerHTML=rows.length?rows.map(name=>{const [f,desc]=catalog[name]||['OTHER','Deterministic strategy signal model.'];const source=config.presets||{};return `<article class="strategy-card"><div class="strategy-card-head"><h3>${esc(name)}</h3><span class="strategy-family">${esc(familyLabel(f))}</span></div><p>${esc(desc)}</p><div class="preset-grid">${['1m','5m','15m','30m'].map(tf=>`<div class="preset-cell"><span>${tf}</span><code title="${esc(fmtParams(source[tf]?.[name]))}">${esc(fmtParams(source[tf]?.[name]))}</code></div>`).join('')}</div></article>`}).join(''):'<div class="catalog-empty">No strategies match this filter.</div>'}

function renderSources(){const labels=config.timeframe_labels||{},map=config.timeframe_preset_source||{};$('timeframeSources').innerHTML=(config.timeframes||[]).map(tf=>{const source=map[tf]||tf,proxy=source!==tf;return `<div class="source-row"><strong>${esc(labels[tf]||tf)}</strong><span>${proxy?'inherits qualified preset':'native qualified preset'}</span><code>${esc(source)}</code></div>`}).join('')}

function loadNamedPreset(preset){const workspace={schema_version:1,saved_at_ms:Date.now(),mode:'BACKTEST',values:{...(preset.payload||{})}};localStorage.setItem('epinnox.workspace.v1',JSON.stringify(workspace));location.href='/?open=strategy'}
async function renderPresets(){try{const d=await fetch('/api/settings/presets').then(r=>r.json()),rows=Array.isArray(d.presets)?d.presets:[];$('strategyPresetCount').textContent=rows.length;$('strategyPresets').innerHTML=rows.length?rows.map((p,i)=>{const v=p.payload||{};return `<div class="preset-row-card"><strong>${esc(p.name)}</strong><span>${esc(v.symbol||'Any symbol')} · ${esc(v.timeframe||'—')} · ${esc(v.strategy||'—')}</span><button class="ep-btn load-preset" data-preset="${i}" type="button">Load</button></div>`}).join(''):'<div class="compact-note" style="padding:12px">No named presets yet.</div>';$('strategyPresets')?.querySelectorAll('.load-preset').forEach(b=>b.addEventListener('click',()=>{const p=rows[Number(b.dataset.preset)];if(p)loadNamedPreset(p)}))}catch(e){$('strategyPresetCount').textContent='—';$('strategyPresets').innerHTML=`<div class="compact-note" style="padding:12px">Preset load failed · ${esc(e.message)}</div>`}}

async function boot(){config=await fetch('/api/config').then(r=>r.json());$('strategyCount').textContent=(config.strategies||[]).length;$('policyCount').textContent=(config.confirmation_policies||[]).length;renderSources();render();await renderPresets();$('strategySearch').addEventListener('input',render);$('strategyCategory').addEventListener('change',render)}
boot().catch(e=>{$('strategyCatalog').innerHTML=`<div class="catalog-empty">Strategy catalog unavailable · ${esc(e.message)}</div>`});