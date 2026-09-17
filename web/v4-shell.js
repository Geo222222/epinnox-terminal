(()=>{
  'use strict';
  if(window.__EPINNOX_V4_SHELL__)return;
  window.__EPINNOX_V4_SHELL__=true;

  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const activeStates=new Set(['RUNNING','RECOVERED','RECONCILING','RECOVERY_REQUIRED']);
  let selected=sessionStorage.getItem('epinnox.v4.selectedSession')||'',timer=null;

  function modeButton(mode){return document.querySelector(`.mode[data-mode="${mode}"]`)}
  function setChartActive(on){if(!on)return;document.dispatchEvent(new Event('epinnox:chart-active'))}
  function activateSession(id){selected=id;sessionStorage.setItem('epinnox.v4.selectedSession',id);modeButton('PAPER')?.click();document.dispatchEvent(new CustomEvent('epinnox:session-selected',{detail:{sessionId:id}}))}
  function render(rows){const list=document.getElementById('epSessionList'),count=document.getElementById('epSessionCount');if(!list)return;const active=rows.filter(x=>activeStates.has(String(x.status||'')));if(count)count.textContent=String(active.length);if(!active.length){list.innerHTML='<span>No active paper sessions.</span>';return}list.innerHTML=active.slice(0,5).map((s,i)=>{const id=String(s.session_id||''),status=String(s.status||'UNKNOWN'),req=s.request||{},symbol=String(s.symbol||req.symbol||'—').split('/')[0],tf=s.timeframe||req.timeframe||'—',strategy=s.strategy||req.strategy||'—';return `<button class="ep-session-row" data-session-id="${esc(id)}" data-state="${esc(status)}"><i></i><span><b>P-${String(i+1).padStart(2,'0')} · ${esc(symbol)} ${esc(tf)}</b><em>${esc(strategy)}</em></span></button>`}).join('');list.querySelectorAll('[data-session-id]').forEach(b=>b.addEventListener('click',()=>activateSession(b.dataset.sessionId)))}
  async function refresh(){if(document.hidden)return;try{const r=await fetch('/api/sessions?limit=60',{headers:{accept:'application/json'}});if(!r.ok)throw new Error();const d=await r.json();render(Array.isArray(d.sessions)?d.sessions:[])}catch{const list=document.getElementById('epSessionList');if(list)list.innerHTML='<span>Session registry unavailable.</span>'}}
  function bind(){document.querySelectorAll('.mode').forEach(btn=>btn.addEventListener('click',()=>setChartActive(btn.dataset.mode==='BACKTEST')));document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});document.addEventListener('epinnox:session-mutated',refresh);refresh();timer=setInterval(refresh,5000);window.addEventListener('beforeunload',()=>timer&&clearInterval(timer));window.EpinnoxV4Sessions={refresh,select:activateSession,get selectedSessionId(){return selected}};if(document.body.classList.contains('v5-chart-active'))import('/static/position-lifecycle.js').catch(err=>console.error('Position lifecycle module failed',err));if(new URLSearchParams(location.search).has('universe')){let attempts=0;const open=()=>{const b=document.getElementById('railUniverse');if(b){b.click();document.dispatchEvent(new Event('epinnox:universe-active'));history.replaceState(null,'','/');return}if(++attempts<50)setTimeout(open,50)};setTimeout(open,0)}}

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();