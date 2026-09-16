(()=>{
  if(window.__EPINNOX_UNIVERSE_REFINED__)return;
  window.__EPINNOX_UNIVERSE_REFINED__=true;

  const $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite=(v,d=0)=>Number.isFinite(Number(v))?Number(v):d;
  const n=(v,d=2)=>v===null||v===undefined||Number.isNaN(Number(v))?'—':Number(v).toFixed(d);
  const money=(v,d=2)=>v===null||v===undefined||Number.isNaN(Number(v))?'—':`$${Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})}`;
  const ago=ms=>{const delta=Math.max(0,Date.now()-finite(ms));const m=Math.floor(delta/60000);if(m<1)return'just now';if(m<60)return`${m}m ago`;const h=Math.floor(m/60);if(h<24)return`${h}h ago`;return`${Math.floor(h/24)}d ago`};
  const family=strategy=>{const s=String(strategy||'').toLowerCase();if(s.includes('mean reversion')||s.includes('vwap')||s.includes('stochastic reversal')||(s.includes('bollinger')&&!s.includes('breakout')))return'MEAN REVERSION';if(s.includes('breakout')||s.includes('donchian'))return'BREAKOUT';if(['supertrend','ema','sma','adx','momentum','macd','price channel','rsi momentum'].some(x=>s.includes(x)))return'TREND / MOMENTUM';return'MIXED'};
  const rowOrder=(a,b)=>Number(Boolean(b.qualified))-Number(Boolean(a.qualified))||finite(a.objective_rank,1e9)-finite(b.objective_rank,1e9)||finite(b.net_pnl)-finite(a.net_pnl);
  const scoreNorm=(value,rows,key,invert=false)=>{const vals=rows.map(key).map(x=>finite(x,NaN)).filter(Number.isFinite);if(!vals.length)return.5;const lo=Math.min(...vals),hi=Math.max(...vals);let z=hi<=lo?.5:(finite(value)-lo)/(hi-lo);if(invert)z=1-z;return Math.max(0,Math.min(1,z))};
  const pearson=(a,b)=>{if(a.length!==b.length||a.length<3)return null;const ma=a.reduce((s,x)=>s+x,0)/a.length,mb=b.reduce((s,x)=>s+x,0)/b.length;let top=0,da=0,db=0;for(let i=0;i<a.length;i++){const x=a[i]-ma,y=b[i]-mb;top+=x*y;da+=x*x;db+=y*y}const den=Math.sqrt(da*db);return den>1e-12?Math.max(-1,Math.min(1,top/den)):null};

  let cytoscapeLib=null;
  let cy=null;
  let runs=[];
  let rows=[];
  let projection={nodes:[],edges:[]};
  let selected=null;
  let lens='Opportunity';
  let inspectorTab='Overview';
  let bottomTab='Top Opportunities';
  let autoTimer=null;
  let installed=false;

  async function ensureCytoscape(){
    if(cytoscapeLib)return cytoscapeLib;
    const mod=await import('https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/+esm');
    cytoscapeLib=mod.default||mod;
    return cytoscapeLib;
  }

  function forceResearchMode(){
    const backtest=document.querySelector('.mode[data-mode="BACKTEST"]');
    if(backtest&&!backtest.classList.contains('active'))backtest.click();
  }

  function activateUniverse(){
    forceResearchMode();
    document.body.classList.remove('scanner-active','session-context-active');
    document.body.classList.add('universe-active','universe-refined');
    $('railUniverse')?.classList.add('active');
    document.querySelectorAll('.rail-primary .rail-workspace').forEach(x=>{if(x!==$('railUniverse'))x.classList.remove('active')});
    prepareSurface();
    loadEvidence(true);
  }

  function prepareSurface(){
    if(!$('universeWorkspace'))return;
    const title=document.querySelector('.universe-title');
    if(title){
      const strong=title.querySelector('strong');if(strong)strong.textContent='MARKET UNIVERSE';
      const sub=title.querySelector('span');if(sub)sub.textContent='Cross-scan market evidence, strategy behavior, and qualification coverage.';
      if(!$('universeEvidenceCoverage'))title.insertAdjacentHTML('beforeend','<div id="universeEvidenceCoverage" class="universe-coverage-line">Loading evidence coverage…</div>');
    }
    const refresh=$('universeRefresh');if(refresh)refresh.textContent='Refresh Evidence';
    const regime=document.querySelector('.universe-lens[data-lens="Regime"]');if(regime)regime.hidden=true;
    const paper=$('universePaper');if(paper){paper.textContent='Prepare Paper';paper.title='Loads a qualified candidate into Paper mode. It does not start execution.'}
    const pin=$('universePin');if(pin)pin.textContent='Save Candidate';
    const compare=$('universeCompare');if(compare)compare.textContent='Compare Evidence';
    const oldAuto=$('universeAuto');
    if(oldAuto){
      oldAuto.checked=false;
      oldAuto.dispatchEvent(new Event('change',{bubbles:true}));
      const replacement=oldAuto.cloneNode(true);
      replacement.id='universeAutoV2';replacement.checked=true;
      oldAuto.replaceWith(replacement);
      replacement.addEventListener('change',setupAuto);
    }
    if(!$('universeCoverageCallout')){
      const canvas=document.querySelector('.universe-canvas-panel');
      canvas?.insertAdjacentHTML('beforeend','<div id="universeCoverageCallout" class="universe-coverage-callout hidden"></div>');
    }
    bindOwnedControls();
    setupAuto();
  }

  function bindOwnedControls(){
    if($('universeWorkspace')?.dataset.refinedBound==='1')return;
    $('universeWorkspace').dataset.refinedBound='1';
    const stop=(el,event,fn)=>el?.addEventListener(event,e=>{e.preventDefault();e.stopImmediatePropagation();fn(e)},true);
    stop($('universeRefresh'),'click',()=>loadEvidence(true));
    stop($('universeFit'),'click',()=>cy?.fit(undefined,50));
    stop($('universeRelayout'),'click',()=>layoutGraph());
    stop($('universeOpenBacktest'),'click',()=>openSelected('BACKTEST'));
    stop($('universePaper'),'click',()=>openSelected('PAPER'));
    stop($('universePin'),'click',()=>saveCandidate());
    stop($('universeCompare'),'click',()=>openCompare());
    ['universeStrategy','universeTimeframe','universeMetric'].forEach(id=>{
      const el=$(id);if(!el)return;
      el.addEventListener('change',e=>{e.stopImmediatePropagation();rebuild()},true);
    });
    document.querySelectorAll('.universe-lens').forEach(el=>stop(el,'click',()=>{
      lens=el.dataset.lens||'Opportunity';
      document.querySelectorAll('.universe-lens').forEach(x=>x.classList.toggle('active',x===el));
      applyLens();renderBottom();
    }));
    document.querySelectorAll('[data-universe-tab]').forEach(el=>stop(el,'click',()=>{
      inspectorTab=el.dataset.universeTab||'Overview';
      document.querySelectorAll('[data-universe-tab]').forEach(x=>x.classList.toggle('active',x===el));
      renderInspector();
    }));
    document.querySelectorAll('[data-universe-bottom]').forEach(el=>stop(el,'click',()=>{
      bottomTab=el.dataset.universeBottom||'Top Opportunities';
      document.querySelectorAll('[data-universe-bottom]').forEach(x=>x.classList.toggle('active',x===el));
      renderBottom();
    }));
  }

  function setupAuto(){
    if(autoTimer)clearInterval(autoTimer);
    autoTimer=null;
    if($('universeAutoV2')?.checked)autoTimer=setInterval(()=>{if(document.body.classList.contains('universe-active')&&!document.hidden)loadEvidence(false)},30000);
  }

  async function loadEvidence(force=false){
    if(!document.body.classList.contains('universe-active')&&!force)return;
    const status=$('universeStatus');if(status)status.textContent='Aggregating recent scanner evidence…';
    const refresh=$('universeRefresh');if(refresh)refresh.disabled=true;
    try{
      const summary=await fetch('/api/scanner/runs?limit=12').then(r=>r.json());
      const recent=(summary.runs||[]).slice(0,12);
      const details=await Promise.all(recent.map(async meta=>{
        try{const r=await fetch(`/api/scanner/runs/${encodeURIComponent(meta.scan_id)}`);if(!r.ok)return null;const d=await r.json();return{meta,data:d}}catch{return null}
      }));
      runs=details.filter(Boolean);
      const dedupe=new Map();
      for(const pack of runs){
        const completed=pack.data.completed_at_ms||pack.meta.completed_at_ms||0;
        for(const r of pack.data.results||[]){
          const key=[r.symbol,r.timeframe,r.strategy,finite(r.target_buffer_pct).toFixed(8)].join('|');
          if(dedupe.has(key))continue;
          dedupe.set(key,{...r,__scan_id:pack.data.scan_id,__completed_at_ms:completed,__objective:pack.data.objective});
        }
      }
      rows=[...dedupe.values()];
      rebuild();
      if(status)status.textContent=`${runs.length} scans · ${new Set(rows.map(r=>r.symbol)).size} symbols · ${rows.length} evidence rows`;
    }catch(err){
      if(status)status.textContent=`Universe error · ${err.message}`;
      rows=[];runs=[];rebuild();
    }finally{if(refresh)refresh.disabled=false}
  }

  function rebuild(){
    projection=projectRows();
    renderCoverage();
    renderGraph();
    renderInspector();
    renderBottom();
  }

  function projectRows(){
    const strategy=$('universeStrategy')?.value||'';
    const timeframe=$('universeTimeframe')?.value||'';
    const filtered=rows.filter(r=>(!strategy||r.strategy===strategy)&&(!timeframe||r.timeframe===timeframe));
    const groups=new Map();
    for(const r of filtered){const arr=groups.get(r.symbol)||[];arr.push(r);groups.set(r.symbol,arr)}
    const best=[...groups.entries()].map(([symbol,items])=>({symbol,best:[...items].sort(rowOrder)[0],items}));
    const basis=best.map(x=>x.best);
    const nodes=best.map(({symbol,best:row,items})=>{
      const score=100*(
        .24*scoreNorm(row.profit_factor,basis,x=>x.profit_factor)+
        .18*scoreNorm(row.trades_per_day,basis,x=>x.trades_per_day)+
        .14*scoreNorm(row.win_rate_pct,basis,x=>x.win_rate_pct)+
        .24*scoreNorm(row.walk_forward?.pass_rate_pct,basis,x=>x.walk_forward?.pass_rate_pct)+
        .10*scoreNorm(row.max_drawdown_pct,basis,x=>x.max_drawdown_pct,true)+
        .10*scoreNorm(row.target_hit_rate_pct,basis,x=>x.target_hit_rate_pct)
      );
      const scanCount=new Set(items.map(x=>x.__scan_id)).size;
      return{
        id:symbol,label:String(symbol).split('/')[0],symbol,qualified:Boolean(row.qualified),cluster:family(row.strategy),score,
        strategy:row.strategy,timeframe:row.timeframe,target_buffer_pct:row.target_buffer_pct,metrics:{profit_factor:row.profit_factor,net_pnl:row.net_pnl,net_expectancy_usdt:row.net_expectancy_usdt,trades_per_day:row.trades_per_day,win_rate_pct:row.win_rate_pct,max_drawdown_pct:row.max_drawdown_pct,target_hit_rate_pct:row.target_hit_rate_pct,walk_forward_pass_rate_pct:row.walk_forward?.pass_rate_pct,median_bars_to_exit:row.median_bars_to_exit,fees_per_day:row.fees_per_day,referral_revenue_per_day:row.referral_revenue_per_day},
        load_payload:row.load_payload,source_row:row,items:[...items].sort(rowOrder),scanCount,latestAt:Math.max(...items.map(x=>finite(x.__completed_at_ms)))
      }
    }).sort((a,b)=>Number(b.qualified)-Number(a.qualified)||b.score-a.score).slice(0,40);

    const bySymbol=new Map(nodes.map(n=>[n.symbol,n]));
    const vectors=new Map(nodes.map(n=>[n.symbol,new Map()]));
    for(const r of filtered){
      if(!bySymbol.has(r.symbol))continue;
      vectors.get(r.symbol).set(`${r.strategy}|${r.timeframe}|${finite(r.target_buffer_pct).toFixed(8)}`,finite(r.net_expectancy_usdt));
    }
    const edges=[];
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i],b=nodes[j],va=vectors.get(a.symbol),vb=vectors.get(b.symbol);
      const common=[...va.keys()].filter(k=>vb.has(k));
      let corr=null;
      if(common.length>=3)corr=pearson(common.map(k=>va.get(k)),common.map(k=>vb.get(k)));
      if(corr!==null&&Math.abs(corr)>=.55)edges.push({id:`${i}-${j}`,source:a.id,target:b.id,kind:'response_correlation',value:corr,common:common.length});
      else if(a.strategy===b.strategy)edges.push({id:`s-${i}-${j}`,source:a.id,target:b.id,kind:'strategy_similarity',value:.35,common});
    }
    return{nodes,edges,filtered};
  }

  async function renderGraph(){
    const box=$('universeCy');if(!box)return;
    if(!projection.nodes.length){
      box.innerHTML='';
      $('universeEmpty')?.classList.remove('hidden');
      selected=null;renderInspector();return;
    }
    $('universeEmpty')?.classList.add('hidden');
    try{
      const lib=await ensureCytoscape();
      if(cy)cy.destroy();
      box.innerHTML='';
      cy=lib({container:box,elements:[
        ...projection.nodes.map(x=>({data:{id:x.id,label:x.label,score:x.score,qualified:x.qualified?'yes':'no',cluster:x.cluster}})),
        ...projection.edges.map(e=>({data:e}))
      ],style:[
        {selector:'node',style:{'background-color':'#0a110d','border-width':3,'border-color':ele=>ele.data('qualified')==='yes'?'#16e884':'#d85a62','width':ele=>44+Math.min(34,finite(ele.data('score'))*.34),'height':ele=>44+Math.min(34,finite(ele.data('score'))*.34),'label':'data(label)','color':'#f7fbf9','font-size':'12px','font-weight':700,'text-valign':'center','text-halign':'center','text-outline-width':2,'text-outline-color':'#050805'}},
        {selector:'node:selected',style:{'border-width':5,'border-color':'#f4fff8'}},
        {selector:'edge',style:{'curve-style':'bezier','line-color':ele=>finite(ele.data('value'))<0?'#d8545c':'#557b68','width':ele=>1+Math.abs(finite(ele.data('value')))*2.2,'opacity':.55,'line-style':ele=>ele.data('kind')==='strategy_similarity'?'dashed':'solid'}},
        {selector:'.dimmed',style:{'opacity':.12}},
        {selector:'.hidden-edge',style:{'display':'none'}}
      ],layout:layoutOptions()});
      cy.on('tap','node',event=>{const node=projection.nodes.find(x=>x.id===event.target.id());if(node){selected=node;renderInspector();renderBottom();applyLens()}});
      if(selected){const still=projection.nodes.find(x=>x.id===selected.id);selected=still||projection.nodes[0]}else selected=projection.nodes[0];
      if(selected)cy.$id(selected.id).select();
      applyLens();
    }catch(err){
      $('universeStatus').textContent=`Graph error · ${err.message}`;
    }
  }

  function layoutOptions(){
    if(projection.nodes.length===1)return{name:'preset',positions:{[projection.nodes[0].id]:{x:420,y:260}},fit:true,padding:120};
    if(projection.nodes.length<=5)return{name:'circle',fit:true,padding:100,avoidOverlap:true};
    return{name:'cose',fit:true,padding:65,animate:false,nodeRepulsion:9000,idealEdgeLength:130,componentSpacing:120,gravity:.18,randomize:true};
  }
  function layoutGraph(){if(!cy)return;cy.layout(layoutOptions()).run()}

  function metricValue(node){const metric=$('universeMetric')?.value||'profit_factor';if(metric==='opportunity_score')return node.score;return finite(node.metrics?.[metric])}
  function applyLens(){
    if(!cy)return;
    cy.elements().removeClass('dimmed hidden-edge');
    const legend=$('universeLegendText');
    const metric=$('universeMetric')?.selectedOptions?.[0]?.textContent||'metric';
    if(legend)legend.textContent=`Node size = ${metric.toLowerCase()} · color = qualification`;
    const vals=projection.nodes.map(metricValue);const lo=Math.min(...vals),hi=Math.max(...vals);
    cy.nodes().forEach(ele=>{const node=projection.nodes.find(x=>x.id===ele.id());if(!node)return;const v=metricValue(node);const z=hi<=lo?.5:(v-lo)/(hi-lo);ele.style('width',44+Math.max(0,Math.min(1,z))*34);ele.style('height',44+Math.max(0,Math.min(1,z))*34)});
    if(lens==='Strategy'&&selected){cy.nodes().forEach(ele=>{const n0=projection.nodes.find(x=>x.id===ele.id());if(n0?.strategy!==selected.strategy)ele.addClass('dimmed')})}
    if(lens==='Correlation')cy.edges().forEach(e=>{if(e.data('kind')!=='response_correlation')e.addClass('hidden-edge')});
    if(lens==='Risk'){const max=Math.max(...projection.nodes.map(x=>finite(x.metrics.max_drawdown_pct)),1);cy.nodes().forEach(ele=>{const node=projection.nodes.find(x=>x.id===ele.id());if(node)ele.style('border-width',2+4*(finite(node.metrics.max_drawdown_pct)/max))})}
    if(lens==='Throughput'){const max=Math.max(...projection.nodes.map(x=>finite(x.metrics.trades_per_day)),1);cy.nodes().forEach(ele=>{const node=projection.nodes.find(x=>x.id===ele.id());if(node){const s=44+34*(finite(node.metrics.trades_per_day)/max);ele.style('width',s);ele.style('height',s)}})}
    if(lens==='Economics'){const max=Math.max(...projection.nodes.map(x=>Math.max(0,finite(x.metrics.net_pnl))),1);cy.nodes().forEach(ele=>{const node=projection.nodes.find(x=>x.id===ele.id());if(node){const s=44+34*(Math.max(0,finite(node.metrics.net_pnl))/max);ele.style('width',s);ele.style('height',s)}})}
    if(selected)cy.$id(selected.id).select();
  }

  function renderCoverage(){
    const coverage=$('universeEvidenceCoverage');
    const symbols=new Set(rows.map(r=>r.symbol)).size;
    const qualified=new Set(rows.filter(r=>r.qualified).map(r=>r.symbol)).size;
    const latest=Math.max(0,...runs.map(x=>finite(x.data.completed_at_ms||x.meta.completed_at_ms)));
    if(coverage)coverage.innerHTML=`<span>${runs.length} scans</span><span>${symbols} symbols</span><span>${qualified} qualified</span><span>${latest?`updated ${ago(latest)}`:'no evidence'}</span>`;
    const callout=$('universeCoverageCallout');if(!callout)return;
    if(projection.nodes.length>=3){callout.classList.add('hidden');return}
    const count=projection.nodes.length;
    callout.classList.remove('hidden');
    callout.innerHTML=`<strong>${count?`${count} symbol represented`:'No matching evidence'}</strong><span>${count<3?'A relationship graph needs broader scanner coverage. Scan at least 3 symbols with shared strategies/timeframes to make this surface informative.':'Adjust the current filters.'}</span><a href="/scanner">Open Scanner</a>`;
  }

  function renderInspector(){
    const body=$('universeInspectorBody'),symbol=$('universeSymbol'),qual=$('universeQual'),sub=$('universeSub');
    if(!body)return;
    if(!selected){if(symbol)symbol.textContent='Select a symbol';if(sub)sub.textContent='Choose a node or opportunity row to inspect evidence.';body.innerHTML='<div class="universe-empty-inspector">No evidence selected.</div>';setActions();return}
    if(symbol)symbol.textContent=selected.symbol;
    if(qual){qual.textContent=selected.qualified?'QUALIFIED':'REJECTED';qual.classList.toggle('rejected',!selected.qualified)}
    if(sub)sub.textContent=`${selected.strategy} · ${selected.timeframe} · ${selected.scanCount} scan${selected.scanCount===1?'':'s'} · ${ago(selected.latestAt)}`;
    if(inspectorTab==='Strategies')body.innerHTML=renderStrategies(selected);
    else if(inspectorTab==='Relationships')body.innerHTML=renderRelationships(selected);
    else if(inspectorTab==='History')body.innerHTML=renderHistory(selected);
    else body.innerHTML=renderOverview(selected);
    setActions();
  }

  function renderOverview(node){const m=node.metrics;return `<div class="universe-metric-grid refined"><div><span>Profit factor</span><b>${n(m.profit_factor,2)}</b></div><div><span>Target hit</span><b>${n(m.target_hit_rate_pct,1)}%</b></div><div><span>Net P&L</span><b class="${finite(m.net_pnl)>=0?'good':''}">${money(m.net_pnl)}</b></div><div><span>Median hold</span><b>${n(m.median_bars_to_exit,1)} bars</b></div><div><span>Win rate</span><b>${n(m.win_rate_pct,1)}%</b></div><div><span>Fees/day</span><b>${money(m.fees_per_day,2)}</b></div><div><span>Trades/day</span><b>${n(m.trades_per_day,2)}</b></div><div><span>Referral/day</span><b>${money(m.referral_revenue_per_day,2)}</b></div><div><span>Max drawdown</span><b>${n(m.max_drawdown_pct,2)}%</b></div><div><span>Walk-forward</span><b>${n(m.walk_forward_pass_rate_pct,1)}%</b></div></div><div class="universe-evidence-card"><span>EVIDENCE COVERAGE</span><strong>${node.items.length} rows · ${node.scanCount} scan${node.scanCount===1?'':'s'}</strong><p>Opportunity score ${n(node.score,0)} is a visualization aid built from scanner evidence. Qualification remains the authoritative gate.</p></div>`}
  function renderStrategies(node){return `<div class="universe-strategy-list">${node.items.slice(0,10).map(r=>`<div class="universe-strategy-item"><div><strong>${esc(r.strategy)}</strong><span>${esc(r.timeframe)} · target +${n(r.target_buffer_pct,4)}% · ${r.qualified?'qualified':'rejected'}</span></div><div class="universe-mini-metrics"><b>${n(r.profit_factor,2)} PF</b><span>${money(r.net_pnl)}</span></div></div>`).join('')}</div>`}
  function renderRelationships(node){const rel=projection.edges.filter(e=>e.source===node.id||e.target===node.id).sort((a,b)=>Math.abs(finite(b.value))-Math.abs(finite(a.value)));if(!rel.length)return'<div class="universe-empty-inspector">No sufficiently supported relationships. Broaden scanner coverage with common strategy/timeframe/target combinations.</div>';return `<div class="universe-relation-list">${rel.map(e=>{const other=e.source===node.id?e.target:e.source;const n0=projection.nodes.find(x=>x.id===other);return `<div class="universe-relation-item"><div><strong>${esc(n0?.label||other)}</strong><span>${e.kind==='response_correlation'?`${e.common} common response dimensions`:'Same best strategy'}</span></div><div><b>${e.kind==='response_correlation'?n(e.value,2):'SIM'}</b><span>${e.kind==='response_correlation'?(e.value>=0?'aligned':'diverging'):'strategy'}</span></div></div>`}).join('')}</div><div class="universe-evidence-card compact"><p>Response correlation compares scanner expectancy vectors. It is not raw-price correlation and is not a causal claim.</p></div>`}
  function renderHistory(node){const groups=new Map();for(const r of node.items){const id=r.__scan_id||'unknown';const g=groups.get(id)||{at:r.__completed_at_ms,rows:[]};g.rows.push(r);groups.set(id,g)}return `<div class="universe-history-list">${[...groups.values()].sort((a,b)=>b.at-a.at).map(g=>{const best=[...g.rows].sort(rowOrder)[0];return `<div class="universe-history-item"><div><strong>${new Date(g.at).toLocaleString()}</strong><span>${esc(best.strategy)} · ${esc(best.timeframe)}</span></div><div><b>${best.qualified?'QUALIFIED':'REJECTED'}</b><span>${money(best.net_pnl)} · WF ${n(best.walk_forward?.pass_rate_pct,1)}%</span></div></div>`}).join('')}</div>`}

  function setActions(){
    const open=$('universeOpenBacktest'),save=$('universePin'),compare=$('universeCompare'),paper=$('universePaper');
    if(open)open.disabled=!selected;if(save)save.disabled=!selected;if(compare)compare.disabled=!selected||projection.nodes.length<2;
    if(paper){paper.disabled=!selected||!selected.qualified;paper.classList.toggle('blocked',Boolean(selected&&!selected.qualified));paper.title=selected&&!selected.qualified?'Paper qualification is blocked because this candidate did not pass scanner qualification.':'Loads a qualified candidate into Paper mode; execution still requires explicit account selection and Start.'}
  }

  function renderBottom(){
    const body=$('universeBottomBody');if(!body)return;
    if(bottomTab==='Strategy Heatmap')body.innerHTML=renderHeatmap();
    else if(bottomTab==='Cluster Analysis')body.innerHTML=renderClusters();
    else if(bottomTab==='Timeline')body.innerHTML=renderTimeline();
    else if(bottomTab==='Universe')body.innerHTML=renderUniverseSummary();
    else body.innerHTML=renderOpportunities();
    body.querySelectorAll('[data-universe-symbol]').forEach(el=>el.addEventListener('click',()=>selectSymbol(el.dataset.universeSymbol)));
  }

  function renderOpportunities(){if(!projection.nodes.length)return'<div class="universe-bottom-empty">No matching evidence.</div>';return `<table class="universe-table refined-table"><thead><tr><th>#</th><th>Symbol</th><th>Best strategy</th><th>TF</th><th>Status</th><th>PF</th><th>Trades/day</th><th>Win</th><th>Max DD</th><th>Target hit</th><th>WF pass</th><th>Coverage</th><th>Score</th></tr></thead><tbody>${projection.nodes.map((x,i)=>`<tr data-universe-symbol="${esc(x.id)}" class="${selected?.id===x.id?'selected':''}"><td>${i+1}</td><td><strong>${esc(x.label)}</strong></td><td>${esc(x.strategy)}</td><td>${esc(x.timeframe)}</td><td><span class="universe-row-status ${x.qualified?'ok':'no'}">${x.qualified?'QUALIFIED':'REJECTED'}</span></td><td>${n(x.metrics.profit_factor,2)}</td><td>${n(x.metrics.trades_per_day,2)}</td><td>${n(x.metrics.win_rate_pct,1)}%</td><td>${n(x.metrics.max_drawdown_pct,2)}%</td><td>${n(x.metrics.target_hit_rate_pct,1)}%</td><td>${n(x.metrics.walk_forward_pass_rate_pct,1)}%</td><td>${x.scanCount} scan${x.scanCount===1?'':'s'}</td><td><div class="universe-score"><div class="universe-score-track"><i style="width:${Math.max(0,Math.min(100,x.score))}%"></i></div><span>${n(x.score,0)}</span></div></td></tr>`).join('')}</tbody></table>`}
  function renderHeatmap(){const symbols=projection.nodes.slice(0,8);const strategies=[...new Set(projection.filtered.map(r=>r.strategy))].slice(0,8);if(!symbols.length||!strategies.length)return'<div class="universe-bottom-empty">Not enough evidence for a strategy heatmap.</div>';return `<table class="universe-table heatmap"><thead><tr><th>Strategy</th>${symbols.map(s=>`<th>${esc(s.label)}</th>`).join('')}</tr></thead><tbody>${strategies.map(st=>`<tr><td><strong>${esc(st)}</strong></td>${symbols.map(sym=>{const rs=projection.filtered.filter(r=>r.symbol===sym.symbol&&r.strategy===st).sort(rowOrder);const r=rs[0];if(!r)return'<td class="heat-none">—</td>';const v=Math.max(0,Math.min(100,finite(r.walk_forward?.pass_rate_pct)));return `<td title="PF ${n(r.profit_factor,2)} · P&L ${money(r.net_pnl)}"><span class="heat-cell ${r.qualified?'ok':'no'}" style="--heat:${v/100}">${n(v,0)}</span></td>`}).join('')}</tr>`).join('')}</tbody></table>`}
  function renderClusters(){const groups=new Map();for(const node of projection.nodes){const arr=groups.get(node.cluster)||[];arr.push(node);groups.set(node.cluster,arr)}return `<div class="universe-cluster-grid">${[...groups.entries()].map(([name,items])=>`<article><span>${esc(name)}</span><strong>${items.length} symbols</strong><div><b>${items.filter(x=>x.qualified).length}</b> qualified</div><div><b>${n(items.reduce((s,x)=>s+x.score,0)/items.length,0)}</b> avg score</div><div><b>${n(items.reduce((s,x)=>s+finite(x.metrics.max_drawdown_pct),0)/items.length,1)}%</b> avg DD</div></article>`).join('')}</div>`}
  function renderTimeline(){if(!runs.length)return'<div class="universe-bottom-empty">No persisted scanner runs.</div>';return `<table class="universe-table"><thead><tr><th>Completed</th><th>Objective</th><th>Evaluated</th><th>Qualified</th><th>Rejected</th><th>Errors</th></tr></thead><tbody>${runs.map(x=>{const s=x.data.summary||{};return `<tr><td>${new Date(x.data.completed_at_ms||x.meta.completed_at_ms).toLocaleString()}</td><td>${esc(x.data.objective||'—')}</td><td>${s.evaluated??'—'}</td><td>${s.qualified??'—'}</td><td>${s.rejected??'—'}</td><td>${s.market_errors??0}</td></tr>`}).join('')}</tbody></table>`}
  function renderUniverseSummary(){const qualified=projection.nodes.filter(x=>x.qualified).length;return `<div class="universe-summary-grid"><article><span>Evidence runs</span><strong>${runs.length}</strong></article><article><span>Visible symbols</span><strong>${projection.nodes.length}</strong></article><article><span>Qualified symbols</span><strong>${qualified}</strong></article><article><span>Relationships</span><strong>${projection.edges.length}</strong></article><article><span>Evidence rows</span><strong>${projection.filtered.length}</strong></article></div>`}

  function selectSymbol(id){const node=projection.nodes.find(x=>x.id===id);if(!node)return;selected=node;if(cy){cy.elements().unselect();cy.$id(id).select();cy.animate({center:{eles:cy.$id(id)},duration:180})}renderInspector();renderBottom();applyLens()}

  function workspacePayload(node,mode){
    const p=node?.load_payload||{};
    const existing=(()=>{try{const x=JSON.parse(localStorage.getItem('epinnox.workspace.v1')||'null');return x?.schema_version===1?x:{schema_version:1,values:{}}}catch{return{schema_version:1,values:{}}}})();
    const values={...(existing.values||{}),symbol:node.symbol,timeframe:node.timeframe,strategy:node.strategy,backtestProfile:p.backtest_profile||'TradingView Parity',balance:String(p.starting_balance??100000),leverage:String(p.leverage??1),allocation:String(p.allocation_pct??5),pyramiding:String(p.pyramiding??1),direction:p.direction||'Both',entryFee:String(p.entry_fee_pct??.05),exitFee:String(p.exit_fee_pct??.05),extraCost:String(p.extra_cost_pct??0),netTarget:String(node.target_buffer_pct??0),referral:String(p.referral_share_pct??30),maintenance:String(p.maintenance_margin_pct??.4),bars:String(p.limit??2000),maxBars:p.max_bars_in_trade==null?'':String(p.max_bars_in_trade),stopLoss:p.stop_loss_pct==null?'':String(p.stop_loss_pct),confirmationPolicy:'Single',confirm1:'',confirm2:''};
    return{schema_version:1,saved_at_ms:Date.now(),mode,values};
  }
  function openSelected(mode){if(!selected)return;if(mode==='PAPER'&&!selected.qualified)return;localStorage.setItem('epinnox.workspace.v1',JSON.stringify(workspacePayload(selected,mode)));location.href='/'}

  function saveCandidate(){if(!selected)return;const key='epinnox.universe.saved.v1';let saved=[];try{saved=JSON.parse(localStorage.getItem(key)||'[]');if(!Array.isArray(saved))saved=[]}catch{saved=[]}const item={saved_at_ms:Date.now(),symbol:selected.symbol,strategy:selected.strategy,timeframe:selected.timeframe,qualified:selected.qualified,score:selected.score,metrics:selected.metrics,scan_count:selected.scanCount,load_payload:selected.load_payload};const dedupe=saved.filter(x=>!(x.symbol===item.symbol&&x.strategy===item.strategy&&x.timeframe===item.timeframe));dedupe.unshift(item);localStorage.setItem(key,JSON.stringify(dedupe.slice(0,40)));$('universeStatus').textContent=`Saved ${selected.label} candidate to Research evidence.`}

  function openCompare(){if(!selected||projection.nodes.length<2)return;document.getElementById('universeCompareOverlay')?.remove();const peers=projection.nodes.filter(x=>x.id!==selected.id).slice(0,3);const all=[selected,...peers];const overlay=document.createElement('div');overlay.id='universeCompareOverlay';overlay.className='universe-compare-overlay';overlay.innerHTML=`<section class="universe-compare-panel"><header><div><span>UNIVERSE EVIDENCE</span><strong>Candidate comparison</strong></div><button id="closeUniverseCompare">×</button></header><div class="universe-compare-table"><table><thead><tr><th>Metric</th>${all.map(x=>`<th>${esc(x.label)}<small>${esc(x.strategy)} · ${esc(x.timeframe)}</small></th>`).join('')}</tr></thead><tbody>${[['Qualification',x=>x.qualified?'QUALIFIED':'REJECTED'],['Opportunity score',x=>n(x.score,0)],['Profit factor',x=>n(x.metrics.profit_factor,2)],['Net P&L',x=>money(x.metrics.net_pnl)],['Trades/day',x=>n(x.metrics.trades_per_day,2)],['Win rate',x=>n(x.metrics.win_rate_pct,1)+'%'],['Max drawdown',x=>n(x.metrics.max_drawdown_pct,2)+'%'],['Walk-forward',x=>n(x.metrics.walk_forward_pass_rate_pct,1)+'%'],['Evidence coverage',x=>`${x.scanCount} scan${x.scanCount===1?'':'s'}`]].map(([label,fn])=>`<tr><td>${label}</td>${all.map(x=>`<td>${fn(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><footer>Comparison is descriptive. Scanner qualification remains the gate for Paper preparation.</footer></section>`;document.body.appendChild(overlay);overlay.addEventListener('click',e=>{if(e.target===overlay||e.target.id==='closeUniverseCompare')overlay.remove()})}

  function install(){
    if(installed)return;
    const rail=$('railUniverse'),workspace=$('universeWorkspace');
    if(!rail||!workspace){setTimeout(install,100);return}
    installed=true;
    document.addEventListener('click',e=>{
      const target=e.target.closest?.('#railUniverse');
      if(!target)return;
      e.preventDefault();e.stopImmediatePropagation();activateUniverse();
    },true);
    document.querySelectorAll('.mode').forEach(btn=>btn.addEventListener('click',()=>{if(btn.dataset.mode!=='BACKTEST')document.body.classList.remove('universe-refined')},true));
    prepareSurface();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
})();
