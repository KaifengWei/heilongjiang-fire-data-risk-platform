(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const workspace = $('#taskWorkspace');
  const baseCanvas = $('#taskMapCanvas');
  const mapShell = baseCanvas?.closest('.interactive-map-shell');
  const sidePanel = $('.map-side-panel');

  if (!workspace || !baseCanvas || !mapShell || !sidePanel) return;

  const taskId = workspace.getAttribute('data-task-id') || '';
  if (!taskId) return;

  const cityRows = $$('.region-filter-row', sidePanel);
  const sideHeading = $('.side-panel-heading', sidePanel);
  const mapRegionLabel = $('#mapRegionLabel');
  const focusBadge = $('#mapFocusBadge');
  const focusText = $('#mapFocusText');
  const dateSlider = $('#mapDateSlider');

  const overlay = document.createElement('canvas');
  overlay.id = 'countyMapOverlay';
  overlay.setAttribute('aria-label', '县区边界');
  mapShell.appendChild(overlay);

  const countyPanel = document.createElement('div');
  countyPanel.className = 'county-drilldown-panel';
  countyPanel.hidden = true;
  countyPanel.innerHTML = `
    <div class="county-panel-heading">
      <button type="button" class="county-back-button">← 返回各市</button>
      <div>
        <span>COUNTY / DISTRICT</span>
        <strong id="countyPanelTitle">县区火点统计</strong>
      </div>
    </div>
    <div class="county-panel-list" id="countyPanelList"></div>
  `;
  sidePanel.appendChild(countyPanel);

  const backButton = $('.county-back-button', countyPanel);
  const countyPanelTitle = $('#countyPanelTitle', countyPanel);
  const countyPanelList = $('#countyPanelList', countyPanel);

  let points = [];
  let dates = [];
  let regionNames = [];
  let countyNames = [];
  let frpP90 = null;
  let persistentCells = [];

  let currentCity = '';
  let countyFeatures = [];
  let countyByName = new Map();
  let selectedCounty = '';
  let loadToken = 0;

  try {
    const persistentNode = $('#taskPersistentCells');
    persistentCells = JSON.parse(persistentNode?.textContent || '[]');
  } catch (_) {
    persistentCells = [];
  }

  function ringsOf(geometry) {
    if (!geometry) return [];
    if (geometry.type === 'Polygon') return geometry.coordinates || [];
    if (geometry.type === 'MultiPolygon') {
      return (geometry.coordinates || []).flat();
    }
    return [];
  }

  function polygonSets(geometry) {
    if (!geometry) return [];
    if (geometry.type === 'Polygon') return [geometry.coordinates || []];
    if (geometry.type === 'MultiPolygon') return geometry.coordinates || [];
    return [];
  }

  function pointInRing(x, y, ring) {
    let inside = false;

    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = Number(ring[i]?.[0]);
      const yi = Number(ring[i]?.[1]);
      const xj = Number(ring[j]?.[0]);
      const yj = Number(ring[j]?.[1]);

      if (![xi, yi, xj, yj].every(Number.isFinite)) continue;

      const intersects = (
        ((yi > y) !== (yj > y))
        && (
          x
          < (
            (xj - xi) * (y - yi)
            / ((yj - yi) || Number.EPSILON)
            + xi
          )
        )
      );

      if (intersects) inside = !inside;
    }

    return inside;
  }

  function geometryContains(geometry, lon, lat) {
    return polygonSets(geometry).some(polygon => {
      if (!polygon.length || !pointInRing(lon, lat, polygon[0])) {
        return false;
      }

      for (let index = 1; index < polygon.length; index += 1) {
        if (pointInRing(lon, lat, polygon[index])) {
          return false;
        }
      }

      return true;
    });
  }

  function boundsOfFeature(feature) {
    if (!feature) return null;

    const xs = [];
    const ys = [];

    ringsOf(feature.geometry).forEach(ring => {
      ring.forEach(point => {
        const x = Number(point?.[0]);
        const y = Number(point?.[1]);

        if (Number.isFinite(x) && Number.isFinite(y)) {
          xs.push(x);
          ys.push(y);
        }
      });
    });

    if (!xs.length) return null;

    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }

  function boundsOfFeatures(features) {
    const boxes = features
      .map(boundsOfFeature)
      .filter(Boolean);

    if (!boxes.length) return null;

    return {
      minX: Math.min(...boxes.map(box => box.minX)),
      maxX: Math.max(...boxes.map(box => box.maxX)),
      minY: Math.min(...boxes.map(box => box.minY)),
      maxY: Math.max(...boxes.map(box => box.maxY)),
    };
  }

  function activeBounds() {
    if (selectedCounty) {
      return boundsOfFeature(
        countyByName.get(selectedCounty)
      );
    }

    return boundsOfFeatures(countyFeatures);
  }

  function projection() {
    const bounds = activeBounds();
    if (!bounds) return null;

    const rect = baseCanvas.getBoundingClientRect();
    const width = Math.max(620, Math.round(rect.width || 900));
    const height = Math.max(420, Math.round(rect.height || 520));

    const pad = 26;
    const spanX = Math.max(.001, bounds.maxX - bounds.minX);
    const spanY = Math.max(.001, bounds.maxY - bounds.minY);

    const scale = Math.min(
      (width - pad * 2) / spanX,
      (height - pad * 2) / spanY
    );

    const xOffset = (width - spanX * scale) / 2;
    const yOffset = (height - spanY * scale) / 2;

    return {
      bounds,
      width,
      height,
      project: point => [
        xOffset + (Number(point[0]) - bounds.minX) * scale,
        height - (yOffset + (Number(point[1]) - bounds.minY) * scale),
      ],
      unproject: point => [
        bounds.minX + (Number(point[0]) - xOffset) / scale,
        bounds.minY + (height - Number(point[1]) - yOffset) / scale,
      ],
    };
  }

  function syncOverlaySize(context) {
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));

    overlay.width = context.width * dpr;
    overlay.height = context.height * dpr;
    overlay.style.width = `${context.width}px`;
    overlay.style.height = `${context.height}px`;

    const ctx = overlay.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, context.width, context.height);

    return ctx;
  }

  function drawCountyOverlay() {
    const context = projection();

    if (!context || !countyFeatures.length) {
      const ctx = overlay.getContext('2d');
      ctx?.clearRect(0, 0, overlay.width, overlay.height);
      return;
    }

    const ctx = syncOverlaySize(context);
    const drawFeatures = selectedCounty
      ? [countyByName.get(selectedCounty)].filter(Boolean)
      : countyFeatures;

    const countyLabelBoxes = [];

    drawFeatures.forEach(feature => {
      const name = feature.properties?.name || '';
      const isSelected = selectedCounty && name === selectedCounty;

      ringsOf(feature.geometry).forEach(ring => {
        if (!ring.length) return;

        ctx.beginPath();

        ring.forEach((point, index) => {
          const [x, y] = context.project(point);

          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });

        ctx.closePath();
        ctx.fillStyle = isSelected
          ? 'rgba(37,137,156,.13)'
          : 'rgba(255,255,255,.015)';
        ctx.fill();

        ctx.strokeStyle = isSelected
          ? 'rgba(18,108,132,.98)'
          : 'rgba(44,109,128,.58)';
        ctx.lineWidth = isSelected ? 1.8 : 1;
        ctx.stroke();
      });

      if (!selectedCounty) {
        const box = boundsOfFeature(feature);
        if (!box) return;

        const [x1, y1] = context.project([box.minX, box.minY]);
        const [x2, y2] = context.project([box.maxX, box.maxY]);
        const screenWidth = Math.abs(x2 - x1);
        const screenHeight = Math.abs(y2 - y1);

        if (screenWidth < 28 || screenHeight < 16) return;

        const [x, y] = context.project([
          (box.minX + box.maxX) / 2,
          (box.minY + box.maxY) / 2,
        ]);

        ctx.save();
        ctx.font = '600 11px Microsoft YaHei, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const textWidth = ctx.measureText(name).width + 8;

        const labelBox = {
          left: x - textWidth / 2 - 3,
          right: x + textWidth / 2 + 3,
          top: y - 11,
          bottom: y + 11,
        };

        const overlaps = countyLabelBoxes.some(existing => (
          labelBox.left < existing.right
          && labelBox.right > existing.left
          && labelBox.top < existing.bottom
          && labelBox.bottom > existing.top
        ));

        if (overlaps) {
          ctx.restore();
          return;
        }

        countyLabelBoxes.push(labelBox);

        ctx.fillStyle = 'rgba(255,255,255,.83)';
        ctx.fillRect(
          x - textWidth / 2,
          y - 8,
          textWidth,
          16
        );

        ctx.fillStyle = 'rgba(35,82,98,.86)';
        ctx.fillText(name, x, y);
        ctx.restore();
      }
    });

    if (selectedCounty) {
      ctx.save();
      ctx.font = '700 13px Microsoft YaHei, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(18,78,98,.9)';
      ctx.fillText(
        `${currentCity} · ${selectedCounty}`,
        context.width / 2,
        27
      );
      ctx.restore();
    }
  }

  function currentDateIndex() {
    const value = Number(dateSlider?.value || 0);
    return value <= 0 ? null : value - 1;
  }

  function currentTheme() {
    if ($('#layerHighFrp')?.checked) return 'frp';
    if ($('#layerPersistent')?.checked) return 'persistent';
    return 'fire';
  }

  function pointMatchesDate(point) {
    const dateIndex = currentDateIndex();
    return dateIndex === null || point[2] === dateIndex;
  }

  function persistentMatchesDate(cell) {
    const dateIndex = currentDateIndex();
    if (dateIndex === null) return true;

    const date = dates[dateIndex] || '';
    const activeDates = Array.isArray(cell.active_dates)
      ? cell.active_dates
      : [];

    return activeDates.includes(date);
  }

  function countyCount(feature) {
    const name = feature.properties?.name || '';
    const theme = currentTheme();

    if (theme === 'persistent') {
      return persistentCells.filter(cell => {
        if (
          currentCity
          && cell.region_name
          && cell.region_name !== currentCity
        ) {
          return false;
        }

        if (!persistentMatchesDate(cell)) return false;

        return geometryContains(
          feature.geometry,
          Number(cell.center_longitude),
          Number(cell.center_latitude)
        );
      }).length;
    }

    const cityIndex = regionNames.indexOf(currentCity);
    const countyIndex = countyNames.indexOf(name);

    if (cityIndex < 0 || countyIndex < 0) return 0;

    return points.filter(point => {
      if (point[3] !== cityIndex) return false;
      if (point[5] !== countyIndex) return false;
      if (!pointMatchesDate(point)) return false;

      if (theme === 'frp') {
        const value = Number(point[4]);

        return (
          Number.isFinite(value)
          && frpP90 !== null
          && value >= frpP90
        );
      }

      return true;
    }).length;
  }

  function metricLabel() {
    const theme = currentTheme();

    if (theme === 'frp') return '热强度较高';
    if (theme === 'persistent') return '持续活跃';
    return '火点';
  }

  function renderCountyPanel() {
    if (!countyPanelList || !currentCity) return;

    const rows = countyFeatures
      .map(feature => ({
        feature,
        name: feature.properties?.name || '',
        count: countyCount(feature),
      }))
      .filter(row => row.name)
      .sort((a, b) => (
        b.count - a.count
        || a.name.localeCompare(b.name, 'zh-CN')
      ));

    const total = rows.reduce(
      (sum, row) => sum + row.count,
      0
    );

    countyPanelTitle.textContent = `${currentCity}县区${metricLabel()}统计`;

    countyPanelList.innerHTML = '';

    const allButton = document.createElement('button');
    allButton.type = 'button';
    allButton.className = `county-filter-row ${selectedCounty ? '' : 'active'}`;
    allButton.innerHTML = `
      <span>全市</span>
      <b>${total.toLocaleString('zh-CN')}</b>
    `;
    allButton.addEventListener('click', () => {
      selectCounty('');
    });
    countyPanelList.appendChild(allButton);

    rows.forEach(row => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = (
        `county-filter-row ${selectedCounty === row.name ? 'active' : ''}`
      );

      button.innerHTML = `
        <span>${row.name}</span>
        <b>${row.count.toLocaleString('zh-CN')}</b>
      `;

      button.addEventListener('click', () => {
        selectCounty(row.name);
      });

      countyPanelList.appendChild(button);
    });
  }

  function setGlobalCountyFilter(name, feature) {
    window.__countyDrilldownSelected = name || '';
    window.__countyDrilldownFeature = feature || null;

    window.__countyContains = feature
      ? ((lon, lat) => (
          geometryContains(
            feature.geometry,
            Number(lon),
            Number(lat)
          )
        ))
      : null;

    window.dispatchEvent(
      new CustomEvent(
        'county-drilldown-change',
        {
          detail: {
            city: currentCity,
            county: name || '',
          },
        }
      )
    );
  }

  function selectCounty(name) {
    selectedCounty = name || '';

    const feature = selectedCounty
      ? countyByName.get(selectedCounty) || null
      : null;

    setGlobalCountyFilter(
      selectedCounty,
      feature
    );

    if (mapRegionLabel) {
      mapRegionLabel.textContent = selectedCounty
        ? `${currentCity} · ${selectedCounty}`
        : currentCity;
    }

    if (focusBadge && focusText) {
      focusText.textContent = selectedCounty
        ? `${currentCity} · ${selectedCounty}`
        : currentCity;
      focusBadge.hidden = !currentCity;
    }

    renderCountyPanel();

    setTimeout(
      drawCountyOverlay,
      115
    );
  }

  function clearCountyState() {
    selectedCounty = '';
    countyFeatures = [];
    countyByName = new Map();

    setGlobalCountyFilter(
      '',
      null
    );

    const ctx = overlay.getContext('2d');
    ctx?.clearRect(
      0,
      0,
      overlay.width,
      overlay.height
    );
  }

  function showCityPanel() {
    cityRows.forEach(row => {
      row.hidden = false;
    });

    if (sideHeading) {
      sideHeading.hidden = false;
    }

    countyPanel.hidden = true;
  }

  function showCountyPanel() {
    cityRows.forEach(row => {
      row.hidden = true;
    });

    if (sideHeading) {
      sideHeading.hidden = true;
    }

    countyPanel.hidden = false;
  }

  async function loadCityCounties(city) {
    const token = ++loadToken;

    currentCity = city || '';
    window.__countyDrilldownActiveCity = currentCity;
    clearCountyState();

    if (!currentCity) {
      showCityPanel();
      return;
    }

    showCountyPanel();

    countyPanelTitle.textContent = `${currentCity}县区加载中…`;
    countyPanelList.innerHTML = `
      <div class="county-panel-loading">
        正在加载县区边界…
      </div>
    `;

    try {
      const response = await fetch(
        `/api/regions/counties?city=${encodeURIComponent(currentCity)}`,
        {
          headers: {
            Accept: 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();

      if (token !== loadToken) return;

      countyFeatures = Array.isArray(payload.features)
        ? payload.features
        : [];

      countyByName = new Map(
        countyFeatures.map(feature => [
          feature.properties?.name || '',
          feature,
        ])
      );

      if (!countyFeatures.length) {
        countyPanelTitle.textContent = `${currentCity}县区边界暂不可用`;
        countyPanelList.innerHTML = `
          <div class="county-panel-loading">
            当前没有可显示的县区边界。
          </div>
        `;
        return;
      }

      renderCountyPanel();

      setTimeout(
        drawCountyOverlay,
        110
      );
    } catch (_) {
      if (token !== loadToken) return;

      countyPanelTitle.textContent = `${currentCity}县区加载失败`;
      countyPanelList.innerHTML = `
        <div class="county-panel-loading">
          请刷新页面后重试。
        </div>
      `;
    }
  }

  backButton?.addEventListener('click', () => {
    const allCities = cityRows.find(row => (
      (row.getAttribute('data-region-filter') || '') === ''
    ));

    if (allCities) {
      allCities.click();
    } else {
      currentCity = '';
      clearCountyState();
      showCityPanel();
    }
  });

  window.addEventListener(
    'city-region-change',
    event => {
      const city = String(
        event.detail?.region || ''
      );

      loadCityCounties(
        city
      );
    }
  );

  dateSlider?.addEventListener(
    'input',
    () => {
      if (!currentCity) return;
      renderCountyPanel();
    }
  );

  $('#mapAllDatesButton')?.addEventListener(
    'click',
    () => {
      if (!currentCity) return;
      setTimeout(
        renderCountyPanel,
        0
      );
    }
  );

  [
    $('#layerAllFires'),
    $('#layerHighFrp'),
    $('#layerPersistent'),
  ].forEach(input => {
    input?.addEventListener(
      'change',
      () => {
        if (!currentCity || !input.checked) return;
        renderCountyPanel();
      }
    );
  });

  overlay.addEventListener(
    'click',
    event => {
      if (
        selectedCounty
        || !countyFeatures.length
      ) {
        return;
      }

      const context = projection();
      if (!context) return;

      const rect = overlay.getBoundingClientRect();

      const x = (
        event.clientX
        - rect.left
      ) * (
        context.width
        / rect.width
      );

      const y = (
        event.clientY
        - rect.top
      ) * (
        context.height
        / rect.height
      );

      const [lon, lat] = context.unproject([
        x,
        y,
      ]);

      const hit = countyFeatures.find(
        feature => geometryContains(
          feature.geometry,
          lon,
          lat
        )
      );

      if (hit) {
        selectCounty(
          hit.properties?.name || ''
        );
      }
    }
  );

  window.addEventListener(
    'resize',
    () => {
      if (!currentCity) return;

      setTimeout(
        drawCountyOverlay,
        130
      );
    }
  );

  async function loadTaskPayload() {
    try {
      const response = await fetch(
        `/api/tasks/${encodeURIComponent(taskId)}/map-data`,
        {
          headers: {
            Accept: 'application/json',
          },
        }
      );

      if (!response.ok) return;

      const payload = await response.json();

      points = Array.isArray(payload.points)
        ? payload.points
        : [];

      dates = Array.isArray(payload.dates)
        ? payload.dates
        : [];

      regionNames = Array.isArray(payload.regions)
        ? payload.regions
        : [];

      countyNames = Array.isArray(payload.counties)
        ? payload.counties
        : [];

      const threshold = Number(
        payload.frp_p90
      );

      frpP90 = Number.isFinite(
        threshold
      )
        ? threshold
        : null;
    } catch (_) {}
  }

  loadTaskPayload();
})();
