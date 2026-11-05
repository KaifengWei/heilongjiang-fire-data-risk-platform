(() => {
  'use strict';

  const panel = document.querySelector('#weatherContextPanel');
  const workspace = document.querySelector('#taskWorkspace');

  if (!panel || !workspace) return;

  const taskId = workspace.getAttribute('data-task-id') || '';
  if (!taskId) return;

  const eyebrow = panel.querySelector('.app-eyebrow');
  const title = panel.querySelector('#weatherContextTitle');
  const source = panel.querySelector('#weatherContextSource');
  const cards = panel.querySelector('#weatherHorizonCards');
  const head = panel.querySelector('.weather-context-head');

  function ensureLead() {
    let lead = panel.querySelector('.weather-context-lead');

    if (!lead && head) {
      lead = document.createElement('p');
      lead.className = 'weather-context-lead';
      head.insertAdjacentElement('afterend', lead);
    }

    return lead;
  }

  function setLead(text) {
    const lead = ensureLead();
    if (lead) lead.textContent = text;
  }

  function setLoading(active) {
    panel.classList.toggle('is-weather-loading', Boolean(active));
  }

  function showLoading() {
    panel.hidden = false;
    setLoading(true);

    if (eyebrow) eyebrow.textContent = 'WEATHER CONTEXT';
    if (title) title.textContent = '正在读取天气资料';
    if (source) source.textContent = '正在连接天气数据源';
    setLead('正在匹配任务日期和重点区域，请稍候。');

    if (cards) {
      cards.innerHTML = `
        <div class="weather-loading-stage" role="status" aria-live="polite">
          <div class="weather-loading-copy">
            <strong>正在生成天气背景与建议</strong>
            <span>读取气象资料 · 匹配任务日期 · 汇总重点区域</span>
          </div>
          <div class="weather-loading-track" aria-hidden="true">
            <span></span>
          </div>
        </div>
      `;
    }
  }

  function revealReady() {
    requestAnimationFrame(() => {
      panel.classList.add('weather-ready');
      setLoading(false);
    });
  }

  function numericOrNull(value) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function metricText(metrics) {
    const rows = [];

    const humidity = numericOrNull(metrics?.humidity_percent);
    const wind = numericOrNull(metrics?.wind_mps);
    const rain = numericOrNull(metrics?.precipitation_mm);
    const temp = numericOrNull(metrics?.temperature_c);

    if (Number.isFinite(humidity)) {
      rows.push(`平均湿度 ${Math.round(humidity)}%`);
    }

    if (Number.isFinite(wind)) {
      rows.push(`平均风速 ${wind.toFixed(1)} m/s`);
    }

    if (Number.isFinite(rain)) {
      rows.push(`日均降水 ${rain.toFixed(1)} mm`);
    }

    if (Number.isFinite(temp)) {
      rows.push(`平均气温 ${temp.toFixed(1)} ℃`);
    }

    return rows;
  }

  function readableFact(label, value) {
    return `<span><b>${label}</b>${value}</span>`;
  }

  function weatherVisual(kind) {
    return `
      <div class="weather-motion weather-motion-${kind}" aria-hidden="true">
        <span class="weather-sun"></span>
        <span class="weather-cloud"></span>
        <span class="weather-wind-line line-a"></span>
        <span class="weather-wind-line line-b"></span>
        <span class="weather-rain-drop drop-a"></span>
        <span class="weather-rain-drop drop-b"></span>
        <span class="weather-rain-drop drop-c"></span>
      </div>
    `;
  }

  function visualClass(item) {
    const rain = Number(item.precipitation_mm);
    const wind = Number(item.wind_mps);
    const humidity = Number(item.humidity_percent);

    if (Number.isFinite(rain) && rain >= 5) return 'rainy';
    if (Number.isFinite(wind) && wind >= 6) return 'windy';
    if (Number.isFinite(humidity) && humidity <= 40) return 'dry';
    return 'calm';
  }

  function airLabel(item) {
    const humidity = Number(item.humidity_percent);

    if (!Number.isFinite(humidity)) return '空气状况暂无';
    if (humidity <= 35) return `空气偏干 · 湿度 ${Math.round(humidity)}%`;
    if (humidity <= 45) return `空气较干 · 湿度 ${Math.round(humidity)}%`;
    if (humidity >= 75) return `空气湿润 · 湿度 ${Math.round(humidity)}%`;
    return `湿度适中 · ${Math.round(humidity)}%`;
  }

  function windLabel(item) {
    const wind = Number(item.wind_mps);

    if (!Number.isFinite(wind)) return '风力状况暂无';
    if (wind >= 8) return `风力较强 · ${wind.toFixed(1)} m/s`;
    if (wind >= 6) return `风力较明显 · ${wind.toFixed(1)} m/s`;
    if (wind >= 4) return `有一定风 · ${wind.toFixed(1)} m/s`;
    return `风力较弱 · ${wind.toFixed(1)} m/s`;
  }

  function rainLabel(item) {
    const rain = Number(item.precipitation_mm);

    if (!Number.isFinite(rain)) return '降水状况暂无';
    if (rain >= 10) return `降水较明显 · 累计 ${rain.toFixed(1)} mm`;
    if (rain >= 5) return `有一定降水 · 累计 ${rain.toFixed(1)} mm`;
    if (rain >= 1) return `有少量降水 · 累计 ${rain.toFixed(1)} mm`;
    return `降水很少 · 累计 ${rain.toFixed(1)} mm`;
  }

  function temperatureLabel(item) {
    const value = Number(item.temperature_c);

    if (!Number.isFinite(value)) return '气温暂无';
    return `气温约 ${value.toFixed(1)} ℃`;
  }

  function actionText(item) {
    const tone = item.tone || 'normal';

    if (tone === 'alert') {
      return '优先查看近期已有火点且重复活跃的县区，必要时安排重点核查。';
    }

    if (tone === 'watch') {
      return '保持对当前活跃县区的巡查，先看重复活跃位置和农田背景火点。';
    }

    if (tone === 'easing') {
      return '可维持常规查看，但已有持续活跃位置仍建议保留在巡查清单中。';
    }

    return '暂不需要扩大关注范围，按当前重点区域继续查看即可。';
  }

  function countyNames(item) {
    const counties = Array.isArray(item.counties) ? item.counties : [];
    const attention = counties
      .filter(row => row.tone === 'alert' || row.tone === 'watch')
      .map(row => row.county_name)
      .filter(Boolean);

    if (attention.length) return attention.slice(0, 3);

    return counties
      .slice()
      .sort((a, b) => Number(b.fire_count || 0) - Number(a.fire_count || 0))
      .map(row => row.county_name)
      .filter(Boolean)
      .slice(0, 2);
  }

  function renderForecast(data) {
    panel.classList.remove('is-weather-unavailable');
    if (eyebrow) eyebrow.textContent = 'SHORT-RANGE WEATHER';

    if (data.spatial_scope === 'densest_observation_area') {
      setLead('以本次实际火点最集中的经纬网格为中心，查看附近的未来24/48/72小时天气；仅代表取样范围内的观测位置。');
    } else {
      setLead('结合当前火点位置，查看未来天气变化和需要继续关注的区域。');
    }

    if (title) title.textContent = data.overall || '未来天气条件';

    if (source) {
      source.textContent = (
        `${data.source || 'NOAA GFS'} · ${data.cycle || '最新运行时次'}`
      );
    }

    if (!cards) return;

    cards.innerHTML = '';

    (data.horizons || []).forEach(item => {
      const article = document.createElement('article');
      article.className = `weather-horizon-card is-${item.tone || 'normal'}`;

      const names = countyNames(item);
      const kind = visualClass(item);

      article.innerHTML = `
        <div class="weather-card-layout">
          <div class="weather-card-copy">
            <div class="weather-horizon-head">
              <span>未来 ${item.hours} 小时</span>
              <b>${item.state || ''}</b>
            </div>

            <p class="weather-main-summary">${item.summary || ''}</p>

            <div class="weather-readable-facts" aria-label="天气条件说明">
              <span>${airLabel(item)}</span>
              <span>${windLabel(item)}</span>
              <span>${rainLabel(item)}</span>
              <span>${temperatureLabel(item)}</span>
            </div>

            <div class="weather-action-note">
              <strong>建议怎么做</strong>
              <span>${actionText(item)}</span>
            </div>

            ${
              names.length
                ? `<div class="weather-focus-region"><b>重点查看</b><span>${names.join('、')}</span></div>`
                : ''
            }
          </div>

          ${weatherVisual(kind)}
        </div>
      `;

      cards.appendChild(article);
    });

    revealReady();
  }

  function renderHistorical(data) {
    panel.classList.remove('is-weather-unavailable');
    if (eyebrow) eyebrow.textContent = 'HISTORICAL WEATHER';

    if (title) {
      title.textContent = data.overall || '任务期间天气背景';
    }

    if (source) {
      const start = data.period?.start || '';
      const end = data.period?.end || '';
      source.textContent = `${data.source || 'NASA POWER Daily'} · ${start} 至 ${end}`;
    }

    setLead(data.spatial_scope === 'representative_point'
      ? '选取本次火点最密集的经纬网格内实际代表点，查看任务日期的历史天气；不套用其他地区的气象资料。'
      : '结合任务日期和重点县区，查看火点出现时的天气条件。');

    if (!cards) return;

    const periodMetrics = data.period?.metrics || {};
    const peak = data.peak_day || {};
    const peakMetrics = peak.metrics || {};
    const counties = Array.isArray(data.counties) ? data.counties : [];

    const periodFacts = metricText(periodMetrics)
      .map(text => `<span>${text}</span>`)
      .join('');

    const peakFacts = [
      readableFact(
        '湿度',
        numericOrNull(peakMetrics.humidity_percent) !== null
          ? `${Math.round(Number(peakMetrics.humidity_percent))}%`
          : '暂无'
      ),
      readableFact(
        '风速',
        numericOrNull(peakMetrics.wind_mps) !== null
          ? `${Number(peakMetrics.wind_mps).toFixed(1)} m/s`
          : '暂无'
      ),
      readableFact(
        '降水',
        numericOrNull(peakMetrics.precipitation_mm) !== null
          ? `${Number(peakMetrics.precipitation_mm).toFixed(1)} mm`
          : '暂无'
      ),
      readableFact(
        '气温',
        numericOrNull(peakMetrics.temperature_c) !== null
          ? `${Number(peakMetrics.temperature_c).toFixed(1)} ℃`
          : '暂无'
      ),
    ].join('');

    const coordinatePoint = data.representative_point || null;
    const countyRows = counties.map(item => {
      const weather = item.peak_day || {};

      return `
        <div class="history-county-row">
          <div>
            <strong>${item.county_name || ''}</strong>
            <span>${Number(item.fire_count || 0).toLocaleString('zh-CN')} 个火点</span>
          </div>
          <p>${item.condition || ''}</p>
          <small>
            湿度 ${numericOrNull(weather.humidity_percent) !== null ? Math.round(Number(weather.humidity_percent)) + '%' : '暂无'} ·
            风速 ${numericOrNull(weather.wind_mps) !== null ? Number(weather.wind_mps).toFixed(1) + ' m/s' : '暂无'} ·
            降水 ${numericOrNull(weather.precipitation_mm) !== null ? Number(weather.precipitation_mm).toFixed(1) + ' mm' : '暂无'}
          </small>
        </div>
      `;
    }).join('');

    cards.innerHTML = `
      <article class="historical-weather-card historical-period-card">
        <div class="historical-weather-head">
          <span>任务期间</span>
          <b>${data.period?.start || ''} 至 ${data.period?.end || ''}</b>
        </div>
        <p>任务期平均天气</p>
        <div class="historical-metric-pills">${periodFacts}</div>
      </article>

      <article class="historical-weather-card historical-peak-card">
        <div class="historical-weather-head">
          <span>火点增多日</span>
          <b>${peak.date || ''} · ${Number(peak.fire_count || 0).toLocaleString('zh-CN')} 个火点</b>
        </div>
        <p>${peak.summary || ''}</p>
        <div class="historical-peak-facts">${peakFacts}</div>
      </article>

      <article class="historical-weather-card historical-county-card">
        <div class="historical-weather-head">
          <span>${coordinatePoint ? '气象取样坐标' : '重点区域'}</span>
          <b>${coordinatePoint ? '本次火点代表位置' : '火点较多的县区'}</b>
        </div>
        ${coordinatePoint
          ? `<p>东经 ${Number(coordinatePoint.longitude).toFixed(4)}°，北纬 ${Number(coordinatePoint.latitude).toFixed(4)}°</p>
             <small>所在网格共 ${Number(coordinatePoint.cell_count)} 条观测；点位天气代表所选坐标，不等同于整个区域平均值。</small>`
          : `<div class="history-county-list">${countyRows}</div>`}
      </article>
    `;

    renderDailyComparison(data);
    revealReady();
  }

  function renderDailyComparison(data) {
    const rows = Array.isArray(data.daily_comparison)
      ? data.daily_comparison.filter(row => /^\d{4}-\d{2}-\d{2}$/.test(String(row.date || '')))
      : [];
    if (!rows.length || !cards) return;

    const box = document.createElement('article');
    box.className = 'weather-daily-comparison';
    box.innerHTML = '<div class="weather-daily-heading"><div><strong>火点日期与天气变化</strong><p>按任务日期对照实际火点数量和取样点的每日天气</p></div><label>天气指标 <select aria-label="切换逐日天气指标"><option value="precipitation_mm">日降水量</option><option value="humidity_percent">相对湿度</option><option value="wind_mps">平均风速</option><option value="temperature_c">平均气温</option></select></label></div><div class="weather-daily-chart"></div><div class="weather-daily-legend"><span class="weather-daily-bar-mark">火点数量</span><span class="weather-daily-line-mark">天气指标</span><small>两组数据使用独立刻度，图形仅用于对照日期变化</small></div>';
    const chartHost = box.querySelector('.weather-daily-chart');
    const picker = box.querySelector('select');
    const labels = {
      precipitation_mm: ['日降水量', 'mm'],
      humidity_percent: ['相对湿度', '%'],
      wind_mps: ['平均风速', 'm/s'],
      temperature_c: ['平均气温', '℃'],
    };
    const NS = 'http://www.w3.org/2000/svg';
    function svgNode(tag, attrs, label) {
      const node = document.createElementNS(NS, tag);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
      if (label !== undefined) node.textContent = label;
      return node;
    }
    function draw() {
      const key = picker.value;
      const unit = labels[key][1];
      // Keep every date in the expanded table; sample only the SVG for legibility.
      const step = Math.max(1, Math.ceil(rows.length / 60));
      const shown = rows.filter((row, index) => index % step === 0 || index === rows.length - 1);
      const width = 920;
      const left = 42;
      const right = 900;
      const bottom = 185;
      const top = 18;
      const span = bottom - top;
      const counts = shown.map(row => Math.max(0, numericOrNull(row.fire_count) || 0));
      const maxCount = Math.max(1, ...counts);
      const values = shown.map(row => numericOrNull(row[key]));
      const available = values.filter(value => value !== null);
      const minWeather = available.length ? Math.min(0, ...available) : 0;
      const maxWeather = available.length ? Math.max(1, ...available) : 1;
      const weatherSpan = Math.max(0.001, maxWeather - minWeather);
      const svg = svgNode('svg', {
        viewBox: '0 0 920 230', role: 'img',
        'aria-label': '逐日火点数量柱状图与' + labels[key][0] + '折线图',
        preserveAspectRatio: 'none'
      });
      for (let tick = 0; tick <= 4; tick++) {
        const y = bottom - tick * span / 4;
        svg.appendChild(svgNode('line', {x1: left, y1: y, x2: right, y2: y, stroke: '#e2eaee', 'stroke-dasharray': '4 5'}));
        svg.appendChild(svgNode('text', {x: left - 8, y: y + 4, 'text-anchor': 'end', fill: '#698392', 'font-size': 11}, String(Math.round(maxCount * tick / 4))));
      }
      const xAt = index => left + (index + .5) * (right - left) / shown.length;
      const barWidth = Math.max(2.5, Math.min(18, (right - left) / shown.length * .62));
      let path = '';
      let connected = false;
      shown.forEach((row, index) => {
        const x = xAt(index);
        const h = counts[index] / maxCount * span;
        const bar = svgNode('rect', {x: x - barWidth / 2, y: bottom - h, width: barWidth, height: Math.max(0, h), rx: 2, fill: '#6ca6ba'});
        bar.appendChild(svgNode('title', {}, row.date + '：' + counts[index] + ' 条观测'));
        svg.appendChild(bar);
        const v = values[index];
        if (v === null) {
          connected = false;
        } else {
          const y = bottom - (v - minWeather) / weatherSpan * span;
          path += (connected ? ' L ' : ' M ') + x.toFixed(2) + ' ' + y.toFixed(2);
          connected = true;
        }
      });
      if (available.length) {
        svg.appendChild(svgNode('path', {d: path, fill: 'none', stroke: '#d38f49', 'stroke-width': 2.5, 'stroke-linejoin': 'round'}));
        shown.forEach((row, index) => {
          const v = values[index];
          if (v === null) return;
          const x = xAt(index);
          const y = bottom - (v - minWeather) / weatherSpan * span;
          const dot = svgNode('circle', {cx: x, cy: y, r: 2.6, fill: '#d38f49'});
          dot.appendChild(svgNode('title', {}, row.date + '：' + labels[key][0] + ' ' + v + ' ' + unit));
          svg.appendChild(dot);
        });
      }
      const marks = new Set([0, shown.length - 1]);
      for (let i = 1; i < 5; i++) marks.add(Math.round((shown.length - 1) * i / 5));
      [...marks].sort((a, b) => a - b).forEach(index => {
        svg.appendChild(svgNode('text', {
          x: xAt(index), y: 210, 'text-anchor': 'middle', 'font-size': 11, fill: '#647f8d'
        }, String(shown[index].date).slice(5)));
      });
      svg.appendChild(svgNode('text', {x: 900, y: 12, 'text-anchor': 'end', 'font-size': 11, fill: '#a56e32'}, labels[key][0] + '（' + unit + '）'));
      chartHost.replaceChildren(svg);
      const note = chartHost.parentElement.querySelector('.weather-daily-data-note');
      if (note) note.textContent = available.length ? '' : '该日期范围暂缺所选天气指标的数据。';
    }
    const note = document.createElement('p');
    note.className = 'weather-daily-data-note';
    box.appendChild(note);

    const details = document.createElement('details');
    details.className = 'weather-daily-details';
    const summary = document.createElement('summary');
    summary.textContent = '查看每日火点与天气数据（' + rows.length + ' 天）';
    details.appendChild(summary);
    const scroller = document.createElement('div');
    scroller.className = 'weather-daily-table-scroll';
    const table = document.createElement('table');
    const head = document.createElement('thead');
    const headerRow = document.createElement('tr');
    ['日期', '火点观测', '气温 ℃', '相对湿度 %', '风速 m/s', '日降水 mm'].forEach(label => {
      const cell = document.createElement('th');
      cell.textContent = label;
      headerRow.appendChild(cell);
    });
    head.appendChild(headerRow);
    table.appendChild(head);
    const body = document.createElement('tbody');
    rows.forEach(row => {
      const tr = document.createElement('tr');
      const values = [
        row.date, row.fire_count, row.temperature_c, row.humidity_percent,
        row.wind_mps, row.precipitation_mm,
      ];
      values.forEach((value, index) => {
        const td = document.createElement('td');
        td.textContent = index === 0 ? String(value) : (numericOrNull(value) === null ? '—' : String(value));
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    scroller.appendChild(table);
    details.appendChild(scroller);
    box.appendChild(details);
    cards.appendChild(box);
    picker.addEventListener('change', draw);
    draw();
  }

  function renderUnavailable(data) {
    panel.classList.add('is-weather-unavailable');
    if (eyebrow) eyebrow.textContent = 'WEATHER CONTEXT';
    if (title) title.textContent = '天气数据状态';
    if (source) source.textContent = 'NASA POWER / NOAA GFS';

    const reason = data && data.reason || 'request_failed';
    const messages = {
      outside_power_range: '任务日期早于 NASA POWER 历史日值资料的起始范围。',
      not_historical: '任务日期尚未结束，历史日值资料暂未形成。',
      no_task_dates: '当前记录没有可用于匹配气象资料的有效日期。',
      no_valid_coordinates: '当前记录没有可用于气象取样的有效经纬度。',
      county_context_unavailable: '历史天气需要真实可定位的观测位置；当前缺少县区定位资料。',
      no_county_locations: '暂未找到能够匹配的县区观测位置。',
      power_unavailable: 'NASA POWER 暂未返回可解析的历史日值数据，请检查网络后重新获取。',
      gfs_unavailable: 'NOAA GFS 当前没有取得完整的 24/48/72 小时预报文件，请稍后重试。',
      gfs_parse_failed: 'GFS 资料已获取，但气象字段解析失败，需要检查 GRIB 数据。',
      no_weather_samples: '天气文件不包含当前重点火点位置的有效格点数据。',
      not_cached: '本地尚未保存这条记录的天气资料，请先联网打开天气模块。',
      request_failed: '天气服务请求未完成，请检查本地程序和网络连接。',
    };
    const message = messages[reason] || '目前没有取得这次任务可用的天气资料。';
    setLead(message);
    if (cards) {
      const article = document.createElement('article');
      article.className = 'weather-unavailable-note';
      const hint = document.createElement('span');
      hint.textContent = '火点观测与空间分析仍可正常使用。';
      article.appendChild(hint);
      if (['power_unavailable', 'gfs_unavailable', 'request_failed', 'not_cached'].includes(reason)) {
        const button = document.createElement('button');
        button.className = 'app-button app-button-ghost';
        button.type = 'button';
        button.textContent = '重新获取天气资料';
        button.addEventListener('click', requestWeather);
        article.appendChild(button);
      }
      cards.replaceChildren(article);
    }
    revealReady();
  }

  function render(data) {
    panel.classList.remove('is-weather-unavailable');
    if (!data?.available) {
      renderUnavailable(data);
      return;
    }

    if (data.mode === 'historical') {
      renderHistorical(data);
      return;
    }

    renderForecast(data);
  }

  function requestWeather() {
    panel.classList.remove('weather-ready', 'is-weather-unavailable');
    showLoading();
    fetch(
      '/api/tasks/' + encodeURIComponent(taskId) + '/weather-context',
      { headers: { Accept: 'application/json' }, cache: 'no-store' }
    )
      .then(response => {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(render)
      .catch(() => renderUnavailable({ reason: 'request_failed' }));
  }

  requestWeather();
})();
