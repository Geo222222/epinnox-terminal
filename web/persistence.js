(()=>{
  'use strict';

  const SCHEMA_VERSION=1;
  const LOCAL_KEY='epinnox.workspace.v1';
  const SESSION_KEY='epinnox.session.v1';
  const BACKTEST_META_KEY='epinnox.backtest-meta.v1';
  const persistentIds=[
    'symbol','timeframe','backtestProfile','startDate','endDate','strategy','confirm1','confirm2',
    'confirmationPolicy','confirmationRequired','confirmationWindow','direction','bars','balance',
    'leverage','allocation','pyramiding','entryFee','exitFee','extraCost','netTarget','referral',
    'maintenance','maxBars','stopLoss','manualParams'
  ];
  let presetCache=[];

  const readJson=(storage,key)=>{try{const value=JSON.parse(storage.getItem(key)||'null');return value&&value.schema_version===SCHEMA_VERSION?value:null}catch{return null}};
  const writeJson=(storage,key,value)=>{try{storage.setItem(key,JSON.stringify(value))}catch{}};
  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const optionExists=(el,value)=>!el.options||[...el.options].some(o=>o.value===String(value));

  function setField(id,value,emit=false){
    const el=document.getElementById(id);if(!el||value===undefined||value===null)return false;
    const text=String(value);if(el.tagName==='SELECT'&&!optionExists(el,text))return false;
    if(el.type==='number'&&text!==''&&!Number.isFinite(Number(text)))return false;
    el.value=text;
    if(emit)el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));
    return true;
  }

  function collectWorkspace(){
    const values={};for(const id of persistentIds){const el=document.getElementById(id);if(el)values[id]=el.value}
    return{schema_version:SCHEMA_VERSION,saved_at_ms:Date.now(),mode:document.querySelector('.mode.active')?.dataset.mode||'BACKTEST',values};
  }
  function collectSessionUi(){return{schema_version:SCHEMA_VERSION,saved_at_ms:Date.now(),inspector_tab:document.querySelector('.inspector-tab.active')?.dataset.inspectorTab||'positionPanel',bottom_tab:document.querySelector('.tabbar button.active')?.dataset.tab||'tester',indicator_collapsed:document.getElementById('indicatorPane')?.classList.contains('collapsed')||false}};
  function saveWorkspace(){writeJson(localStorage,LOCAL_KEY,collectWorkspace())}
  function saveSessionUi(){writeJson(sessionStorage,SESSION_KEY,collectSessionUi())}

  function backendDefaults(config){
    const d=config?.defaults||{},terminal=d.terminal||{},account=d.account_defaults||{},econ=d.economics_defaults||{},backtest=d.backtest_defaults||{};
    return{symbol:terminal.default_symbol,timeframe:terminal.default_timeframe,backtestProfile:terminal.default_backtest_profile,strategy:terminal.default_strategy,confirmationPolicy:terminal.default_confirmation_policy,balance:account.starting_balance,leverage:account.leverage,allocation:account.allocation_pct,pyramiding:account.pyramiding,direction:account.direction,entryFee:econ.entry_fee_pct,exitFee:econ.exit_fee_pct,extraCost:econ.extra_cost_pct,netTarget:econ.desired_net_profit_pct,referral:econ.referral_share_pct,maintenance:econ.maintenance_margin_pct,bars:backtest.history_bars};
  }
  function syncTimeframeButtons(value){document.querySelectorAll('.tf').forEach(b=>b.classList.toggle('active',b.dataset.tf===value))}

  function restoreWorkspace(config){
    const saved=readJson(localStorage,LOCAL_KEY),values=saved?.values||backendDefaults(config);
    for(const [id,value] of Object.entries(values))setField(id,value,false);
    if(values.timeframe)syncTimeframeButtons(String(values.timeframe));
    const desired=saved?.mode||config?.defaults?.terminal?.default_mode||'BACKTEST';
    const mode=document.querySelector(`.mode[data-mode="${desired}"]`);if(mode&&!mode.classList.contains('active'))mode.click();
    for(const id of persistentIds){const el=document.getElementById(id);if(!el||id==='timeframe')continue;el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}))}
    const tf=document.getElementById('timeframe')?.value,button=tf&&document.querySelector(`.tf[data-tf="${CSS.escape(tf)}"]`);if(button)button.click();
    saveWorkspace();
  }
  function restoreSessionUi(){
    const saved=readJson(sessionStorage,SESSION_KEY);if(!saved)return;
    document.querySelector(`.inspector-tab[data-inspector-tab="${CSS.escape(String(saved.inspector_tab||''))}"]`)?.click();
    document.querySelector(`.tabbar button[data-tab="${CSS.escape(String(saved.bottom_tab||''))}"]`)?.click();
    const pane=document.getElementById('indicatorPane');if(pane&&Boolean(saved.indicator_collapsed)!==pane.classList.contains('collapsed'))document.getElementById('toggleIndicator')?.click();
  }

  function setPresetStatus(text){const el=document.getElementById('presetStatus');if(el)el.textContent=text}
  async function refreshPresets(){
    const select=document.getElementById('namedPreset');if(!select)return;
    try{const body=await fetch('/api/settings/presets').then(r=>r.json());presetCache=Array.isArray(body.presets)?body.presets:[];const selected=select.value;select.innerHTML='<option value="">Saved preset…</option>'+presetCache.map(p=>`<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)}</option>`).join('');if(presetCache.some(p=>p.name===selected))select.value=selected}catch(error){setPresetStatus(`Preset load failed · ${error.message}`)}
  }
  async function saveNamedPreset(){
    const name=document.getElementById('presetName')?.value.trim();if(!name)return setPresetStatus('Enter a preset name first.');
    try{const response=await fetch('/api/settings/presets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,schema_version:SCHEMA_VERSION,payload:collectWorkspace().values})});const body=await response.json();if(!response.ok)throw new Error(body.detail||'Preset save failed');await refreshPresets();document.getElementById('namedPreset').value=name;setPresetStatus(`Saved “${name}”.`)}catch(error){setPresetStatus(`Preset save failed · ${error.message}`)}
  }
  function applySelectedPreset(){const name=document.getElementById('namedPreset')?.value,preset=presetCache.find(p=>p.name===name);if(!preset)return setPresetStatus('Choose a saved preset first.');for(const [id,value] of Object.entries(preset.payload||{}))setField(id,value,true);const tf=preset.payload?.timeframe,b=tf&&document.querySelector(`.tf[data-tf="${CSS.escape(String(tf))}"]`);if(b)b.click();saveWorkspace();setPresetStatus(`Applied “${name}”.`)}
  async function deleteSelectedPreset(){
    const name=document.getElementById('namedPreset')?.value;if(!name)return setPresetStatus('Choose a saved preset first.');
    try{const response=await fetch(`/api/settings/presets/${encodeURIComponent(name)}`,{method:'DELETE'}),body=await response.json();if(!response.ok)throw new Error(body.detail||'Preset delete failed');await refreshPresets();setPresetStatus(`Deleted “${name}”.`)}catch(error){setPresetStatus(`Preset delete failed · ${error.message}`)}
  }

  async function recoverPaper(){
    const button=document.getElementById('paperRecover');if(button)button.disabled=true;
    try{const response=await fetch('/api/paper-live/recover',{method:'POST'}),body=await response.json();if(!response.ok)throw new Error(body.detail||'Recovery failed');document.dispatchEvent(new CustomEvent('epinnox:session-mutated'))}catch(error){const state=document.getElementById('paperState');if(state)state.textContent=`Paper recovery failed: ${error.message}`}finally{if(button)button.disabled=false;await refreshPaperRecoveryState()}
  }
  async function refreshPaperRecoveryState(){
    const recover=document.getElementById('paperRecover'),badge=document.getElementById('paperBadge');if(!recover||!badge)return;
    try{const state=await fetch('/api/paper-live/status').then(r=>r.json()),needs=state.status==='RECOVERY_REQUIRED';recover.classList.toggle('hidden',!needs);if(state.status&&!['RUNNING','STOPPED'].includes(state.status)){badge.textContent=state.status.replaceAll('_',' ');badge.className=`status-pill ${state.status==='RECOVERED'?'long':'neutral'}`}}catch{}
  }

  async function waitForAppReady(){for(let i=0;i<120;i++){if(document.querySelectorAll('#strategy option').length>0&&document.querySelectorAll('#symbol option').length>0)return true;await new Promise(resolve=>setTimeout(resolve,50))}return false}
  async function bootPersistence(){
    if(!await waitForAppReady())return;
    let config=null;try{config=await fetch('/api/config').then(r=>r.ok?r.json():null)}catch{}
    restoreWorkspace(config);restoreSessionUi();
    for(const id of persistentIds){const el=document.getElementById(id);if(!el)continue;el.addEventListener('input',saveWorkspace);el.addEventListener('change',saveWorkspace)}
    document.querySelectorAll('.mode,.tf').forEach(el=>el.addEventListener('click',saveWorkspace));
    document.querySelectorAll('.inspector-tab,.tabbar button,#toggleIndicator').forEach(el=>el.addEventListener('click',saveSessionUi));
    document.getElementById('presetSave')?.addEventListener('click',saveNamedPreset);document.getElementById('presetApply')?.addEventListener('click',applySelectedPreset);document.getElementById('presetDelete')?.addEventListener('click',deleteSelectedPreset);document.getElementById('namedPreset')?.addEventListener('change',e=>{if(e.target.value)document.getElementById('presetName').value=e.target.value});document.getElementById('paperRecover')?.addEventListener('click',recoverPaper);
    window.addEventListener('beforeunload',()=>{saveWorkspace();saveSessionUi()});await refreshPresets();await refreshPaperRecoveryState();setInterval(refreshPaperRecoveryState,2500);
  }

  const originalFetch=window.fetch.bind(window);
  window.fetch=async(...args)=>{
    const response=await originalFetch(...args);
    try{const target=typeof args[0]==='string'?args[0]:args[0]?.url||'',method=String(args[1]?.method||'GET').toUpperCase();if(target.includes('/api/backtest')&&method==='POST'&&response.ok){const data=await response.clone().json();writeJson(localStorage,BACKTEST_META_KEY,{schema_version:SCHEMA_VERSION,saved_at_ms:Date.now(),symbol:data.symbol,timeframe:data.timeframe,strategy:data.strategy,entry_model:data.entry_model,backtest_profile:data.backtest_profile,backtest_window:data.backtest_window,metrics:data.metrics})}if((target.includes('/api/paper-live/')||target.includes('/api/sessions/'))&&method!=='GET'&&response.ok)document.dispatchEvent(new CustomEvent('epinnox:session-mutated'))}catch{}
    return response;
  };

  window.EpinnoxPersistence={schemaVersion:SCHEMA_VERSION,saveWorkspace,getWorkspace:()=>readJson(localStorage,LOCAL_KEY),getLastBacktestMeta:()=>readJson(localStorage,BACKTEST_META_KEY),clearWorkspace:()=>{localStorage.removeItem(LOCAL_KEY);sessionStorage.removeItem(SESSION_KEY)},listPresets:async()=>fetch('/api/settings/presets').then(r=>r.json()),savePreset:async(name,payload=collectWorkspace().values)=>fetch('/api/settings/presets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,schema_version:SCHEMA_VERSION,payload})}).then(async r=>{const body=await r.json();if(!r.ok)throw new Error(body.detail||'Preset save failed');return body}),deletePreset:async name=>fetch(`/api/settings/presets/${encodeURIComponent(name)}`,{method:'DELETE'}).then(r=>r.json()),applyPreset:payload=>{if(!payload||typeof payload!=='object')return;for(const [id,value] of Object.entries(payload))setField(id,value,true);saveWorkspace()}};

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bootPersistence);else bootPersistence();
})();