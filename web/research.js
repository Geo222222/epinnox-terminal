const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=(v,d=2)=>v===null||v===undefined||Number.isNaN(Number(v))?'—':`$${Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})}`;
const n=(v,d=2)=>v===null||v===undefined||Number.isNaN(Number(v))?'—':Number(v).toFixed(d);
const PIN_KEY='epinnox.v4.pins.v1',CANDIDATE_KEY='epinnox.universe.saved.v1',WORKSPACE_KEY='epinnox.workspace.v1';

function loadPins(){try{const x=JSON.parse(localStorage.getItem(PIN_KEY)||'[]');return Array.isArray(x)?x:[]}catch{return[]}}
function loadCandidates(){try{const x=JSON.parse(localStorage.getItem(CANDIDATE_KEY)||'[]');return Array.isArray(x)?x:[]}catch{return[]}}
function itemIndex(i){return String(i+1).padStart(2,'0')}
function date(ms){return ms?new Date(ms).toLocaleString():'—'}
function loadPin(pin){localStorage.setItem(WORKSPACE_KEY,JSON.stringify({schema_version:1,saved_at_ms:Date.now(),mode:'BACKTEST',values:{...(pin.config||{})}}));location.href='/'}

function candidateWorkspace(c){
  const p=c.load_payload||{};
  let existing={schema_version:1,values:{}};
  try{const x=JSON.parse(localStorage.getItem(WORKSPACE_KEY)||'null');if(x?.schema_version===1)existing=x}catch{}
  return{schema_version:1,saved_at_ms:Date.now(),mode:'BACKTEST',values:{...(existing.values||{}),symbol:c.symbol,timeframe:c.timeframe,strategy:c.strategy,backtestProfile:p.backtest_profile||'TradingView Parity',balance:String(p.starting_balance??100000),leverage:String(p.leverage??1),allocation:String(p.allocation_pct??5),pyramiding:String(p.pyramiding??1),direction:p.direction||'Both',entryFee:String(p.entry_fee_pct??.05),exitFee:String(p.exit_fee_pct??.05),extraCost:String(p.extra_cost_pct??0),netTarget:String(p.target_buffer_pct??0),referral:String(p.referral_share_pct??30),maintenance:String(p.maintenance_margin_pct??.4),bars:String(p.limit??2000),maxBars:p.max_bars_in_trade==null?'':String(p.max_bars_in_trade),stopLoss:p.stop_loss_pct==null?'':String(p.stop_loss_pct),confirmationPolicy:'Single',confirm1:'',confirm2:''}}
}
function loadCandidate(c){localStorage.setItem(WORKSPACE_KEY,JSON.stringify(candidateWorkspace(c)));location.href='/'}
function removeCandidate(index){const rows=loadCandidates();rows.splice(index,1);localStorage.setItem(CANDIDATE_KEY,JSON.stringify(rows));renderCandidates(rows)}

function renderCandidates(candidates){
  $('researchCandidatesCount').textContent=candidates.length;
  const root=$('researchCandidates');if(!root)return;
  if(!candidates.length){root.innerHTML='<div class="empty-state"><div><strong>No saved candidates</strong><p>Save a candidate from Universe when it deserves inspection or comparison.</p></div></div>';return}
  root.innerHTML=candidates.map((c,i)=>`<div class="research-item candidate-item"><div class="research-item-index">${itemIndex(i)}</div><div class="research-item-main"><strong>${esc(c.symbol||'—')} · ${esc(c.timeframe||'—')} · ${esc(c.strategy||'—')}</strong><span>saved ${esc(date(c.saved_at_ms))} · ${c.scan_count??1} scan${Number(c.scan_count)===1?'':'s'} · score ${n(c.score,0)}</span></div><div class="research-item-meta"><span class="status-chip ${c.qualified?'qualified':'rejected'}">${c.qualified?'qualified':'rejected'}</span><b class="${Number(c.metrics?.net_pnl)>=0?'positive':'negative'}">${money(c.metrics?.net_pnl)}</b><button class="ep-btn load-candidate" data-candidate="${i}">Inspect</button><button class="ep-btn candidate-remove" data-remove-candidate="${i}" title="Remove saved candidate">×</button></div></div>`).join('');
  root.querySelectorAll('.load-candidate').forEach(b=>b.addEventListener('click',()=>{const rows=loadCandidates(),c=rows[Number(b.dataset.candidate)];if(c)loadCandidate(c)}));
  root.querySelectorAll('.candidate-remove').forEach(b=>b.addEventListener('click',()=>removeCandidate(Number(b.dataset.removeCandidate))));
}

function renderPins(pins){$('researchPinsCount').textContent=pins.length;if(!pins.length)return;$('researchPins').innerHTML=pins.slice().reverse().map((p,i)=>`<div class="research-item"><div class="research-item-index">${itemIndex(i)}</div><div class="research-item-main"><strong>${esc(p.symbol||'—')} · ${esc(p.timeframe||'—')} · ${esc(p.strategy||'—')}</strong><span>${esc(p.profile||'Backtest')} · saved ${esc(date(p.saved_at_ms))}</span></div><div class="research-item-meta"><b class="${Number(p.metrics?.total_equity_pnl)>=0?'positive':'negative'}">${money(p.metrics?.total_equity_pnl)}</b><button class="ep-btn load-pin" data-pin="${esc(p.id)}">Load</button></div></div>`).join('');document.querySelectorAll('.load-pin').forEach(b=>b.addEventListener('click',()=>{const p=pins.find(x=>String(x.id)===b.dataset.pin);if(p)loadPin(p)}))}

async function renderScans(){try{const d=await fetch('/api/scanner/runs?limit=20').then(r=>r.json()),runs=Array.isArray(d.runs)?d.runs:[];$('researchScansCount').textContent=runs.length;if(!runs.length)return;$('researchScans').innerHTML=runs.map((r,i)=>{const b=r.summary?.best_candidate;return `<div class="research-item"><div class="research-item-index">${itemIndex(i)}</div><div class="research-item-main"><strong>${esc(r.objective)}</strong><span>${esc(date(r.completed_at_ms))} · ${r.summary?.evaluated??0} evaluated · ${r.summary?.qualified??0} qualified${b?` · best ${esc(b.symbol)} ${esc(b.timeframe)} ${esc(b.strategy)}`:''}</span></div><div class="research-item-meta"><b>${r.summary?.qualified??0} pass</b><a class="ep-btn" href="/scanner">Open</a></div></div>`}).join('')}catch(e){$('researchScans').innerHTML=`<div class="empty-state"><div><strong>Scanner history unavailable</strong><p>${esc(e.message)}</p></div></div>`;$('researchScansCount').textContent='—'}}

async function renderPresets(){try{const d=await fetch('/api/settings/presets').then(r=>r.json()),rows=Array.isArray(d.presets)?d.presets:[];$('researchPresetsCount').textContent=rows.length;if(!rows.length)return;$('researchPresets').innerHTML=rows.map((p,i)=>{const v=p.payload||{};return `<div class="research-item"><div class="research-item-index">${itemIndex(i)}</div><div class="research-item-main"><strong>${esc(p.name)}</strong><span>${esc(v.symbol||'Any symbol')} · ${esc(v.timeframe||'—')} · ${esc(v.strategy||'—')} · updated ${esc(date(p.updated_at_ms))}</span></div><div class="research-item-meta"><span class="product-badge">preset</span></div></div>`}).join('')}catch(e){$('researchPresets').innerHTML=`<div class="empty-state"><div><strong>Preset library unavailable</strong><p>${esc(e.message)}</p></div></div>`;$('researchPresetsCount').textContent='—'}}

async function renderSessions(){try{const d=await fetch('/api/sessions?limit=250').then(r=>r.json());$('researchSessionsCount').textContent=Array.isArray(d.sessions)?d.sessions.length:0}catch{$('researchSessionsCount').textContent='—'}}

const candidates=loadCandidates(),pins=loadPins();renderCandidates(candidates);renderPins(pins);await Promise.all([renderScans(),renderPresets(),renderSessions()]);
