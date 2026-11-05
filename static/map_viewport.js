/* Pure WGS84 Canvas viewport math, shared by wheel, buttons and drag.
 * Projection is identical for FIRMS points and stored GeoJSON polygons.
 * This file neither fetches data nor changes analysis task state.
 */
(function (root, create) {
  'use strict';
  const api = create();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.FireMapViewport = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  function fitBounds(bounds, width, height, pad = 26) {
    const spanX = Math.max(.001, bounds.maxX - bounds.minX);
    const spanY = Math.max(.001, bounds.maxY - bounds.minY);
    const scale = Math.min(
      (width - 2 * pad) / spanX,
      (height - 2 * pad) / spanY
    );
    const xOffset = (width - spanX * scale) / 2;
    const yOffset = (height - spanY * scale) / 2;
    const project = point => [
      xOffset + (Number(point[0]) - bounds.minX) * scale,
      height - (yOffset + (Number(point[1]) - bounds.minY) * scale),
    ];
    const unproject = (x, y) => [
      bounds.minX + (x - xOffset) / scale,
      bounds.minY + (height - y - yOffset) / scale,
    ];
    return { width, height, pad, scale, project, unproject };
  }

  function visibleBounds(transform) {
    const sw = transform.unproject(
      transform.pad, transform.height - transform.pad
    );
    const ne = transform.unproject(
      transform.width - transform.pad, transform.pad
    );
    return {
      minX: sw[0], minY: sw[1], maxX: ne[0], maxY: ne[1],
    };
  }

  function zoomAt(transform, previousZoom, nextZoom, x, y) {
    if (!Number.isFinite(previousZoom) || previousZoom <= 0 ||
        !Number.isFinite(nextZoom) || nextZoom <= 0) {
      throw new RangeError('Zoom levels must be positive.');
    }
    const scale = transform.scale * nextZoom / previousZoom;
    const center = transform.unproject(x, y);
    const spanX = (transform.width - 2 * transform.pad) / scale;
    const spanY = (transform.height - 2 * transform.pad) / scale;
    const minX = center[0] - (x - transform.pad) / scale;
    const minY = center[1] -
      (transform.height - transform.pad - y) / scale;
    return {
      minX, minY,
      maxX: minX + spanX,
      maxY: minY + spanY,
    };
  }

  function panBounds(bounds, dx, dy, scale) {
    if (!Number.isFinite(scale) || scale <= 0) {
      throw new RangeError('Scale must be positive.');
    }
    const shiftX = -dx / scale;
    const shiftY = dy / scale;
    return {
      minX: bounds.minX + shiftX,
      maxX: bounds.maxX + shiftX,
      minY: bounds.minY + shiftY,
      maxY: bounds.maxY + shiftY,
    };
  }

  return { fitBounds, visibleBounds, zoomAt, panBounds };
});
