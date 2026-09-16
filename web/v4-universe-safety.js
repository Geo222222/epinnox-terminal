(()=>{
  if(window.__EPINNOX_UNIVERSE_SAFETY__)return;
  window.__EPINNOX_UNIVERSE_SAFETY__=true;

  const $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let cache={at:0,rows:[]};
  let reasonTimer=null;

  function active(){return document.body.classList.contains('universe-active')}
  function setResearchChrome(){
    const count=$('sessionCount');
    if(count)count.hidden=active();
    if(active()){
      document.querySelectorAll('.mode').forEach(btn=>btn.setAttribute('aria-disabled',btn.dataset.mode==='BACKTEST'?'false':'true'));
    }else{
      document.querySelectorAll('.mode').forEach(btn=>btn.removeAttribute('aria-disabled'));
      $('universeRejectReasons')?.remove();
    }
  }

  function leaveUniverseForMode(modeButton){
    document.body.classList.remove('universe-active','universe-refined');
    $('railUniverse')?.classList.remove('active');
    $('railBacktest')?.classList.add('active');
    setResearchChrome();
    requestAnimationFrame(()=>modeButton.click());
  }

  document.addEventListener('click',event=>{
    const mode=event.target.closest?.('.mode');
    if(!mode||!active()||mode.dataset.mode==='BACKTEST')return;
    event.preventDefault();
    event.stopImmediatePropagation();
    leaveUniverseForMode(mode);
  },true);

  async function evidenceRows(){
    if(Date.now()-cache.at<30000)return cache.rows;
    const summary=await fetch('/api/scanner/runs?limit=12').then(r=>{if(!r.ok)throw new Error(`scanner runs ${r.status}`);return r.json()});
    const details=await Promise.all((summary.runs||[]).slice(0,12).map(async run=>{
      try{const r=await fetch(`/api/scanner/runs/${encodeURIComponent(run.scan_id)}`);return r.ok?await r.json():null}catch{return null}
    }));
    const dedupe=new Map();
    for(const scan of details.filter(Boolean)){
      for(const row of scan.results||[]){
        const key=[row.symbol,row.timeframe,row.strategy,Number(row.target_buffer_pct||0).toFixed(8)].join('|');
        if(!dedupe.has(key))dedupe.set(key,row);
      }
    }
    cache={at:Date.now(),rows:[...dedupe.values()]};
    return cache.rows;
  }

  function context(){
    const symbol=$('universeSymbol')?.textContent?.trim()||'';
    const parts=($('universeSub')?.textContent||'').split(' · ').map(x=>x.trim());
    return{symbol,strategy:parts[0]||'',timeframe:parts[1]||''};
  }

  function rowOrder(a,b){
    return Number(Boolean(b.qualified))-Number(Boolean(a.qualified))||Number(a.objective_rank??1e9)-Number(b.objective_rank??1e9)||Number(b.net_pnl||0)-Number(a.net_pnl||0);
  }

  async function renderRejectReasons(){
    $('universeRejectReasons')?.remove();
    if(!active()||$('universeQual')?.textContent?.trim().toUpperCase()!=='REJECTED')return;
    const ctx=context();
    if(!ctx.symbol||!ctx.strategy||!ctx.timeframe)return;
    try{
      const rows=await evidenceRows();
      const match=rows.filter(r=>r.symbol===ctx.symbol&&r.strategy===ctx.strategy&&r.timeframe===ctx.timeframe).sort(rowOrder)[0];
      if(!match)return;
      const reasons=Array.isArray(match.reject_reasons)?match.reject_reasons.filter(Boolean):[];
      const card=document.createElement('div');
      card.id='universeRejectReasons';
      card.className='universe-evidence-card universe-reject-card';
      card.innerHTML=`<span>WHY THIS CANDIDATE FAILED</span><strong>${reasons.length?`${reasons.length} qualification gate${reasons.length===1?'':'s'} failed`:'Scanner qualification returned REJECTED'}</strong>${reasons.length?`<div class="universe-reject-list">${reasons.slice(0,5).map(reason=>`<p>× ${esc(reason)}</p>`).join('')}</div>`:'<p>Open the Scanner experiment to inspect the complete qualification evidence.</p>'}<a href="/scanner">Review scanner evidence</a>`;
      $('universeInspectorBody')?.appendChild(card);
    }catch{
      // Qualification state remains authoritative even if explanatory evidence cannot be reloaded.
    }
  }

  function scheduleReasons(){
    if(reasonTimer)clearTimeout(reasonTimer);
    reasonTimer=setTimeout(renderRejectReasons,80);
  }

  function installObservers(){
    const bodyObserver=new MutationObserver(()=>{setResearchChrome();if(active())scheduleReasons()});
    bodyObserver.observe(document.body,{attributes:true,attributeFilter:['class']});
    const targetObserver=new MutationObserver(scheduleReasons);
    const symbol=$('universeSymbol'),qual=$('universeQual'),sub=$('universeSub');
    if(symbol)targetObserver.observe(symbol,{childList:true,characterData:true,subtree:true});
    if(qual)targetObserver.observe(qual,{childList:true,characterData:true,subtree:true});
    if(sub)targetObserver.observe(sub,{childList:true,characterData:true,subtree:true});
    setResearchChrome();
    scheduleReasons();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installObservers,{once:true});
  else installObservers();
})();
