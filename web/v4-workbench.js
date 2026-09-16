(()=>{
  const PIN_KEY='epinnox.v4.pins.v1';
  const MAX_PINS=8;
  let current=null;
  let lastFingerprint='';
  let lastCaptureAt=0;
  const $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=(v,d=2)=>(v===null||v===undefined||Number.isNaN(Number(v)))?'—':Number(v).toFixed(d);
  const money=(v,d=2)=>(v===null||v===undefined||Number.isNaN(Number(v)))?'—':`$${Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})}`;

  function loadPins(){try{const x=JSON.parse(localStorage.getItem(PIN_KEY)||'[]');return Array.isArray(x)?x:[]}catch{return[]}}
  function savePins(rows){try{localStorage.setItem(PIN_KEY,JSON.stringify(rows.slice(-MAX_PINS)))}catch{}}
  function collectConfig(){
    const ids=['symbol','timeframe','backtestProfile','startDate','endDate','strategy','confirm1','confirm2','confirmationPolicy','confirmationRequired','confirmationWindow','direction','bars','balance','leverage','allocation','pyramiding','entryFee','exitFee','extraCost','netTarget','referral','maintenance','maxBars','stopLoss','manualParams'];
    const out={};for(const id of ids){const el=$(id);if(el)out[id]=el.value}return out;
  }
  function fingerprint(d){const w=d?.backtest_window||{},m=d?.metrics||{};return [d?.symbol,d?.timeframe,d?.strategy,w.start_ts_ms,w.end_ts_ms,m.closed_trades,m.total_equity_pnl].join('|')}
  function capture(data){
    if(!data||!Array.isArray(data.candles)||!Array.isArray(data.trades)||!data.metrics)return;
    const fp=fingerprint(data),now=Date.now();
    if(fp===lastFingerprint&&now-lastCaptureAt<1200)return;
    lastFingerprint=fp;lastCaptureAt=now;current=data;
    annotateTradeRows();updateActions();
    document.dispatchEvent(new CustomEvent('epinnox:workbench-result',{detail:{symbol:data.symbol,timeframe:data.timeframe,strategy:data.strategy}}));
  }

  const nativeJson=Response.prototype.json;
  Response.prototype.json=async function(...args){const data=await nativeJson.apply(this,args);try{capture(data)}catch{}return data};

  function install(){
    if(document.querySelector('link[href="/static/v4-workbench.css"]')===null){const l=document.createElement('link');l.rel='stylesheet';l.href='/static/v4-workbench.css';document.head.appendChild(l)}
    const header=document.querySelector('.dock-header');
    if(header&&!$('workbenchActions')){
      const actions=document.createElement('div');actions.id='workbenchActions';actions.className='workbench-actions';
      actions.innerHTML='<button id="pinResult" class="wb-btn wb-primary" disabled>＋ Pin result</button><button id="comparePins" class="wb-btn">Compare <span id="pinCount" class="wb-count">0</span></button><div class="wb-export-wrap"><button id="exportResult" class="wb-btn" disabled>Export ▾</button><div id="exportMenu" class="wb-menu hidden"><button data-export="trades">Trades CSV</button><button data-export="equity">Equity CSV</button><button data-export="metrics">Metrics CSV</button><button data-export="config">Configuration JSON</button></div></div>';
      header.appendChild(actions);
    }
    if(!$('compareOverlay')){
      const overlay=document.createElement('div');overlay.id='compareOverlay';overlay.className='wb-overlay hidden';overlay.innerHTML='<section class="wb-compare"><header><div><span class="wb-kicker">BACKTEST WORKBENCH</span><h2>Pinned result comparison</h2></div><button id="closeCompare" class="wb-close">×</button></header><div id="pinCards" class="wb-pin-cards"></div><div id="compareTable" class="wb-compare-table"></div><footer><span class="wb-help">Pins store compact experiment metadata locally; current trade/equity exports come from the active result.</span><button id="clearPins" class="wb-btn wb-danger">Clear pins</button></footer></section>';document.body.appendChild(overlay)
    }
    bind();updateActions();observeTrades();
  }

  function bind(){
    $('pinResult')?.addEventListener('click',pinCurrent);
    $('comparePins')?.addEventListener('click',openCompare);
    $('closeCompare')?.addEventListener('click',closeCompare);
    $('compareOverlay')?.addEventListener('click',e=>{if(e.target===$('compareOverlay'))closeCompare()});
    $('clearPins')?.addEventListener('click',()=>{savePins([]);renderCompare();updateActions()});
    $('exportResult')?.addEventListener('click',()=> $('exportMenu')?.classList.toggle('hidden'));
    $('exportMenu')?.addEventListener('click',e=>{const type=e.target?.dataset?.export;if(type)exportCurrent(type);$('exportMenu')?.classList.add('hidden')});
    document.addEventListener('click',e=>{if(!e.target.closest?.('.wb-export-wrap'))$('exportMenu')?.classList.add('hidden')});
    $('tradeRows')?.addEventListener('click',e=>{const row=e.target.closest('tr[data-trade-index]');if(row)focusTrade(Number(row.dataset.tradeIndex),row)});
  }

  function updateActions(){const pins=loadPins();if($('pinCount'))$('pinCount').textContent=String(pins.length);if($('pinResult'))$('pinResult').disabled=!current;if($('exportResult'))$('exportResult').disabled=!current;if($('comparePins'))$('comparePins').disabled=pins.length<1}
  function nextLabel(pins){const letters='ABCDEFGH';return letters[pins.length]||String(pins.length+1)}
  function pinCurrent(){
    if(!current)return;
    let pins=loadPins();const fp=fingerprint(current);
    if(pins.some(x=>x.fingerprint===fp)){setWorkbenchStatus('That result is already pinned.');return}
    const m=current.metrics||{},w=current.backtest_window||{};
    const pin={id:crypto.randomUUID?.()||`${Date.now()}`,fingerprint:fp,label:nextLabel(pins),saved_at_ms:Date.now(),symbol:current.symbol,timeframe:current.timeframe,strategy:current.strategy,profile:current.backtest_profile,entry_model:current.entry_model,window:w,metrics:m,config:collectConfig()};
    pins=[...pins,pin].slice(-MAX_PINS);pins.forEach((p,i)=>p.label='ABCDEFGH'[i]||String(i+1));savePins(pins);updateActions();setWorkbenchStatus(`Pinned ${pin.symbol} ${pin.timeframe} · ${pin.strategy}.`)
  }
  function setWorkbenchStatus(text){const s=$('status');if(s)s.textContent=text}

  function openCompare(){renderCompare();$('compareOverlay')?.classList.remove('hidden')}
  function closeCompare(){$('compareOverlay')?.classList.add('hidden')}
  function renderCompare(){
    const pins=loadPins();updateActions();
    if($('pinCards'))$('pinCards').innerHTML=pins.length?pins.map(p=>`<article class="wb-pin"><div class="wb-pin-label">${esc(p.label)}</div><div><strong>${esc(p.symbol)} · ${esc(p.timeframe)}</strong><span>${esc(p.strategy)}</span></div><div class="wb-pin-actions"><button data-load-pin="${esc(p.id)}">Load</button><button data-remove-pin="${esc(p.id)}">×</button></div></article>`).join(''):'<div class="wb-empty">No pinned results yet.</div>';
    const metrics=[['Total equity P&L','total_equity_pnl',v=>money(v,2)],['Closed P&L','net_pnl_closed',v=>money(v,2)],['Closed trades','closed_trades',v=>n(v,0)],['Trades / day','trades_per_day',v=>n(v,2)],['Win rate','win_rate_pct',v=>`${n(v,2)}%`],['Profit factor','profit_factor',v=>n(v,3)],['Max drawdown','max_drawdown_pct',v=>`${n(v,2)}%`],['Target hit','target_hit_rate_pct',v=>`${n(v,2)}%`],['Fees paid','fees_paid',v=>money(v,2)],['Referral','referral_revenue',v=>money(v,2)],['Median hold','median_bars_to_exit',v=>`${n(v,1)} bars`],['Liquidations','liquidation_exits',v=>n(v,0)]];
    if($('compareTable'))$('compareTable').innerHTML=pins.length?`<table><thead><tr><th>Metric</th>${pins.map(p=>`<th><span class="wb-col-label">${esc(p.label)}</span>${esc(p.symbol)} ${esc(p.timeframe)}</th>`).join('')}</tr></thead><tbody>${metrics.map(([label,key,fmt])=>`<tr><td>${esc(label)}</td>${pins.map(p=>`<td>${esc(fmt(p.metrics?.[key]))}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'';
    $('pinCards')?.querySelectorAll('[data-remove-pin]').forEach(b=>b.addEventListener('click',()=>{savePins(loadPins().filter(p=>p.id!==b.dataset.removePin));renderCompare()}));
    $('pinCards')?.querySelectorAll('[data-load-pin]').forEach(b=>b.addEventListener('click',()=>loadPin(b.dataset.loadPin)));
  }

  function setField(id,value){const el=$(id);if(!el||value===undefined||value===null)return;el.value=String(value);el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}))}
  function loadPin(id){const pin=loadPins().find(p=>p.id===id);if(!pin)return;for(const [key,value] of Object.entries(pin.config||{}))setField(key,value);const tf=pin.config?.timeframe;document.querySelector(`.tf[data-tf="${CSS.escape(String(tf||''))}"]`)?.click();closeCompare();setWorkbenchStatus(`Loaded pin ${pin.label}; backtest recalculating.`)}

  function observeTrades(){const body=$('tradeRows');if(!body)return;const ob=new MutationObserver(()=>annotateTradeRows());ob.observe(body,{childList:true,subtree:false})}
  function annotateTradeRows(){
    const body=$('tradeRows');if(!body||!current)return;const trades=(current.trades||[]).slice().reverse();[...body.querySelectorAll('tr')].forEach((row,i)=>{const t=trades[i];if(!t)return;const original=(current.trades||[]).indexOf(t);row.dataset.tradeIndex=String(original);row.title='Open this trade on the chart';row.classList.add('wb-trade-row')})
  }
  function focusTrade(index,row){
    const trade=current?.trades?.[index];const runtime=window.EpinnoxChartRuntime;if(!trade||!runtime?.chart)return;
    const start=Math.floor(Number(trade.entry_ts_ms)/1000),end=Math.floor(Number(trade.exit_ts_ms)/1000);const span=Math.max(60,end-start),pad=Math.max(120,Math.round(span*.35));
    try{runtime.chart.timeScale().setVisibleRange({from:start-pad,to:end+pad})}catch{}
    document.querySelectorAll('#tradeRows tr').forEach(x=>x.classList.remove('wb-selected-trade'));row?.classList.add('wb-selected-trade');
    document.querySelector('[data-tab="trades"]')?.click();
    const audit=$('tradeAudit');if(audit)audit.innerHTML=`<strong>Trade #${esc(trade.trade)} · ${esc(String(trade.side||'').toUpperCase())}</strong><span>Entry ${esc(new Date(trade.entry_ts_ms).toLocaleString())} @ ${esc(n(trade.entry_price,4))} → Exit ${esc(new Date(trade.exit_ts_ms).toLocaleString())} @ ${esc(n(trade.exit_price,4))} · ${esc(trade.exit_reason)}</span>`;
  }

  function safeCell(v){let s=String(v??'');if(/^[=+\-@]/.test(s))s=`'${s}`;return /[",\n]/.test(s)?`"${s.replaceAll('"','""')}"`:s}
  function csv(rows){if(!rows.length)return'';const keys=Object.keys(rows[0]);return [keys.join(','),...rows.map(r=>keys.map(k=>safeCell(r[k])).join(','))].join('\n')}
  function download(name,text,type='text/csv;charset=utf-8'){const blob=new Blob([text],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),0)}
  function fileStem(){return `${String(current?.symbol||'market').replace(/[^a-z0-9]+/gi,'-')}-${current?.timeframe||'tf'}-${String(current?.strategy||'strategy').replace(/[^a-z0-9]+/gi,'-')}`.toLowerCase()}
  function exportCurrent(type){
    if(!current)return;const stem=fileStem();
    if(type==='trades'){const rows=(current.trades||[]).map(t=>({trade:t.trade,side:t.side,entry_time:new Date(t.entry_ts_ms).toISOString(),exit_time:new Date(t.exit_ts_ms).toISOString(),entry_price:t.entry_price,exit_price:t.exit_price,qty:t.qty,layers:t.layers,leverage:t.leverage,margin:t.margin,gross_pnl:t.gross_pnl,net_pnl:t.net_pnl,entry_fee:t.entry_fee,exit_fee:t.exit_fee,total_fee:t.total_fee,referral_commission:t.referral_commission,funding:t.funding,mae_pct:t.mae_pct,mfe_pct:t.mfe_pct,bars_held:t.bars_held,exit_reason:t.exit_reason}));download(`${stem}-trades.csv`,csv(rows))}
    else if(type==='equity'){download(`${stem}-equity.csv`,csv((current.equity_curve||[]).map(x=>({time:new Date(x.ts_ms).toISOString(),equity:x.equity}))))}
    else if(type==='metrics'){download(`${stem}-metrics.csv`,csv(Object.entries(current.metrics||{}).map(([metric,value])=>({metric,value}))))}
    else if(type==='config'){download(`${stem}-configuration.json`,JSON.stringify({exported_at:new Date().toISOString(),symbol:current.symbol,timeframe:current.timeframe,strategy:current.strategy,profile:current.backtest_profile,entry_model:current.entry_model,params:current.params,window:current.backtest_window,simulation:current.simulation,workspace:collectConfig()},null,2),'application/json')}
    setWorkbenchStatus(`Exported ${type}.`)
  }

  function boot(){install();setTimeout(annotateTradeRows,500)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
  window.EpinnoxWorkbench={pin:pinCurrent,compare:openCompare,export:exportCurrent,get current(){return current},get pins(){return loadPins()}};
})();
