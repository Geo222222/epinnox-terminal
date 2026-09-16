import {createChart,CandlestickSeries,HistogramSeries,LineSeries,createSeriesMarkers} from 'https://cdn.jsdelivr.net/npm/lightweight-charts@5.0.8/+esm';

const $=id=>document.getElementById(id);
let chart,indicator,candleSeries,volumeSeries,currentMode='BACKTEST',paperPoll=null,autoTimer=null,backtestController=null,requestGeneration=0,booting=true,lastBacktest=null;
const palette=['#60a5fa','#f59e0b','#22c55e','#f87171','#a78bfa','#22d3ee','#fb923c','#86efac'];
const strategyControlIds=['backtestProfile','startDate','endDate','strategy','confirm1','confirm2','confirmationPolicy','confirmationRequired','confirmationWindow','direction','bars','balance','leverage','allocation','pyramiding','entryFee','exitFee','extraCost','netTarget','referral','maintenance','maxBars','stopLoss','manualParams'];

function sec(ms){return Math.floor(ms/1000)}
function n(v,d=2){if(v===null||v===undefined||Number.isNaN(Number(v)))return '—';return Number(v).toFixed(d)}
function money(v,d=0){if(v===null||v===undefined||Number.isNaN(Number(v)))return '—';return `$${Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})}`}
function setStatus(x){$('status').textContent=x}
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function showRecalc(on){$('recalcOverlay').classList.toggle('hidden',!on)}
function dateMs(id){const raw=$(id).value;if(!raw)return null;const ms=new Date(raw).getTime();return Number.isFinite(ms)?ms:null}
function dateLabel(ms){return ms?new Date(ms).toLocaleString():'—'}

function initCharts(){
  chart=createChart($('chart'),{autoSize:true,layout:{background:{color:'#070b10'},textColor:'#74839a',fontFamily:'Inter,system-ui,sans-serif'},grid:{vertLines:{color:'#111a24'},horzLines:{color:'#111a24'}},crosshair:{mode:0,vertLine:{color:'#46566c',style:3,labelBackgroundColor:'#172130'},horzLine:{color:'#46566c',style:3,labelBackgroundColor:'#172130'}},rightPriceScale:{borderColor:'#18222d',scaleMargins:{top:.08,bottom:.12}},timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#18222d',rightOffset:5,barSpacing:7}});
  candleSeries=chart.addSeries(CandlestickSeries,{upColor:'#21c97a',downColor:'#f05252',borderVisible:false,wickUpColor:'#21c97a',wickDownColor:'#f05252',priceLineColor:'#3b82f6',priceLineStyle:2,lastValueVisible:true});
  volumeSeries=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'vol',lastValueVisible:false,priceLineVisible:false});
  chart.priceScale('vol').applyOptions({scaleMargins:{top:.84,bottom:0}});
  indicator=createChart($('indicator'),{autoSize:true,layout:{background:{color:'#070b10'},textColor:'#64748b',fontFamily:'Inter,system-ui,sans-serif'},grid:{vertLines:{color:'#101923'},horzLines:{color:'#101923'}},rightPriceScale:{borderColor:'#18222d'},timeScale:{visible:false}});
  chart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)indicator.timeScale().setVisibleLogicalRange(r)});
}
function resetDynamic(){chart?.remove();indicator?.remove();$('chart').innerHTML='';$('indicator').innerHTML='';initCharts()}
function optionList(items,includeNone=false){return `${includeNone?'<option value="">(none)</option>':''}${items.map(s=>`<option>${esc(s)}</option>`).join('')}`}

async function loadConfig(){
  const c=await fetch('/api/config').then(r=>r.json());
  $('strategy').innerHTML=optionList(c.strategies);$('confirm1').innerHTML=optionList(c.strategies,true);$('confirm2').innerHTML=optionList(c.strategies,true);$('confirmationPolicy').innerHTML=c.confirmation_policies.map(x=>`<option>${esc(x)}</option>`).join('');
  if(c.backtest_profiles?.length)$('backtestProfile').innerHTML=c.backtest_profiles.map(x=>`<option>${esc(x)}</option>`).join('');
  $('strategy').value='Supertrend';$('confirmationPolicy').value='Single';$('backtestProfile').value='TradingView Parity';
  try{const s=await fetch('/api/symbols').then(r=>r.json());$('symbol').innerHTML=s.symbols.map(x=>`<option>${esc(x)}</option>`).join('');$('symbol').value=c.default_symbol}catch{$('symbol').innerHTML='<option>ETH/USDT:USDT</option><option>BTC/USDT:USDT</option><option>DOGE/USDT:USDT</option>'}
  syncConfirmationControls();updateStaticHeader();updateAccountGlance();updateProfileHelp();
}

function syncConfirmationControls(){
  const policy=$('confirmationPolicy').value;const single=policy==='Single';
  $('confirm1').disabled=single;$('confirm2').disabled=single;$('confirmationRequired').disabled=single||policy!=='Quorum Recent Events';$('confirmationWindow').disabled=single||policy==='Primary + All States';
  updateStaticHeader();
}
function updateProfileHelp(){
  const parity=$('backtestProfile').value==='TradingView Parity';
  $('profileHelp').textContent=parity?'TradingView Parity disables Terminal liquidation estimates and funding so entry/exit behavior can be compared first.':'Simplified Isolated enables Terminal’s research liquidation estimate. It is not an authoritative HTX liquidation price.';
  $('profileBadge').textContent=$('backtestProfile').value;
}
function requestPayload(){
  const nullable=id=>$(id).value?Number($(id).value):null;let manual=null;const raw=$('manualParams').value.trim();if(raw)manual=JSON.parse(raw);
  const confirmations=[$('confirm1').value,$('confirm2').value].filter(Boolean).filter(x=>x!==$('strategy').value);
  const start=dateMs('startDate'),end=dateMs('endDate');if((start===null)!==(end===null))throw new Error('Set both Start and End, or leave both blank.');if(start!==null&&start>=end)throw new Error('Start must be before End.');
  return{symbol:$('symbol').value,timeframe:$('timeframe').value,strategy:$('strategy').value,confirmations,confirmation_policy:$('confirmationPolicy').value,confirmation_required:Number($('confirmationRequired').value),confirmation_window_bars:Number($('confirmationWindow').value),limit:Number($('bars').value),start_ts_ms:start,end_ts_ms:end,backtest_profile:$('backtestProfile').value,starting_balance:Number($('balance').value),leverage:Number($('leverage').value),allocation_pct:Number($('allocation').value),pyramiding:Number($('pyramiding').value),direction:$('direction').value,entry_fee_pct:Number($('entryFee').value),exit_fee_pct:Number($('exitFee').value),extra_cost_pct:Number($('extraCost').value),desired_net_profit_pct:Number($('netTarget').value),referral_share_pct:Number($('referral').value),maintenance_margin_pct:Number($('maintenance').value),max_bars_in_trade:nullable('maxBars'),stop_loss_pct:nullable('stopLoss'),funding_bps_per_8h:0,manual_params:manual};
}
function receiptSummary(r){if(!Array.isArray(r)||!r.length)return 'single';return r.map(x=>`${x.matched?'✓':'×'} ${x.strategy}${x.age_bars===null||x.age_bars===undefined?'':` (${x.age_bars}b)`}`).join(' · ')}
function shortSymbol(symbol){return(symbol||'ETH').split('/')[0].split(':')[0]}
function updateStaticHeader(){
  if(!$('symbol'))return;const primary=$('strategy')?.value||'Strategy';const policy=$('confirmationPolicy')?.value||'Single';
  $('chartTitle').textContent=`${$('symbol').value||'ETH/USDT:USDT'} · ${$('timeframe').value||'5m'}`;$('entryModelSummary').textContent=`${primary} · ${policy}`;
  const badge=document.querySelector('.symbol-badge');if(badge)badge.textContent=shortSymbol($('symbol').value).slice(0,4);
}
function updateAccountGlance(){
  const balance=Number($('balance').value)||0,lev=Number($('leverage').value)||0,alloc=Number($('allocation').value)||0;
  const notional=balance*lev*(alloc/100);$('glanceBalance').textContent=money(balance,0);$('glanceLeverage').textContent=`${n(lev,0)}×`;$('glanceAllocation').textContent=`${n(alloc,2)}%`;$('glanceNotional').textContent=money(notional,2);
}
function updateMarketHeader(data){
  updateStaticHeader();const candles=data.candles||[];if(!candles.length)return;const last=candles[candles.length-1],prev=candles.length>1?candles[candles.length-2]:last;const chg=prev.close?((last.close-prev.close)/prev.close)*100:0;
  $('quotePrice').textContent=n(last.close,2);$('quoteChange').textContent=`${chg>=0?'+':''}${n(chg,2)}%`;$('quoteChange').className=`market-change ${chg>=0?'positive':'negative'}`;
}

function draw(data){
  resetDynamic();updateMarketHeader(data);
  candleSeries.setData(data.candles.map(c=>({time:sec(c.ts_ms),open:c.open,high:c.high,low:c.low,close:c.close})));
  volumeSeries.setData(data.candles.map(c=>({time:sec(c.ts_ms),value:c.volume,color:c.close>=c.open?'rgba(34,197,94,.20)':'rgba(239,68,68,.18)'})));
  let k=0;for(const [name,pts] of Object.entries(data.overlays||{})){const s=chart.addSeries(LineSeries,{color:palette[k++%palette.length],lineWidth:2,title:name,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});s.setData(pts.map(p=>({time:sec(p.ts_ms),value:p.value})))}
  let j=0;for(const [name,pts] of Object.entries(data.panes||{})){const s=indicator.addSeries(LineSeries,{color:palette[j++%palette.length],lineWidth:2,title:name,priceLineVisible:false,lastValueVisible:true});s.setData(pts.map(p=>({time:sec(p.ts_ms),value:p.value})))}
  const markers=(data.markers||[]).map(m=>({time:sec(m.ts_ms),position:m.kind==='entry'?(m.side==='long'?'belowBar':'aboveBar'):(m.side==='long'?'aboveBar':'belowBar'),color:m.kind==='entry'?(m.side==='long'?'#22c55e':'#ef4444'):'#f59e0b',shape:m.kind==='entry'?(m.side==='long'?'arrowUp':'arrowDown'):'circle',text:m.text})).sort((a,b)=>a.time-b.time);createSeriesMarkers(candleSeries,markers);
  const p=data.open_position;if(p){candleSeries.createPriceLine({price:p.avg_entry,color:'#60a5fa',lineWidth:1,title:'AVG',axisLabelVisible:true});candleSeries.createPriceLine({price:p.break_even,color:'#f59e0b',lineWidth:1,lineStyle:2,title:'B/E'});candleSeries.createPriceLine({price:p.profit_target,color:'#22c55e',lineWidth:1,title:'TARGET'});if(p.liquidation!==null&&p.liquidation!==undefined)candleSeries.createPriceLine({price:p.liquidation,color:'#ef4444',lineWidth:1,lineStyle:2,title:'EST LIQ'});}
  chart.timeScale().fitContent();render(data);
}

function liquidationAuditHtml(t){
  const r=t?.exit_receipt;if(!r)return '<span class="muted">This trade has no liquidation receipt.</span>';
  return `<div class="audit-grid"><div><span>Exit</span><b>ESTIMATED LIQUIDATION</b></div><div><span>Model</span><b>${esc(r.model)}</b></div><div><span>Entry</span><b>${n(r.entry_price)}</b></div><div><span>Estimated liq</span><b class="negative">${n(r.estimated_liquidation_price)}</b></div><div><span>Leverage</span><b>${n(r.leverage,0)}×</b></div><div><span>Maint. margin</span><b>${n(r.maintenance_margin_pct,3)}%</b></div><div><span>Candle low</span><b>${n(r.candle_low)}</b></div><div><span>Candle high</span><b>${n(r.candle_high)}</b></div><div><span>Distance</span><b>${n(r.distance_from_entry_pct,4)}%</b></div></div><p class="muted">${esc(r.note)}</p>`;
}
function showTradeAudit(tradeNo){const t=lastBacktest?.trades?.find(x=>Number(x.trade)===Number(tradeNo));$('tradeAudit').innerHTML=liquidationAuditHtml(t)}

function render(d){
  lastBacktest=d;const m=d.metrics;const cls=v=>Number(v)>=0?'positive':'negative';const model=d.entry_model||{label:d.strategy,policy:'Single',window_bars:1};$('entryModelSummary').textContent=`${model.label} · ${model.policy}`;$('profileBadge').textContent=d.backtest_profile||'TradingView Parity';
  const metricDefs=[['Net P&L',m.total_equity_pnl,4],['Open P&L',m.open_pnl,4],['Profit factor',m.profit_factor,3],['Win rate',m.win_rate_pct,2,'%'],['Max drawdown',m.max_drawdown_pct,2,'%'],['Target hit',m.target_hit_rate_pct,2,'%'],['Liquidations',m.liquidation_exits,0],['Median hold',m.median_bars_to_exit,1,' bars'],['Fees paid',m.fees_paid,4],['Referral',m.referral_revenue,4],['Trades/day',m.trades_per_day,2],['Closed trades',m.closed_trades,0]];
  const w=d.backtest_window||{};const sim=d.simulation||{};
  $('tester').innerHTML=`<div class="metrics">${metricDefs.map(([a,b,digits,suffix=''])=>`<div class="metric"><span class="muted">${a}</span><b class="${a.includes('P&L')?cls(b):''}">${n(b,digits)}${suffix}</b></div>`).join('')}</div><p class="muted"><b style="color:#aebdce">Profile:</b> ${esc(d.backtest_profile||'—')} · <b style="color:#aebdce">Liquidation:</b> ${esc(sim.liquidation_model||'—')} · <b style="color:#aebdce">Entry:</b> ${esc(sim.entry_timing||'—')}</p>`;
  $('windowCandles').textContent=`${w.candles??0} candles`;$('windowSummary').innerHTML=`<b>${esc(d.backtest_profile||'—')}</b><br><span class="muted">From</span> ${esc(dateLabel(w.start_ts_ms))}<br><span class="muted">To</span> ${esc(dateLabel(w.end_ts_ms))}<br><span class="muted">Liquidation model</span> ${esc(sim.liquidation_model||'—')}`;
  $('tradeRows').innerHTML=d.trades.slice().reverse().map(t=>`<tr class="${t.exit_reason==='liquidation'?'liquidation-row':''}"><td>${t.trade}</td><td class="${t.side==='long'?'positive':'negative'}">${esc(t.side.toUpperCase())}</td><td title="${esc(receiptSummary(t.entry_confirmation))}">${esc(receiptSummary(t.entry_confirmation))}</td><td>${t.layers}</td><td>${n(t.entry_price)}</td><td>${n(t.exit_price)}</td><td class="${cls(t.net_pnl)}">${n(t.net_pnl,4)}</td><td>${n(t.entry_fee,4)}</td><td>${n(t.exit_fee,4)}</td><td>${n(t.total_fee,4)}</td><td>${n(t.referral_commission,4)}</td><td>${n(t.leverage,0)}x</td><td>${n(t.margin,2)}</td><td>${n(t.mae_pct,3)}%</td><td>${n(t.mfe_pct,3)}%</td><td>${t.bars_held}</td><td>${esc(t.exit_reason)}</td><td>${t.exit_receipt?`<button class="audit-btn" data-trade="${t.trade}">Inspect</button>`:'—'}</td></tr>`).join('');
  document.querySelectorAll('.audit-btn').forEach(b=>b.addEventListener('click',()=>showTradeAudit(b.dataset.trade)));
  $('tradeAudit').innerHTML='<span class="muted">Select a liquidation trade to inspect the exit receipt.</span>';
  $('economics').innerHTML=`<div class="metrics"><div class="metric"><span>Trader fees</span><b>${n(m.fees_paid,4)}</b></div><div class="metric"><span>Referrer payout</span><b>${n(m.referral_revenue,4)}</b></div><div class="metric"><span>Trades/day</span><b>${n(m.trades_per_day,2)}</b></div><div class="metric"><span>Referral/day</span><b>${n(m.referral_revenue_per_day,4)}</b></div></div>`;
  const p=d.open_position,posStatus=$('positionStatus');if(p){posStatus.textContent=p.side.toUpperCase();posStatus.className=`status-pill ${p.side}`;const liq=p.liquidation===null||p.liquidation===undefined?'Disabled':n(p.liquidation);$('openPosition').innerHTML=`<b>OPEN ${esc(p.side.toUpperCase())}</b><div class="position-grid"><div><span>Layers</span><b>${p.layers}</b></div><div><span>Average</span><b>${n(p.avg_entry)}</b></div><div><span>Break-even</span><b>${n(p.break_even)}</b></div><div><span>Target</span><b class="positive">${n(p.profit_target)}</b></div><div><span>Open P&L</span><b class="${cls(p.open_pnl)}">${n(p.open_pnl,4)}</b></div><div><span>Est. liquidation</span><b class="${p.liquidation==null?'':'negative'}">${liq}</b></div><div><span>Used margin</span><b>${n(p.used_margin,4)}</b></div><div><span>MAE</span><b>${n(p.mae_pct,3)}%</b></div></div><small class="muted">${esc(p.liquidation_model||'')} · ${esc(receiptSummary(p.entry_confirmation))}</small>`}else{posStatus.textContent='FLAT';posStatus.className='status-pill neutral';$('openPosition').innerHTML='<span class="muted">No open position</span>'}
  $('dockTrades').textContent=`${m.closed_trades} trades`;$('dockPnl').textContent=`P&L ${Number(m.total_equity_pnl)>=0?'+':''}${n(m.total_equity_pnl,4)}`;$('dockPnl').className=cls(m.total_equity_pnl);updateAccountGlance();
}

function scheduleBacktest(delay=320){
  updateStaticHeader();updateAccountGlance();updateProfileHelp();if(booting||currentMode!=='BACKTEST')return;clearTimeout(autoTimer);setStatus('Strategy settings changed · recalculation queued…');autoTimer=setTimeout(()=>runBacktest(),delay);
}
async function runBacktest(){
  if(currentMode!=='BACKTEST')return;let payload;try{payload=requestPayload()}catch(e){setStatus(`Settings error · ${e.message}`);return}
  const generation=++requestGeneration;if(backtestController)backtestController.abort();backtestController=new AbortController();showRecalc(true);$('autoApplyBadge').textContent='CALCULATING';setStatus('Recalculating strategy against HTX candles…');
  try{const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:backtestController.signal});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Backtest failed');if(generation!==requestGeneration)return;draw(d);setStatus(`Applied · ${d.entry_model.label} · ${d.backtest_window.candles} candles · ${d.metrics.closed_trades} closed trades`)}catch(e){if(e.name!=='AbortError')setStatus(`Backtest error · ${e.message}`)}finally{if(generation===requestGeneration){showRecalc(false);$('autoApplyBadge').textContent='AUTO APPLY'}}
}

async function pollPaper(){
  try{const d=await fetch('/api/paper-live/status').then(r=>r.json());$('paperStart').disabled=currentMode!=='PAPER'||d.running;$('paperStop').disabled=currentMode!=='PAPER'||!d.running;const badge=$('paperBadge');badge.textContent=d.running?'RUNNING':'OFF';badge.className=`status-pill ${d.running?'long':'neutral'}`;const p=d.position,sig=d.last_signal,model=d.entry_model;$('paperState').innerHTML=`<b>${d.running?'RUNNING':'STOPPED'}</b>${model?`<br><span class="muted">${esc(model.primary)} · ${esc(model.policy)}</span>`:''}<br><span class="muted">Last closed bar</span> ${d.last_bar_ts_ms?new Date(d.last_bar_ts_ms).toLocaleString():'—'}${sig?`<br><span class="muted">Last signal</span> ${esc(sig.side)} · ${esc(receiptSummary(sig.receipt))}`:''}${p?`<br><span class="muted">Position</span> ${esc(p.side)} ${n(p.qty,6)} @ ${n(p.entry_price)}<br><span class="muted">Layers</span> ${d.layers}`:'<br><span class="muted">Position</span> flat'}${d.last_error?`<br><span class="negative">${esc(d.last_error)}</span>`:''}`;$('paperEventRows').innerHTML=(d.events||[]).slice().reverse().map(e=>`<tr><td>${new Date(e.ts_ms).toLocaleTimeString()}</td><td>${esc(e.kind)}</td><td>${esc(e.detail)}</td></tr>`).join('')}catch(e){$('paperState').textContent=`Paper status error: ${e.message}`}
}
async function startPaper(){try{setStatus('Starting PAPER strategy through epinnox-online…');const r=await fetch('/api/paper-live/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(requestPayload())});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Paper start failed');setStatus('PAPER strategy running · settings are locked into this runner until restarted.');await pollPaper()}catch(e){setStatus(`PAPER start error · ${e.message}`)}}
async function stopPaper(){try{await fetch('/api/paper-live/stop',{method:'POST'});setStatus('PAPER runner stopped · existing paper positions unchanged.');await pollPaper()}catch(e){setStatus(`PAPER stop error · ${e.message}`)}}

function setMode(mode){
  currentMode=mode;document.querySelectorAll('.mode').forEach(x=>x.classList.toggle('active',x.dataset.mode===mode));$('modeText').textContent=mode;$('autoStatus').textContent=mode==='BACKTEST'?'Backtest auto-apply enabled':mode==='PAPER'?'Paper runner uses staged strategy settings':'Live execution remains unarmed';
  $('paperStart').disabled=mode!=='PAPER';$('paperStop').disabled=true;
  if(mode==='BACKTEST'){setStatus('Backtest mode · strategy changes apply automatically.');scheduleBacktest(50)}else if(mode==='PAPER'){setStatus('Paper mode · configure Strategy tab, then start the paper runner.');pollPaper()}else setStatus('LIVE is not armed in Terminal yet.');
}
function setInspectorTab(id){document.querySelectorAll('.inspector-tab').forEach(b=>b.classList.toggle('active',b.dataset.inspectorTab===id));document.querySelectorAll('.inspector-panel').forEach(p=>p.classList.toggle('active',p.id===id))}
function setTimeframe(tf){$('timeframe').value=tf;document.querySelectorAll('.tf').forEach(b=>b.classList.toggle('active',b.dataset.tf===tf));scheduleBacktest(80)}

$('paperStart').addEventListener('click',startPaper);$('paperStop').addEventListener('click',stopPaper);
$('confirmationPolicy').addEventListener('change',()=>{syncConfirmationControls();scheduleBacktest(100)});
document.querySelectorAll('.mode').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));
document.querySelectorAll('.tf').forEach(b=>b.addEventListener('click',()=>setTimeframe(b.dataset.tf)));
document.querySelectorAll('.inspector-tab').forEach(b=>b.addEventListener('click',()=>setInspectorTab(b.dataset.inspectorTab)));
$('openStrategyTab').addEventListener('click',()=>setInspectorTab('strategyPanel'));
$('fitChart').addEventListener('click',()=>chart?.timeScale().fitContent());
$('toggleIndicator').addEventListener('click',()=>{$('indicatorPane').classList.toggle('collapsed')});
$('symbol').addEventListener('change',()=>scheduleBacktest(80));
for(const id of strategyControlIds){const el=$(id);if(!el)continue;if(id==='confirmationPolicy')continue;const evt=(el.tagName==='SELECT'||el.type==='datetime-local')?'change':'input';el.addEventListener(evt,()=>{if(id==='strategy'||id==='confirm1'||id==='confirm2')updateStaticHeader();if(id==='backtestProfile')updateProfileHelp();scheduleBacktest(evt==='input'?420:100)})}
document.querySelectorAll('.tabbar button').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tabbar button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab').forEach(x=>x.classList.add('hidden'));b.classList.add('active');$(b.dataset.tab).classList.remove('hidden')}));

initCharts();await loadConfig();booting=false;setTimeframe('5m');await runBacktest();paperPoll=setInterval(()=>{if(currentMode==='PAPER')pollPaper()},2000);
