"""Catch JavaScript map boot failures missed by node --check and Python API tests.

A minimal DOM harness runs the actual product.js in Node's vm, fetches a real
FIRMS-shaped map payload and checks Canvas drawing.  No browser package or
network access is required on CI or the Windows build host.
"""

from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_map_button_listeners_use_multi_element_selector():
    source = (ROOT / "static" / "product.js").read_text(encoding="utf-8")
    assert not re.search(
        r"(?<!\$)\$\(['\"][^'\"]+['\"]\)\.forEach\(", source
    ), "querySelector returns one element; use $$ for .forEach"
    for action in ("data-map-theme", "data-map-reset", "data-map-date"):
        assert f"$$('[{action}]').forEach(button =>" in source


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is unavailable")
def test_real_product_script_boots_canvas_and_binds_map_actions():
    javascript = r"""
    const assert = require('node:assert/strict');
    const fs = require('node:fs');
    const vm = require('node:vm');

    const product = fs.readFileSync(process.argv[1], 'utf8');
    const viewport = require(process.argv[2]);
    const traces = { arcs: 0, fetches: 0 };
    const ctx = new Proxy({}, {
      get(_target, property) {
        if (property === 'measureText') return text => ({ width: String(text).length * 7 });
        return (..._args) => {
          if (property === 'arc') traces.arcs++;
        };
      },
      set() { return true; }
    });
    function makeElement(id, attrs = {}) {
      const listeners = new Map();
      const element = {
        id, hidden: false, disabled: false, checked: false,
        classList: {
          add() {}, remove() {}, toggle() {}, contains() { return false; }
        },
        style: { setProperty() {} },
        textContent: id === 'taskMapFeatures'
          ? JSON.stringify({ type: 'FeatureCollection', features: [] })
          : id === 'taskPersistentCells' ? '[]' : '',
        getAttribute(key) {
          if (id === 'taskWorkspace' && key === 'data-task-id') return 'runtime-test';
          if (id === 'taskWorkspace' && key === 'data-coordinate-mode') return 'true';
          return Object.prototype.hasOwnProperty.call(attrs, key) ? attrs[key] : null;
        },
        setAttribute(key, value) { attrs[key] = String(value); },
        getBoundingClientRect() { return { left: 0, top: 0, width: 900, height: 530 }; },
        getContext() { return ctx; },
        scrollIntoView() {},
        addEventListener(type, listener) {
          if (!listeners.has(type)) listeners.set(type, []);
          listeners.get(type).push(listener);
        },
        dispatchEvent(event) {
          for (const listener of listeners.get(event.type) || []) listener(event);
        },
        countListeners(type) { return (listeners.get(type) || []).length; }
      };
      return element;
    }
    const ids = [
      'taskWorkspace', 'taskMapCanvas', 'taskMapFeatures', 'taskPersistentCells',
      'mapLoadingChip', 'taskMapEmpty', 'mapDateSlider', 'mapDateLabel',
      'layerAllFires', 'layerHighFrp', 'layerPersistent',
      'mapVisibleCount', 'mapVisibleMetricLabel', 'mapRegionLabel',
      'mapZoomIn', 'mapZoomOut', 'mapZoomModeButton', 'mapPointerCoordinate'
    ];
    const elements = new Map(ids.map(id => [id, makeElement(id)]));
    elements.get('layerAllFires').checked = true;

    const actions = new Map([
      ['[data-map-theme]', [makeElement('theme', {'data-map-theme': 'persistent'})]],
      ['[data-map-reset]', [makeElement('reset')]],
      ['[data-map-date]', [makeElement('date', {'data-map-date': '2026-04-01'})]],
      ['[data-map-focus-bbox]', [makeElement('focus', {'data-map-focus-bbox': '124,45,124.25,45.25'})]]
    ]);
    const document = {
      body: { classList: { add() {}, remove() {} } },
      addEventListener() {},
      querySelector(selector) {
        return selector.startsWith('#') ? elements.get(selector.slice(1)) || null : null;
      },
      querySelectorAll(selector) { return actions.get(selector) || []; }
    };
    const window = {
      FireMapViewport: viewport,
      location: { pathname: '/tasks/runtime-test' },
      addEventListener() {}, dispatchEvent() {}
    };
    const errors = [];
    const environment = {
      document, window,
      console: { error(...parts) { errors.push(parts.map(String).join(' ')); }, log() {} },
      setTimeout() { return 1; }, clearTimeout() {},
      setInterval() { return 1; }, clearInterval() {},
      requestAnimationFrame(handler) { handler(); return 1; },
      Event: class { constructor(type) { this.type = type; } },
      CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
      sessionStorage: { getItem() { return null; }, setItem() {} },
      localStorage: { getItem() { return null; }, setItem() {} },
      fetch: async url => {
        traces.fetches++;
        assert.ok(String(url).includes('/map-data'));
        return { ok: true, json: async () => ({
          points: [
            [124.10, 45.10, 0, 0, 8.0, 0],
            [124.12, 45.12, 0, 0, 9.0, 0]
          ],
          dates: ['2026-04-01'],
          regions: ['测试区域'], counties: [],
          frp_p90: 8.5
        }) };
      }
    };
    vm.runInNewContext(product, environment, { filename: 'product.js', timeout: 10000 });
    (async () => {
      await new Promise(resolve => setImmediate(resolve));
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(errors.length, 0, errors.join('\n'));
      assert.equal(elements.get('mapLoadingChip').hidden, true, 'map load should complete');
      assert.equal(traces.fetches, 1, 'FIRMS map endpoint should be fetched');
      assert.ok(traces.arcs >= 2, 'actual FIRMS points must render to Canvas');
      for (const name of ['[data-map-theme]', '[data-map-reset]', '[data-map-date]']) {
        assert.equal(actions.get(name)[0].countListeners('click'), 1, name);
      }
      assert.equal(elements.get('mapZoomIn').countListeners('click'), 1);
      assert.equal(elements.get('mapZoomOut').countListeners('click'), 1);
      assert.equal(actions.get('[data-map-focus-bbox]')[0].countListeners('click'), 1);
      process.stdout.write('map runtime bootstrap: Canvas and action buttons OK\n');
    })().catch(error => { console.error(error); process.exitCode = 1; });
    """
    completed = subprocess.run(
        [shutil.which("node"), "-e", javascript,
         str(ROOT / "static" / "product.js"),
         str(ROOT / "static" / "map_viewport.js")],
        capture_output=True, text=True, timeout=18,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
