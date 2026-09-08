const state = {
  summary: null,
  map: null,
  status: null,

  // 始终保留完整的 13 个地市级行政区边界，
  // 这样选择某个市以后仍可以在地图上点击其他市切换。
  fullBoundary: null,

  mapRegions: [],
  hoveredRegion: null,
};

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

function geometryPath(geometry, project) {
  const path = new Path2D();

  const addRing = (ring) => {
    if (!ring || !ring.length) return;

    const [startX, startY] = project(ring[0]);
    path.moveTo(startX, startY);

    ring.slice(1).forEach((point) => {
      const [x, y] = project(point);
      path.lineTo(x, y);
    });

    path.closePath();
  };

  const addGeometry = (item) => {
    if (!item) return;

    if (item.type === 'Polygon') {
      item.coordinates.forEach(addRing);
    } else if (item.type === 'MultiPolygon') {
      item.coordinates.forEach((polygon) => {
        polygon.forEach(addRing);
      });
    } else if (item.type === 'GeometryCollection') {
      item.geometries.forEach(addGeometry);
    }
  };

  addGeometry(geometry);
  return path;
}

function featurePairs(feature) {
  return coordinatePairs(
    feature && feature.geometry
  );
}

function canvasPoint(event) {
  const canvas = $('mapCanvas');
  const rect = canvas.getBoundingClientRect();

  return {
    x: (
      (event.clientX - rect.left)
      * canvas.width
      / rect.width
    ),
    y: (
      (event.clientY - rect.top)
      * canvas.height
      / rect.height
    ),
  };
}

function findRegionAtCanvasPoint(x, y) {
  const canvas = $('mapCanvas');
  const ctx = canvas.getContext('2d');

  for (
    let i = state.mapRegions.length - 1;
    i >= 0;
    i -= 1
  ) {
    const item = state.mapRegions[i];

    if (
      ctx.isPointInPath(
        item.path,
        x,
        y,
        'evenodd'
      )
    ) {
      return item;
    }
  }

  return null;
}

function showMapTooltip(event, regionName) {
  const tooltip = $('mapTooltip');
  const viewport = document.querySelector(
    '.map-viewport'
  );
  const rect = viewport.getBoundingClientRect();

  tooltip.textContent = `${regionName} · 单击选择`;
  tooltip.hidden = false;

  tooltip.style.left = (
    event.clientX - rect.left + 14
  ) + 'px';

  tooltip.style.top = (
    event.clientY - rect.top + 14
  ) + 'px';
}

function hideMapTooltip() {
  $('mapTooltip').hidden = true;
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

  /*
   * 首次取得全部行政区时缓存。
   * 后续即使筛选哈尔滨市，也继续绘制完整黑龙江，
   * 从而允许直接点击齐齐哈尔等其他区域切换。
   */
  const incomingBoundary = (
    payload.boundary
    || {
      type: 'FeatureCollection',
      features: [],
    }
  );

  if (
    incomingBoundary.features
    && incomingBoundary.features.length > 1
  ) {
    state.fullBoundary = incomingBoundary;
  }

  const boundary = (
    state.fullBoundary
    || incomingBoundary
  );

  const boundaryPairs = collectBoundaryPairs(
    boundary
  );

  const active = (
    payload.active_fire.points
    || []
  );

  const burned = (
    payload.burned_pixels.points
    || []
  );

  /*
   * 地图范围以完整行政区边界为主。
   * 避免某个异常点把整个黑龙江地图缩得非常小。
   */
  const allPairs = boundaryPairs.length
    ? boundaryPairs
    : [
        ...active,
        ...burned,
      ].map(
        (point) => [
          point.longitude,
          point.latitude,
        ]
      );

  ctx.clearRect(
    0,
    0,
    canvas.width,
    canvas.height
  );

  state.mapRegions = [];

  if (!allPairs.length) {
    ctx.fillStyle = '#64748b';
    ctx.font = '22px Microsoft YaHei';
    ctx.textAlign = 'center';

    ctx.fillText(
      '请先导入行政区边界与数据，再进行查询。',
      canvas.width / 2,
      canvas.height / 2
    );

    return;
  }

  const lons = allPairs.map(
    (point) => Number(point[0])
  );

  const lats = allPairs.map(
    (point) => Number(point[1])
  );

  let minLon = Math.min(...lons);
  let maxLon = Math.max(...lons);
  let minLat = Math.min(...lats);
  let maxLat = Math.max(...lats);

  /*
   * 简单局部等距近似：
   * 经度乘以中心纬度 cos 值，
   * 避免高纬地区东西方向被严重拉长。
   */
  const centerLat = (
    (minLat + maxLat) / 2
  );

  const lonFactor = Math.cos(
    centerLat * Math.PI / 180
  );

  const projectedMinX = minLon * lonFactor;
  const projectedMaxX = maxLon * lonFactor;

  const geoWidth = Math.max(
    projectedMaxX - projectedMinX,
    0.000001
  );

  const geoHeight = Math.max(
    maxLat - minLat,
    0.000001
  );

  const margin = 48;

  const contentW = (
    canvas.width - margin * 2
  );

  const contentH = (
    canvas.height - margin * 2
  );

  /*
   * X / Y 使用同一个 scale。
   * 这是本次修复地图“太瘪”的关键。
   */
  const scale = Math.min(
    contentW / geoWidth,
    contentH / geoHeight
  );

  const drawnWidth = geoWidth * scale;
  const drawnHeight = geoHeight * scale;

  const offsetX = (
    (canvas.width - drawnWidth) / 2
  );

  const offsetY = (
    (canvas.height - drawnHeight) / 2
  );

  const project = ([lon, lat]) => {
    const px = Number(lon) * lonFactor;

    return [
      offsetX
        + (
          px - projectedMinX
        ) * scale,

      canvas.height
        - offsetY
        - (
          Number(lat) - minLat
        ) * scale,
    ];
  };

  ctx.fillStyle = '#edf7f4';

  ctx.fillRect(
    0,
    0,
    canvas.width,
    canvas.height
  );

  /*
   * 轻量参考线。
   */
  ctx.strokeStyle = '#cbdfe4';
  ctx.lineWidth = 1;
  ctx.setLineDash([5, 7]);

  for (let i = 1; i < 6; i += 1) {
    const y = (
      margin
      + (
        canvas.height
        - margin * 2
      ) * i / 6
    );

    ctx.beginPath();
    ctx.moveTo(margin, y);
    ctx.lineTo(
      canvas.width - margin,
      y
    );
    ctx.stroke();
  }

  ctx.setLineDash([]);

  const selectedRegion = (
    $('regionSelect').value
  );

  /*
   * 行政区绘制。
   */
  (
    boundary.features || []
  ).forEach((feature) => {
    const regionName = (
      feature.properties
      && feature.properties.name
    )
      || '';

    const path = geometryPath(
      feature.geometry,
      project
    );

    state.mapRegions.push({
      name: regionName,
      feature,
      path,
    });

    const isHovered = (
      state.hoveredRegion
      === regionName
    );

    const isSelected = (
      selectedRegion
      === regionName
    );

    if (isSelected) {
      ctx.fillStyle = (
        'rgba(23, 107, 135, .27)'
      );

      ctx.strokeStyle = '#0f5875';
      ctx.lineWidth = 3;
    } else if (isHovered) {
      ctx.fillStyle = (
        'rgba(54, 151, 168, .22)'
      );

      ctx.strokeStyle = '#176b87';
      ctx.lineWidth = 2.6;
    } else {
      ctx.fillStyle = (
        'rgba(93, 161, 181, .11)'
      );

      ctx.strokeStyle = '#4387a3';
      ctx.lineWidth = 1.5;
    }

    ctx.fill(
      path,
      'evenodd'
    );

    ctx.stroke(path);
  });

  /*
   * MCD64A1 烧毁像元。
   */
  if ($('showBurned').checked) {
    burned.forEach((point) => {
      const [x, y] = project([
        point.longitude,
        point.latitude,
      ]);

      ctx.fillStyle = (
        'rgba(46, 139, 103, .88)'
      );

      ctx.fillRect(
        x - 3,
        y - 3,
        6,
        6
      );
    });
  }

  /*
   * FIRMS 主动火点：
   * 白色外圈 + 红色核心，
   * 比旧版 2.5px 圆点更醒目。
   */
  if ($('showActive').checked) {
    active.forEach((point) => {
      const [x, y] = project([
        point.longitude,
        point.latitude,
      ]);

      ctx.beginPath();

      ctx.arc(
        x,
        y,
        6,
        0,
        Math.PI * 2
      );

      ctx.fillStyle = (
        'rgba(255, 255, 255, .95)'
      );

      ctx.fill();

      ctx.beginPath();

      ctx.arc(
        x,
        y,
        4,
        0,
        Math.PI * 2
      );

      ctx.fillStyle = (
        'rgba(217, 78, 65, .96)'
      );

      ctx.fill();
    });
  }

  /*
   * 如果存在选中行政区，
   * 在地图左上角标识当前筛选。
   */
  if (selectedRegion) {
    ctx.font = (
      '700 18px Microsoft YaHei'
    );

    ctx.textAlign = 'left';

    ctx.fillStyle = '#17324d';

    ctx.fillText(
      `当前区域：${selectedRegion}`,
      24,
      34
    );
  }

  ctx.fillStyle = '#526b7c';

  ctx.font = (
    '13px Microsoft YaHei'
  );

  ctx.textAlign = 'left';

  ctx.fillText(
    (
      `范围：`
      + `${minLon.toFixed(2)}°E–`
      + `${maxLon.toFixed(2)}°E，`
      + `${minLat.toFixed(2)}°N–`
      + `${maxLat.toFixed(2)}°N`
    ),
    24,
    canvas.height - 18
  );

  setText(
    'mapNote',
    (
      `红色主动火点显示 `
      + `${number(active.length)} / `
      + `${number(payload.active_fire.total)} 条；`
      + `绿色烧毁像元显示 `
      + `${number(burned.length)} / `
      + `${number(payload.burned_pixels.total)} 个。`
      + `地图每个图层最多显示所选上限数量的记录；`
      + `统计结果使用全部符合当前筛选条件的数据。`
    )
  );
}

function renderStatus(status) {
  const active = (
    status.active_fire || {}
  );

  const burned = (
    status.burned_pixels || {}
  );

  setText(
    'dataState',
    (
      `已导入 ${number(status.regions)} 个区域；`
      + `主动火点 ${number(active.count)} 条`
      + `（${active.start || '—'} 至 ${active.end || '—'}）；`
      + `烧毁像元 ${number(burned.count)} 个`
      + `（${burned.start || '—'} 至 ${burned.end || '—'}）。`
    )
  );

  const typeLabels = {
    active_fire_observations:
      'FIRMS 主动火点',

    burned_pixels_tif:
      'MCD64A1 烧毁像元',

    burned_pixels:
      '烧毁像元',
  };

  const statusLabels = {
    completed: '已完成',
    failed: '失败',
    running: '处理中',
    created: '已创建',
  };

  const tbody = $('importRows');

  const imports = (
    status.imports || []
  );

  tbody.innerHTML = imports.length
    ? imports.map((item) => {
        const sourceRef = (
          item.source_ref || ''
        );

        const shortSource = (
          sourceRef
            .split(/[\\/]/)
            .pop()
          || '—'
        );

        const typeLabel = (
          typeLabels[item.data_kind]
          || item.data_kind
        );

        const statusLabel = (
          statusLabels[item.status]
          || item.status
        );

        const statusClass = (
          item.status === 'completed'
          ? 'status-completed'
          : (
              item.status === 'failed'
              ? 'status-failed'
              : 'status-neutral'
            )
        );

        return (
          '<tr>'
          + `<td>${escapeHtml(typeLabel)}</td>`
          + '<td>'
          + `<span class="status-badge ${statusClass}">`
          + `${escapeHtml(statusLabel)}`
          + '</span>'
          + '</td>'
          + `<td>${number(item.stored_count)}</td>`
          + `<td title="${escapeHtml(sourceRef)}">`
          + `${escapeHtml(shortSource)}`
          + '</td>'
          + '</tr>'
        );
      }).join('')
    : (
        '<tr>'
        + '<td colspan="4" class="empty">'
        + '尚未导入数据。'
        + '</td>'
        + '</tr>'
      );
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

function setupMapInteraction() {
  const canvas = $('mapCanvas');

  canvas.addEventListener(
    'mousemove',
    (event) => {
      if (!state.map) return;

      const { x, y } = canvasPoint(
        event
      );

      const region = findRegionAtCanvasPoint(
        x,
        y
      );

      const nextRegion = (
        region
        ? region.name
        : null
      );

      if (
        nextRegion
        !== state.hoveredRegion
      ) {
        state.hoveredRegion = nextRegion;

        renderMap(
          state.map
        );
      }

      if (region) {
        canvas.classList.add(
          'is-region-hover'
        );

        showMapTooltip(
          event,
          region.name
        );
      } else {
        canvas.classList.remove(
          'is-region-hover'
        );

        hideMapTooltip();
      }
    }
  );

  canvas.addEventListener(
    'mouseleave',
    () => {
      state.hoveredRegion = null;

      canvas.classList.remove(
        'is-region-hover'
      );

      hideMapTooltip();

      if (state.map) {
        renderMap(
          state.map
        );
      }
    }
  );

  canvas.addEventListener(
    'click',
    async (event) => {
      const { x, y } = canvasPoint(
        event
      );

      const region = findRegionAtCanvasPoint(
        x,
        y
      );

      if (!region) return;

      const select = $('regionSelect');

      const exists = Array.from(
        select.options
      ).some(
        (option) => (
          option.value
          === region.name
        )
      );

      if (!exists) return;

      select.value = region.name;

      state.hoveredRegion = null;

      hideMapTooltip();

      await refresh();
    }
  );
}

document.addEventListener(
  'DOMContentLoaded',
  async () => {
    setupMapInteraction();

    try {
      await loadRegions();
      await refresh();
    } catch (error) {
      $('dataState').textContent = (
        `初始化失败：${error.message}`
      );
    }

    $('refreshButton').addEventListener(
      'click',
      refresh
    );

    $('showActive').addEventListener(
      'change',
      () => (
        state.map
        && renderMap(state.map)
      )
    );

    $('showBurned').addEventListener(
      'change',
      () => (
        state.map
        && renderMap(state.map)
      )
    );
  }
);
