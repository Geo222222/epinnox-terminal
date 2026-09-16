(()=>{
  if(window.__EPINNOX_CHART_WORKSTATION_V2__)return;
  window.__EPINNOX_CHART_WORKSTATION_V2__=true;

  const $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
  const fmt=(v,d=2)=>Number.isFinite(Number(v))?Number(v).toFixed(d):'—';
  const sec=ms=>Math.floor(Number(ms)/1000);
  const PREFS_KEY='epinnox.chart.workstation.v2';
  const SERIES_COLORS=['#60a5fa','#f59e0b','#22c55e','#f87171','#a78bfa','#22d3ee','#fb923c','#86efac'];
  const DEFAULT_PREFS={layers:{volume:true,indicators:true,fills:true,drawings:true},hiddenStudies:[],indicatorPane:true};

  function loadPrefs(){
    try{
      const raw=JSON.parse(localStorage.getItem(PREFS_KEY)||'{}');
      return {
        layers:{...DEFAULT_PREFS.layers,...(raw.layers||{})},
        hiddenStudies:new Set(Array.isArray(raw.hiddenStudies)?raw.hiddenStudies:[]),
        indicatorPane:raw.indicatorPane!==false,
      };
    }catch{return {layers:{...DEFAULT_PREFS.layers},hiddenStudies:new Set(),indicatorPane:true}}
  }
  const prefs=loadPrefs();
  const state={runtime:null,latest:null,markers:[],selectedTradeIndex:null,paintQueued:false,toolObserver:null};

  function savePrefs(){
    try{localStorage.setItem(PREFS_KEY,JSON.stringify({layers:prefs.layers,hiddenStudies:[...prefs.hiddenStudies],indicatorPane:prefs.indicatorPane}))}catch{}
  }
  function isBacktestPayload(data){return !!(data&&Array.isArray(data.candles)&&Array.isArray(data.markers)&&data.metrics&&data.entry_model)}
  function filteredRecord(record){
    if(!prefs.layers.indicators)return {};
    return Object.fromEntries(Object.entries(record||{}).filter(([name])=>!prefs.hiddenStudies.has(name)));
  }
  function transformBacktest(data){
    state.latest=data;
    state.markers=(data.markers||[]).map((m,index)=>({...m,__index:index}));
    const clone={...data,markers:[],overlays:filteredRecord(data.overlays),panes:filteredRecord(data.panes)};
    if(!prefs.layers.volume)clone.candles=(data.candles||[]).map(c=>({...c,volume:0}));
    queuePaint();
    queueMicrotask(renderStudyManager);
    return clone;
  }

  const nativeJson=Response.prototype.json;
  Response.prototype.json=async function(...args){
    let data=await nativeJson.apply(this,args);
    try{if(isBacktestPayload(data))data=transformBacktest(data)}catch(err){console.warn('Chart workstation transform failed',err)}
    return data;
  };

  let runtimeValue=window.EpinnoxChartRuntime;
  try{
    Object.defineProperty(window,'EpinnoxChartRuntime',{
      configurable:true,
      enumerable:true,
      get(){return runtimeValue},
      set(value){runtimeValue=value;state.runtime=value;attachRuntime(value)},
    });
  }catch{}
  if(runtimeValue){state.runtime=runtimeValue;attachRuntime(runtimeValue)}

  function attachRuntime(runtime){
    if(!runtime?.chart||!runtime?.candleSeries)return;
    try{runtime.chart.applyOptions({timeScale:{rightOffset:16}})}catch{}
    const ts=runtime.chart.timeScale?.();
    try{ts?.subscribeVisibleTimeRangeChange?.(()=>queuePaint())}catch{}
    try{ts?.subscribeVisibleLogicalRangeChange?.(()=>queuePaint())}catch{}
    try{ts?.subscribeSizeChange?.(()=>queuePaint())}catch{}
    queuePaint();
  }

  function queuePaint(){
    if(state.paintQueued)return;
    state.paintQueued=true;
    requestAnimationFrame(()=>{state.paintQueued=false;renderMarkers();renderSeriesGutter();syncLayerControls()});
  }

  function installChartControls(){
    const actions=document.querySelector('.chart-actions');
    if(!actions||$('cwLayersButton'))return;
    actions.classList.add('cw-chart-actions');
    const indicator=$('toggleIndicator');
    if(indicator){indicator.textContent='Indicators';indicator.title='Manage active indicators';indicator.setAttribute('aria-haspopup','true')}
    const context=document.createElement('span');context.id='cwChartContext';context.className='cw-chart-context';context.textContent='HTX PERPETUAL · BACKTEST';actions.insertBefore(context,actions.firstChild);
    const layers=document.createElement('button');layers.id='cwLayersButton';layers.className='chart-tool cw-control';layers.type='button';layers.innerHTML='Layers <span id="cwLayerCount" class="cw-count">0</span>';layers.setAttribute('aria-haspopup','true');actions.appendChild(layers);
    const fullscreen=document.createElement('button');fullscreen.id='cwFullscreen';fullscreen.className='chart-tool cw-icon-control';fullscreen.type='button';fullscreen.title='Fullscreen chart workspace';fullscreen.setAttribute('aria-label','Fullscreen chart workspace');fullscreen.textContent='⛶';actions.appendChild(fullscreen);

    const toolbar=document.querySelector('.chart-toolbar');
    const layerPop=document.createElement('div');layerPop.id='cwLayersPopover';layerPop.className='cw-popover hidden';toolbar.appendChild(layerPop);
    const studyPop=document.createElement('div');studyPop.id='cwIndicatorsPopover';studyPop.className='cw-popover hidden';toolbar.appendChild(studyPop);

    layers.addEventListener('click',e=>{e.stopPropagation();renderLayerManager();togglePopover(layerPop)});
    indicator?.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();renderStudyManager();togglePopover(studyPop)},true);
    fullscreen.addEventListener('click',async()=>{
      const target=document.querySelector('.chart-workspace');
      try{if(document.fullscreenElement)await document.exitFullscreen();else await target?.requestFullscreen?.()}catch{}
    });
    document.addEventListener('fullscreenchange',()=>document.querySelector('.chart-workspace')?.classList.toggle('cw-fullscreen',!!document.fullscreenElement));
    document.addEventListener('click',e=>{if(!e.target.closest?.('.cw-popover')&&!e.target.closest?.('#cwLayersButton')&&!e.target.closest?.('#toggleIndicator'))closePopovers()});
    document.querySelectorAll('.mode').forEach(btn=>btn.addEventListener('click',()=>setTimeout(updateChartContext,0)));
    updateChartContext();
  }

  function updateChartContext(){
    const mode=$('modeText')?.textContent?.trim()||document.querySelector('.mode.active')?.dataset?.mode||'BACKTEST';
    const el=$('cwChartContext');if(el)el.textContent=`HTX PERPETUAL · ${mode}`;
  }
  function closePopovers(){document.querySelectorAll('.cw-popover').forEach(x=>x.classList.add('hidden'))}
  function togglePopover(el){const show=el.classList.contains('hidden');closePopovers();el.classList.toggle('hidden',!show)}

  function renderLayerManager(){
    const box=$('cwLayersPopover');if(!box)return;
    const rows=[
      ['volume','Volume','Market activity'],
      ['indicators','Indicators','Overlays and indicator pane'],
      ['fills','Backtest fills','Accepted entries and exits'],
      ['drawings','Drawings','Manual chart annotations'],
    ];
    box.innerHTML=`<div class="cw-pop-head"><div><b>CHART LAYERS</b><span>Control visual density without changing strategy logic.</span></div></div><div class="cw-layer-list">${rows.map(([key,label,help])=>`<label class="cw-layer-row"><span><b>${label}</b><em>${help}</em></span><input type="checkbox" data-cw-layer="${key}" ${prefs.layers[key]?'checked':''}></label>`).join('')}<label class="cw-layer-row cw-locked"><span><b>Price & position levels</b><em>Execution context remains visible</em></span><input type="checkbox" checked disabled></label></div>`;
    box.querySelectorAll('[data-cw-layer]').forEach(input=>input.addEventListener('change',()=>setLayer(input.dataset.cwLayer,input.checked)));
  }

  function setLayer(key,value){
    prefs.layers[key]=!!value;savePrefs();
    if(key==='drawings'){applyDrawingVisibility();queuePaint();return}
    if(key==='fills'){queuePaint();return}
    if(key==='indicators'&&!value)$('indicatorPane')?.classList.add('collapsed');
    if(key==='indicators'&&value&&prefs.indicatorPane)$('indicatorPane')?.classList.remove('collapsed');
    triggerVisualRebuild();
  }
  function triggerVisualRebuild(){
    const bars=$('bars');
    if(bars&&document.querySelector('.mode[data-mode="BACKTEST"]')?.classList.contains('active'))bars.dispatchEvent(new Event('input',{bubbles:true}));
    queuePaint();
  }
  function syncLayerControls(){
    const count=(prefs.layers.volume?1:0)+(prefs.layers.indicators?1:0)+(prefs.layers.fills?1:0)+(prefs.layers.drawings?1:0);
    if($('cwLayerCount'))$('cwLayerCount').textContent=String(count);
    document.querySelectorAll('[data-cw-layer]').forEach(input=>{input.checked=!!prefs.layers[input.dataset.cwLayer]});
  }

  function studyNames(){return [...new Set([...Object.keys(state.latest?.overlays||{}),...Object.keys(state.latest?.panes||{})])]}
  function renderStudyManager(){
    const box=$('cwIndicatorsPopover');if(!box)return;
    const names=studyNames();
    box.innerHTML=`<div class="cw-pop-head"><div><b>INDICATORS</b><span>${names.length?`${names.length} active study${names.length===1?'':'ies'}`:'No active studies for this strategy.'}</span></div></div><label class="cw-layer-row cw-pane-row"><span><b>Indicator pane</b><em>Show the lower study pane when present</em></span><input id="cwPaneToggle" type="checkbox" ${prefs.indicatorPane?'checked':''}></label><div class="cw-study-list">${names.map((name,i)=>`<label class="cw-study-row"><span class="cw-series-swatch" style="--cw-series:${SERIES_COLORS[i%SERIES_COLORS.length]}"></span><span><b>${esc(name)}</b><em>${state.latest?.overlays?.[name]?'Price overlay':'Indicator pane'}</em></span><input type="checkbox" data-cw-study="${esc(name)}" ${prefs.hiddenStudies.has(name)?'':'checked'}></label>`).join('')||'<div class="cw-empty">Run a strategy with overlays or pane indicators to manage them here.</div>'}</div>${names.length?'<div class="cw-pop-actions"><button type="button" data-cw-study-action="show">Show all</button><button type="button" data-cw-study-action="hide">Hide all</button></div>':''}`;
    $('cwPaneToggle')?.addEventListener('change',e=>{prefs.indicatorPane=e.target.checked;savePrefs();if(prefs.layers.indicators)$('indicatorPane')?.classList.toggle('collapsed',!prefs.indicatorPane)});
    box.querySelectorAll('[data-cw-study]').forEach(input=>input.addEventListener('change',()=>{input.checked?prefs.hiddenStudies.delete(input.dataset.cwStudy):prefs.hiddenStudies.add(input.dataset.cwStudy);savePrefs();triggerVisualRebuild()}));
    box.querySelectorAll('[data-cw-study-action]').forEach(btn=>btn.addEventListener('click',()=>{if(btn.dataset.cwStudyAction==='show')prefs.hiddenStudies.clear();else names.forEach(name=>prefs.hiddenStudies.add(name));savePrefs();renderStudyManager();triggerVisualRebuild()}));
  }

  function installVisualLayers(){
    const stage=document.querySelector('.chart-stage');if(!stage)return;
    if(!$('cwExecutionLayer')){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.id='cwExecutionLayer';svg.classList.add('cw-execution-layer');stage.appendChild(svg)}
    if(!$('cwSeriesGutter')){const gutter=document.createElement('div');gutter.id='cwSeriesGutter';gutter.className='cw-series-gutter';stage.appendChild(gutter)}
    if(!$('cwMarkerTooltip')){const tip=document.createElement('div');tip.id='cwMarkerTooltip';tip.className='cw-marker-tooltip hidden';stage.appendChild(tip)}
  }

  function visibleRange(){
    try{return state.runtime?.chart?.timeScale?.().getVisibleRange?.()||null}catch{return null}
  }
  function markerReason(m){
    const text=String(m.text||'').toLowerCase();
    if(m.kind==='entry')return m.side==='long'?'LONG':'SHORT';
    if(text.includes('liquid'))return 'LIQ';if(text.includes('target'))return 'TP';if(text.includes('stop'))return 'SL';if(text.includes('time'))return 'TIME';return 'EXIT';
  }
  function markerColor(m){
    const reason=markerReason(m);if(reason==='LONG'||reason==='TP')return '#28d17c';if(reason==='SHORT'||reason==='LIQ'||reason==='SL')return '#f05252';return '#f5a524';
  }
  function candleForMarker(m){return (state.latest?.candles||[]).find(c=>Number(c.ts_ms)===Number(m.ts_ms))||null}
  function markerY(m){
    const series=state.runtime?.candleSeries;if(!series)return null;const candle=candleForMarker(m);
    let price=Number(m.price);
    if(candle){if(m.kind==='entry')price=m.side==='long'?Number(candle.low):Number(candle.high);else price=m.side==='long'?Number(candle.high):Number(candle.low)}
    const y=series.priceToCoordinate?.(price);if(y==null)return null;
    if(m.kind==='entry')return y+(m.side==='long'?9:-9);
    return y+(m.side==='long'?-9:9);
  }
  function markerSvg(m,x,y,detail,selected){
    const color=markerColor(m),reason=markerReason(m),halo=selected?`<circle cx="${x}" cy="${y}" r="10" fill="none" stroke="#d9e8ff" stroke-width="1.5" opacity=".9"/>`:'';
    if(m.kind==='entry'){
      const up=m.side==='long';const pts=up?`${x},${y-6} ${x-5},${y+4} ${x+5},${y+4}`:`${x},${y+6} ${x-5},${y-4} ${x+5},${y-4}`;
      return `${halo}<polygon points="${pts}" fill="#071018" stroke="${color}" stroke-width="2"/>${detail?`<text x="${x+8}" y="${y+4}" fill="${color}" font-size="10" font-weight="700">${reason==='LONG'?'L':'S'}</text>`:''}`;
    }
    const pts=`${x},${y-5} ${x+5},${y} ${x},${y+5} ${x-5},${y}`;
    return `${halo}<polygon points="${pts}" fill="${color}" stroke="#071018" stroke-width="1"/>${detail?`<text x="${x+8}" y="${y+4}" fill="${color}" font-size="9" font-weight="700">${reason}</text>`:''}`;
  }
  function tradeIndexForMarker(m){
    const trades=state.latest?.trades||[],ts=Number(m.ts_ms);
    let idx=trades.findIndex(t=>Number(m.kind==='entry'?t.entry_ts_ms:t.exit_ts_ms)===ts);
    if(idx<0&&m.kind==='entry')idx=trades.findIndex(t=>Number(t.entry_ts_ms)<=ts&&Number(t.exit_ts_ms)>=ts&&String(t.side)===String(m.side));
    return idx;
  }
  function renderMarkers(){
    const svg=$('cwExecutionLayer'),runtime=state.runtime;if(!svg||!runtime?.chart||!runtime?.candleSeries)return;
    const rect=$('chart')?.getBoundingClientRect();if(!rect?.width||!rect?.height)return;
    svg.setAttribute('viewBox',`0 0 ${rect.width} ${rect.height}`);svg.style.width=`${rect.width}px`;svg.style.height=`${rect.height}px`;
    if(!prefs.layers.fills||!state.markers.length){svg.innerHTML='';return}
    const vr=visibleRange();const rows=state.markers.map((m,index)=>({...m,__renderIndex:index,__time:sec(m.ts_ms)})).filter(m=>!vr||(m.__time>=Number(vr.from)&&m.__time<=Number(vr.to)));
    const detail=rows.length<=28,medium=rows.length<=85;
    const html=[];
    for(const m of rows){
      const x=runtime.chart.timeScale().timeToCoordinate?.(m.__time),y=markerY(m);if(x==null||y==null)continue;
      if(!medium){const color=markerColor(m);html.push(`<g class="cw-marker cw-marker-dense" data-cw-marker="${m.__renderIndex}"><circle cx="${x}" cy="${y}" r="3" fill="${color}" opacity=".82"/></g>`);continue}
      const tradeIndex=tradeIndexForMarker(m),selected=tradeIndex>=0&&tradeIndex===state.selectedTradeIndex;
      html.push(`<g class="cw-marker" data-cw-marker="${m.__renderIndex}">${markerSvg(m,x,y,detail,selected)}</g>`);
    }
    svg.innerHTML=html.join('');
    svg.querySelectorAll('[data-cw-marker]').forEach(node=>{
      node.addEventListener('mouseenter',e=>showMarkerTooltip(Number(node.dataset.cwMarker),e));
      node.addEventListener('mousemove',e=>moveMarkerTooltip(e));
      node.addEventListener('mouseleave',hideMarkerTooltip);
      node.addEventListener('click',e=>{e.stopPropagation();openMarkerTrade(Number(node.dataset.cwMarker))});
    });
  }
  function showMarkerTooltip(index,e){
    const m=state.markers[index],tip=$('cwMarkerTooltip');if(!m||!tip)return;const reason=markerReason(m);
    tip.innerHTML=`<b>${m.kind==='entry'?'Backtest entry':'Backtest exit'} · ${esc(reason)}</b><span>${new Date(Number(m.ts_ms)).toLocaleString()} · ${Number.isFinite(Number(m.price))?Number(m.price).toFixed(4):'—'}</span>`;tip.classList.remove('hidden');moveMarkerTooltip(e);
  }
  function moveMarkerTooltip(e){const tip=$('cwMarkerTooltip'),stage=document.querySelector('.chart-stage');if(!tip||!stage)return;const r=stage.getBoundingClientRect();tip.style.left=`${Math.min(r.width-230,Math.max(8,e.clientX-r.left+12))}px`;tip.style.top=`${Math.max(8,e.clientY-r.top-54)}px`}
  function hideMarkerTooltip(){$('cwMarkerTooltip')?.classList.add('hidden')}
  function openMarkerTrade(index){
    const m=state.markers[index];if(!m)return;const tradeIndex=tradeIndexForMarker(m);if(tradeIndex<0)return;
    state.selectedTradeIndex=tradeIndex;renderMarkers();document.querySelector('[data-tab="trades"]')?.click();
    setTimeout(()=>{const row=document.querySelector(`#tradeRows tr[data-trade-index="${tradeIndex}"]`);row?.click();row?.scrollIntoView?.({block:'nearest',behavior:'smooth'})},40);
  }

  function renderSeriesGutter(){
    const gutter=$('cwSeriesGutter'),runtime=state.runtime;if(!gutter||!runtime?.candleSeries)return;
    if(!prefs.layers.indicators||!state.latest?.overlays){gutter.innerHTML='';return}
    const vr=visibleRange(),to=vr?Number(vr.to):Infinity,entries=[];
    let colorIndex=0;
    for(const [name,points] of Object.entries(state.latest.overlays||{})){
      const color=SERIES_COLORS[colorIndex++%SERIES_COLORS.length];if(prefs.hiddenStudies.has(name))continue;
      const valid=(points||[]).filter(p=>Number.isFinite(Number(p.value))&&sec(p.ts_ms)<=to);const point=valid.at(-1);if(!point)continue;
      const y=runtime.candleSeries.priceToCoordinate?.(Number(point.value));if(y==null)continue;entries.push({name,value:Number(point.value),y,color});
    }
    entries.sort((a,b)=>a.y-b.y);const gap=24,max=($('chart')?.clientHeight||500)-24;
    for(let i=0;i<entries.length;i++)entries[i].displayY=Math.max(8,Math.min(max,i?Math.max(entries[i].y,entries[i-1].displayY+gap):entries[i].y));
    for(let i=entries.length-2;i>=0;i--)if(entries[i].displayY>entries[i+1].displayY-gap)entries[i].displayY=Math.max(8,entries[i+1].displayY-gap);
    gutter.innerHTML=entries.map(e=>`<div class="cw-series-label" style="top:${e.displayY}px;--cw-series:${e.color}"><span>${esc(e.name)}</span><b>${fmt(e.value,e.value>=100?2:4)}</b></div>`).join('');
  }

  function applyDrawingVisibility(){
    const hide=$('hideDrawingTool');
    if(hide){const currentlyHidden=hide.classList.contains('active');if(prefs.layers.drawings===currentlyHidden)hide.click()}
    const layer=$('drawingLayer');if(layer)layer.style.visibility=prefs.layers.drawings?'visible':'hidden';
  }

  function compactDrawingToolbar(){
    const bar=$('drawingToolbar');if(!bar||bar.dataset.cwCompact)return;
    const byTool=name=>bar.querySelector(`[data-draw-tool="${name}"]`),byId=id=>$(id);
    const cursor=byTool('cursor'),trend=byTool('trend'),horizontal=byTool('horizontal'),vertical=byTool('vertical'),channel=byTool('channel'),path=byTool('path'),fib=byTool('fib'),text=byTool('text'),ruler=byTool('ruler'),zoom=byTool('zoom');
    const magnet=byId('magnetTool'),keep=byId('keepDrawingTool'),hide=byId('hideDrawingTool'),undo=byId('undoDrawing'),redo=byId('redoDrawing'),del=byId('deleteDrawing'),lock=byId('lockDrawingTool');
    const nodes=[cursor,trend,horizontal,vertical,channel,path,fib,text,ruler,zoom,magnet,keep,hide,undo,redo,del].filter(Boolean);nodes.forEach(n=>n.remove());bar.querySelectorAll('.tool-sep').forEach(n=>n.remove());lock?.remove();
    bar.dataset.cwCompact='1';bar.classList.add('cw-drawing-toolbar');
    const lineWrap=document.createElement('div');lineWrap.className='cw-tool-group';lineWrap.innerHTML='<button type="button" class="cw-menu-tool" aria-label="Line tools" title="Line tools">╱<small>›</small></button><div class="cw-tool-flyout" data-cw-flyout="lines"></div>';lineWrap.querySelector('.cw-tool-flyout').append(...[trend,horizontal,vertical,channel,path].filter(Boolean));
    const noteWrap=document.createElement('div');noteWrap.className='cw-tool-group';noteWrap.innerHTML='<button type="button" class="cw-menu-tool" aria-label="Annotation tools" title="Annotation tools">T<small>›</small></button><div class="cw-tool-flyout" data-cw-flyout="notes"></div>';noteWrap.querySelector('.cw-tool-flyout').append(...[text,ruler].filter(Boolean));
    const moreWrap=document.createElement('div');moreWrap.className='cw-tool-group cw-more-group';moreWrap.innerHTML='<button type="button" class="cw-menu-tool" aria-label="Drawing utilities" title="Drawing utilities">•••</button><div class="cw-tool-flyout cw-utility-flyout" data-cw-flyout="more"></div>';moreWrap.querySelector('.cw-tool-flyout').append(...[undo,redo,del].filter(Boolean));
    if(del){del.title='Delete selected drawing or clear all drawings'}
    bar.append(cursor,lineWrap,fib,noteWrap,zoom);
    const sep=document.createElement('span');sep.className='tool-sep';bar.appendChild(sep);bar.append(...[magnet,keep,hide].filter(Boolean));const sep2=sep.cloneNode();bar.appendChild(sep2);bar.appendChild(moreWrap);
    bar.querySelectorAll('.cw-menu-tool').forEach(btn=>btn.addEventListener('click',e=>{e.stopPropagation();const wrap=btn.closest('.cw-tool-group');bar.querySelectorAll('.cw-tool-group').forEach(x=>{if(x!==wrap)x.classList.remove('open')});wrap.classList.toggle('open')}));
    bar.querySelectorAll('.cw-tool-flyout button').forEach(btn=>btn.addEventListener('click',()=>{btn.closest('.cw-tool-group')?.classList.remove('open');setTimeout(syncToolGroups,0)}));
    cursor?.addEventListener('click',()=>setTimeout(syncToolGroups,0));fib?.addEventListener('click',()=>setTimeout(syncToolGroups,0));zoom?.addEventListener('click',()=>setTimeout(syncToolGroups,0));
    hide?.addEventListener('click',()=>setTimeout(()=>{prefs.layers.drawings=!hide.classList.contains('active');savePrefs();syncLayerControls()},0));
    document.addEventListener('click',e=>{if(!e.target.closest?.('.cw-drawing-toolbar'))bar.querySelectorAll('.cw-tool-group').forEach(x=>x.classList.remove('open'))});
    window.addEventListener('keydown',e=>{if(e.key==='Escape')setTimeout(syncToolGroups,0)});
    applyDrawingVisibility();syncToolGroups();
  }
  function syncToolGroups(){
    const bar=$('drawingToolbar');if(!bar)return;
    const active=bar.querySelector('[data-draw-tool].active')?.dataset?.drawTool||'cursor';
    bar.querySelector('[data-cw-flyout="lines"]')?.parentElement?.classList.toggle('is-active',['trend','horizontal','vertical','channel','path'].includes(active));
    bar.querySelector('[data-cw-flyout="notes"]')?.parentElement?.classList.toggle('is-active',['text','ruler'].includes(active));
  }

  function watchDrawingToolbar(){
    compactDrawingToolbar();if($('drawingToolbar'))return;
    state.toolObserver=new MutationObserver(()=>{if($('drawingToolbar')){compactDrawingToolbar();state.toolObserver?.disconnect();state.toolObserver=null}});state.toolObserver.observe(document.body,{childList:true,subtree:true});
  }

  function bindTradeSelection(){
    document.addEventListener('click',e=>{const row=e.target.closest?.('#tradeRows tr[data-trade-index]');if(!row)return;state.selectedTradeIndex=Number(row.dataset.tradeIndex);queuePaint()},true);
  }

  function boot(){
    installChartControls();installVisualLayers();watchDrawingToolbar();bindTradeSelection();
    if(prefs.indicatorPane===false)$('indicatorPane')?.classList.add('collapsed');
    syncLayerControls();updateChartContext();
    window.EpinnoxChartWorkstation={
      get latest(){return state.latest},
      get layers(){return {...prefs.layers}},
      get hiddenStudies(){return [...prefs.hiddenStudies]},
      setLayer,
      refresh:queuePaint,
    };
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
