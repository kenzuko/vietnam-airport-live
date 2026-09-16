const DATA_SOURCES = [
  { url: 'https://raw.githubusercontent.com/kenzuko/vietnam-airport-live/data-live/data/sgn.json', mode: 'fresh' },
  { url: './data/sgn.json', mode: 'pages-fallback' }
];

const AIRLINES = {
  VN:'Vietnam Airlines', VJ:'VietJet Air', VU:'Vietravel Airlines', QH:'Bamboo Airways', BL:'Pacific Airlines',
  SQ:'Singapore Airlines', TG:'Thai Airways', AK:'AirAsia', FD:'Thai AirAsia', TR:'Scoot', KE:'Korean Air',
  OZ:'Asiana Airlines', CX:'Cathay Pacific', BR:'EVA Air', CI:'China Airlines', CZ:'China Southern', MU:'China Eastern',
  CA:'Air China', JL:'Japan Airlines', NH:'ANA', QR:'Qatar Airways', EK:'Emirates', JQ:'Jetstar', '5J':'Cebu Pacific',
  TK:'Turkish Airlines', QF:'Qantas', PR:'Philippine Airlines', UA:'United Airlines', AA:'American Airlines', DL:'Delta Air Lines', SK:'SAS'
};

const state = { data:null, direction:'arrival', terminal:'all', filter:'all', query:'', visibleLimit:30 };
const $ = id => document.getElementById(id);

function normalizeText(value='') { return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().trim(); }
function esc(value){ return String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;'); }
function hhmmToMinutes(value){ if(!/^\d{2}:\d{2}$/.test(value||'')) return null; const [h,m]=value.split(':').map(Number); return h*60+m; }
function vnNowParts(){ const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date()); return {hour:Number(p.find(x=>x.type==='hour')?.value||0),minute:Number(p.find(x=>x.type==='minute')?.value||0)}; }
function vnNowMinutes(){ const p=vnNowParts(); return p.hour*60+p.minute; }
function formatMinuteOfDay(value){ const v=((value%1440)+1440)%1440; return `${String(Math.floor(v/60)).padStart(2,'0')}:${String(v%60).padStart(2,'0')}`; }
function airlineFromFlight(number=''){ const n=String(number).replace(/\s+/g,'').toUpperCase(); for(const code of Object.keys(AIRLINES).sort((a,b)=>b.length-a.length)){ if(n.startsWith(code))return AIRLINES[code]; } return ''; }
function airlineLabel(f){ return f?.airline||airlineFromFlight(f?.flight_number)||''; }
function isCompleted(f){ const s=normalizeText(f.status); return s.includes('da ha canh')||s.includes('da khoi hanh')||s.includes('departed')||s.includes('landed'); }
function futureDiff(f){ if(isCompleted(f))return null; const t=hhmmToMinutes(f.estimated||f.actual||f.scheduled); if(t==null)return null; let diff=t-vnNowMinutes(); if(diff < -720) diff += 1440; if(diff > 720) diff -= 1440; return diff; }
function isWithinNextHours(f,hours){ const diff=futureDiff(f); return diff!=null&&diff>=0&&diff<=hours*60; }
function isWithinNext3Hours(f){ return isWithinNextHours(f,3); }
function isDelayed(f){ const s=normalizeText(f.status); return Number(f.delay_minutes)>=15||s.includes('tre')||s.includes('delay')||s.includes('late'); }
function isChanged(f){ return isDelayed(f)||Boolean(f.estimated&&f.estimated!==f.scheduled); }
function codeshareText(f){ return (Array.isArray(f.flight_numbers)?f.flight_numbers:[]).filter(Boolean).join(' '); }
function flightSearchText(f){ return normalizeText([f.flight_number,codeshareText(f),airlineLabel(f),f.origin,f.destination,f.route_airport,f.status,f.terminal,f.gate,f.counter,f.belt].filter(Boolean).join(' ')); }
function routeLabel(value=''){ const map={'PUDONG- SHANGHAI':'Shanghai Pudong','NARITA-TOKYO':'Tokyo Narita','HANEDA-TOKYO':'Tokyo Haneda','DON MUANG':'Bangkok Don Mueang'}; return map[value]||value; }

function filteredFlights(){
  if(!state.data?.flights) return [];
  const q=normalizeText(state.query);
  return state.data.flights.filter(f=>{
    if(state.direction!=='all'&&f.direction!==state.direction)return false;
    if(state.terminal!=='all'&&String(f.terminal||'').toUpperCase()!==state.terminal)return false;
    if(state.filter==='next3'&&!isWithinNext3Hours(f))return false;
    if(state.filter==='delayed'&&!isChanged(f))return false;
    if(state.filter==='international'&&!f.is_international)return false;
    if(state.filter==='domestic'&&f.is_international)return false;
    if(q&&!flightSearchText(f).includes(q))return false;
    return true;
  }).sort((a,b)=>{
    const ta=hhmmToMinutes(a.estimated||a.scheduled)||9999;
    const tb=hhmmToMinutes(b.estimated||b.scheduled)||9999;
    return ta-tb;
  });
}

function statusClass(f){ if(isDelayed(f))return 'delay'; const s=normalizeText(f.status); if(s.includes('ha canh')||s.includes('khoi hanh')||s.includes('departed')||s.includes('landed')||s.includes('on time'))return 'ok'; return ''; }
function displayStatus(f){ if(f.status)return f.status; if(f.actual)return f.direction==='arrival'?'Đã hạ cánh':'Đã khởi hành'; if(f.estimated&&f.estimated!==f.scheduled)return 'Đã cập nhật giờ'; return 'Theo kế hoạch'; }

function flightRow(f){
  const route=routeLabel(f.route_airport||(f.direction==='arrival'?f.origin:f.destination)||'Đang cập nhật');
  const timeMain=f.actual||f.estimated||f.scheduled||'--:--';
  const scheduled=f.scheduled||'--:--';
  const delay=Number.isFinite(Number(f.delay_minutes))?Number(f.delay_minutes):null;
  const delayLabel=delay!=null&&delay>=10?`<span class="delay-minutes">+${delay} phút</span>`:'';
  const meta=[f.gate?`Cổng ${f.gate}`:null,f.counter?`Quầy ${f.counter}`:null,f.belt?`Băng chuyền ${f.belt}`:null].filter(Boolean).join(' · ');
  const shares=Array.isArray(f.flight_numbers)?f.flight_numbers.filter(n=>n&&n!==f.flight_number):[];
  const carrier=airlineLabel(f);
  const secondary=[carrier||null,shares.length?`Liên danh ${shares.slice(0,3).join(', ')}`:null].filter(Boolean).join(' · ')||'Chuyến bay';
  return `<article class="flight-row">
    <div class="flight-time"><strong>${esc(timeMain)}</strong><small>Lịch ${esc(scheduled)}</small></div>
    <div class="flight-main"><strong>${esc(f.flight_number||'-')}</strong><small>${esc(secondary)}</small></div>
    <div class="flight-route"><strong>${esc(route)}</strong><small>${f.direction==='arrival'?'Đến SGN':'Rời SGN'}</small></div>
    <div class="flight-meta"><span class="terminal-tag">${esc(f.terminal||'-')}</span><small>${esc(meta||'Đang cập nhật cổng/quầy')}</small></div>
    <div class="flight-status"><span class="status-badge ${statusClass(f)}">${esc(displayStatus(f))}</span>${delayLabel}</div>
  </article>`;
}

function renderBoard(){
  const all=filteredFlights();
  const shown=all.slice(0,state.visibleLimit);
  $('flightList').innerHTML=shown.length?shown.map(flightRow).join(''):`<div class="empty-state">Không có chuyến phù hợp với bộ lọc hiện tại.</div>`;
  const more=$('showMoreBtn');
  if(all.length>state.visibleLimit){ more.classList.remove('hidden'); more.textContent=`Xem thêm ${Math.min(30,all.length-state.visibleLimit)} chuyến`; }
  else more.classList.add('hidden');
}

function renderWatch(){
  const flights=(state.data?.flights||[]).filter(f=>isChanged(f)&&!isCompleted(f)).sort((a,b)=>(Number(b.delay_minutes)||0)-(Number(a.delay_minutes)||0)).slice(0,8);
  $('watchCount').textContent=flights.length;
  $('watchList').innerHTML=flights.length?flights.map(f=>{
    const delay=Number(f.delay_minutes); const extra=Number.isFinite(delay)&&delay>=10?` · +${delay} phút`:'';
    const carrier=airlineLabel(f); const carrierText=carrier?` · ${carrier}`:'';
    return `<div class="watch-item"><strong>${esc(f.flight_number)} · ${esc(routeLabel(f.route_airport||'-'))}</strong><span>${esc(displayStatus(f))}${esc(extra)}${esc(carrierText)}</span></div>`;
  }).join(''):`<div class="empty-state">Chưa thấy chuyến nào cần chú ý.</div>`;
}

function renderPulse(){
  const flights=state.data?.flights||[];
  const next60=flights.filter(f=>isWithinNextHours(f,1));
  const next180=flights.filter(f=>isWithinNextHours(f,3));
  const arr=next180.filter(f=>f.direction==='arrival');
  const dep=next180.filter(f=>f.direction==='departure');
  const changed=next180.filter(isChanged);
  $('nextHourTotal').textContent=next60.length;
  $('next3Arrivals').textContent=arr.length;
  $('next3Departures').textContent=dep.length;
  $('next3Changed').textContent=changed.length;
  const now=vnNowMinutes(); $('pulseClock').textContent=`${formatMinuteOfDay(now)} → ${formatMinuteOfDay(now+180)}`;
  const intl3=next180.filter(f=>f.is_international).length;
  let sentence=`Trong 3 giờ tới đang thấy ${arr.length} chuyến đến và ${dep.length} chuyến đi`;
  if(intl3)sentence+=`, trong đó ${intl3} chuyến quốc tế`;
  if(changed.length)sentence+=`. Có ${changed.length} chuyến đang đổi giờ hoặc trễ, nên kiểm tra kỹ trước khi ra sân bay.`;
  else sentence+=`. Chưa thấy thay đổi giờ đáng kể trong nhóm chuyến sắp tới.`;
  $('opsNarrative').textContent=sentence;

  const domestic=flights.filter(f=>!f.is_international).length;
  const international=flights.filter(f=>f.is_international).length;
  const total=Math.max(1,domestic+international);
  $('domesticNow').textContent=domestic;
  $('internationalNow').textContent=international;
  $('domesticPct').textContent=`${Math.round(domestic/total*100)}% dữ liệu hiện tại`;
  $('internationalPct').textContent=`${Math.round(international/total*100)}% dữ liệu hiện tại`;

  const routes=new Map();
  for(const f of flights){ const k=routeLabel(f.route_airport||''); if(k)routes.set(k,(routes.get(k)||0)+1); }
  const top=[...routes.entries()].sort((a,b)=>b[1]-a[1]).slice(0,5);
  $('routeHighlights').innerHTML=top.length?top.map(([label,count])=>`<span class="route-chip">${esc(label)} <b>${count}</b></span>`).join(''):'<span class="route-chip">Đang tổng hợp tuyến bay</span>';
}

function renderNextArrivals(){
  const list=(state.data?.flights||[]).filter(f=>f.direction==='arrival'&&isWithinNextHours(f,6)).sort((a,b)=>(futureDiff(a)??9999)-(futureDiff(b)??9999)).slice(0,7);
  $('nextArrivalsList').innerHTML=list.length?list.map(f=>{
    const time=f.estimated||f.scheduled||'--:--';
    const delay=Number(f.delay_minutes);
    const badge=Number.isFinite(delay)&&delay>=10?`<span class="eta-delay">+${delay} phút</span>`:`<span class="eta-ok">${esc(f.terminal||'-')}</span>`;
    const carrier=airlineLabel(f); const carrierText=carrier?` · ${carrier}`:'';
    return `<div class="next-arrival"><time>${esc(time)}</time><div><strong>${esc(f.flight_number||'-')} · ${esc(routeLabel(f.route_airport||'-'))}</strong><small>Lịch ${esc(f.scheduled||'-')} · ${esc(f.terminal||'-')}${carrierText?esc(carrierText):''}${f.belt?` · Băng chuyền ${esc(f.belt)}`:''}</small></div>${badge}</div>`;
  }).join(''):'<div class="empty-state">Chưa thấy chuyến đến trong vài giờ tới.</div>';
}

function renderTerminalPulse(){
  const flights=state.data?.flights||[];
  const items=['T1','T2','T3'].map(t=>({terminal:t,count:flights.filter(f=>String(f.terminal).toUpperCase()===t).length}));
  const max=Math.max(1,...items.map(x=>x.count));
  $('terminalPulse').innerHTML=items.map(x=>`<div class="terminal-line"><strong>${x.terminal}</strong><div class="terminal-track"><div class="terminal-fill" style="width:${Math.max(5,Math.round(x.count/max*100))}%"></div></div><b>${x.count}</b></div>`).join('');
}

function ageInfo(generatedAt){
  if(!generatedAt)return{minutes:Infinity,label:'chưa có dữ liệu'};
  const t=new Date(generatedAt).getTime(); if(!Number.isFinite(t))return{minutes:Infinity,label:'không rõ'};
  const mins=Math.max(0,Math.round((Date.now()-t)/60000));
  if(mins<1)return{minutes:mins,label:'vừa cập nhật'};
  if(mins<60)return{minutes:mins,label:`${mins} phút`};
  return{minutes:mins,label:`${Math.floor(mins/60)} giờ ${mins%60} phút`};
}

function firstSeenLabel(value){
  if(!value)return 'Đang tích lũy dữ liệu';
  try{ return `ghi nhận từ ${new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}).format(new Date(value))}`; }
  catch{return 'Đang tích lũy dữ liệu';}
}

function renderSummary(){
  const d=state.data; const s=d?.summary||{}; const day=d?.day_summary||{};
  const feedTotal=Number(s.feed_total??s.total??0);
  const dayTotal=Number(day.total??feedTotal);
  $('totalFlights').textContent=dayTotal;
  $('liveWindowCount').textContent=feedTotal;
  $('arrivalsCount').textContent=s.arrivals??0;
  $('departuresCount').textContent=s.departures??0;
  $('delayedCount').textContent=s.delayed??0;
  $('todayCoverage').textContent=day.complete_day?'đã theo dõi từ đầu ngày':firstSeenLabel(day.first_seen_at);

  const total=feedTotal, delayed=Number(s.delayed)||0, ratio=total?delayed/total:0;
  if(!total){$('opsState').textContent='ĐANG CHỜ';$('opsDetail').textContent='Chờ đồng bộ dữ liệu';}
  else if(ratio>=.18){$('opsState').textContent='CẦN CHÚ Ý';$('opsDetail').textContent=`${delayed} chuyến đang trễ hoặc đổi giờ`;}
  else if(delayed>0){$('opsState').textContent='CÓ THAY ĐỔI';$('opsDetail').textContent=`${delayed} chuyến cần chú ý`;}
  else{$('opsState').textContent='BÌNH THƯỜNG';$('opsDetail').textContent='Chưa thấy trễ đáng kể trong dữ liệu hiện tại';}

  $('coverage').textContent=`${feedTotal} chuyến`;
  $('terminals').textContent=(s.terminals||[]).join(', ')||'-';
  const age=ageInfo(d?.generated_at);
  $('dataAge').textContent=age.label;
  $('updatedAt').textContent=d?.generated_at?(age.minutes<1?'Dữ liệu vừa cập nhật':`Dữ liệu cách đây ${age.label}`):'Chưa đồng bộ';

  const pill=$('healthPill'); pill.className='health-pill';
  if(!total){pill.classList.add('loading');pill.innerHTML='<i></i> ĐANG CHỜ';$('qaBadge').textContent='CHỜ';$('healthTitle').textContent='CHƯA CÓ DỮ LIỆU';$('healthDescription').textContent='Chưa nhận được bộ dữ liệu SGN hợp lệ.';$('healthIcon').textContent='⋯';}
  else if(age.minutes>10){pill.classList.add('stale');pill.innerHTML='<i></i> CHẬM CẬP NHẬT';$('qaBadge').textContent='CHẬM';$('healthTitle').textContent='DỮ LIỆU ĐANG CHẬM';$('healthDescription').textContent='Dữ liệu đã cũ hơn 10 phút. Nên kiểm tra lại trước khi sử dụng.';$('healthIcon').textContent='!';}
  else{pill.innerHTML='<i></i> TRỰC TIẾP';$('qaBadge').textContent='TỐT';$('healthTitle').textContent='DỮ LIỆU ĐANG HOẠT ĐỘNG';$('healthDescription').textContent='Dữ liệu SGN đang được cập nhật bình thường.';$('healthIcon').textContent='✓';}
}

function renderAll(){ renderSummary(); renderPulse(); renderNextArrivals(); renderTerminalPulse(); renderBoard(); renderWatch(); }
function setActive(container,key,value){ container.querySelectorAll('button').forEach(btn=>btn.classList.toggle('active',btn.dataset[key]===value)); }
async function fetchJsonWithTimeout(url,timeoutMs=7000){ const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),timeoutMs); try{const sep=url.includes('?')?'&':'?';const res=await fetch(`${url}${sep}t=${Date.now()}`,{cache:'no-store',signal:controller.signal,credentials:'omit'});if(!res.ok)throw new Error(`HTTP ${res.status}`);const data=await res.json();if(!data||!Array.isArray(data.flights)||!data.summary)throw new Error('Dữ liệu không hợp lệ');return data;}finally{clearTimeout(timer);} }

async function loadData(){
  $('refreshBtn').disabled=true; $('errorBox').classList.add('hidden'); let lastError=null;
  for(const source of DATA_SOURCES){
    try{
      const candidate=await fetchJsonWithTimeout(source.url);
      if(!state.data || !state.data.generated_at || new Date(candidate.generated_at)>=new Date(state.data.generated_at)) state.data=candidate;
      renderAll(); $('refreshBtn').disabled=false; return;
    }catch(err){lastError=err;console.warn('SGN data source failed',source.mode,err);}
  }
  $('healthPill').className='health-pill error';$('healthPill').innerHTML='<i></i> LỖI';$('errorBox').textContent=`Không đọc được dữ liệu SGN: ${lastError?.message||'lỗi không xác định'}`;$('errorBox').classList.remove('hidden');$('refreshBtn').disabled=false;
}

$('directionTabs').addEventListener('click',e=>{const btn=e.target.closest('[data-direction]');if(!btn)return;state.direction=btn.dataset.direction;state.visibleLimit=30;setActive($('directionTabs'),'direction',state.direction);renderBoard();});
$('terminalTabs').addEventListener('click',e=>{const btn=e.target.closest('[data-terminal]');if(!btn)return;state.terminal=btn.dataset.terminal;state.visibleLimit=30;setActive($('terminalTabs'),'terminal',state.terminal);renderBoard();});
$('filterTabs').addEventListener('click',e=>{const btn=e.target.closest('[data-filter]');if(!btn)return;state.filter=btn.dataset.filter;state.visibleLimit=30;setActive($('filterTabs'),'filter',state.filter);renderBoard();});
$('searchInput').addEventListener('input',e=>{state.query=e.target.value;state.visibleLimit=30;renderBoard();});
$('showMoreBtn').addEventListener('click',()=>{state.visibleLimit+=30;renderBoard();});
$('refreshBtn').addEventListener('click',loadData);

loadData();
