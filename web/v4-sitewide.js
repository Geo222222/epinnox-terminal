(()=>{
  if(window.__EPINNOX_V4_SITEWIDE__)return;
  window.__EPINNOX_V4_SITEWIDE__=true;
  const $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const codeOf=s=>String(s||'').split('/')[0].replace(/[^A-Z0-9]/gi,'').toUpperCase()||'—';

  function icon(symbol,size='sm'){
    if(window.EpinnoxChrome?.iconMarkup)return window.EpinnoxChrome.iconMarkup(symbol,size);
    const c=codeOf(symbol);
    if(c==='ETH')return `<span class="site-token ${size} eth"><svg viewBox="0 0 24 24"><path d="M12 2 5.8 12.2 12 15.8l6.2-3.6L12 2Zm0 15.1-6.2-3.6L12 22l6.2-8.5-6.2 3.6Z"/></svg></span>`;
    if(c==='BTC')return `<span class="site-token ${size} btc">₿</span>`;
    if(c==='SOL')return `<span class="site-token ${size} sol"><i></i><i></i><i></i></span>`;
    if(c==='XRP')return `<span class="site-token ${size} xrp"><svg viewBox="0 0 24 24"><path d="M5 6c1.7 0 2.5.7 3.7 2l3.3 3.5L15.3 8C16.5 6.7 17.3 6 19 6h2l-5.8 6 5.8 6h-2c-1.7 0-2.5-.7-3.7-2L12 12.5 8.7 16C7.5 17.3 6.7 18 5 18H3l5.8-6L3 6h2Z"/></svg></span>`;
    return `<span class="site-token ${size} generic">${esc(c.slice(0,2))}</span>`;
  }

  function installMarketIdentity(){const identity=document.querySelector('.market-identity');if(!identity||$('siteMarketIcon'))return;const holder=document.createElement('span');holder.id='siteMarketIcon';holder.className='site-market-icon';identity.insertBefore(holder,identity.firstChild);updateMarketIdentity();$('symbol')?.addEventListener('change',updateMarketIdentity)}
  function updateMarketIdentity(){const holder=$('siteMarketIcon'),symbol=$('symbol')?.value;if(holder)holder.innerHTML=symbol?icon(symbol,'md'):''}

  function installRailArt(){const rail=$('sessionRail');if(!rail||rail.querySelector('.site-rail-art'))return;const art=document.createElement('div');art.className='site-rail-art';art.innerHTML='<div class="site-rail-art-land"></div><span>DISCIPLINE<br>BUILDS FREEDOM</span>';const foot=rail.querySelector('.rail-foot');rail.insertBefore(art,foot||null)}

  function decorateScanner(){document.querySelectorAll('#v4ScannerRows tr').forEach(row=>{const cell=row.children?.[2];if(!cell||cell.querySelector('.site-inline-asset'))return;const raw=cell.textContent.trim();if(!raw.includes('/'))return;cell.innerHTML=`<span class="site-inline-asset">${icon(raw,'xs')}<span><b>${esc(codeOf(raw))}</b><em>${esc(raw)}</em></span></span>`})}
  function decorateUniverseBottom(){document.querySelectorAll('#universeBottomBody tbody tr').forEach(row=>{const cell=row.children?.[1];if(!cell||cell.querySelector('.site-inline-asset'))return;const raw=cell.textContent.trim();if(!raw||raw.length>20)return;const match=(window.EpinnoxWorkbench?.current?.symbol&&codeOf(window.EpinnoxWorkbench.current.symbol)===raw)?window.EpinnoxWorkbench.current.symbol:`${raw}/USDT:USDT`;cell.innerHTML=`<span class="site-inline-asset compact">${icon(match,'xs')}<span><b>${esc(raw)}</b></span></span>`})}
  function observeTables(){const root=document.querySelector('.workspace');if(!root)return;const run=()=>{decorateScanner();decorateUniverseBottom();updateMarketIdentity()};run();new MutationObserver(run).observe(root,{subtree:true,childList:true})}

  function installSurfacePulse(){const top=document.querySelector('.topbar');if(!top||$('siteSurfacePulse'))return;const pulse=document.createElement('div');pulse.id='siteSurfacePulse';pulse.className='site-surface-pulse';pulse.innerHTML='<i></i><span>INTELLIGENCE ONLINE</span>';top.appendChild(pulse)}

  function boot(){installMarketIdentity();installRailArt();installSurfacePulse();observeTables()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();