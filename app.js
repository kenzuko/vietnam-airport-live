const DATA_URL = './data/sgn.json';

const state = {
  data: null,
  direction: 'arrival',
  terminal: 'all',
  filter: 'all',
  query: ''
};

const $ = (id) => document.getElementById(id);

function normalizeText(value = '') {
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
    .trim();
}

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function hhmmToMinutes(value) {
  if (!/^\d{2}:\d{2}$/.test(value || '')) return null;
  const [h, m] = value.split(':').map(Number);
  return h * 60 + m;
}

function vnNowMinutes() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false
  }).formatToParts(new Date());
  const h = Number(parts.find(p => p.type === 'hour')?.value || 0);
  const m = Number(parts.find(p => p.type === 'minute')?.value || 0);
  return h * 60 + m;
}

function isWithinNext3Hours(flight) {
  const raw = flight.estimated || flight.scheduled;
  const t = hhmmToMinutes(raw);
  if (t == null) return false;
  const now = vnNowMinutes();
  let diff = t - now;
  if (diff < -720) diff += 1440;
  return diff >= 0 && diff <= 180;
}

function isDelayed(flight) {
  const status = normalizeText(flight.status);
  return (Number(flight.delay_minutes) >= 15) || status.includes('tre') || status.includes('delay');
}

function isChanged(flight) {
  return isDelayed(flight) || Boolean(flight.estimated && flight.estimated !== flight.scheduled);
}

function flightSearchText(f) {
  return normalizeText([
    f.flight_number, f.airline, f.origin, f.destination, f.route_airport,
    f.status, f.terminal, f.gate, f.counter, f.belt
  ].filter(Boolean).join(' '));
}

function filteredFlights() {
  if (!state.data?.flights) return [];
  const q = normalizeText(state.query);
  return state.data.flights.filter(f => {
    if (state.direction !== 'all' && f.direction !== state.direction) return false;
    if (state.terminal !== 'all' && String(f.terminal || '').toUpperCase() !== state.terminal) return false;
    if (state.filter === 'next3' && !isWithinNext3Hours(f)) return false;
    if (state.filter === 'delayed' && !isChanged(f)) return false;
    if (state.filter === 'international' && !f.is_international) return false;
    if (q && !flightSearchText(f).includes(q)) return false;
    return true;
  });
}

function statusClass(f) {
  if (isDelayed(f)) return 'delay';
  const s = normalizeText(f.status);
  if (s.includes('ha canh') || s.includes('departed') || s.includes('landed') || s.includes('on time')) return 'ok';
  return '';
}

function displayStatus(f) {
  if (f.status) return f.status;
  if (f.actual) return f.direction === 'arrival' ? 'Đã hạ cánh' : 'Đã khởi hành';
  if (f.estimated && f.estimated !== f.scheduled) return 'Updated';
  return 'Scheduled';
}

function flightRow(f) {
  const route = f.route_airport || (f.direction === 'arrival' ? f.origin : f.destination) || 'Đang cập nhật';
  const timeMain = f.estimated || f.actual || f.scheduled || '--:--';
  const scheduled = f.scheduled || '--:--';
  const delay = Number.isFinite(Number(f.delay_minutes)) ? Number(f.delay_minutes) : null;
  const delayLabel = delay != null && delay >= 10 ? `<span class="delay-minutes">+${delay} phút</span>` : '';
  const meta = [f.gate ? `Gate ${f.gate}` : null, f.counter ? `Quầy ${f.counter}` : null, f.belt ? `Belt ${f.belt}` : null].filter(Boolean).join(' · ');

  return `<article class="flight-row">
    <div class="flight-time"><strong>${esc(timeMain)}</strong><small>Lịch ${esc(scheduled)}</small></div>
    <div class="flight-main"><strong>${esc(f.flight_number || '-')}</strong><small>${esc(f.airline || 'Hãng bay')}</small></div>
    <div class="flight-route"><strong>${esc(route)}</strong><small>${f.direction === 'arrival' ? 'Đến SGN' : 'Rời SGN'}</small></div>
    <div class="flight-meta"><span class="terminal-tag">${esc(f.terminal || '-')}</span><small>${esc(meta || 'Thông tin cổng đang cập nhật')}</small></div>
    <div class="flight-status"><span class="status-badge ${statusClass(f)}">${esc(displayStatus(f))}</span>${delayLabel}</div>
  </article>`;
}

function renderBoard() {
  const flights = filteredFlights();
  $('flightList').innerHTML = flights.length
    ? flights.map(flightRow).join('')
    : `<div class="empty-state">Không có chuyến phù hợp bộ lọc hiện tại.</div>`;
}

function renderWatch() {
  const flights = (state.data?.flights || [])
    .filter(isChanged)
    .sort((a, b) => (Number(b.delay_minutes) || 0) - (Number(a.delay_minutes) || 0))
    .slice(0, 7);
  $('watchCount').textContent = flights.length;
  $('watchList').innerHTML = flights.length
    ? flights.map(f => {
        const delay = Number(f.delay_minutes);
        const extra = Number.isFinite(delay) && delay >= 10 ? ` · +${delay} phút` : '';
        return `<div class="watch-item"><strong>${esc(f.flight_number)} · ${esc(f.route_airport || '-')}</strong><span>${esc(displayStatus(f))}${esc(extra)}</span></div>`;
      }).join('')
    : `<div class="empty-state">Chưa thấy thay đổi đáng chú ý.</div>`;
}

function ageInfo(generatedAt) {
  if (!generatedAt) return { minutes: Infinity, label: 'Chưa có dữ liệu' };
  const t = new Date(generatedAt).getTime();
  if (!Number.isFinite(t)) return { minutes: Infinity, label: 'Không rõ' };
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 1) return { minutes: mins, label: 'vừa cập nhật' };
  if (mins < 60) return { minutes: mins, label: `${mins} phút` };
  return { minutes: mins, label: `${Math.floor(mins / 60)}g ${mins % 60}p` };
}

function renderSummary() {
  const d = state.data;
  const s = d?.summary || {};
  $('totalFlights').textContent = s.total ?? 0;
  $('arrivalsCount').textContent = s.arrivals ?? 0;
  $('departuresCount').textContent = s.departures ?? 0;
  $('delayedCount').textContent = s.delayed ?? 0;

  const total = Number(s.total) || 0;
  const delayed = Number(s.delayed) || 0;
  const ratio = total ? delayed / total : 0;
  if (!total) {
    $('opsState').textContent = 'WAITING';
    $('opsDetail').textContent = 'Chờ lần đồng bộ đầu tiên';
  } else if (ratio >= 0.18) {
    $('opsState').textContent = 'WATCH';
    $('opsDetail').textContent = `${delayed} chuyến đang có thay đổi`;
  } else if (delayed > 0) {
    $('opsState').textContent = 'ACTIVE';
    $('opsDetail').textContent = `${delayed} chuyến cần chú ý`;
  } else {
    $('opsState').textContent = 'NORMAL';
    $('opsDetail').textContent = 'Chưa thấy trễ đáng kể trong feed';
  }

  $('sourceName').textContent = d?.source || '-';
  $('coverage').textContent = d?.coverage || '-';
  $('terminals').textContent = (s.terminals || []).join(', ') || '-';

  const age = ageInfo(d?.generated_at);
  $('dataAge').textContent = age.label;
  $('updatedAt').textContent = d?.generated_at ? `Cập nhật ${age.label} trước` : 'Chưa đồng bộ';
  $('sourceText').textContent = d?.source || 'SGN data feed';

  const pill = $('healthPill');
  pill.className = 'health-pill';
  if (!total) {
    pill.classList.add('loading');
    pill.innerHTML = '<i></i> WAITING';
    $('qaBadge').textContent = 'WAIT';
    $('healthTitle').textContent = 'WAITING FOR DATA';
    $('healthDescription').textContent = 'Workflow đang chờ lấy bộ dữ liệu SGN đầu tiên.';
    $('healthIcon').textContent = '⋯';
  } else if (age.minutes > 15) {
    pill.classList.add('stale');
    pill.innerHTML = '<i></i> STALE';
    $('qaBadge').textContent = 'STALE';
    $('healthTitle').textContent = 'DATA STALE';
    $('healthDescription').textContent = 'Dữ liệu đã cũ hơn 15 phút. Không coi là realtime.';
    $('healthIcon').textContent = '!';
  } else {
    pill.innerHTML = '<i></i> LIVE';
    $('qaBadge').textContent = 'OK';
    $('healthTitle').textContent = 'DATA HEALTHY';
    $('healthDescription').textContent = 'Feed SGN đang nằm trong cửa sổ cập nhật cho phép.';
    $('healthIcon').textContent = '✓';
  }
}

function setActive(container, selector, key, value) {
  container.querySelectorAll(selector).forEach(btn => {
    btn.classList.toggle('active', btn.dataset[key] === value);
  });
}

async function loadData() {
  $('refreshBtn').disabled = true;
  $('errorBox').classList.add('hidden');
  try {
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data || !Array.isArray(data.flights)) throw new Error('Dataset không hợp lệ');
    state.data = data;
    renderSummary();
    renderBoard();
    renderWatch();
  } catch (err) {
    $('healthPill').className = 'health-pill error';
    $('healthPill').innerHTML = '<i></i> ERROR';
    $('errorBox').textContent = `Không đọc được dữ liệu SGN: ${err.message}`;
    $('errorBox').classList.remove('hidden');
  } finally {
    $('refreshBtn').disabled = false;
  }
}

$('directionTabs').addEventListener('click', e => {
  const btn = e.target.closest('[data-direction]');
  if (!btn) return;
  state.direction = btn.dataset.direction;
  setActive($('directionTabs'), 'button', 'direction', state.direction);
  renderBoard();
});

$('terminalTabs').addEventListener('click', e => {
  const btn = e.target.closest('[data-terminal]');
  if (!btn) return;
  state.terminal = btn.dataset.terminal;
  setActive($('terminalTabs'), 'button', 'terminal', state.terminal);
  renderBoard();
});

$('filterTabs').addEventListener('click', e => {
  const btn = e.target.closest('[data-filter]');
  if (!btn) return;
  state.filter = btn.dataset.filter;
  setActive($('filterTabs'), 'button', 'filter', state.filter);
  renderBoard();
});

$('searchInput').addEventListener('input', e => {
  state.query = e.target.value;
  renderBoard();
});

$('refreshBtn').addEventListener('click', loadData);

loadData();
setInterval(loadData, 60_000);
