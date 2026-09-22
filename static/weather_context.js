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

  function metricText(metrics) {
    const rows = [];

    const humidity = Number(metrics?.humidity_percent);
    const wind = Number(metrics?.wind_mps);
    const rain = Number(metrics?.precipitation_mm);
    const temp = Number(metrics?.temperature_c);

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
    if (eyebrow) eyebrow.textContent = 'SHORT-RANGE WEATHER';

    setLead('结合当前火点位置，查看未来天气变化和需要继续关注的区域。');

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
    if (eyebrow) eyebrow.textContent = 'HISTORICAL WEATHER';

    if (title) {
      title.textContent = data.overall || '任务期间天气背景';
    }

    if (source) {
      const start = data.period?.start || '';
      const end = data.period?.end || '';
      source.textContent = `${data.source || 'NASA POWER Daily'} · ${start} 至 ${end}`;
    }

    setLead('结合任务日期和重点县区，查看火点出现时的天气条件。');

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
        Number.isFinite(Number(peakMetrics.humidity_percent))
          ? `${Math.round(Number(peakMetrics.humidity_percent))}%`
          : '暂无'
      ),
      readableFact(
        '风速',
        Number.isFinite(Number(peakMetrics.wind_mps))
          ? `${Number(peakMetrics.wind_mps).toFixed(1)} m/s`
          : '暂无'
      ),
      readableFact(
        '降水',
        Number.isFinite(Number(peakMetrics.precipitation_mm))
          ? `${Number(peakMetrics.precipitation_mm).toFixed(1)} mm`
          : '暂无'
      ),
      readableFact(
        '气温',
        Number.isFinite(Number(peakMetrics.temperature_c))
          ? `${Number(peakMetrics.temperature_c).toFixed(1)} ℃`
          : '暂无'
      ),
    ].join('');

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
            湿度 ${Number.isFinite(Number(weather.humidity_percent)) ? Math.round(Number(weather.humidity_percent)) + '%' : '暂无'} ·
            风速 ${Number.isFinite(Number(weather.wind_mps)) ? Number(weather.wind_mps).toFixed(1) + ' m/s' : '暂无'} ·
            降水 ${Number.isFinite(Number(weather.precipitation_mm)) ? Number(weather.precipitation_mm).toFixed(1) + ' mm' : '暂无'}
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
          <span>重点区域</span>
          <b>火点较多的县区</b>
        </div>
        <div class="history-county-list">${countyRows}</div>
      </article>
    `;

    revealReady();
  }

  function renderUnavailable(data) {
    if (eyebrow) eyebrow.textContent = 'WEATHER CONTEXT';
    if (title) title.textContent = '天气资料暂不可用';
    if (source) source.textContent = '天气数据服务';

    const reason = data?.reason || '';

    const text = reason === 'outside_power_range'
      ? `这条任务早于当前历史气象数据覆盖范围（${data.earliest_supported || '1981-01-01'}起）。`
      : '暂时没有取得与这条任务时间相匹配的天气资料。';

    setLead(text);

    if (cards) {
      cards.innerHTML = `
        <article class="weather-unavailable-note">
          火点分析结果仍可正常查看。
        </article>
      `;
    }

    revealReady();
  }

  function render(data) {
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

  showLoading();

  fetch(
    `/api/tasks/${encodeURIComponent(taskId)}/weather-context`,
    { headers: { Accept: 'application/json' } }
  )
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch(() => {
      renderUnavailable({ reason: 'request_failed' });
    });
})();
