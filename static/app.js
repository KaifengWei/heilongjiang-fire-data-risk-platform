const state = { summary: null, map: null, status: null };

const $ = (id) => document.getElementById(id);
const number = (value, digits = 0) => Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits });

function buildQuery(includeLimit = false) {
  const params = new URLSearchParams();
  const region = $('regionSelect').value;
  const start = $('startDate').value;
  const end = $('endDate').value;
  if (region) params.set('region', region);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (includeLimit) params.set('limit', $('mapLimit').value);
  return params.toString();
}

async function getJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || '请求失败');
  return payload;
}

function setText(id, value) { $(id).textContent = value; }

function renderSummary(summary) {
  setText('activeCount', number(summary.active_fire_observation_count));
  setText('burnedCount', number(summary.burned_pixel_count));
  setText('burnedArea', number(summary.burned_area_km2, 2));
  const parts = [];
  summary.active_by_source.forEach((item) => parts.push(`主动火点：${item.firms_source} ${number(item.count)} 条`));
  summary.burned_by_source.forEach((item) => parts.push(`火烧迹地：${item.source_product} ${number(item.pixels)} 像元 / ${number(item.area_km2, 2)} km²`));
  $('sourceBreakdown').innerHTML = parts.length
    ? parts.map((text) => `<div class="source-item"><strong>${escapeHtml(text)}</strong></div>`).join('')
    : '<p class="empty">当前筛选条件下没有已导入记录。</p>';
}

function escapeHtml(text) {
  return String(text).replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[c]);
}

function renderDaily(rows) {
  const tbody = $('dailyRows');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">当前筛选条件下没有逐日记录。</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((row) => `<tr><td>${row.date}</td><td>${number(row.active_fire_observation_count)}</td><td>${number(row.burned_pixel_count)}</td><td>${number(row.burned_area_km2, 4)}</td></tr>`).join('');
}

function coordinatePairs(geometry, out = []) {
  if (!geometry) return out;
  const walk = (value) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number') {
      out.push(value);
    } else {
      value.forEach(walk);
    }
  };
  if (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon') walk(geometry.coordinates);
  if (geometry.type === 'GeometryCollection') geometry.geometries.forEach((item) => coordinatePairs(item, out));
  return out;
}

function collectBoundaryPairs(featureCollection) {
  const pairs = [];
  (featureCollection.features || []).forEach((feature) => coordinatePairs(feature.geometry, pairs));
  return pairs;
}

function drawRing(ctx, ring, project) {
  if (!ring || !ring.length) return;
  ctx.moveTo(...project(ring[0]));
  ring.slice(1).forEach((point) => ctx.lineTo(...project(point)));
  ctx.closePath();
}

function drawGeometry(ctx, geometry, project) {
  if (!geometry) return;
  if (geometry.type === 'Polygon') {
    ctx.beginPath(); geometry.coordinates.forEach((ring) => drawRing(ctx, ring, project)); ctx.fill('evenodd'); ctx.stroke();
  } else if (geometry.type === 'MultiPolygon') {
    ctx.beginPath(); geometry.coordinates.forEach((polygon) => polygon.forEach((ring) => drawRing(ctx, ring, project))); ctx.fill('evenodd'); ctx.stroke();
  } else if (geometry.type === 'GeometryCollection') {
    geometry.geometries.forEach((item) => drawGeometry(ctx, item, project));
  }
}

function renderMap(payload) {
  const canvas = $('mapCanvas');
  const ctx = canvas.getContext('2d');
  const boundaryPairs = collectBoundaryPairs(payload.boundary);
  const active = payload.active_fire.points || [];
  const burned = payload.burned_pixels.points || [];
  const pointPairs = [...active, ...burned].map((p) => [p.longitude, p.latitude]);
  const allPairs = [...boundaryPairs, ...pointPairs];
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!allPairs.length) {
    ctx.fillStyle = '#64748b'; ctx.font = '22px Microsoft YaHei'; ctx.textAlign = 'center';
    ctx.fillText('请先导入行政区边界与数据，再进行查询。', canvas.width / 2, canvas.height / 2);
    return;
  }
  const lons = allPairs.map((p) => p[0]); const lats = allPairs.map((p) => p[1]);
  let minLon = Math.min(...lons), maxLon = Math.max(...lons), minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const lonPadding = Math.max((maxLon - minLon) * .06, .03); const latPadding = Math.max((maxLat - minLat) * .06, .03);
  minLon -= lonPadding; maxLon += lonPadding; minLat -= latPadding; maxLat += latPadding;
  const margin = 34; const contentW = canvas.width - margin * 2; const contentH = canvas.height - margin * 2;
  const project = ([lon, lat]) => [margin + ((lon - minLon) / (maxLon - minLon || 1)) * contentW, canvas.height - margin - ((lat - minLat) / (maxLat - minLat || 1)) * contentH];
  ctx.fillStyle = '#edf7f4'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = '#b9d2d7'; ctx.lineWidth = 1; ctx.setLineDash([5, 6]);
  for (let i = 1; i < 6; i++) { const y = margin + contentH * i / 6; ctx.beginPath(); ctx.moveTo(margin, y); ctx.lineTo(canvas.width - margin, y); ctx.stroke(); }
  ctx.setLineDash([]);
  ctx.fillStyle = 'rgba(109, 169, 188, .12)'; ctx.strokeStyle = '#367692'; ctx.lineWidth = 1.4;
  (payload.boundary.features || []).forEach((feature) => drawGeometry(ctx, feature.geometry, project));
  if ($('showBurned').checked) {
    ctx.fillStyle = 'rgba(46, 139, 103, .72)';
    burned.forEach((point) => { const [x, y] = project([point.longitude, point.latitude]); ctx.fillRect(x - 2, y - 2, 4, 4); });
  }
  if ($('showActive').checked) {
    ctx.fillStyle = 'rgba(217, 78, 65, .74)';
    active.forEach((point) => { const [x, y] = project([point.longitude, point.latitude]); ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill(); });
  }
  ctx.fillStyle = '#40566a'; ctx.font = '13px Microsoft YaHei'; ctx.textAlign = 'left';
  ctx.fillText(`范围：${minLon.toFixed(2)}°E–${maxLon.toFixed(2)}°E，${minLat.toFixed(2)}°N–${maxLat.toFixed(2)}°N`, margin, canvas.height - 10);
  setText('mapNote', `红色主动火点显示 ${number(active.length)} / ${number(payload.active_fire.total)} 条；绿色烧毁像元显示 ${number(burned.length)} / ${number(payload.burned_pixels.total)} 个。为保证浏览器响应，地图可能抽样，统计卡片始终使用全量数据。`);
}

function renderStatus(status) {
  const active = status.active_fire || {}; const burned = status.burned_pixels || {};
  setText('dataState', `已导入 ${number(status.regions)} 个区域；主动火点 ${number(active.count)} 条（${active.start || '—'} 至 ${active.end || '—'}）；烧毁像元 ${number(burned.count)} 个（${burned.start || '—'} 至 ${burned.end || '—'}）。`);
  const tbody = $('importRows');
  const imports = status.imports || [];
  tbody.innerHTML = imports.length ? imports.map((item) => `<tr><td>${escapeHtml(item.data_kind)}</td><td>${escapeHtml(item.status)}</td><td>${number(item.stored_count)}</td><td title="${escapeHtml(item.source_ref)}">${escapeHtml(item.source_ref)}</td></tr>`).join('') : '<tr><td colspan="4" class="empty">尚未导入数据。</td></tr>';
}

async function loadRegions() {
  const payload = await getJson('/api/regions');
  const select = $('regionSelect');
  payload.regions.forEach((region) => {
    const option = document.createElement('option'); option.value = region.name; option.textContent = `${region.name}（${region.level}）`; select.appendChild(option);
  });
}

async function refresh() {
  $('refreshButton').disabled = true; $('refreshButton').textContent = '查询中…';
  try {
    const query = buildQuery(); const mapQuery = buildQuery(true);
    const [summary, daily, map, status] = await Promise.all([
      getJson(`/api/summary?${query}`), getJson(`/api/daily?${query}`), getJson(`/api/map?${mapQuery}`), getJson('/api/status'),
    ]);
    state.summary = summary; state.map = map; state.status = status;
    renderSummary(summary); renderDaily(daily.series); renderMap(map); renderStatus(status);
    $('exportLink').href = `/api/export.csv?${query}`;
  } catch (error) {
    alert(`查询失败：${error.message}`);
  } finally {
    $('refreshButton').disabled = false; $('refreshButton').textContent = '查询统计';
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  try { await loadRegions(); await refresh(); } catch (error) { $('dataState').textContent = `初始化失败：${error.message}`; }
  $('refreshButton').addEventListener('click', refresh);
  $('showActive').addEventListener('change', () => state.map && renderMap(state.map));
  $('showBurned').addEventListener('change', () => state.map && renderMap(state.map));
});
