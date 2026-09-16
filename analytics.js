const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').toLowerCase();
const AIRLINES={VN:'Vietnam Airlines',VJ:'VietJet Air',VU:'Vietravel Airlines',QH:'Bamboo Airways',BL:'Pacific Airlines',SQ:'Singapore Airlines',TG:'Thai Airways',AK:'AirAsia',FD:'Thai AirAsia',TR:'Scoot',KE:'Korean Air',OZ:'Asiana Airlines',CX:'Cathay Pacific',BR:'EVA Air',CI:'China Airlines',CZ:'China Southern',MU:'China Eastern',CA:'Air China',JL:'Japan Airlines',NH:'ANA',QR:'Qatar Airways',EK:'Emirates',JQ:'Jetstar','5J':'Cebu Pacific',TK:'Turkish Airlines',QF:'Qantas',PR:'Philippine Airlines',UA:'United Airlines',AA:'American Airlines',DL:'Delta Air Lines',SK:'SAS'};
function delayed(f){return Number(f.delay_minutes)>=15||norm(f.status).includes('tre')||norm(f.status).includes('delay')||norm(f.status).includes('late');}
function fmtTime(value){if(!value)return'-';try{return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}).format(new Date(value));}catch{return'-';}}
function carrier(number=''){const n=String(number).replace(/\s+/g,'').toUpperCase();for(const code of Object.keys(AIRLINES).sort((a,b)=>b.length-a.length)){if(n.startsWith(code))return AIRLINES[code];}return'';}
function routeLabel(value=''){const map={'PUDONG- SHANGHAI':'Shanghai Pudong','NARITA-TOKYO':'Tokyo Narita','HANEDA-TOKYO':'Tokyo Haneda','DON MUANG':'Bangkok Don Mueang'};return map[value]||value;}
function barList(target,items){const el=$(target);if(!el)return;const max=Math.max(1,...items.map(x=>x.value));el.innerHTML=items.length?items.map(x=>`<div class="bar-row"><span>${esc(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.round(x.value/max*100)}%"></div></div><b>${x.value}</b></div>`).join(''):'<div class="empty-state">Chưa đủ dữ liệu.</div>';}
function countBy(list,keyFn){const map=new Map();for(const x of list){const k=keyFn(x);if(!k)continue;map.set(k,(map.get(k)||0)+1);}return [...map].sort((a,b)=>b[1]-a[1]).map(([label,value])=>({label,value}));}
async function getJson(url){const r=await fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}
async function firstAvailable(urls){let last;for(const url of urls){try{return{data:await getJson(url),url};}catch(e){last=e;}}throw last||new Error('Không có nguồn dữ liệu');}

async function load(){
  const dayUrl='https://raw.githubusercontent.com/kenzuko/vietnam-airport-live/data-live/data/sgn-day.json';
  const liveUrl='https://raw.githubusercontent.com/kenzuko/vietnam-airport-live/data-live/data/sgn.json';
  const result=await firstAvailable([dayUrl,'./data/sgn-day.json',liveUrl,'./data/sgn.json']);
  const d=result.data;const f=Array.isArray(d.flights)?d.flights:[];const s=d.summary||{};
  const isDay=Boolean(d.first_seen_at||d.last_seen_at||d.complete_day!==undefined);
  const arrivals=s.arrivals??f.filter(x=>x.direction==='arrival').length;
  const departures=s.departures??f.filter(x=>x.direction==='departure').length;
  const international=s.international??f.filter(x=>x.is_international).length;
  const delayedCount=s.delayed??f.filter(delayed).length;
  const total=s.total??f.length;
  $('aTotal').textContent=total;$('aArrivals').textContent=arrivals;$('aDepartures').textContent=departures;$('aInternational').textContent=international;$('aDelayed').textContent=delayedCount;

  if(isDay){$('coverageNote').textContent=d.complete_day?'Phạm vi dữ liệu: đã theo dõi từ đầu ngày':`Phạm vi dữ liệu: ghi nhận từ ${fmtTime(d.first_seen_at)} - chưa phải toàn bộ ngày`;}
  else{$('coverageNote').textContent='Đang dùng cửa sổ dữ liệu trực tiếp - chưa phải tổng cả ngày';}

  const delayPct=f.length?Math.round(f.filter(delayed).length/f.length*100):0;
  const intlPct=f.length?Math.round(f.filter(x=>x.is_international).length/f.length*100):0;
  const domestic=f.length-international;
  const scope=isDay?(d.complete_day?'Tập dữ liệu từ đầu ngày':'Tập dữ liệu tích lũy từ lúc hệ thống bắt đầu theo dõi'):'Cửa sổ dữ liệu trực tiếp';
  $('reportBox').innerHTML=`${scope} hiện có <b>${total}</b> chuyến được quan sát, gồm <b>${arrivals}</b> chuyến đến và <b>${departures}</b> chuyến đi. Quốc tế chiếm khoảng <b>${intlPct}%</b>. Có <b>${delayedCount}</b> chuyến trễ hoặc thay đổi từ 15 phút trở lên, khoảng <b>${delayPct}%</b> tập dữ liệu. ${!isDay||!d.complete_day?'Đây là số liệu quan sát của hệ thống, không nên hiểu là thống kê đầy đủ toàn bộ lịch khai thác trong ngày.':''}`;

  barList('marketBars',[{label:'Nội địa',value:domestic},{label:'Quốc tế',value:international}]);
  barList('terminalDelayBars',['T1','T2','T3'].map(t=>({label:t,value:f.filter(x=>String(x.terminal).toUpperCase()===t&&delayed(x)).length})));

  const airlineItems=countBy(f,x=>x.airline||carrier(x.flight_number)).slice(0,10);
  barList('airlineBars',airlineItems);
  const intlRoutes=countBy(f.filter(x=>x.is_international),x=>routeLabel(x.route_airport||'')).slice(0,10);
  barList('internationalRouteBars',intlRoutes);
  barList('routeBars',countBy(f,x=>routeLabel(x.route_airport||'')).slice(0,12));
  barList('terminalBars',countBy(f,x=>x.terminal||'-'));

  const hours=Array.from({length:24},()=>0);for(const x of f){const m=/^(\d{2}):/.exec(x.scheduled||'');if(m)hours[Number(m[1])]++;}
  const max=Math.max(1,...hours);$('hourGrid').innerHTML=hours.map((v,h)=>`<div class="hour-col"><div class="hour-bar" style="height:${Math.max(3,Math.round(v/max*118))}px" title="${h}:00 - ${v} chuyến"></div><span>${String(h).padStart(2,'0')}</span></div>`).join('');
}
load().catch(err=>{$('coverageNote').textContent='Chưa có dữ liệu thống kê';$('reportBox').textContent=`Không đọc được dữ liệu: ${err.message}`;});
