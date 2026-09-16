(()=>{
  if(window.__EPINNOX_FINAL_CHROME__)return;
  window.__EPINNOX_FINAL_CHROME__=true;

  const $=id=>document.getElementById(id);
  const WATCH=[
    {symbol:'BTC/USDT:USDT',code:'BTC',name:'Bitcoin'},
    {symbol:'ETH/USDT:USDT',code:'ETH',name:'Ethereum'},
    {symbol:'SOL/USDT:USDT',code:'SOL',name:'Solana'},
    {symbol:'XRP/USDT:USDT',code:'XRP',name:'XRP'},
  ];
  const FAVORITES_KEY='epinnox.v4.favorites.v1';
  const marketCache=new Map();
  let refreshTimer=null,clockTimer=null,universeObserver=null,bodyObserver=null,universeSparkToken=0;

  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=(v,d=2)=>Number.isFinite(Number(v))?Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
  const codeOf=s=>String(s||'').split('/')[0].replace(/[^A-Z0-9]/gi,'').toUpperCase()||'—';
  const iconKind=code=>['BTC','ETH','SOL','XRP'].includes(code)?code.toLowerCase():'generic';
  const loadFavorites=()=>{try{const x=JSON.parse(localStorage.getItem(FAVORITES_KEY)||'[]');return new Set(Array.isArray(x)?x:[])}catch{return new Set()}};
  const saveFavorites=set=>{try{localStorage.setItem(FAVORITES_KEY,JSON.stringify([...set]))}catch{}};

  function iconMarkup(symbol,size='md'){
    const code=codeOf(symbol),kind=iconKind(code);
    if(kind==='eth')return `<span class="asset-icon ${size} eth" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 2 5.8 12.2 12 15.8l6.2-3.6L12 2Zm0 15.1-6.2-3.6L12 22l6.2-8.5-6.2 3.6Z"/></svg></span>`;
    if(kind==='sol')return `<span class="asset-icon ${size} sol" aria-hidden="true"><i></i><i></i><i></i></span>`;
    if(kind==='xrp')return `<span class="asset-icon ${size} xrp" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 6c1.7 0 2.5.7 3.7 2l3.3 3.5L15.3 8C16.5 6.7 17.3 6 19 6h2l-5.8 6 5.8 6h-2c-1.7 0-2.5-.7-3.7-2L12 12.5 8.7 16C7.5 17.3 6.7 18 5 18H3l5.8-6L3 6h2Z"/></svg></span>`;
    if(kind==='btc')return `<span class="asset-icon ${size} btc" aria-hidden="true">₿</span>`;
    return `<span class="asset-icon ${size} generic" aria-hidden="true">${esc(code.slice(0,2))}</span>`;
  }

  function sparkline(values,width=58,height=18){
    const pts=values.map(Number).filter(Number.isFinite);if(pts.length<2)return '';
    const lo=Math.min(...pts),hi=Math.max(...pts),range=hi-lo||1;
    const d=pts.map((v,i)=>`${i?'L':'M'}${(i/(pts.length-1)*width).toFixed(1)},${(height-2-((v-lo)/range)*(height-4)).toFixed(1)}`).join(' ');
    return `<svg class="micro-spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true"><path d="${d}"/></svg>`;
  }

  function installTopbar(){
    const top=document.querySelector('.topbar');if(!top)return;
    const center=top.querySelector('.topbar-center');
    if(center&&!$('chromeTickerDeck')){
      center.id='chromeTickerDeck';center.className='chrome-ticker-deck';
      center.innerHTML=WATCH.map(x=>`<button class="ticker-card" type="button" data-watch="${x.symbol}" title="Open ${x.name}"><span class="ticker-identity">${iconMarkup(x.symbol,'xs')}<b>${x.code}</b></span><span class="ticker-values"><strong data-price>—</strong><em data-change>—</em></span><span class="ticker-spark" data-spark></span></button>`).join('');
      center.querySelectorAll('.ticker-card').forEach(b=>b.addEventListener('click',()=>applySymbol(b.dataset.watch)));
    }
    if(!$('chromeTopTools')){
      const tools=document.createElement('div');tools.id='chromeTopTools';tools.className='chrome-top-tools';
      tools.innerHTML=`<div class="symbol-search-wrap"><span class="search-glyph">⌕</span><input id="chromeSymbolSearch" type="search" autocomplete="off" spellcheck="false" placeholder="Search symbol…" aria-label="Search symbol"><div id="chromeSearchResults" class="chrome-popover search-results hidden"></div></div><button id="chromeAlerts" class="chrome-icon-btn" type="button" title="System alerts" aria-label="System alerts">◌<span class="chrome-notice-dot"></span></button><button id="chromeSettings" class="chrome-icon-btn" type="button" title="Strategy settings" aria-label="Strategy settings">⚙</button><button id="chromeProfile" class="chrome-profile" type="button" aria-label="Epinnox system status"><span>E</span><b>Epinnox<em><i></i> Connected</em></b></button><div id="chromeSystemPopover" class="chrome-popover system-popover hidden"></div>`;
      const modes=top.querySelector('.modes');top.insertBefore(tools,modes||null);
      $('chromeSymbolSearch')?.addEventListener('input',renderSearchResults);
      $('chromeSymbolSearch')?.addEventListener('keydown',e=>{if(e.key==='Enter'){const first=$('chromeSearchResults')?.querySelector('[data-symbol]');if(first){e.preventDefault();applySymbol(first.dataset.symbol);closePopovers()}}if(e.key==='Escape')closePopovers()});
      $('chromeAlerts')?.addEventListener('click',e=>{e.stopPropagation();showSystemPopover('alerts')});
      $('chromeProfile')?.addEventListener('click',e=>{e.stopPropagation();showSystemPopover('profile')});
      $('chromeSettings')?.addEventListener('click',()=>{document.body.classList.remove('universe-active','scanner-active');$('railBacktest')?.click();document.querySelector('.inspector-tab[data-inspector-tab="strategyPanel"]')?.click()});
      document.addEventListener('click',e=>{if(!e.target.closest?.('.symbol-search-wrap')&&!e.target.closest?.('#chromeTopTools'))closePopovers()});
    }
  }

  function installRailIcons(){
    const rail=$('sessionRail');if(!rail)return;
    const mapping={CHART:'⌁',SCANNER:'⌘',UNIVERSE:'⌘',SESSIONS:'▣',RESEARCH:'◇'};
    rail.querySelectorAll('.rail-workspace').forEach(el=>{
      if(el.querySelector('.rail-nav-icon'))return;const strong=el.querySelector('strong');const label=strong?.textContent?.trim()?.toUpperCase();if(!label)return;
      const ico=document.createElement('span');ico.className=`rail-nav-icon rail-nav-${label.toLowerCase()}`;ico.textContent=mapping[label]||'◇';el.insertBefore(ico,el.firstChild);el.classList.add('rail-workspace-polished');
    });
  }

  function installFooter(){
    const bar=document.querySelector('.statusbar');if(!bar||$('chromeFooter'))return;
    const existing=document.createElement('div');existing.className='chrome-footer-system';while(bar.firstChild)existing.appendChild(bar.firstChild);
    const foot=document.createElement('div');foot.id='chromeFooter';foot.className='chrome-footer';
    foot.innerHTML=`<div class="chrome-footer-left"><span class="footer-clock-dot"></span><b id="chromeClock">--:--:--</b></div><div id="chromeFooterTickers" class="chrome-footer-tickers"></div><div class="chrome-footer-right"><span>◇ Evidence First</span><span>★ No Assumptions</span><span>Serve Benjamin ↗</span></div>`;
    bar.appendChild(foot);bar.appendChild(existing);
    tickClock();clockTimer=setInterval(tickClock,1000);
  }

  function installChartAssetHero(){
    const panel=$('positionPanel');if(!panel||$('inspectorAssetHero'))return;
    const hero=document.createElement('div');hero.id='inspectorAssetHero';hero.className='inspector-asset-hero';
    hero.innerHTML=`<div class="inspector-asset-main"><span id="inspectorAssetIcon"></span><div><b id="inspectorAssetSymbol">—</b><span id="inspectorAssetStrategy">Strategy workspace</span></div></div><div id="inspectorAssetSpark" class="inspector-asset-spark"></div>`;
    panel.insertBefore(hero,panel.firstChild);updateCurrentAsset();
  }

  function ensureUniverseDecor(){
    const inspector=document.querySelector('.universe-inspector');if(!inspector)return;
    const line=inspector.querySelector('.universe-symbol-line');
    if(line&&!line.querySelector('.universe-token-icon')){
      const holder=document.createElement('span');holder.className='universe-token-icon';line.insertBefore(holder,line.firstChild);
      const fav=document.createElement('button');fav.type='button';fav.id='universeFavorite';fav.className='universe-favorite';fav.title='Favorite symbol';fav.textContent='☆';line.appendChild(fav);fav.addEventListener('click',toggleUniverseFavorite);
    }
    if(!$('universeMarketCard')){
      const card=document.createElement('section');card.id='universeMarketCard';card.className='universe-market-card';card.innerHTML=`<div class="universe-market-card-head"><span>MARKET PRICE · RECENT</span><b id="universeMarketChange">—</b></div><div id="universeMarketSpark" class="universe-market-spark"><span>Waiting for symbol…</span></div>`;
      const body=$('universeInspectorBody');if(body)body.insertAdjacentElement('afterend',card);
    }
    attachUniverseSymbolObserver();updateUniverseDecoration();
  }

  function attachUniverseSymbolObserver(){
    const el=$('universeSymbol');if(!el||universeObserver)return;
    universeObserver=new MutationObserver(()=>updateUniverseDecoration());universeObserver.observe(el,{childList:true,characterData:true,subtree:true});
  }

  function currentUniverseSymbol(){const t=$('universeSymbol')?.textContent?.trim()||'';return t.includes('/')?t:''}
  function updateUniverseDecoration(){
    const symbol=currentUniverseSymbol(),holder=document.querySelector('.universe-token-icon');if(holder)holder.innerHTML=symbol?iconMarkup(symbol,'lg'):'';
    const fav=$('universeFavorite');if(fav){const set=loadFavorites();fav.textContent=symbol&&set.has(symbol)?'★':'☆';fav.classList.toggle('active',!!symbol&&set.has(symbol));fav.disabled=!symbol}
    if(symbol)loadUniverseSpark(symbol);else if($('universeMarketSpark'))$('universeMarketSpark').innerHTML='<span>Select a symbol to inspect recent price action.</span>';
  }

  function toggleUniverseFavorite(){const symbol=currentUniverseSymbol();if(!symbol)return;const set=loadFavorites();set.has(symbol)?set.delete(symbol):set.add(symbol);saveFavorites(set);updateUniverseDecoration()}

  async function loadUniverseSpark(symbol){
    const token=++universeSparkToken;try{const data=await fetchMarket(symbol,100);if(token!==universeSparkToken)return;const closes=(data.candles||[]).map(c=>Number(c[4])).filter(Number.isFinite),first=closes[0],last=closes.at(-1),chg=first?((last/first)-1)*100:0;
      if($('universeMarketSpark'))$('universeMarketSpark').innerHTML=`${sparkline(closes.slice(-60),260,54)}<div><strong>${num(last,last>=100?2:4)}</strong><span>${chg>=0?'+':''}${num(chg,2)}%</span></div>`;
      const c=$('universeMarketChange');if(c){c.textContent=`${chg>=0?'+':''}${num(chg,2)}%`;c.classList.toggle('negative',chg<0)}
    }catch{if($('universeMarketSpark'))$('universeMarketSpark').innerHTML='<span>Market sparkline unavailable.</span>'}
  }

  function tickClock(){const el=$('chromeClock');if(el)el.textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}

  function symbolOptions(){return [...($('symbol')?.options||[])].map(o=>({value:o.value,label:o.textContent||o.value})).filter(x=>x.value)}
  function renderSearchResults(){const q=($('chromeSymbolSearch')?.value||'').trim().toLowerCase(),box=$('chromeSearchResults');if(!box)return;if(!q){box.classList.add('hidden');box.innerHTML='';return}const rows=symbolOptions().filter(x=>x.value.toLowerCase().includes(q)||x.label.toLowerCase().includes(q)).slice(0,8);box.innerHTML=rows.length?rows.map(x=>`<button type="button" data-symbol="${esc(x.value)}">${iconMarkup(x.value,'xs')}<span><b>${esc(codeOf(x.value))}</b><em>${esc(x.value)}</em></span></button>`).join(''):'<span class="search-empty">No matching symbol</span>';box.classList.remove('hidden');box.querySelectorAll('[data-symbol]').forEach(b=>b.addEventListener('click',()=>{applySymbol(b.dataset.symbol);closePopovers()}))}
  function closePopovers(){$('chromeSearchResults')?.classList.add('hidden');$('chromeSystemPopover')?.classList.add('hidden')}

  async function showSystemPopover(kind){
    const box=$('chromeSystemPopover');if(!box)return;box.classList.toggle('hidden',box.dataset.kind===kind&&!box.classList.contains('hidden'));box.dataset.kind=kind;if(box.classList.contains('hidden'))return;
    box.innerHTML=kind==='profile'?`<div class="system-pop-head">EPINNOX</div><div class="system-row"><span>Terminal</span><b>Connected</b></div><div class="system-row"><span>Intelligence</span><b>Serving Benjamin</b></div><div class="system-note">Command center session is local to this browser.</div>`:`<div class="system-pop-head">SYSTEM STATUS</div><div class="system-row"><span>Market data</span><b>Checking…</b></div>`;
    if(kind==='alerts')try{const s=await fetch('/api/execution/status').then(r=>r.json());box.innerHTML=`<div class="system-pop-head">SYSTEM STATUS</div><div class="system-row"><span>Backtest</span><b>${esc(s.backtest||'—')}</b></div><div class="system-row"><span>Scanner</span><b>${esc(s.scanner||'—')}</b></div><div class="system-row"><span>Paper sessions</span><b>${esc(s.paper_sessions_active??0)} active</b></div><div class="system-row warning"><span>Live routing</span><b>${esc(s.live_order_routing||'not armed')}</b></div>`}catch{box.innerHTML='<div class="system-note">Execution status unavailable.</div>'}
  }

  function applySymbol(symbol){
    const select=$('symbol');if(!select)return;const option=[...select.options].find(o=>o.value===symbol)||[...select.options].find(o=>codeOf(o.value)===codeOf(symbol));if(!option)return;select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));$('chromeSymbolSearch')&&( $('chromeSymbolSearch').value='' );updateCurrentAsset();
  }

  async function fetchMarket(symbol,limit=100){
    const key=`${symbol}|1m|${limit}`,cached=marketCache.get(key);if(cached&&Date.now()-cached.at<12000)return cached.data;
    const r=await fetch(`/api/market?symbol=${encodeURIComponent(symbol)}&timeframe=1m&limit=${limit}`);const d=await r.json();if(!r.ok)throw new Error(d.detail||'market unavailable');marketCache.set(key,{at:Date.now(),data:d});return d;
  }

  async function refreshWatch(){
    if(document.hidden)return;await Promise.allSettled(WATCH.map(async item=>{const data=await fetchMarket(item.symbol,100),closes=(data.candles||[]).map(c=>Number(c[4])).filter(Number.isFinite);if(closes.length<2)return;const first=closes[0],last=closes.at(-1),chg=((last/first)-1)*100;const card=document.querySelector(`[data-watch="${CSS.escape(item.symbol)}"]`);if(card){card.querySelector('[data-price]').textContent=num(last,last>=100?2:4);const ce=card.querySelector('[data-change]');ce.textContent=`${chg>=0?'+':''}${num(chg,2)}%`;ce.classList.toggle('negative',chg<0);card.querySelector('[data-spark]').innerHTML=sparkline(closes.slice(-34),52,15)}marketCache.set(item.symbol,{at:Date.now(),price:last,change:chg,closes})}));renderFooterTickers();updateCurrentAsset()}

  function renderFooterTickers(){const el=$('chromeFooterTickers');if(!el)return;el.innerHTML=WATCH.map(x=>{const d=marketCache.get(x.symbol);return `<span><b>${x.code}</b><em class="${d?.change<0?'negative':''}">${Number.isFinite(d?.change)?`${d.change>=0?'+':''}${num(d.change,2)}%`:'—'}</em></span>`}).join('')}

  function updateCurrentAsset(){
    const symbol=$('symbol')?.value||'';if(!symbol)return;const code=codeOf(symbol),icon=$('inspectorAssetIcon'),label=$('inspectorAssetSymbol'),strategy=$('strategy')?.value||'Strategy workspace';if(icon)icon.innerHTML=iconMarkup(symbol,'lg');if(label)label.textContent=symbol;if($('inspectorAssetStrategy'))$('inspectorAssetStrategy').textContent=strategy;
    const badge=document.querySelector('.symbol-badge');if(badge){badge.innerHTML=iconMarkup(symbol,'sm');badge.title=code}
    const d=marketCache.get(symbol)||marketCache.get(WATCH.find(w=>w.code===code)?.symbol);const spark=$('inspectorAssetSpark');if(spark&&d?.closes)spark.innerHTML=sparkline(d.closes.slice(-32),76,24)
  }

  function observeDynamicUi(){
    if(bodyObserver)return;bodyObserver=new MutationObserver(()=>{installRailIcons();ensureUniverseDecor();installChartAssetHero()});bodyObserver.observe(document.body,{childList:true,subtree:true});
    $('symbol')?.addEventListener('change',()=>{updateCurrentAsset();setTimeout(ensureUniverseDecor,0)});$('strategy')?.addEventListener('change',updateCurrentAsset);document.addEventListener('epinnox:workbench-result',updateCurrentAsset);
  }

  function boot(){installTopbar();installRailIcons();installFooter();installChartAssetHero();ensureUniverseDecor();observeDynamicUi();refreshWatch();refreshTimer=setInterval(refreshWatch,30000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshWatch()})}
  function teardown(){if(refreshTimer)clearInterval(refreshTimer);if(clockTimer)clearInterval(clockTimer);universeObserver?.disconnect();bodyObserver?.disconnect()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  window.addEventListener('beforeunload',teardown,{once:true});
  window.EpinnoxChrome={refresh:refreshWatch,applySymbol,iconMarkup};
})();