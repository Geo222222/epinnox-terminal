(()=>{
  if(window.__EPINNOX_V4_SHELL__)return;
  window.__EPINNOX_V4_SHELL__=true;
  if(!document.querySelector('script[src="/static/v4-workbench.js"]')){
    const workbench=document.createElement('script');
    workbench.src='/static/v4-workbench.js';
    workbench.defer=true;
    document.body.appendChild(workbench);
  }
  const rail=document.getElementById('sessionRail');
  if(!rail)return;
  const list=document.getElementById('sessionList');
  const count=document.getElementById('sessionCount');
  const backtest=document.getElementById('railBacktest');
  const strategy=document.getElementById('railStrategy');
  if(strategy)strategy.id='openStrategyTab';
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
      const name=s.name||req._terminal_session_name||`${symbolLabel(req.symbol)} ${req.timeframe||''}`.trim();
      const label=activeStates.has(status)?`P-${String(i+1).padStart(2,'0')}`:`H-${String(i+1).padStart(2,'0')}`;
      return `<button class="session-card ${selected===id?'active':''}" data-session-id="${esc(id)}" data-state="${esc(status)}" title="${esc(status)} · ${esc(id)}"><span class="session-code">${label} · ${esc(status.replaceAll('_',' '))}</span><strong>${esc(name)}</strong><span class="session-meta">${esc(symbolLabel(req.symbol))} · ${esc(req.timeframe||'—')} · ${esc(req.strategy||'—')}</span></button>`;
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