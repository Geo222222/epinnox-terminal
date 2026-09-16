(()=>{
  if(window.__EPINNOX_V4_SHELL__)return;
  window.__EPINNOX_V4_SHELL__=true;
  if(!document.querySelector('script[src="/static/v4-workbench.js"]')){
    const workbench=document.createElement('script');
    workbench.src='/static/v4-workbench.js';
    workbench.defer=true;
    document.body.appendChild(workbench);
  }
  if(!document.querySelector('link[href="/static/v4-command-center.css"]')){
    const style=document.createElement('link');
    style.rel='stylesheet';style.href='/static/v4-command-center.css';document.head.appendChild(style);
  }
  if(!document.querySelector('script[src="/static/v4-command-center.js"]')){
    const cc=document.createElement('script');
    cc.src='/static/v4-command-center.js';
    cc.defer=true;
    document.body.appendChild(cc);
  }
  if(!document.querySelector('link[href="/static/v4-universe.css"]')){
    const universeStyle=document.createElement('link');
    universeStyle.rel='stylesheet';universeStyle.href='/static/v4-universe.css';document.head.appendChild(universeStyle);
  }
  if(!document.querySelector('script[src="/static/v4-universe.js"]')){
    const universe=document.createElement('script');
    universe.src='/static/v4-universe.js';
    universe.defer=true;
    document.body.appendChild(universe);
  }
  if(!document.querySelector('link[href="/static/v4-final-chrome.css"]')){
    const chromeStyle=document.createElement('link');
    chromeStyle.rel='stylesheet';chromeStyle.href='/static/v4-final-chrome.css';document.head.appendChild(chromeStyle);
  }
  if(!document.querySelector('script[src="/static/v4-final-chrome.js"]')){
    const chrome=document.createElement('script');
    chrome.src='/static/v4-final-chrome.js';
    chrome.defer=true;
    document.body.appendChild(chrome);
  }
  if(!document.querySelector('link[href="/static/v4-sitewide.css"]')){
    const polishStyle=document.createElement('link');
    polishStyle.rel='stylesheet';polishStyle.href='/static/v4-sitewide.css';document.head.appendChild(polishStyle);
  }
  if(!document.querySelector('script[src="/static/v4-sitewide.js"]')){
    const polish=document.createElement('script');
    polish.src='/static/v4-sitewide.js';
    polish.defer=true;
    document.body.appendChild(polish);
  }
  // Universe research assets load after global chrome so research-only semantics
  // and safety gates own the final behavior/cascade while this surface is active.
  if(!document.querySelector('link[href="/static/v4-universe-refine.css"]')){
    const universeRefineStyle=document.createElement('link');
    universeRefineStyle.rel='stylesheet';universeRefineStyle.href='/static/v4-universe-refine.css';document.head.appendChild(universeRefineStyle);
  }
  if(!document.querySelector('link[href="/static/v4-universe-safety.css"]')){
    const universeSafetyStyle=document.createElement('link');
    universeSafetyStyle.rel='stylesheet';universeSafetyStyle.href='/static/v4-universe-safety.css';document.head.appendChild(universeSafetyStyle);
  }
  if(!document.querySelector('script[src="/static/v4-universe-refine.js"]')){
    const universeRefine=document.createElement('script');
    universeRefine.src='/static/v4-universe-refine.js';
    universeRefine.defer=true;
    document.body.appendChild(universeRefine);
  }
  if(!document.querySelector('script[src="/static/v4-universe-safety.js"]')){
    const universeSafety=document.createElement('script');
    universeSafety.src='/static/v4-universe-safety.js';
    universeSafety.defer=true;
    document.body.appendChild(universeSafety);
  }
  const rail=document.getElementById('sessionRail');
  if(!rail)return;
  const list=document.getElementById('sessionList');
  const count=document.getElementById('sessionCount');
  const backtest=document.getElementById('railBacktest');
  const strategy=document.getElementById('railStrategy');
  if(strategy)strategy.id='openStrategyTab';
  const primary=rail.querySelector('.rail-primary');
  if(primary&&!primary.querySelector('a[href="/sessions"]')){
    primary.insertAdjacentHTML('beforeend','<a class="rail-workspace rail-workspace-link" href="/sessions"><strong>SESSIONS</strong><span>Paper operations</span></a><a class="rail-workspace rail-workspace-link" href="/research"><strong>RESEARCH</strong><span>Evidence library</span></a>');
  }
  const foot=rail.querySelector('.rail-foot');
  if(foot&&!foot.querySelector('a[href="/strategies"]'))foot.insertAdjacentHTML('beforeend','<a class="rail-link" href="/strategies">◇ Strategy library</a>');
  let selected=sessionStorage.getItem('epinnox.v4.selectedSession')||'';
  let timer=null;

  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const symbolLabel=s=>String(s||'—').split(':')[0].replace('/','');
  const activeStates=new Set(['RUNNING','RECOVERED','RECONCILING','RECOVERY_REQUIRED']);

  function modeButton(mode){return document.querySelector(`.mode[data-mode="${mode}"]`)}
  function setBacktestActive(on){backtest?.classList.toggle('active',on)}
  function activateSession(id){
    selected=id;
    sessionStorage.setItem('epinnox.v4.selectedSession',id);
    setBacktestActive(false);
    modeButton('PAPER')?.click();
    list?.querySelectorAll('.session-card').forEach(x=>x.classList.toggle('active',x.dataset.sessionId===id));
    document.dispatchEvent(new CustomEvent('epinnox:session-selected',{detail:{sessionId:id}}));
  }

  function render(rows){
    if(!list)return;
    const active=rows.filter(x=>activeStates.has(String(x.status||'')));
    if(count)count.textContent=String(active.length);
    if(!rows.length){list.innerHTML='<div class="rail-empty">No paper sessions yet.<br>Choose Paper mode and an account to start one.</div>';return}
    list.innerHTML=rows.map((s,i)=>{
      const id=String(s.session_id||'');
      const status=String(s.status||'UNKNOWN');
      const req=s.request||{};
      const name=s.name||`${symbolLabel(s.symbol||req.symbol)} ${s.timeframe||req.timeframe||''}`.trim();
      const label=activeStates.has(status)?`P-${String(i+1).padStart(2,'0')}`:`H-${String(i+1).padStart(2,'0')}`;
      return `<button class="session-card ${selected===id?'active':''}" data-session-id="${esc(id)}" data-state="${esc(status)}" title="${esc(status)} · ${esc(id)}"><span class="session-code">${label} · ${esc(status.replaceAll('_',' '))}</span><strong>${esc(name)}</strong><span class="session-meta">${esc(symbolLabel(s.symbol||req.symbol))} · ${esc(s.timeframe||req.timeframe||'—')} · ${esc(s.strategy||req.strategy||'—')}</span></button>`;
    }).join('');
    list.querySelectorAll('.session-card').forEach(btn=>btn.addEventListener('click',()=>activateSession(btn.dataset.sessionId)));
  }

  async function refresh(){
    if(document.hidden)return;
    try{
      const r=await fetch('/api/sessions?limit=60',{headers:{accept:'application/json'}});
      if(!r.ok)throw new Error(`sessions ${r.status}`);
      const data=await r.json();
      render(Array.isArray(data.sessions)?data.sessions:[]);
      rail.dataset.health='ok';
    }catch(err){
      rail.dataset.health='error';
      if(list&&!list.children.length)list.innerHTML='<div class="rail-empty">Session registry unavailable.</div>';
    }
  }

  backtest?.addEventListener('click',()=>{
    selected='';
    sessionStorage.removeItem('epinnox.v4.selectedSession');
    setBacktestActive(true);
    modeButton('BACKTEST')?.click();
    list?.querySelectorAll('.session-card').forEach(x=>x.classList.remove('active'));
  });
  strategy?.addEventListener('click',()=>document.querySelector('.inspector-tab[data-inspector-tab="strategyPanel"]')?.click());
  document.querySelectorAll('.mode').forEach(btn=>btn.addEventListener('click',()=>setBacktestActive(btn.dataset.mode==='BACKTEST')));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
  document.addEventListener('epinnox:session-mutated',refresh);

  refresh();
  timer=setInterval(refresh,5000);
  window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer)});
  window.EpinnoxV4Sessions={refresh,select:activateSession,get selectedSessionId(){return selected}};
})();