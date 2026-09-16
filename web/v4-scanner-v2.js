(()=>{
  if(window.__EPINNOX_SCANNER_V2_VIEW__)return;
  window.__EPINNOX_SCANNER_V2_VIEW__=true;
  const $=id=>document.getElementById(id);
  const n=(v,d=2)=>v===null||v===undefined||Number.isNaN(Number(v))?'—':Number(v).toFixed(d);
  const money=(v,d=2)=>v===null||v===undefined||Number.isNaN(Number(v))?'—':`$${Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})}`;
  let lastScanId='';

  function installStyle(){
    if($('scannerV2Style'))return;
    const style=document.createElement('style');style.id='scannerV2Style';style.textContent=`
      .scanner-validation-banner{display:flex;align-items:center;gap:10px;min-height:30px;padding:6px 10px;border:1px solid rgba(29,232,132,.18);background:rgba(9,30,21,.52);color:#8ea99a;font-size:10px;letter-spacing:.04em}
      .scanner-validation-banner strong{color:#37e99a;font-size:10px;letter-spacing:.08em}
      .scanner-validation-banner span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .scanner-table-v4 tr[data-robustness] td:first-child::after{content:'R ' attr(data-robustness);display:block;color:#3ddc91;font-size:8px;margin-top:2px}
    `;document.head.appendChild(style);
  }

  function prepare(){
    const workspace=$('scannerWorkspace');if(!workspace)return false;
    installStyle();
    const title=workspace.querySelector('.scanner-command-title span');if(title)title.textContent='Strategy × market × target · walk-forward + chronological holdout';
    const bars=$('v4ScanBars');if(bars){bars.min='600';if(Number(bars.value)<600)bars.value='600'}
    const command=workspace.querySelector('.scanner-commandbar');
    if(command&&!$('scannerValidationBanner')){
      const banner=document.createElement('div');banner.id='scannerValidationBanner';banner.className='scanner-validation-banner';banner.innerHTML='<strong>VALIDATION V2</strong><span>25% chronological holdout · walk-forward calibration · Pine parity semantics</span>';command.insertAdjacentElement('afterend',banner)
    }
    const heads=[...workspace.querySelectorAll('.scanner-table-v4 thead th')];
    if(heads.length>=13){heads[6].textContent='OOS T/day';heads[7].textContent='OOS P&L';heads[8].textContent='OOS Exp';heads[9].textContent='OOS PF';heads[12].textContent='OOS Referral/day'}
    const status=$('v4ScanStatus');
    if(status&&status.dataset.v2Bound!=='1'){
      status.dataset.v2Bound='1';
      const ob=new MutationObserver(()=>{if(String(status.textContent||'').includes('Complete'))setTimeout(()=>refreshLatest(true),80)});
      ob.observe(status,{childList:true,subtree:true,characterData:true});
    }
    return true;
  }

  function decorate(data){
    if(!data||!Array.isArray(data.results))return;
    lastScanId=String(data.scan_id||'');
    const best=data.summary?.best_candidate;
    const holdoutPct=Number(data.validation_policy?.holdout_fraction??.25)*100;
    const banner=$('scannerValidationBanner');
    if(banner)banner.innerHTML=`<strong>VALIDATION V2</strong><span>${n(holdoutPct,0)}% chronological holdout · ${data.validation_policy?.walk_forward_windows??'—'} WF windows · ${data.parity_semantics_version||'Pine parity'} · ${data.engine_stats?.strategy_builds_avoided??0} indicator rebuilds avoided</span>`;
    if(best){
      const o=best.holdout||{};
      const summary=$('v4ScanSummary');if(summary)summary.innerHTML=`<div><span>Evaluated</span><b>${data.summary?.evaluated??0}</b></div><div><span>Qualified</span><b>${data.summary?.qualified??0}</b></div><div><span>OOS P&L</span><b>${money(o.net_pnl)}</b></div><div><span>OOS T/day</span><b>${n(o.trades_per_day,2)}</b></div><div><span>Robustness</span><b>${n(best.robustness_score,1)}</b></div>`;
      const card=$('v4BestCandidate');if(card)card.innerHTML=`<div class="best-main"><span>TOP HOLDOUT-QUALIFIED CANDIDATE</span><b>${best.symbol} · ${best.timeframe} · ${best.strategy}</b></div><div class="best-stat"><span>OOS P&L</span><b>${money(o.net_pnl)}</b></div><div class="best-stat"><span>OOS expectancy</span><b>${money(o.net_expectancy_usdt,4)}</b></div><div class="best-stat"><span>OOS trades/day</span><b>${n(o.trades_per_day,2)}</b></div><div class="best-stat"><span>Robustness</span><b>${n(best.robustness_score,1)}</b></div><div class="best-stat"><span>WF pass</span><b>${n(best.walk_forward?.pass_rate_pct,1)}%</b></div>`;
    }
    const byRank=new Map(data.results.map(r=>[String(r.objective_rank),r]));
    document.querySelectorAll('#v4ScannerRows tr').forEach(tr=>{
      const button=tr.querySelector('.scan-open[data-rank]');if(!button)return;
      const row=byRank.get(String(button.dataset.rank));if(!row)return;
      const cells=tr.children,o=row.holdout||{};
      tr.dataset.robustness=n(row.robustness_score,0);
      tr.title=[...(row.reject_reasons||[]),`robustness ${n(row.robustness_score,1)}`,`OOS ${o.closed_trades??0} trades`].join(' · ');
      if(cells.length>=13){cells[6].textContent=n(o.trades_per_day,2);cells[7].textContent=money(o.net_pnl);cells[8].textContent=money(o.net_expectancy_usdt,4);cells[9].textContent=n(o.profit_factor,2);cells[12].textContent=money(o.referral_revenue_per_day,3)}
    });
  }

  async function refreshLatest(force=false){
    try{
      const meta=await fetch('/api/scanner/runs?limit=1').then(r=>r.ok?r.json():null);const latest=meta?.runs?.[0];if(!latest)return;
      if(!force&&String(latest.scan_id)===lastScanId)return;
      const response=await fetch(`/api/scanner/runs/${encodeURIComponent(latest.scan_id)}`);if(!response.ok)return;decorate(await response.json())
    }catch{}
  }

  async function boot(){
    for(let i=0;i<120;i++){
      if(prepare()){await refreshLatest(false);return}
      await new Promise(resolve=>setTimeout(resolve,50));
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();