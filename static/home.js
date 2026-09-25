(() => {
  const canvas = document.getElementById('homeMapCanvas');
  const node = document.getElementById('homeRegionFeatures');
  if (!canvas || !node) return;

  let collection = {};
  try {
    collection = JSON.parse(node.textContent || '{}');
  } catch (_) {
    return;
  }

  const features = Array.isArray(collection.features)
    ? collection.features
    : [];

  function ringsOf(geometry) {
    if (!geometry) return [];
    if (geometry.type === 'Polygon') return geometry.coordinates || [];
    if (geometry.type === 'MultiPolygon') return (geometry.coordinates || []).flat();
    return [];
  }

  const all = [];
  features.forEach(feature => {
    ringsOf(feature.geometry).forEach(ring => {
      ring.forEach(point => all.push(point));
    });
  });

  if (!all.length) return;

  const xs = all.map(point => Number(point[0]));
  const ys = all.map(point => Number(point[1]));

  const bounds = {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };

  function centroid(feature) {
    const points = [];
    ringsOf(feature.geometry).forEach(ring => {
      ring.forEach(point => points.push(point));
    });

    if (!points.length) return null;

    return [
      points.reduce((sum, point) => sum + Number(point[0]), 0) / points.length,
      points.reduce((sum, point) => sum + Number(point[1]), 0) / points.length,
    ];
  }

  const centers = features.map(centroid).filter(Boolean);
  let phase = 0;

  function draw() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const width = Math.max(320, Math.round(rect.width || 620));
    const height = Math.max(320, Math.round(rect.height || 520));

    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }

    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const pad = Math.max(30, width * .065);
    const spanX = Math.max(.001, bounds.maxX - bounds.minX);
    const spanY = Math.max(.001, bounds.maxY - bounds.minY);
    const scale = Math.min(
      (width - pad * 2) / spanX,
      (height - pad * 2) / spanY
    );
    const ox = (width - spanX * scale) / 2;
    const oy = (height - spanY * scale) / 2;

    const project = point => [
      ox + (Number(point[0]) - bounds.minX) * scale,
      height - (oy + (Number(point[1]) - bounds.minY) * scale),
    ];

    ctx.strokeStyle = 'rgba(46, 125, 153, .54)';
    ctx.fillStyle = 'rgba(80, 165, 194, .075)';
    ctx.lineWidth = 1;

    features.forEach(feature => {
      ringsOf(feature.geometry).forEach(ring => {
        if (!ring.length) return;

        ctx.beginPath();
        ring.forEach((point, index) => {
          const [x, y] = project(point);
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      });
    });

    phase += .012;

    centers.forEach((point, index) => {
      const [x, y] = project(point);
      const pulse = (Math.sin(phase * 4 + index * .83) + 1) / 2;
      const outer = 4 + pulse * 6;

      ctx.beginPath();
      ctx.arc(x, y, outer, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(38, 137, 169, ${.07 + pulse * .12})`;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(x, y, 1.45 + pulse * .85, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(30, 115, 146, ${.52 + pulse * .34})`;
      ctx.fill();
    });

    requestAnimationFrame(draw);
  }

  draw();
})();
