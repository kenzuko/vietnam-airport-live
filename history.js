const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').toLowerCase();
const DATA_BASE='https://raw.githubusercontent.com/kenzuko/vietnam-airport-live/data-live/data';
let active=null;
function delayed(f){return Number(f.delay_minutes)>=15||norm(f.status).includes('tre')||norm(f.status).includes('delay')||norm(f.status).includes('late');}
function row(f){const t=f.actual||f.estimated||f.scheduled||'--:--';const route=f.route_airport||'-';const meta=[f.terminal,f.gate?`Cổng ${f.gate}`:null,f.belt?`Băng chuyền ${f.belt}`:null,f.counter?`Quầy ${f.counter}`:null].filter(Boolean).join(' · ');return `<div class="history-row"><div><strong>${esc(t)}</strong><small>Lịch ${esc(f.scheduled||'-')}</small></div><div><strong>${esc(f.flight_number||'-')}</strong><small>${f.direction==='arrival'?'Đến':'Đi'}</small></div><div><strong>${esc(route)}</strong><small>${esc(meta||'-')}</small></div><div class="hide-mobile">${esc(f.status||'Theo kế hoạch')}</div><div>${delayed(f)?`<span class="status-badge delay">+${esc(f.delay_minutes??'?')} phút</span>`:`<span class="status-badge ok">${esc(f.status||'Bình thường')}</span>`}</div></div>`;}
function render(){if(!active)return;const s=active.summary||{};$('hTotal').textContent=s.total??active.flights?.length??0;$('hArrivals').textContent=s.arrivals??0;$('hDepartures').textContent=s.departures??0;$('hInternational').textContent=s.international??(active.flights||[]).filter(x=>x.is_international).length;$('hDelayed').textContent=s.delayed??(active.flights||[]).filter(delayed).length;$('historyTitle').textContent=`Dữ liệu ngày ${active.date||'-'}`;$('historyHealth').textContent=active.live_only?'Đang hiển thị cửa sổ dữ liệu trực tiếp hiện có':(active.complete_day?'Đã ghi nhận từ đầu ngày':'Ngày này chưa được ghi nhận đủ từ đầu ngày');filterRows();}
function filterRows(){const q=norm($('historySearch').value);const list=(active?.flights||[]).filter(f=>!q||norm([f.flight_number,(f.flight_numbers||[]).join(' '),f.route_airport,f.airline,f.terminal,f.status].join(' ')).includes(q));$('historyList').innerHTML=list.length?list.slice(0,250).map(row).join(''):'<div class="empty-state">Không có chuyến phù hợp.</div>';}
async function getJson(url){const r=await fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}
async function loadDay(url){active=await getJson(url);render();}
async function init(){
  let current=null,index={days:[]};
  try{current=await getJson(`${DATA_BASE}/sgn-day.json`);}catch{
    try{current=await getJson(`${DATA_BASE}/sgn.json`);current={...current,live_only:true,complete_day:false};}catch{}
  }
  try{index=await getJson(`${DATA_BASE}/history-index.json`);}catch{}
  const options=[];
  if(current?.date)options.push({date:current.date,url:current.live_only?`${DATA_BASE}/sgn.json`:`${DATA_BASE}/sgn-day.json`,current:true,live_only:current.live_only});
  for(const d of index.days||[]){
    if(options.some(x=>x.date===d.date))continue;
    const file=String(d.file||'').replace(/^\.\//,'');
    options.push({date:d.date,url:`${DATA_BASE}/${file}`});
  }
  options.sort((a,b)=>b.date.localeCompare(a.date));
  $('dateSelect').innerHTML=options.length?options.map((x,i)=>`<option value="${esc(x.url)}" ${i===0?'selected':''}>${esc(x.date)}${x.current?' · hôm nay':''}</option>`).join(''):'<option>Chưa có dữ liệu</option>';
  if(options.length){await loadDay(options[0].url);if(options[0].live_only){active.live_only=true;render();}}
  else $('historyHealth').textContent='Chưa có dữ liệu lịch sử';
}
$('dateSelect').addEventListener('change',e=>loadDay(e.target.value).catch(err=>$('historyHealth').textContent=`Lỗi: ${err.message}`));
$('historySearch').addEventListener('input',filterRows);
init().catch(err=>$('historyHealth').textContent=`Không đọc được lịch sử: ${err.message}`);
