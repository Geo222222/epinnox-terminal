(()=>{
  'use strict';
  if(window.__EPINNOX_V5_CHART_WORKSPACE__)return;
  window.__EPINNOX_V5_CHART_WORKSPACE__=true;

  const $=id=>document.getElementById(id);
  const svg=(name)=>({
    settings:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19 13.5l1.5 1.1-2 3.4-1.8-.7a7.5 7.5 0 0 1-2.1 1.2L14.3 21h-4.6l-.3-2.5a7.5 7.5 0 0 1-2.1-1.2l-1.8.7-2-3.4L5 13.5a7.8 7.8 0 0 1 0-3L3.5 9.4l2-3.4 1.8.7a7.5 7.5 0 0 1 2.1-1.2L9.7 3h4.6l.3 2.5a7.5 7.5 0 0 1 2.1 1.2l1.8-.7 2 3.4L19 10.5a7.8 7.8 0 0 1 0 3z"/></svg>',
    fit:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/><path d="M3 8l5-5m13 5l-5-5M3 16l5 5m13-5l-5 5"/></svg>',
    indicator:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17l5-6 4 3 5-8 4 3"/><path d="M3 21h18"/></svg>',
    collapse:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
    expand:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>',
    close:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    cursor:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3l12 9-6 1-3 6z"/></svg>',
    trend:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18L19 5"/><circle cx="4" cy="18" r="1.5"/><circle cx="19" cy="5" r="1.5"/></svg>',
    horizontal:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h18"/></svg>',
    vertical:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v18"/></svg>',
    channel:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 16L18 5M6 20L20 9"/></svg>',
    path:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17c4-9 7 3 11-6 2-4 4-4 7-5"/></svg>',
    fib:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16M4 9h16M4 13h16M4 17h16M4 21h16"/></svg>',
    text:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14M12 5v14M8 19h8"/></svg>',
    ruler:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 17L17 4l3 3L7 20zM14 7l3 3"/><path d="M10 11l2 2m1-5l2 2m-8 4l2 2"/></svg>',
    zoom:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="M14.5 14.5L21 21M10 7v6M7 10h6"/></svg>',
    magnet:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4v8a6 6 0 0 0 12 0V4h-4v8a2 2 0 0 1-4 0V4z"/></svg>',
    pen:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20l4-1 11-11-3-3L5 16zM14 7l3 3"/></svg>',
    lock:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
    eye:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z"/><circle cx="12" cy="12" r="2.5"/></svg>',
    undo:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7L4 12l5 5"/><path d="M5 12h8a6 6 0 0 1 6 6"/></svg>',
    redo:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 7l5 5-5 5"/><path d="M19 12h-8a6 6 0 0 0-6 6"/></svg>',
    trash:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>'
  }[name]||'');
  const drawIcons={cursor:'cursor',trend:'trend',horizontal:'horizontal',vertical:'vertical',channel:'channel',path:'path',fib:'fib',text:'text',ruler:'ruler',zoom:'zoom'};

  function installDrawingIcons(){document.querySelectorAll('#drawingToolbar [data-draw-tool]').forEach(btn=>{const icon=drawIcons[btn.dataset.drawTool];if(icon)btn.innerHTML=svg(icon)});const ids={magnetTool:'magnet',keepDrawingTool:'pen',lockDrawingTool:'lock',hideDrawingTool:'eye',undoDrawing:'undo',redoDrawing:'redo',deleteDrawing:'trash'};Object.entries(ids).forEach(([id,icon])=>{const b=$(id);if(b)b.innerHTML=svg(icon)})}
  function installQuickStrategy(){const toolbar=document.querySelector('.chart-toolbar'),source=$('strategy');if(!toolbar||!source||$('v5QuickStrategy'))return;const wrap=document.createElement('div');wrap.className='v5-quick-strategy';wrap.innerHTML=`<span class="v5-quick-label">Strategy</span><select id="v5QuickStrategy" aria-label="Primary strategy"></select><button id="v5StrategySettings" class="v5-icon-button" type="button" title="Strategy settings">${svg('settings')}</button>`;toolbar.insertBefore(wrap,toolbar.querySelector('.chart-actions')||null);const quick=$('v5QuickStrategy');const sync=()=>{const prior=quick.value||source.value;quick.innerHTML=[...source.options].map(o=>`<option value="${String(o.value).replaceAll('&','&amp;').replaceAll('"','&quot;')}">${o.textContent}</option>`).join('');quick.value=[...quick.options].some(o=>o.value===source.value)?source.value:prior};sync();new MutationObserver(sync).observe(source,{childList:true});source.addEventListener('change',()=>{if(quick.value!==source.value)quick.value=source.value});quick.addEventListener('change',()=>{if(source.value!==quick.value){source.value=quick.value;source.dispatchEvent(new Event('change',{bubbles:true}))}});$('v5StrategySettings')?.addEventListener('click',openStrategyModal)}
  function installActionIcons(){const fit=$('fitChart'),ind=$('toggleIndicator');if(fit&&!fit.querySelector('svg'))fit.innerHTML=`${svg('fit')}<span>Fit</span>`;if(ind&&!ind.querySelector('svg'))ind.innerHTML=`${svg('indicator')}<span>Indicator</span>`}

  function installPositionDock(){const dock=document.querySelector('.bottom-dock'),tabbar=dock?.querySelector('.tabbar'),pos=$('positionPanel');if(!dock||!tabbar||!pos)return;let tab=tabbar.querySelector('[data-v5-tab="position"]');if(!tab){tab=document.createElement('button');tab.type='button';tab.dataset.v5Tab='position';tab.textContent='Position';tabbar.appendChild(tab)}let host=$('v5PositionDock');if(!host){host=document.createElement('div');host.id='v5PositionDock';host.className='tab hidden v5-position-dock';dock.appendChild(host)}if(pos.parentElement!==host)host.appendChild(pos);pos.classList.add('active');tab.addEventListener('click',()=>{dock.querySelectorAll('.tabbar button').forEach(b=>b.classList.remove('active'));dock.querySelectorAll(':scope > .tab').forEach(p=>p.classList.add('hidden'));tab.classList.add('active');host.classList.remove('hidden')});tabbar.querySelectorAll('button[data-tab]').forEach(btn=>btn.addEventListener('click',()=>{tab.classList.remove('active');host.classList.add('hidden')}))}

  function installStrategyModal(){
    const panel=$('strategyPanel');if(!panel||$('v5StrategyModal'))return;
    const modal=document.createElement('div');modal.id='v5StrategyModal';modal.className='v5-modal hidden';modal.setAttribute('role','dialog');modal.setAttribute('aria-labelledby','v5StrategyModalTitle');
    modal.innerHTML=`<section class="v5-modal-card"><header class="v5-modal-head"><div><span class="eyebrow">EXPERIMENT CONTROL</span><h2 id="v5StrategyModalTitle">Strategy settings</h2></div><div class="v5-modal-head-actions"><span class="v5-auto-apply-note">Auto-apply</span><button class="v5-icon-button" id="v5ModalClose" type="button" aria-label="Close strategy settings">${svg('close')}</button></div></header><div id="v5StrategyModalBody" class="v5-modal-body"></div><footer class="v5-modal-foot"><button id="v5ModalDone" class="v5-modal-primary" type="button">Done</button></footer></section>`;
    document.body.appendChild(modal);$('v5StrategyModalBody').appendChild(panel);panel.classList.add('active');
    $('v5ModalClose')?.addEventListener('click',closeStrategyModal);$('v5ModalDone')?.addEventListener('click',closeStrategyModal);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.classList.contains('hidden'))closeStrategyModal()});
  }
  function openStrategyModal(){const modal=$('v5StrategyModal');if(!modal)return;modal.classList.remove('hidden');requestAnimationFrame(()=>requestAnimationFrame(()=>modal.querySelector('select,input,button')?.focus()))}
  function closeStrategyModal(){const modal=$('v5StrategyModal');if(!modal)return;modal.classList.add('hidden');$('v5StrategySettings')?.focus()}

  function setDockHeight(px){const min=34,max=Math.floor(innerHeight*.45),h=Math.max(min,Math.min(max,px));document.documentElement.style.setProperty('--v5-dock',`${h}px`);try{localStorage.setItem('epinnox.chartDockHeight',String(h))}catch{}}
  function installDockControls(){const dock=document.querySelector('.bottom-dock'),head=dock?.querySelector('.dock-header');if(!dock||!head||$('v5DockControls'))return;const grip=document.createElement('div');grip.id='v5DockResize';grip.className='v5-dock-resize';grip.title='Drag to resize results';dock.prepend(grip);let startY=0,startH=0;grip.addEventListener('pointerdown',e=>{startY=e.clientY;startH=dock.getBoundingClientRect().height;grip.setPointerCapture(e.pointerId);document.body.classList.add('v5-resizing-dock')});grip.addEventListener('pointermove',e=>{if(!grip.hasPointerCapture(e.pointerId))return;setDockHeight(startH+(startY-e.clientY))});grip.addEventListener('pointerup',e=>{if(grip.hasPointerCapture(e.pointerId))grip.releasePointerCapture(e.pointerId);document.body.classList.remove('v5-resizing-dock')});const controls=document.createElement('div');controls.id='v5DockControls';controls.className='v5-dock-controls';controls.innerHTML=`<button id="v5DockSettings" class="v5-icon-button" type="button" title="Strategy settings">${svg('settings')}</button><button id="v5DockToggle" class="v5-icon-button" type="button" title="Collapse results">${svg('collapse')}</button>`;head.appendChild(controls);$('v5DockSettings')?.addEventListener('click',openStrategyModal);$('v5DockToggle')?.addEventListener('click',()=>{const collapsed=document.body.classList.toggle('v5-dock-collapsed');const b=$('v5DockToggle');b.innerHTML=svg(collapsed?'expand':'collapse');b.title=collapsed?'Expand results':'Collapse results';try{localStorage.setItem('epinnox.chartDockCollapsed',collapsed?'1':'0')}catch{}});try{const h=Number(localStorage.getItem('epinnox.chartDockHeight'));if(Number.isFinite(h)&&h>0)setDockHeight(h);if(localStorage.getItem('epinnox.chartDockCollapsed')==='1')document.body.classList.add('v5-dock-collapsed')}catch{}}

  function boot(){installDrawingIcons();installQuickStrategy();installActionIcons();installPositionDock();installStrategyModal();installDockControls();document.dispatchEvent(new Event('epinnox:chart-active'))}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();