(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  // ---------------------------------------------------------
  // Tutorial modal — initialize first so map errors can never
  // disable the tutorial/help experience.
  // ---------------------------------------------------------
  const modal = $('#guideModal');
  const dontShow = $('#guideDontShow');
  const DISMISS_KEY = 'fireMonitorGuideDismissedV1';

  const slides = $$('[data-guide-slide]');
  const jumps = $$('[data-guide-jump]');
  const prevButton = $('#guidePrevButton');
  const nextButton = $('#guideNextButton');

  let slideIndex = 0;
  let slideBusy = false;

  function renderGuideStep(index, direction = 1, animate = false) {
    if (!slides.length) return;

    const target = Math.max(0, Math.min(slides.length - 1, Number(index) || 0));
    const current = slides.find(item => item.classList.contains('active'));

    if (current && current !== slides[target] && animate) {
      if (slideBusy) return;
      slideBusy = true;

      current.classList.add(direction >= 0 ? 'leaving-left' : 'leaving-right');

      setTimeout(() => {
        current.classList.remove('active', 'leaving-left', 'leaving-right');

        const incoming = slides[target];
        incoming.classList.add(
          'active',
          direction >= 0 ? 'entering-right' : 'entering-left'
        );

        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            incoming.classList.remove('entering-right', 'entering-left');
          });
        });

        slideBusy = false;
      }, 165);
    } else {
      slides.forEach((slide, idx) => {
        slide.classList.toggle('active', idx === target);
      });
    }

    slideIndex = target;

    jumps.forEach((button, idx) => {
      button.classList.toggle('active', idx === target);
      button.classList.toggle('done', idx < target);
    });

    if (prevButton) prevButton.disabled = target === 0;

    if (nextButton) {
      nextButton.textContent = target === slides.length - 1 ? '完成' : '下一步';
    }
  }

  function openHelp(index = 0) {
    if (!modal) return;

    renderGuideStep(index, 1, false);
    modal.classList.remove('closing');
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');

    requestAnimationFrame(() => {
      requestAnimationFrame(() => modal.classList.add('open'));
    });

    document.body.classList.add('modal-open');
  }

  function closeHelp({ remember = false } = {}) {
    if (!modal) return;

    if (remember && dontShow?.checked) {
      try {
        localStorage.setItem(DISMISS_KEY, '1');
      } catch (_) {}
    }

    modal.classList.remove('open');
    modal.classList.add('closing');
    document.body.classList.remove('modal-open');

    setTimeout(() => {
      modal.hidden = true;
      modal.classList.remove('closing');
      modal.setAttribute('aria-hidden', 'true');
    }, 300);
  }

  $$('[data-open-help]').forEach(button => {
    button.addEventListener('click', () => openHelp(0));
  });

  $$('[data-close-help]').forEach(button => {
    button.addEventListener('click', () => closeHelp());
  });

  jumps.forEach((button, idx) => {
    button.addEventListener('click', () => {
      const direction = idx >= slideIndex ? 1 : -1;
      renderGuideStep(idx, direction, true);
    });
  });

  prevButton?.addEventListener('click', () => {
    renderGuideStep(slideIndex - 1, -1, true);
  });

  nextButton?.addEventListener('click', () => {
    if (slideIndex >= slides.length - 1) {
      closeHelp({ remember: true });
      return;
    }
    renderGuideStep(slideIndex + 1, 1, true);
  });

  document.addEventListener('keydown', event => {
    if (recordModal && !recordModal.hidden && event.key === 'Escape') {
      closeRecordModal();
      return;
    }

    if (!modal || modal.hidden) return;

    if (event.key === 'Escape') closeHelp();
    if (event.key === 'ArrowRight') renderGuideStep(slideIndex + 1, 1, true);
    if (event.key === 'ArrowLeft') renderGuideStep(slideIndex - 1, -1, true);
  });

  function maybeOpenDesktopGuide() {
    let dismissed = false;

    try {
      dismissed = localStorage.getItem(DISMISS_KEY) === '1';
    } catch (_) {}

    if (!dismissed && window.pywebview) {
      openHelp(0);
    }
  }

  window.addEventListener?.('pywebviewready', maybeOpenDesktopGuide);
  document.addEventListener?.('pywebviewready', maybeOpenDesktopGuide);
  setTimeout(maybeOpenDesktopGuide, 900);


  // ---------------------------------------------------------
  // Upload experience
  // ---------------------------------------------------------
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
      fileText.textContent = '只需选择 NASA FIRMS 下载并解压后的 CSV';
      dropzone?.classList.remove('has-files');
      return;
    }

    fileText.textContent = files.length === 1
      ? files[0].name
      : `已选择 ${files.length} 个 CSV：${files.map(file => file.name).join('、')}`;

    dropzone?.classList.add('has-files');
  }

  fileInput?.addEventListener('change', updateFileText);

  ['dragenter', 'dragover'].forEach(type => {
    dropzone?.addEventListener(type, event => {
      event.preventDefault();
      dropzone.classList.add('dragging');
    });
  });

  ['dragleave', 'drop'].forEach(type => {
    dropzone?.addEventListener(type, event => {
      event.preventDefault();
      dropzone.classList.remove('dragging');
    });
  });

  dropzone?.addEventListener('drop', event => {
    if (!fileInput || !event.dataTransfer?.files?.length) return;

    const files = Array.from(event.dataTransfer.files);
    const invalid = files.find(file => !file.name.toLowerCase().endsWith('.csv'));

    if (invalid) {
      fileText.textContent = `不支持 ${invalid.name}：当前只接收 FIRMS CSV`;
      return;
    }

    try {
      const transfer = new DataTransfer();
      files.forEach(file => transfer.items.add(file));
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


  // ---------------------------------------------------------
  // Gentle reveal
  // ---------------------------------------------------------
  const revealItems = $$('.reveal-item');

  revealItems.forEach((item, index) => {
    item.style.setProperty('--reveal-delay', `${Math.min(index, 6) * 48}ms`);
  });

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.06 });

    revealItems.forEach(item => observer.observe(item));
  } else {
    revealItems.forEach(item => item.classList.add('visible'));
  }


  // ---------------------------------------------------------
  // Record management
  // ---------------------------------------------------------
  const recordModal = $('#recordManageModal');
  const renameForm = $('#recordRenameForm');
  const renameInput = $('#recordRenameInput');
  const deleteForm = $('#recordDeleteForm');
  const deleteName = $('#recordDeleteName');

  function recordReturnTarget() {
    return window.location.pathname === '/' ? 'home' : 'tasks';
  }

  function openRecordModal(mode, taskId, taskName) {
    if (!recordModal) return;

    $$('[data-record-mode]', recordModal).forEach(node => {
      node.hidden = node.getAttribute('data-record-mode') !== mode;
    });

    if (mode === 'rename' && renameForm && renameInput) {
      renameForm.action = `/tasks/${encodeURIComponent(taskId)}/rename`;
      renameInput.value = taskName || '';

      const returnField = $('#recordRenameReturnTo');
      if (returnField) returnField.value = recordReturnTarget();

      setTimeout(() => {
        renameInput.focus();
        renameInput.select();
      }, 30);
    }

    if (mode === 'delete' && deleteForm) {
      deleteForm.action = `/tasks/${encodeURIComponent(taskId)}/delete`;

      if (deleteName) {
        deleteName.textContent = taskName || '这条分析记录';
      }

      const returnField = $('#recordDeleteReturnTo');
      if (returnField) returnField.value = recordReturnTarget();
    }

    recordModal.hidden = false;
    recordModal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
  }

  function closeRecordModal() {
    if (!recordModal) return;

    recordModal.hidden = true;
    recordModal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
  }

  $$('[data-record-rename]').forEach(button => {
    button.addEventListener('click', () => {
      openRecordModal(
        'rename',
        button.getAttribute('data-task-id') || '',
        button.getAttribute('data-task-name') || ''
      );
    });
  });

  $$('[data-record-delete]').forEach(button => {
    button.addEventListener('click', () => {
      openRecordModal(
        'delete',
        button.getAttribute('data-task-id') || '',
        button.getAttribute('data-task-name') || ''
      );
    });
  });

  $$('[data-record-modal-close]').forEach(button => {
    button.addEventListener('click', closeRecordModal);
  });


  // ---------------------------------------------------------
  // FIRMS map workspace.
  // Map failures are isolated from the rest of the product JS.
  // ---------------------------------------------------------
  async function initTaskMapWorkspace() {
    const workspace = $('#taskWorkspace');
    const canvas = $('#taskMapCanvas');
    const featuresNode = $('#taskMapFeatures');

    if (!workspace || !canvas || !featuresNode) return;

    const taskId = workspace.getAttribute('data-task-id') || '';
    if (!taskId) return;

    const loadingChip = $('#mapLoadingChip');
    const mapEmpty = $('#taskMapEmpty');
    const dateSlider = $('#mapDateSlider');
    const dateLabel = $('#mapDateLabel');
    const playButton = $('#mapPlayButton');
    const allDatesButton = $('#mapAllDatesButton');
    const layerAllFires = $('#layerAllFires');
    const layerHighFrp = $('#layerHighFrp');
    const layerPersistent = $('#layerPersistent');
    const focusBadge = $('#mapFocusBadge');
    const focusText = $('#mapFocusText');
    const clearRegionFocus = $('#clearRegionFocus');
    const mapVisibleCount = $('#mapVisibleCount');
    const mapVisibleMetricLabel = $('#mapVisibleMetricLabel');
    const mapRegionLabel = $('#mapRegionLabel');

    let featureCollection = {};
    let persistentCells = [];

    try {
      featureCollection = JSON.parse(featuresNode.textContent || '{}');

      const persistentNode = $('#taskPersistentCells');
      persistentCells = JSON.parse(persistentNode?.textContent || '[]');
    } catch (_) {
      featureCollection = {};
      persistentCells = [];
    }

    const features = featureCollection?.features || [];
    const featureByName = new Map(
      features.map(feature => [
        feature.properties?.name || '',
        feature,
      ])
    );

    const boundaryPoints = [];

    function ringsOf(geometry) {
      if (!geometry) return [];
      if (geometry.type === 'Polygon') return geometry.coordinates || [];
      if (geometry.type === 'MultiPolygon') return (geometry.coordinates || []).flat();
      return [];
    }

    features.forEach(feature => {
      ringsOf(feature.geometry).forEach(ring => {
        ring.forEach(point => boundaryPoints.push(point));
      });
    });

    const xs = boundaryPoints.map(point => Number(point[0]));
    const ys = boundaryPoints.map(point => Number(point[1]));

    const provinceBounds = xs.length ? {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    } : null;

    function featureBounds(feature) {
      if (!feature) return null;

      const localPoints = [];

      ringsOf(feature.geometry).forEach(ring => {
        ring.forEach(point => localPoints.push(point));
      });

      if (!localPoints.length) return null;

      const localXs = localPoints.map(point => Number(point[0]));
      const localYs = localPoints.map(point => Number(point[1]));

      return {
        minX: Math.min(...localXs),
        maxX: Math.max(...localXs),
        minY: Math.min(...localYs),
        maxY: Math.max(...localYs),
      };
    }

    function activeBounds() {
      if (selectedRegion) {
        return featureBounds(featureByName.get(selectedRegion))
          || provinceBounds;
      }

      return provinceBounds;
    }

    let points = [];
    let allDates = [];
    let regionNames = [];
    let selectedDate = null;
    let selectedRegion = '';
    let focusPoint = null;
    let playTimer = null;
    let frpP90 = null;
    let loaded = false;

    function filteredPoints() {
      return points.filter(point => {
        if (selectedDate !== null && point[2] !== selectedDate) return false;
        if (selectedRegion && regionNames[point[3]] !== selectedRegion) return false;
        return true;
      });
    }

    function filteredPersistentCells() {
      const selectedDateValue = selectedDate === null
        ? null
        : (allDates[selectedDate] || null);

      return persistentCells.filter(cell => {
        if (
          selectedRegion
          && cell.region_name
          && cell.region_name !== selectedRegion
        ) {
          return false;
        }

        if (!selectedDateValue) {
          return true;
        }

        const activeDates = Array.isArray(cell.active_dates)
          ? cell.active_dates
          : [];

        return activeDates.includes(selectedDateValue);
      });
    }

    function stopPlayback() {
      if (playTimer) {
        clearInterval(playTimer);
        playTimer = null;
      }

      if (playButton) playButton.textContent = '▶';
    }

    function setSelectedDateIndex(dateIndex) {
      selectedDate = dateIndex;

      if (dateLabel) {
        dateLabel.textContent = dateIndex === null
          ? '全部日期'
          : (allDates[dateIndex] || '全部日期');
      }

      if (dateSlider) {
        dateSlider.value = dateIndex === null
          ? '0'
          : String(dateIndex + 1);
      }

      redrawMap();
    }

    function selectRegion(region) {
      selectedRegion = region || '';

      $$('.region-filter-row').forEach(button => {
        button.classList.toggle(
          'active',
          (button.getAttribute('data-region-filter') || '') === selectedRegion
        );
      });

      if (mapRegionLabel) {
        mapRegionLabel.textContent = selectedRegion || '黑龙江省';
      }

      if (focusBadge && focusText) {
        if (selectedRegion) {
          focusText.textContent = selectedRegion;
          focusBadge.hidden = false;
        } else if (!focusPoint) {
          focusBadge.hidden = true;
        }
      }

      canvas.classList.add('map-transitioning');

      setTimeout(() => {
        redrawMap();
        requestAnimationFrame(() => {
          canvas.classList.remove('map-transitioning');
        });
      }, 90);
    }

    function geometryContext() {
      const bounds = activeBounds();
      if (!bounds) return null;

      const rect = canvas.getBoundingClientRect();
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      const width = Math.max(620, Math.round(rect.width || 900));
      const height = Math.max(420, Math.round(rect.height || 520));

      canvas.width = width * dpr;
      canvas.height = height * dpr;

      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const pad = 26;
      const spanX = Math.max(.001, bounds.maxX - bounds.minX);
      const spanY = Math.max(.001, bounds.maxY - bounds.minY);

      const scale = Math.min(
        (width - pad * 2) / spanX,
        (height - pad * 2) / spanY
      );

      const xOffset = (width - spanX * scale) / 2;
      const yOffset = (height - spanY * scale) / 2;

      const project = point => [
        xOffset + (Number(point[0]) - bounds.minX) * scale,
        height - (yOffset + (Number(point[1]) - bounds.minY) * scale),
      ];

      return { ctx, width, height, project };
    }

    function drawBoundaries(context) {
      if (!context) return;

      const { ctx, project } = context;
      const bounds = activeBounds();

      if (!bounds) return;

      const spanX = Math.max(.001, bounds.maxX - bounds.minX);
      const spanY = Math.max(.001, bounds.maxY - bounds.minY);
      const maxSpan = Math.max(spanX, spanY);
      const step = maxSpan > 8 ? 2 : maxSpan > 4 ? 1 : maxSpan > 2 ? .5 : .25;

      ctx.save();
      ctx.strokeStyle = 'rgba(103,145,160,.10)';
      ctx.fillStyle = 'rgba(75,112,126,.42)';
      ctx.lineWidth = .6;
      ctx.font = '9px Microsoft YaHei, sans-serif';

      const firstLon = Math.ceil(bounds.minX / step) * step;
      const firstLat = Math.ceil(bounds.minY / step) * step;

      for (let lon = firstLon; lon <= bounds.maxX; lon += step) {
        const [x1, y1] = project([lon, bounds.minY]);
        const [x2, y2] = project([lon, bounds.maxY]);

        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        ctx.fillText(`${lon.toFixed(step < 1 ? 1 : 0)}°E`, x1 + 3, context.height - 8);
      }

      for (let lat = firstLat; lat <= bounds.maxY; lat += step) {
        const [x1, y1] = project([bounds.minX, lat]);
        const [x2, y2] = project([bounds.maxX, lat]);

        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        ctx.fillText(`${lat.toFixed(step < 1 ? 1 : 0)}°N`, 7, y1 - 3);
      }

      ctx.restore();

      const drawFeatures = selectedRegion
        ? [featureByName.get(selectedRegion)].filter(Boolean)
        : features;

      drawFeatures.forEach(feature => {
        const name = feature.properties?.name || '';
        const active = selectedRegion && name === selectedRegion;

        ringsOf(feature.geometry).forEach(ring => {
          if (!ring.length) return;

          ctx.beginPath();

          ring.forEach((point, index) => {
            const [x, y] = project(point);
            if (index === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });

          ctx.closePath();
          ctx.fillStyle = active
            ? 'rgba(52,145,165,.10)'
            : 'rgba(248,251,252,.96)';
          ctx.fill();

          ctx.strokeStyle = active
            ? 'rgba(33,126,148,.96)'
            : 'rgba(91,147,167,.76)';
          ctx.lineWidth = active ? 1.7 : 1;
          ctx.stroke();
        });
      });

      if (!selectedRegion) {
        ctx.save();
        ctx.font = '10px Microsoft YaHei, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        features.forEach(feature => {
          const name = feature.properties?.name || '';
          const box = featureBounds(feature);
          if (!name || !box) return;

          const [x, y] = project([
            (box.minX + box.maxX) / 2,
            (box.minY + box.maxY) / 2,
          ]);

          const width = ctx.measureText(name).width + 8;
          ctx.fillStyle = 'rgba(248,251,252,.78)';
          ctx.fillRect(x - width / 2, y - 8, width, 16);

          ctx.fillStyle = 'rgba(44,83,98,.70)';
          ctx.fillText(name, x, y);
        });

        ctx.restore();
      } else {
        ctx.save();
        ctx.font = '600 12px Microsoft YaHei, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillStyle = 'rgba(26,78,97,.74)';
        ctx.fillText(selectedRegion, context.width / 2, 26);
        ctx.restore();
      }
    }

    function redrawMap() {
      const context = geometryContext();

      if (!context) {
        if (mapEmpty) {
          mapEmpty.textContent = '行政区边界暂不可用。';
          mapEmpty.hidden = false;
        }
        return;
      }

      drawBoundaries(context);

      const { ctx, project } = context;

      if (!loaded) {
        if (mapEmpty) mapEmpty.hidden = true;
        return;
      }

      const visible = filteredPoints();

      if (mapEmpty) {
        mapEmpty.textContent = '当前筛选条件下没有火点。';
        mapEmpty.hidden = visible.length > 0;
      }

      if (layerAllFires?.checked !== false) {
        ctx.fillStyle = 'rgba(218,72,55,.38)';

        visible.forEach(point => {
          const [x, y] = project([point[0], point[1]]);

          ctx.beginPath();
          ctx.arc(
            x,
            y,
            selectedDate === null ? 1.35 : 2.2,
            0,
            Math.PI * 2
          );
          ctx.fill();
        });
      }

      if (layerHighFrp?.checked && frpP90 !== null) {
        visible.forEach(point => {
          const value = point[4];

          if (value === null || !Number.isFinite(value) || value < frpP90) {
            return;
          }

          const [x, y] = project([point[0], point[1]]);

          const size = selectedDate === null ? 2.8 : 3.7;

          ctx.beginPath();
          ctx.moveTo(x, y - size);
          ctx.lineTo(x + size, y);
          ctx.lineTo(x, y + size);
          ctx.lineTo(x - size, y);
          ctx.closePath();
          ctx.fillStyle = 'rgba(255,145,28,.82)';
          ctx.fill();

          ctx.strokeStyle = 'rgba(255,255,255,.92)';
          ctx.lineWidth = .8;
          ctx.stroke();
        });
      }

      if (layerPersistent?.checked) {
        filteredPersistentCells()
          .slice(
            0,
            selectedDate === null
              ? (selectedRegion ? 180 : 160)
              : 260
          )
          .forEach(cell => {
          if (
            selectedRegion
            && cell.region_name
            && cell.region_name !== selectedRegion
          ) {
            return;
          }

          const [x, y] = project([
            cell.center_longitude,
            cell.center_latitude,
          ]);

          const size = selectedRegion ? 4.0 : 2.8;

          ctx.beginPath();
          ctx.moveTo(x, y - size);
          ctx.lineTo(x - size * .88, y + size * .72);
          ctx.lineTo(x + size * .88, y + size * .72);
          ctx.closePath();
          ctx.fillStyle = 'rgba(22,125,151,.52)';
          ctx.fill();
          ctx.strokeStyle = 'rgba(12,100,123,.72)';
          ctx.lineWidth = .8;
          ctx.stroke();
        });
      }

      if (mapVisibleCount && mapVisibleMetricLabel) {
        let displayCount = visible.length;
        let displayLabel = '当前显示火点';

        if (layerHighFrp?.checked && frpP90 !== null) {
          displayCount = visible.filter(point => {
            const value = point[4];
            return value !== null && Number.isFinite(value) && value >= frpP90;
          }).length;
          displayLabel = '高 FRP 火点';
        }

        if (layerPersistent?.checked) {
          displayCount = filteredPersistentCells()
            .slice(
              0,
              selectedDate === null
                ? (selectedRegion ? 180 : 160)
                : 260
            )
            .length;
          displayLabel = '持续活跃标记';
        }

        mapVisibleCount.textContent = displayCount.toLocaleString('zh-CN');
        mapVisibleMetricLabel.textContent = displayLabel;
      }

      if (focusPoint) {
        const [x, y] = project([focusPoint.lon, focusPoint.lat]);

        ctx.beginPath();
        ctx.arc(x, y, 13, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(14,98,121,.96)';
        ctx.lineWidth = 2.2;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(x, y, 3.1, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(14,98,121,.96)';
        ctx.fill();
      }
    }

    // Draw the boundary immediately. The page no longer waits for
    // 28k+ fire records to be embedded in the initial HTML.
    redrawMap();

    try {
      const response = await fetch(
        `/api/tasks/${encodeURIComponent(taskId)}/map-data`,
        { headers: { Accept: 'application/json' } }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();

      points = Array.isArray(payload.points) ? payload.points : [];
      allDates = Array.isArray(payload.dates) ? payload.dates : [];
      regionNames = Array.isArray(payload.regions) ? payload.regions : [];
      frpP90 = Number.isFinite(Number(payload.frp_p90))
        ? Number(payload.frp_p90)
        : null;

      loaded = true;

      if (dateSlider) {
        dateSlider.max = String(allDates.length);
        dateSlider.value = '0';
      }

      if (loadingChip) loadingChip.hidden = true;

      redrawMap();
    } catch (error) {
      loaded = true;

      if (loadingChip) {
        loadingChip.hidden = false;
        loadingChip.textContent = '火点加载失败，请刷新页面重试';
        loadingChip.classList.add('error');
      }

      redrawMap();
    }

    dateSlider?.addEventListener('input', () => {
      stopPlayback();

      const value = Number(dateSlider.value || 0);
      setSelectedDateIndex(value <= 0 ? null : value - 1);
    });

    allDatesButton?.addEventListener('click', () => {
      stopPlayback();
      setSelectedDateIndex(null);
    });

    playButton?.addEventListener('click', () => {
      if (!allDates.length) return;

      if (playTimer) {
        stopPlayback();
        return;
      }

      let index = selectedDate === null ? -1 : selectedDate;
      playButton.textContent = 'Ⅱ';

      playTimer = setInterval(() => {
        index += 1;

        if (index >= allDates.length) {
          stopPlayback();
          return;
        }

        setSelectedDateIndex(index);
      }, 650);
    });

    [layerAllFires, layerHighFrp, layerPersistent].forEach(input => {
      input?.addEventListener('change', () => {
        if (!input.checked) return;

        $$('.map-mode-switch label').forEach(label => {
          label.classList.toggle(
            'active',
            label.contains(input)
          );
        });


        canvas.classList.add('map-transitioning');

        setTimeout(() => {
          redrawMap();
          requestAnimationFrame(() => {
            canvas.classList.remove('map-transitioning');
          });
        }, 90);
      });
    });

    $$('.region-filter-row').forEach(button => {
      button.addEventListener('click', () => {
        focusPoint = null;
        selectRegion(button.getAttribute('data-region-filter') || '');
      });
    });

    $$('[data-map-date]').forEach(button => {
      button.addEventListener('click', () => {
        stopPlayback();

        const date = button.getAttribute('data-map-date') || '';
        const index = allDates.indexOf(date);

        if (index >= 0) {
          setSelectedDateIndex(index);
        }

        canvas.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
      });
    });

    $$('[data-map-focus]').forEach(button => {
      button.addEventListener('click', () => {
        const lat = Number(button.getAttribute('data-focus-lat'));
        const lon = Number(button.getAttribute('data-focus-lon'));
        const region = button.getAttribute('data-focus-region') || '';

        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

        focusPoint = { lat, lon };

        if (focusBadge && focusText) {
          focusText.textContent = region
            ? `${region} · 持续活跃区域`
            : '持续活跃区域';
          focusBadge.hidden = false;
        }

        if (region) {
          selectRegion(region);
        } else {
          redrawMap();
        }

        canvas.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
      });
    });

    clearRegionFocus?.addEventListener('click', () => {
      focusPoint = null;
      selectRegion('');

      if (focusBadge) focusBadge.hidden = true;

      redrawMap();
    });

    let resizeTimer = null;

    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(redrawMap, 120);
    });
  }

  initTaskMapWorkspace().catch(() => {
    const loadingChip = $('#mapLoadingChip');

    if (loadingChip) {
      loadingChip.hidden = false;
      loadingChip.textContent = '地图初始化失败，请刷新页面重试';
      loadingChip.classList.add('error');
    }
  });
})();
