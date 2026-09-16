const DATA_SOURCES = [
  { url: 'https://raw.githubusercontent.com/kenzuko/vietnam-airport-live/main/data/sgn.json', mode: 'fresh' },
  { url: './data/sgn.json', mode: 'pages-fallback' }
];

const state = { data:null, direction:'arrival', terminal:'all', filter:'all', query:'', visibleLimit:30 };
const $ = id => document.getElementById(id);

function normalizeText(value='') { return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().trim(); }
function esc(value){ return String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;'); }
function hhmmToMinutes(value){ if(!/^\d{2}:\d{2}$/.test(value||'')) return null; const [h,m]=value.split(':').map(Number); return h*60+m; }
function vnNowMinutes(){ const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date()); return Number(p.find(x=>x.type==='hour')?.value||0)*60+Number(p.find(x=>x.type==='minute')?.value||0); }
function isWithinNext3Hours(f){ const t=hhmmToMinutes(f.estimated||f.actual||f.scheduled); if(t==null)return false; let diff=t-vnNowMinutes(); if(diff < -720) diff += 1440; return diff>=0&&diff<=180; }
function isDelayed(f){ const s=normalizeText(f.status); return Number(f.delay_minutes)>=15||s.includes('tre')||s.includes('delay')||s.includes('late'); }
function isChanged(f){ return isDelayed(f)||Boolean(f.estimated&&f.estimated!==f.scheduled); }
function codeshareText(f){ return (Array.isArray(f.flight_numbers)?f.flight_numbers:[]).filter(Boolean).join(' '); }
function flightSearchText(f){ return normalizeText([f.flight_number,codeshareText(f),f.airline,f.origin,f.destination,f.route_airport,f.status,f.terminal,f.gate,f.counter,f.belt].filter(Boolean).join(' ')); }

function filteredFlights(){
  if(!state.data?.flights) return [];
  const q=normalizeText(state.query);
  return state.data.flights.filter(f=>{
    if(state.direction!=='all'&&f.direction!==state.direction)return false;
    if(state.terminal!=='all'&&String(f.terminal||'').toUpperCase()!==state.terminal)return false;
    if(state.filter==='next3'&&!isWithinNext3Hours(f))return false;
    if(state.filter==='delayed'&&!isChanged(f))return false;
    if(state.filter==='international'&&!f.is_international)return false;
    if(q&&!flightSearchText(f).includes(q))return false;
    return true;
  });
}

function statusClass(f){ if(isDelayed(f))return 'delay'; const s=normalizeText(f.status); if(s.includes('ha canh')||s.includes('khoi hanh')||s.includes('departed')||s.includes('landed')||s.includes('on time'))return 'ok'; return ''; }
function displayStatus(f){ if(f.status)return f.status; if(f.actual)return f.direction==='arrival'?'Đã hạ cánh':'Đã khởi hành'; if(f.estimated&&f.estimated!==f.scheduled)return 'Đã cập nhật giờ'; return 'Theo kế hoạch'; }

function flightRow(f){
  const route=f.route_airport||(f.direction==='arrival'?f.origin:f.destination)||'Đang cập nhật';
  const timeMain=f.actual||f.estimated||f.scheduled||'--:--';
  const scheduled=f.scheduled||'--:--';
  const delay=Number.isFinite(Number(f.delay_minutes))?Number(f.delay_minutes):null;
  const delayLabel=delay!=null&&delay>=10?`<span class="delay-minutes">+${delay} phút</span>`:'';
  const meta=[f.gate?`Cổng ${f.gate}`:null,f.counter?`Quầy ${f.counter}`:null,f.belt?`Băng chuyền ${f.belt}`:null].filter(Boolean).join(' · ');
  const shares=Array.isArray(f.flight_numbers)?f.flight_numbers.filter(n=>n&&n!==f.flight_number):[];
  const secondary=shares.length?`Liên danh ${shares.slice(0,3).join(', ')}`:(f.airline||'Chuyến bay');
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
  const flights=(state.data?.flights||[]).filter(isChanged).sort((a,b)=>(Number(b.delay_minutes)||0)-(Number(a.delay_minutes)||0)).slice(0,8);
  $('watchCount').textContent=flights.length;
  $('watchList').innerHTML=flights.length?flights.map(f=>{
    const delay=Number(f.delay_minutes); const extra=Number.isFinite(delay)&&delay>=10?` · +${delay} phút`:'';
    return `<div class="watch-item"><strong>${esc(f.flight_number)} · ${esc(f.route_airport||'-')}</strong><span>${esc(displayStatus(f))}${esc(extra)}</span></div>`;
  }).join(''):`<div class="empty-state">Chưa thấy chuyến nào cần chú ý.</div>`;
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
  $('todayCoverage').textContent=day.complete_day?'đã ghi nhận từ đầu ngày':firstSeenLabel(day.first_seen_at);

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

function setActive(container,key,value){ container.querySelectorAll('button').forEach(btn=>btn.classList.toggle('active',btn.dataset[key]===value)); }
async function fetchJsonWithTimeout(url,timeoutMs=7000){ const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),timeoutMs); try{const sep=url.includes('?')?'&':'?';const res=await fetch(`${url}${sep}t=${Date.now()}`,{cache:'no-store',signal:controller.signal,credentials:'omit'});if(!res.ok)throw new Error(`HTTP ${res.status}`);const data=await res.json();if(!data||!Array.isArray(data.flights)||!data.summary)throw new Error('Dữ liệu không hợp lệ');return data;}finally{clearTimeout(timer);} }

async function loadData(){
  $('refreshBtn').disabled=true; $('errorBox').classList.add('hidden'); let lastError=null;
  for(const source of DATA_SOURCES){
    try{
      const candidate=await fetchJsonWithTimeout(source.url);
      if(!state.data || !state.data.generated_at || new Date(candidate.generated_at)>=new Date(state.data.generated_at)) state.data=candidate;
      renderSummary();renderBoard();renderWatch();$('refreshBtn').disabled=false;return;
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
