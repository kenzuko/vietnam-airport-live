const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').toLowerCase();
function delayed(f){return Number(f.delay_minutes)>=15||norm(f.status).includes('tre')||norm(f.status).includes('delay')||norm(f.status).includes('late');}
function fmtTime(value){if(!value)return'-';try{return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}).format(new Date(value));}catch{return'-';}}
function barList(target,items){const max=Math.max(1,...items.map(x=>x.value));$(target).innerHTML=items.length?items.map(x=>`<div class="bar-row"><span>${esc(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.round(x.value/max*100)}%"></div></div><b>${x.value}</b></div>`).join(''):'<div class="empty-state">Chưa đủ dữ liệu.</div>';}
async function getJson(url){const r=await fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}
async function load(){
  let d; let fallback=false;
  try{d=await getJson('./data/sgn-day.json');}
  catch{d=await getJson('https://raw.githubusercontent.com/kenzuko/vietnam-airport-live/main/data/sgn.json');fallback=true;}
  const f=d.flights||[];const s=d.summary||{};
  $('aTotal').textContent=s.total??f.length;$('aArrivals').textContent=s.arrivals??0;$('aDepartures').textContent=s.departures??0;$('aInternational').textContent=s.international??f.filter(x=>x.is_international).length;$('aDelayed').textContent=s.delayed??f.filter(delayed).length;
  if(fallback){$('coverageNote').textContent='Đang dùng dữ liệu trực tiếp hiện tại - chưa phải tổng cả ngày';}
  else{$('coverageNote').textContent=d.complete_day?'Phạm vi dữ liệu: đã ghi nhận từ đầu ngày':`Phạm vi dữ liệu: ghi nhận từ ${fmtTime(d.first_seen_at)} - chưa phải toàn bộ ngày`;}
  const delayPct=f.length?Math.round((f.filter(delayed).length/f.length)*100):0;const intlPct=f.length?Math.round((f.filter(x=>x.is_international).length/f.length)*100):0;
  const scope=fallback?'Dữ liệu hiện tại đang hiển thị':(d.complete_day?'Dữ liệu đã ghi nhận từ đầu ngày':'Dữ liệu tích lũy từ thời điểm hệ thống bắt đầu theo dõi hôm nay');
  $('reportBox').innerHTML=`${scope} có <b>${s.total??f.length}</b> chuyến, gồm <b>${s.arrivals??0}</b> chuyến đến và <b>${s.departures??0}</b> chuyến đi. Chuyến quốc tế chiếm khoảng <b>${intlPct}%</b> trong tập dữ liệu này. Có <b>${s.delayed??f.filter(delayed).length}</b> chuyến trễ hoặc thay đổi từ 15 phút trở lên, tương đương khoảng <b>${delayPct}%</b>. ${fallback||!d.complete_day?'Các tỷ lệ này chỉ phản ánh phần dữ liệu hệ thống đã quan sát, không nên hiểu là thống kê đầy đủ của cả ngày.':''}`;
  const routes=new Map();for(const x of f){const k=x.route_airport||'-';routes.set(k,(routes.get(k)||0)+1);}barList('routeBars',[...routes].sort((a,b)=>b[1]-a[1]).slice(0,12).map(([label,value])=>({label,value})));
  const terms=new Map();for(const x of f){const k=x.terminal||'-';terms.set(k,(terms.get(k)||0)+1);}barList('terminalBars',[...terms].sort((a,b)=>b[1]-a[1]).map(([label,value])=>({label,value})));
  const hours=Array.from({length:24},()=>0);for(const x of f){const m=/^(\d{2}):/.exec(x.scheduled||'');if(m)hours[Number(m[1])]++;}const max=Math.max(1,...hours);$('hourGrid').innerHTML=hours.map((v,h)=>`<div class="hour-col"><div class="hour-bar" style="height:${Math.max(3,Math.round(v/max*118))}px" title="${h}:00 - ${v} chuyến"></div><span>${String(h).padStart(2,'0')}</span></div>`).join('');
}
load().catch(err=>{$('coverageNote').textContent='Chưa có dữ liệu thống kê';$('reportBox').textContent=`Không đọc được dữ liệu: ${err.message}`;});
