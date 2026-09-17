import {LineSeries} from 'https://cdn.jsdelivr.net/npm/lightweight-charts@5.0.8/+esm';

const COLORS={avg:'#60a5fa',be:'#f59e0b',target:'#22c55e'};
let selectedSeries=[];
let selectedTrade=null;

const sec=ms=>Math.floor(Number(ms)/1000);
const n=(v,d=2)=>(v===null||v===undefined||Number.isNaN(Number(v)))?'—':Number(v).toFixed(d);

function runtime(){return window.EpinnoxChartRuntime}
function result(){return window.EpinnoxWorkbench?.current||null}

function ensureContext(){
  const stage=document.querySelector('.chart-stage');
  if(!stage)return null;
  let el=document.getElementById('positionLifecycleContext');
  if(el)return el;
  el=document.createElement('div');
  el.id='positionLifecycleContext';
  el.className='position-lifecycle-context';
  stage.appendChild(el);
  const style=document.createElement('style');
  style.textContent=`
    .position-lifecycle-context{position:absolute;right:74px;top:10px;z-index:22;max-width:min(520px,44vw);display:grid;gap:4px;pointer-events:none;font:600 10px/1.35 Inter,system-ui,sans-serif}
    .position-lifecycle-context .plc-row{display:flex;align-items:center;gap:7px;padding:6px 8px;border:1px solid rgba(107,128,116,.25);border-radius:4px;background:rgba(3,8,5,.86);backdrop-filter:blur(7px);color:#9eaaa4}
    .position-lifecycle-context .plc-row strong{color:#eef8f2;letter-spacing:.045em}
    .position-lifecycle-context .plc-row.current{border-color:rgba(96,165,250,.28)}
    .position-lifecycle-context .plc-row.closed{border-color:rgba(244,183,64,.32)}
    .position-lifecycle-context .plc-tag{font:800 8px/1 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.08em;padding:3px 5px;border-radius:3px;background:#09100c;color:#82a18f}
    .position-lifecycle-context .plc-tag.long{color:#63f1a7}.position-lifecycle-context .plc-tag.short{color:#ff8f8f}
    @media(max-width:1100px){.position-lifecycle-context{right:62px;max-width:48vw}.position-lifecycle-context .plc-detail{display:none}}
  `;
  document.head.appendChild(style);
  return el;
}

function clearSelectedSeries(){
  const r=runtime();
  if(r?.chart){for(const s of selectedSeries){try{r.chart.removeSeries(s)}catch{}}}
  selectedSeries=[];
}

function addSegment(level,startMs,endMs,key,title){
  const r=runtime();
  if(!r?.chart||level===null||level===undefined||!Number.isFinite(Number(level)))return;
  const from=sec(startMs),to=sec(endMs);
  if(!Number.isFinite(from)||!Number.isFinite(to)||to<from)return;
  const series=r.chart.addSeries(LineSeries,{color:COLORS[key],lineWidth:1,lineStyle:key==='avg'?0:2,title,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  series.setData([{time:from,value:Number(level)},{time:to,value:Number(level)}]);
  selectedSeries.push(series);
}

function renderSelectedTrade(trade){
  clearSelectedSeries();
  selectedTrade=trade||null;
  if(!trade){renderContext();return}
  const history=Array.isArray(trade.level_history)&&trade.level_history.length?trade.level_history:[{
    ts_ms:trade.entry_ts_ms,
    avg_entry:trade.entry_price,
    break_even:trade.break_even,
    profit_target:trade.profit_target,
    layers:trade.layers||1,
  }];
  for(let i=0;i<history.length;i++){
    const row=history[i],end=history[i+1]?.ts_ms??trade.exit_ts_ms;
    addSegment(row.avg_entry,row.ts_ms,end,'avg',`#${trade.trade} AVG L${row.layers||i+1}`);
    addSegment(row.break_even,row.ts_ms,end,'be',`#${trade.trade} B/E L${row.layers||i+1}`);
    addSegment(row.profit_target,row.ts_ms,end,'target',`#${trade.trade} TP L${row.layers||i+1}`);
  }
  renderContext();
}

function renderContext(){
  const el=ensureContext();
  if(!el)return;
  const d=result(),open=d?.open_position;
  const rows=[];
  if(open){
    const side=String(open.side||'').toUpperCase();
    rows.push(`<div class="plc-row current"><span class="plc-tag ${String(open.side||'')}">CURRENT</span><strong>${side} · ${open.position_id||'OPEN POSITION'}</strong><span class="plc-detail">${open.layers||0} layer${open.layers===1?'':'s'} · avg ${n(open.avg_entry)} · target ${n(open.profit_target)}</span></div>`);
  }
  if(selectedTrade){
    const side=String(selectedTrade.side||'').toUpperCase();
    rows.push(`<div class="plc-row closed"><span class="plc-tag ${String(selectedTrade.side||'')}">CLOSED</span><strong>#${selectedTrade.trade} ${side} · ${String(selectedTrade.exit_reason||'exit').toUpperCase()}</strong><span class="plc-detail">${selectedTrade.position_id||''} · ${selectedTrade.layers||1} layer${selectedTrade.layers===1?'':'s'} · ${n(selectedTrade.entry_price)} → ${n(selectedTrade.exit_price)}</span></div>`);
    if(open)rows.push('<div class="plc-row"><span class="plc-detail">Bounded historical AVG / B-E / TP segments belong to the selected closed trade. Right-edge price lines belong to the CURRENT open position.</span></div>');
  }
  el.innerHTML=rows.join('');
  el.hidden=!rows.length;
}

function selectedFromRow(row){
  const d=result(),index=Number(row?.dataset?.tradeIndex);
  if(!d||!Array.isArray(d.trades)||!Number.isInteger(index)||index<0)return null;
  return d.trades[index]||null;
}

document.addEventListener('click',event=>{
  const row=event.target.closest?.('#tradeRows tr[data-trade-index]');
  if(row)queueMicrotask(()=>renderSelectedTrade(selectedFromRow(row)));
});

document.addEventListener('epinnox:workbench-result',()=>{
  selectedTrade=null;
  clearSelectedSeries();
  queueMicrotask(renderContext);
});

document.addEventListener('epinnox:chart-active',()=>queueMicrotask(renderContext));
window.addEventListener('resize',renderContext,{passive:true});

const observer=new MutationObserver(()=>renderContext());
const boot=()=>{
  ensureContext();
  const target=document.getElementById('openPosition')||document.body;
  observer.observe(target,{childList:true,subtree:true,characterData:true});
  renderContext();
};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();

window.EpinnoxPositionLifecycle={renderSelectedTrade,clear:()=>renderSelectedTrade(null)};
