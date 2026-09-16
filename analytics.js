const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').toLowerCase();
function delayed(f){return Number(f.delay_minutes)>=15||norm(f.status).includes('tre')||norm(f.status).includes('delay')||norm(f.status).includes('late');}
function fmtTime(value){if(!value)return'-';try{return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}).format(new Date(value));}catch{return'-';}}
function barList(target,items){const max=Math.max(1,...items.map(x=>x.value));$(target).innerHTML=items.length?items.map(x=>`<div class="bar-row"><span>${esc(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.round(x.value/max*100)}%"></div></div><b>${x.value}</b></div>`).join(''):'<div class="empty-state">Chưa đủ dữ liệu.</div>';}
async function load(){
  const res=await fetch(`./data/sgn-day.json?t=${Date.now()}`,{cache:'no-store'});if(!res.ok)throw new Error(`HTTP ${res.status}`);const d=await res.json();const f=d.flights||[];const s=d.summary||{};
  $('aTotal').textContent=s.total??f.length;$('aArrivals').textContent=s.arrivals??0;$('aDepartures').textContent=s.departures??0;$('aInternational').textContent=s.international??0;$('aDelayed').textContent=s.delayed??0;
  $('coverageNote').textContent=d.complete_day?'Độ phủ: đủ chu kỳ từ đầu ngày':`Độ phủ: hệ thống ghi nhận từ ${fmtTime(d.first_seen_at)} - chưa phải toàn bộ ngày`;
  const delayPct=f.length?Math.round((f.filter(delayed).length/f.length)*100):0;const intlPct=f.length?Math.round((f.filter(x=>x.is_international).length/f.length)*100):0;
  $('reportBox').innerHTML=`Hệ thống đã ghi nhận <b>${s.total??f.length}</b> chuyến trong ngày ${esc(d.date||'')}, gồm <b>${s.arrivals??0}</b> chuyến đến và <b>${s.departures??0}</b> chuyến đi. Tỷ trọng chuyến quốc tế trong tập đã ghi nhận khoảng <b>${intlPct}%</b>. Có <b>${s.delayed??0}</b> chuyến có mức trễ hoặc thay đổi trên ngưỡng 15 phút theo dữ liệu đang lưu, tương đương khoảng <b>${delayPct}%</b>. ${d.complete_day?'Tập dữ liệu đủ chu kỳ từ đầu ngày.':'Hôm nay hệ thống khởi động giữa ngày nên các tỷ lệ này chỉ phản ánh phần dữ liệu đã quan sát, chưa đại diện toàn bộ lịch khai thác SGN.'}`;
  const routes=new Map();for(const x of f){const k=x.route_airport||'-';routes.set(k,(routes.get(k)||0)+1);}barList('routeBars',[...routes].sort((a,b)=>b[1]-a[1]).slice(0,12).map(([label,value])=>({label,value})));
  const terms=new Map();for(const x of f){const k=x.terminal||'-';terms.set(k,(terms.get(k)||0)+1);}barList('terminalBars',[...terms].sort((a,b)=>b[1]-a[1]).map(([label,value])=>({label,value})));
  const hours=Array.from({length:24},()=>0);for(const x of f){const m=/^(\d{2}):/.exec(x.scheduled||'');if(m)hours[Number(m[1])]++;}const max=Math.max(1,...hours);$('hourGrid').innerHTML=hours.map((v,h)=>`<div class="hour-col"><div class="hour-bar" style="height:${Math.max(3,Math.round(v/max*118))}px" title="${h}:00 - ${v} chuyến"></div><span>${String(h).padStart(2,'0')}</span></div>`).join('');
}
load().catch(err=>{$('coverageNote').textContent='Chưa có dữ liệu thống kê';$('reportBox').textContent=`Không đọc được dữ liệu: ${err.message}`;});
