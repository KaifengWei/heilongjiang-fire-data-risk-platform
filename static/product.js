(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const modal = $('#guideModal');
  const dontShow = $('#guideDontShow');
  const DISMISS_KEY = 'fireMonitorGuideDismissedV1';

  function switchHelpTab(name) {
    $$('[data-help-tab]').forEach(button => button.classList.toggle('active', button.dataset.helpTab === name));
    $$('[data-help-panel]').forEach(panel => panel.classList.toggle('active', panel.dataset.helpPanel === name));
  }

  function openHelp(tab = 'start') {
    if (!modal) return;
    switchHelpTab(tab);
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => modal.classList.add('open'));
    document.body.classList.add('modal-open');
  }

  function closeHelp({ remember = false } = {}) {
    if (!modal) return;
    if (remember && dontShow?.checked) {
      try { localStorage.setItem(DISMISS_KEY, '1'); } catch (_) {}
    }
    modal.classList.remove('open');
    document.body.classList.remove('modal-open');
    setTimeout(() => {
      modal.hidden = true;
      modal.setAttribute('aria-hidden', 'true');
    }, 180);
  }

  $$('[data-open-help]').forEach(button => button.addEventListener('click', () => openHelp('start')));
  $$('[data-close-help]').forEach(button => button.addEventListener('click', () => closeHelp()));
  $$('[data-help-tab]').forEach(button => button.addEventListener('click', () => switchHelpTab(button.dataset.helpTab)));
  $('#guideStartButton')?.addEventListener('click', () => closeHelp({ remember: true }));

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && modal && !modal.hidden) closeHelp();
  });

  function maybeOpenDesktopGuide() {
    let dismissed = false;
    try { dismissed = localStorage.getItem(DISMISS_KEY) === '1'; } catch (_) {}
    if (!dismissed && window.pywebview) openHelp('start');
  }

  window.addEventListener?.('pywebviewready', maybeOpenDesktopGuide);
  document.addEventListener?.('pywebviewready', maybeOpenDesktopGuide);
  setTimeout(maybeOpenDesktopGuide, 900);

  // Upload experience.
  const fileInput = $('#analysisFiles');
  const fileText = $('#selectedFileText');
  const form = $('#autoAnalyzeForm');
  const submit = $('#analyzeButton');
  const progress = $('#analysisProgress');
  const dropzone = $('#uploadDropzone');

  function updateFileText() {
    if (!fileInput || !fileText) return;
    const files = Array.from(fileInput.files || []);
    if (!files.length) {
      fileText.textContent = '支持 FIRMS CSV 与 MCD64A1 GeoTIFF';
      return;
    }
    fileText.textContent = files.length === 1
      ? files[0].name
      : `已选择 ${files.length} 个文件：${files.map(file => file.name).join('、')}`;
    dropzone?.classList.add('has-files');
  }

  fileInput?.addEventListener('change', updateFileText);

  ['dragenter', 'dragover'].forEach(type => dropzone?.addEventListener(type, event => {
    event.preventDefault();
    dropzone.classList.add('dragging');
  }));
  ['dragleave', 'drop'].forEach(type => dropzone?.addEventListener(type, event => {
    event.preventDefault();
    dropzone.classList.remove('dragging');
  }));
  dropzone?.addEventListener('drop', event => {
    if (!fileInput || !event.dataTransfer?.files?.length) return;
    try {
      const transfer = new DataTransfer();
      Array.from(event.dataTransfer.files).forEach(file => transfer.items.add(file));
      fileInput.files = transfer.files;
      updateFileText();
    } catch (_) {}
  });

  form?.addEventListener('submit', () => {
    if (submit) {
      submit.disabled = true;
      submit.textContent = '正在分析…';
    }
    if (progress) progress.hidden = false;
  });

  // Gentle reveal animation.
  const revealItems = $$('.reveal-item');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    revealItems.forEach(item => observer.observe(item));
  } else {
    revealItems.forEach(item => item.classList.add('visible'));
  }

  // Animate server-rendered result bars.
  requestAnimationFrame(() => {
    $$('.bar-track span').forEach((bar, index) => {
      setTimeout(() => bar.classList.add('grow'), 80 + index * 40);
    });
    $$('.time-column span').forEach((bar, index) => {
      setTimeout(() => bar.classList.add('grow'), 120 + Math.min(index, 30) * 18);
    });
  });

  // Task-level administrative-region map. It deliberately uses only the
  // current analysis record's statistics and the bundled region boundaries.
  const canvas = $('#taskMapCanvas');
  const featuresNode = $('#taskMapFeatures');
  const statsNode = $('#taskMapStats');

  if (canvas && featuresNode && statsNode) {
    let featureCollection = null;
    let stats = [];
    try {
      featureCollection = JSON.parse(featuresNode.textContent || '{}');
      stats = JSON.parse(statsNode.textContent || '[]');
    } catch (_) {}

    const features = featureCollection?.features || [];
    const byRegion = new Map(stats.map(row => [row.region_name, row]));
    const useFire = stats.some(row => Number(row.active_fire_count || 0) > 0);
    const metric = row => useFire ? Number(row?.active_fire_count || 0) : Number(row?.burned_area_km2 || 0);
    const maxValue = Math.max(0, ...stats.map(metric));

    function ringsOf(geometry) {
      if (!geometry) return [];
      if (geometry.type === 'Polygon') return geometry.coordinates || [];
      if (geometry.type === 'MultiPolygon') return (geometry.coordinates || []).flat();
      return [];
    }

    const points = [];
    features.forEach(feature => ringsOf(feature.geometry).forEach(ring => ring.forEach(point => points.push(point))));

    if (!points.length) {
      const empty = $('#taskMapEmpty');
      if (empty) empty.hidden = false;
    } else {
      const xs = points.map(point => Number(point[0]));
      const ys = points.map(point => Number(point[1]));
      const bounds = { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };

      function drawMap() {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
        const width = Math.max(520, Math.round(rect.width || 760));
        const height = Math.max(340, Math.round(rect.height || 460));
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        const ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        const pad = 28;
        const spanX = Math.max(0.001, bounds.maxX - bounds.minX);
        const spanY = Math.max(0.001, bounds.maxY - bounds.minY);
        const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY);
        const xOffset = (width - spanX * scale) / 2;
        const yOffset = (height - spanY * scale) / 2;
        const project = point => [xOffset + (Number(point[0]) - bounds.minX) * scale, height - (yOffset + (Number(point[1]) - bounds.minY) * scale)];

        features.forEach(feature => {
          const name = feature.properties?.name || '';
          const value = metric(byRegion.get(name));
          const ratio = maxValue > 0 ? Math.sqrt(value / maxValue) : 0;
          const alpha = value > 0 ? 0.18 + ratio * 0.58 : 0.035;

          ringsOf(feature.geometry).forEach(ring => {
            if (!ring.length) return;
            ctx.beginPath();
            ring.forEach((point, index) => {
              const [x, y] = project(point);
              if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            });
            ctx.closePath();
            ctx.fillStyle = useFire ? `rgba(219, 73, 61, ${alpha})` : `rgba(41, 139, 102, ${alpha})`;
            ctx.fill();
            ctx.strokeStyle = 'rgba(83, 139, 165, .78)';
            ctx.lineWidth = 1;
            ctx.stroke();
          });
        });

        features.forEach(feature => {
          const name = feature.properties?.name || '';
          const value = metric(byRegion.get(name));
          if (value <= 0) return;
          const ring = ringsOf(feature.geometry)[0] || [];
          if (!ring.length) return;
          const centroid = ring.reduce((acc, point) => [acc[0] + Number(point[0]), acc[1] + Number(point[1])], [0, 0]).map(total => total / ring.length);
          const [x, y] = project(centroid);
          const radius = 3.5 + 9 * Math.sqrt(value / Math.max(1, maxValue));
          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fillStyle = useFire ? 'rgba(218, 67, 52, .82)' : 'rgba(35, 132, 93, .82)';
          ctx.fill();
          ctx.strokeStyle = 'rgba(255,255,255,.9)';
          ctx.lineWidth = 1.8;
          ctx.stroke();
        });
      }

      drawMap();
      let timer = null;
      window.addEventListener('resize', () => {
        clearTimeout(timer);
        timer = setTimeout(drawMap, 140);
      });
    }
  }
})();
