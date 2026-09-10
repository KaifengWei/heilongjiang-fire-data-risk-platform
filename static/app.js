const state = {
  summary: null,
  provinceSummary: null,
  daily: [],
  map: null,
  status: null,

  hoveredRegion: null,
  projectedFeatures: [],

  pipelineKind: "firms",

  region: "",
};


const $ = (id) =>
  document.getElementById(id);


function formatNumber(
  value,
  digits = 0
) {

  const n = Number(value || 0);

  return n.toLocaleString(
    "zh-CN",
    {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }
  );
}


function escapeHtml(value) {

  return String(value ?? "")
    .replace(
      /[&<>"']/g,
      (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[char]
    );
}


function setText(
  id,
  value
) {

  const element = $(id);

  if (element) {
    element.textContent = value;
  }
}


async function getJson(url) {

  const response =
    await fetch(url);


  let payload = null;


  try {

    payload =
      await response.json();

  } catch {

    payload = null;

  }


  if (!response.ok) {

    throw new Error(
      payload?.message
      || `请求失败：${response.status}`
    );

  }


  return payload;
}



function buildQuery({
  includeRegion = true,
  includeLimit = false,
} = {}) {

  const params =
    new URLSearchParams();


  const region =
    $("regionSelect")?.value || "";


  const start =
    $("startDate")?.value || "";


  const end =
    $("endDate")?.value || "";


  if (
    includeRegion
    && region
  ) {

    params.set(
      "region",
      region
    );

  }


  if (start) {

    params.set(
      "start",
      start
    );

  }


  if (end) {

    params.set(
      "end",
      end
    );

  }


  if (includeLimit) {

    params.set(
      "limit",
      $("mapLimit")?.value || "1000"
    );

  }


  return params.toString();
}



function animateInteger(
  element,
  target
) {

  if (!element) {
    return;
  }


  const end =
    Number(target || 0);


  const start =
    performance.now();


  const duration =
    550;


  function frame(now) {

    const progress =
      Math.min(
        1,
        (now - start)
        / duration
      );


    const eased =
      1 -
      Math.pow(
        1 - progress,
        3
      );


    const current =
      Math.round(
        end * eased
      );


    element.textContent =
      formatNumber(current);


    if (progress < 1) {

      requestAnimationFrame(
        frame
      );

    }

  }


  requestAnimationFrame(
    frame
  );
}



function renderSummary(
  summary,
  daily
) {

  animateInteger(
    $("activeCount"),
    summary
      ?.active_fire_observation_count
  );


  setText(
    "burnedArea",
    formatNumber(
      summary?.burned_area_km2,
      2
    )
  );


  const rows =
    daily || [];


  if (!rows.length) {

    setText(
      "peakDay",
      "—"
    );

    setText(
      "peakDayLabel",
      "暂无数据"
    );

    return;
  }


  const peak =
    [...rows]
      .sort(
        (a, b) =>
          Number(
            b.active_fire_observation_count
            || 0
          )
          -
          Number(
            a.active_fire_observation_count
            || 0
          )
      )[0];


  setText(
    "peakDay",
    peak.date || "—"
  );


  setText(
    "peakDayLabel",
    `${
      formatNumber(
        peak
          .active_fire_observation_count
      )
    } 条主动火点观测`
  );

}



function renderRegionComparison() {

  const region =
    $("regionSelect")?.value
    || "";


  const current =
    Number(
      state.summary
        ?.active_fire_observation_count
      || 0
    );


  const province =
    Number(
      state.provinceSummary
        ?.active_fire_observation_count
      || 0
    );


  const percentage =
    region && province > 0
      ? Math.min(
          100,
          current
          / province
          * 100
        )
      : 100;


  const gauge =
    $("compareGauge");


  if (gauge) {

    gauge.style.setProperty(
      "--percentage",
      percentage.toFixed(1)
    );

  }


  setText(
    "comparePercent",
    `${percentage.toFixed(1)}%`
  );


  if (region) {

    setText(
      "currentViewText",
      `黑龙江省 · ${region}`
    );


    setText(
      "mapScopeText",
      region
    );


    setText(
      "compareRegionName",
      region
    );


    setText(
      "regionMetric",
      region
    );


    setText(
      "regionMetricNote",
      "当前行政区"
    );


    setText(
      "compareFireValue",
      formatNumber(current)
    );


    setText(
      "compareExplanation",
      province > 0
        ? (
          `当前区域 FIRMS 主动火点观测`
          + `约占相同日期条件下全省的 `
          + `${percentage.toFixed(1)}%。`
        )
        : "当前日期范围内全省暂无可比较记录。"
    );


    $("resetOverviewButton")
      ?.removeAttribute(
        "hidden"
      );


    $("mapResetButton")
      ?.removeAttribute(
        "hidden"
      );

  } else {

    setText(
      "currentViewText",
      "黑龙江省 · 全省总览"
    );


    setText(
      "mapScopeText",
      "全省"
    );


    setText(
      "compareRegionName",
      "黑龙江省"
    );


    setText(
      "regionMetric",
      "全省"
    );


    setText(
      "regionMetricNote",
      "当前为全省总览"
    );


    setText(
      "compareFireValue",
      formatNumber(current)
    );


    setText(
      "compareExplanation",
      "当前显示相同日期条件下的黑龙江省全省结果。"
    );


    $("resetOverviewButton")
      ?.setAttribute(
        "hidden",
        ""
      );


    $("mapResetButton")
      ?.setAttribute(
        "hidden",
        ""
      );

  }

}



function renderDaily(rows) {

  const container =
    $("dailyMiniChart");


  const topList =
    $("topDaysList");


  const tbody =
    $("dailyRows");


  if (!rows?.length) {

    if (container) {

      container.innerHTML =
        `
          <div class="v1-empty">
            暂无数据
          </div>
        `;

    }


    if (topList) {

      topList.innerHTML =
        `
          <div class="v1-empty">
            暂无数据
          </div>
        `;

    }


    if (tbody) {

      tbody.innerHTML =
        `
          <tr>
            <td
              colspan="4"
              class="v1-empty"
            >
              当前查询无逐日记录
            </td>
          </tr>
        `;

    }


    setText(
      "trendHighlight",
      "当前查询无时间序列"
    );


    return;
  }


  const values =
    rows.map(
      (row) =>
        Number(
          row
            .active_fire_observation_count
          || 0
        )
    );


  const maxValue =
    Math.max(
      ...values,
      1
    );


  if (container) {

    container.innerHTML =
      rows
        .map(
          (
            row,
            index
          ) => {

            const value =
              Number(
                row
                  .active_fire_observation_count
                || 0
              );


            const height =
              Math.max(
                5,
                value
                / maxValue
                * 100
              );


            return `
              <div
                class="v1-trend-column"
                title="${
                  escapeHtml(
                    row.date
                  )
                }：${
                  formatNumber(value)
                } 条"
              >

                <div
                  class="v1-trend-bar"
                  style="
                    --bar-height:
                    ${height.toFixed(1)}%;
                    --delay:
                    ${index * 18}ms;
                  "
                >
                </div>

                <span>
                  ${
                    escapeHtml(
                      row.date
                        ?.slice(5)
                        || ""
                    )
                  }
                </span>

              </div>
            `;

          }
        )
        .join("");


    requestAnimationFrame(
      () => {

        container
          .querySelectorAll(
            ".v1-trend-bar"
          )
          .forEach(
            (bar) => {

              bar.classList.add(
                "show"
              );

            }
          );

      }
    );

  }


  const ranking =
    [...rows]
      .sort(
        (a, b) =>
          Number(
            b
              .active_fire_observation_count
            || 0
          )
          -
          Number(
            a
              .active_fire_observation_count
            || 0
          )
      )
      .slice(
        0,
        5
      );


  if (topList) {

    topList.innerHTML =
      ranking
        .map(
          (
            row,
            index
          ) => {

            const value =
              Number(
                row
                  .active_fire_observation_count
                || 0
              );


            const width =
              value
              / maxValue
              * 100;


            return `
              <div class="v1-rank-item">

                <div class="v1-rank-number">
                  ${index + 1}
                </div>


                <div class="v1-rank-content">

                  <div class="v1-rank-line">

                    <strong>
                      ${
                        escapeHtml(
                          row.date
                        )
                      }
                    </strong>

                    <span>
                      ${
                        formatNumber(
                          value
                        )
                      } 条
                    </span>

                  </div>


                  <div class="v1-rank-track">

                    <div
                      class="v1-rank-fill"
                      style="
                        width:
                        ${width.toFixed(1)}%;
                      "
                    >
                    </div>

                  </div>

                </div>

              </div>
            `;

          }
        )
        .join("");

  }


  const peak =
    ranking[0];


  setText(
    "trendHighlight",
    peak
      ? (
        `${peak.date} 为当前查询峰值日，`
        + `${formatNumber(
          peak
            .active_fire_observation_count
        )} 条观测`
      )
      : "—"
  );


  if (tbody) {

    tbody.innerHTML =
      rows
        .map(
          (row) => `
            <tr>

              <td>
                ${
                  escapeHtml(
                    row.date
                  )
                }
              </td>

              <td>
                ${
                  formatNumber(
                    row
                      .active_fire_observation_count
                  )
                }
              </td>

              <td>
                ${
                  formatNumber(
                    row
                      .burned_pixel_count
                  )
                }
              </td>

              <td>
                ${
                  formatNumber(
                    row
                      .burned_area_km2,
                    4
                  )
                }
              </td>

            </tr>
          `
        )
        .join("");

  }

}



/* ========================================================
   地图
======================================================== */


function collectCoordinatePairs(
  geometry,
  output = []
) {

  if (!geometry) {
    return output;
  }


  const walk =
    (value) => {

      if (!Array.isArray(value)) {
        return;
      }


      if (
        value.length >= 2
        && typeof value[0]
          === "number"
        && typeof value[1]
          === "number"
      ) {

        output.push(
          [
            value[0],
            value[1],
          ]
        );

        return;

      }


      value.forEach(
        walk
      );

    };


  if (
    geometry.type
    === "GeometryCollection"
  ) {

    (
      geometry.geometries
      || []
    )
      .forEach(
        (item) =>
          collectCoordinatePairs(
            item,
            output
          )
      );

  } else {

    walk(
      geometry.coordinates
    );

  }


  return output;
}



function createProjection(
  pairs,
  width,
  height,
  padding = 40
) {

  const longitudes =
    pairs.map(
      (pair) =>
        pair[0]
    );


  const latitudes =
    pairs.map(
      (pair) =>
        pair[1]
    );


  const minLon =
    Math.min(
      ...longitudes
    );


  const maxLon =
    Math.max(
      ...longitudes
    );


  const minLat =
    Math.min(
      ...latitudes
    );


  const maxLat =
    Math.max(
      ...latitudes
    );


  const centerLat =
    (
      minLat
      + maxLat
    )
    / 2;


  const cosLat =
    Math.cos(
      centerLat
      * Math.PI
      / 180
    );


  const rangeX =
    Math.max(
      (
        maxLon
        - minLon
      )
      * cosLat,
      0.001
    );


  const rangeY =
    Math.max(
      maxLat
      - minLat,
      0.001
    );


  const usableWidth =
    width
    - padding * 2;


  const usableHeight =
    height
    - padding * 2;


  const scale =
    Math.min(
      usableWidth
      / rangeX,
      usableHeight
      / rangeY
    );


  const contentWidth =
    rangeX
    * scale;


  const contentHeight =
    rangeY
    * scale;


  const offsetX =
    (
      width
      - contentWidth
    )
    / 2;


  const offsetY =
    (
      height
      - contentHeight
    )
    / 2;


  function project(
    pair
  ) {

    const [
      lon,
      lat,
    ] = pair;


    const x =
      offsetX
      + (
        lon
        - minLon
      )
      * cosLat
      * scale;


    const y =
      height
      - (
        offsetY
        + (
          lat
          - minLat
        )
        * scale
      );


    return [
      x,
      y,
    ];

  }


  return {
    project,
    extent:
      `${
        minLon.toFixed(2)
      }°E–${
        maxLon.toFixed(2)
      }°E · ${
        minLat.toFixed(2)
      }°N–${
        maxLat.toFixed(2)
      }°N`,
  };
}



function geometryToPolygons(
  geometry,
  project
) {

  if (!geometry) {
    return [];
  }


  if (
    geometry.type
    === "Polygon"
  ) {

    return [
      geometry.coordinates
        .map(
          (ring) =>
            ring.map(
              project
            )
        ),
    ];

  }


  if (
    geometry.type
    === "MultiPolygon"
  ) {

    return geometry.coordinates
      .map(
        (polygon) =>
          polygon.map(
            (ring) =>
              ring.map(
                project
              )
          )
      );

  }


  if (
    geometry.type
    === "GeometryCollection"
  ) {

    return (
      geometry.geometries
      || []
    )
      .flatMap(
        (item) =>
          geometryToPolygons(
            item,
            project
          )
      );

  }


  return [];
}



function drawRing(
  context,
  ring
) {

  if (!ring?.length) {
    return;
  }


  context.moveTo(
    ring[0][0],
    ring[0][1]
  );


  for (
    let index = 1;
    index < ring.length;
    index += 1
  ) {

    context.lineTo(
      ring[index][0],
      ring[index][1]
    );

  }


  context.closePath();
}



function drawPolygons(
  context,
  polygons
) {

  polygons.forEach(
    (polygon) => {

      polygon.forEach(
        (ring) =>
          drawRing(
            context,
            ring
          )
      );

    }
  );
}



function pointInRing(
  point,
  ring
) {

  let inside =
    false;


  const [
    x,
    y,
  ] = point;


  for (
    let i = 0,
      j = ring.length - 1;
    i < ring.length;
    j = i++
  ) {

    const xi =
      ring[i][0];


    const yi =
      ring[i][1];


    const xj =
      ring[j][0];


    const yj =
      ring[j][1];


    const intersects =
      (
        yi > y
      )
      !==
      (
        yj > y
      )
      &&
      x
      <
      (
        (
          xj - xi
        )
        *
        (
          y - yi
        )
        /
        (
          (
            yj - yi
          )
          || 1e-9
        )
        + xi
      );


    if (intersects) {

      inside =
        !inside;

    }

  }


  return inside;
}



function pointInPolygonSet(
  point,
  polygons
) {

  for (
    const polygon
    of polygons
  ) {

    const outer =
      polygon[0];


    if (
      !outer
      || !pointInRing(
        point,
        outer
      )
    ) {

      continue;

    }


    let insideHole =
      false;


    for (
      let index = 1;
      index < polygon.length;
      index += 1
    ) {

      if (
        pointInRing(
          point,
          polygon[index]
        )
      ) {

        insideHole =
          true;

        break;

      }

    }


    if (!insideHole) {

      return true;

    }

  }


  return false;
}



function featureName(
  feature
) {

  return (
    feature?.properties?.name
    || feature?.properties?.NAME
    || feature?.properties?.region
    || "未命名行政区"
  );
}



function findRegion(
  point
) {

  for (
    let index =
      state.projectedFeatures.length - 1;
    index >= 0;
    index -= 1
  ) {

    const item =
      state.projectedFeatures[
        index
      ];


    if (
      pointInPolygonSet(
        point,
        item.polygons
      )
    ) {

      return item;

    }

  }


  return null;
}



function renderMap(
  payload
) {

  const canvas =
    $("mapCanvas");


  if (!canvas) {
    return;
  }


  const context =
    canvas.getContext(
      "2d"
    );


  context.clearRect(
    0,
    0,
    canvas.width,
    canvas.height
  );


  const boundaryFeatures =
    payload?.boundary
      ?.features
    || [];


  const boundaryPairs =
    [];


  boundaryFeatures
    .forEach(
      (feature) =>
        collectCoordinatePairs(
          feature.geometry,
          boundaryPairs
        )
    );


  const activePoints =
    payload?.active_fire
      ?.points
    || [];


  const burnedPoints =
    payload?.burned_pixels
      ?.points
    || [];


  const pointPairs =
    [
      ...activePoints,
      ...burnedPoints,
    ]
      .map(
        (point) => [
          Number(
            point.longitude
          ),
          Number(
            point.latitude
          ),
        ]
      );


  const allPairs =
    [
      ...boundaryPairs,
      ...pointPairs,
    ];


  if (!allPairs.length) {

    context.fillStyle =
      "#60758a";


    context.font =
      "20px Microsoft YaHei";


    context.textAlign =
      "center";


    context.fillText(
      "当前查询没有可显示的空间数据",
      canvas.width / 2,
      canvas.height / 2
    );


    return;
  }


  const {
    project,
    extent,
  } =
    createProjection(
      allPairs,
      canvas.width,
      canvas.height,
      46
    );


  state.projectedFeatures =
    boundaryFeatures
      .map(
        (feature) => ({
          name:
            featureName(
              feature
            ),
          polygons:
            geometryToPolygons(
              feature.geometry,
              project
            ),
        })
      );


  context.fillStyle =
    "#edf6f8";


  context.fillRect(
    0,
    0,
    canvas.width,
    canvas.height
  );



  /* 背景网格 */

  context.strokeStyle =
    "rgba(65, 120, 145, 0.10)";


  context.lineWidth =
    1;


  context.setLineDash(
    [
      5,
      8,
    ]
  );


  for (
    let row = 1;
    row <= 5;
    row += 1
  ) {

    const y =
      canvas.height
      / 6
      * row;


    context.beginPath();


    context.moveTo(
      40,
      y
    );


    context.lineTo(
      canvas.width - 40,
      y
    );


    context.stroke();

  }


  context.setLineDash(
    []
  );



  const selected =
    $("regionSelect")?.value
    || "";



  /* 行政区 */

  state.projectedFeatures
    .forEach(
      (item) => {

        const hovered =
          state.hoveredRegion
          === item.name;


        const selectedItem =
          selected
          === item.name;


        context.beginPath();


        drawPolygons(
          context,
          item.polygons
        );


        if (selectedItem) {

          context.fillStyle =
            "rgba(31, 126, 168, 0.21)";


          context.strokeStyle =
            "#0d658c";


          context.lineWidth =
            2.6;

        } else if (hovered) {

          context.fillStyle =
            "rgba(33, 139, 174, 0.16)";


          context.strokeStyle =
            "#167da4";


          context.lineWidth =
            2.2;

        } else {

          context.fillStyle =
            "rgba(68, 139, 166, 0.10)";


          context.strokeStyle =
            "#4c91b0";


          context.lineWidth =
            1.35;

        }


        context.fill(
          "evenodd"
        );


        context.stroke();

      }
    );



  /* MCD64A1 */

  if (
    $("showBurned")?.checked
  ) {

    burnedPoints
      .forEach(
        (point) => {

          const [
            x,
            y,
          ] =
            project(
              [
                Number(
                  point.longitude
                ),
                Number(
                  point.latitude
                ),
              ]
            );


          context.fillStyle =
            "rgba(42, 142, 99, 0.22)";


          context.fillRect(
            x - 5,
            y - 5,
            10,
            10
          );


          context.fillStyle =
            "rgba(28, 120, 81, 0.82)";


          context.fillRect(
            x - 2.2,
            y - 2.2,
            4.4,
            4.4
          );

        }
      );

  }



  /* FIRMS */

  if (
    $("showActive")?.checked
  ) {

    activePoints
      .forEach(
        (point) => {

          const [
            x,
            y,
          ] =
            project(
              [
                Number(
                  point.longitude
                ),
                Number(
                  point.latitude
                ),
              ]
            );


          context.beginPath();


          context.fillStyle =
            "rgba(224, 78, 62, 0.15)";


          context.arc(
            x,
            y,
            7.5,
            0,
            Math.PI * 2
          );


          context.fill();


          context.beginPath();


          context.fillStyle =
            "rgba(225, 70, 55, 0.88)";


          context.arc(
            x,
            y,
            3,
            0,
            Math.PI * 2
          );


          context.fill();

        }
      );

  }



  setText(
    "mapNote",
    (
      `FIRMS 显示 ${
        formatNumber(
          activePoints.length
        )
      } / ${
        formatNumber(
          payload?.active_fire?.total
        )
      } 条 · `
      +
      `MCD64A1 显示 ${
        formatNumber(
          burnedPoints.length
        )
      } / ${
        formatNumber(
          payload
            ?.burned_pixels
            ?.total
        )
      } 个 · `
      +
      extent
    )
  );

}



function updateTooltip(
  event,
  region
) {

  const tooltip =
    $("mapTooltip");


  const canvas =
    $("mapCanvas");


  if (
    !tooltip
    || !canvas
  ) {

    return;

  }


  if (!region) {

    tooltip.hidden =
      true;

    return;

  }


  const rect =
    canvas
      .getBoundingClientRect();


  tooltip.hidden =
    false;


  tooltip.innerHTML =
    `
      <strong>
        ${
          escapeHtml(
            region.name
          )
        }
      </strong>

      <span>
        单击进入该行政区分析
      </span>
    `;


  tooltip.style.left =
    `${
      event.clientX
      - rect.left
      + 14
    }px`;


  tooltip.style.top =
    `${
      event.clientY
      - rect.top
      + 14
    }px`;

}



function setupMapInteraction() {

  const canvas =
    $("mapCanvas");


  if (!canvas) {
    return;
  }


  canvas.addEventListener(
    "mousemove",
    (event) => {

      const rect =
        canvas
          .getBoundingClientRect();


      const x =
        (
          event.clientX
          - rect.left
        )
        *
        canvas.width
        /
        rect.width;


      const y =
        (
          event.clientY
          - rect.top
        )
        *
        canvas.height
        /
        rect.height;


      const hit =
        findRegion(
          [
            x,
            y,
          ]
        );


      const name =
        hit
          ? hit.name
          : null;


      if (
        state.hoveredRegion
        !== name
      ) {

        state.hoveredRegion =
          name;


        if (state.map) {

          renderMap(
            state.map
          );

        }

      }


      canvas.style.cursor =
        hit
          ? "pointer"
          : "default";


      updateTooltip(
        event,
        hit
      );

    }
  );


  canvas.addEventListener(
    "mouseleave",
    () => {

      state.hoveredRegion =
        null;


      canvas.style.cursor =
        "default";


      updateTooltip(
        null,
        null
      );


      if (state.map) {

        renderMap(
          state.map
        );

      }

    }
  );


  canvas.addEventListener(
    "click",
    async () => {

      if (
        !state.hoveredRegion
      ) {

        return;

      }


      const select =
        $("regionSelect");


      if (!select) {

        return;

      }


      const exists =
        [...select.options]
          .some(
            (option) =>
              option.value
              === state.hoveredRegion
          );


      if (!exists) {

        return;

      }


      select.value =
        state.hoveredRegion;


      await refresh();

    }
  );

}



/* ========================================================
   处理链
======================================================== */


function latestCompletedRun(
  status,
  kind
) {

  const targetKind =
    kind === "firms"
      ? "active_fire_observations"
      : "burned_pixels_tif";


  return (
    status?.imports
    || []
  )
    .find(
      (item) =>
        item.data_kind
          === targetKind
        &&
        item.status
          === "completed"
    )
    || null;
}



function buildFirmsPipeline(
  run
) {

  if (!run) {
    return [];
  }


  const meta =
    run.metadata
    || {};


  const input =
    Number(
      meta.input_rows
      ?? run.input_count
      ?? 0
    );


  const accepted =
    Number(
      meta
        .normalization_accepted
      ?? input
    );


  const outsideDate =
    Number(
      meta
        .outside_task_date_range
      ?? 0
    );


  const afterDate =
    Math.max(
      0,
      accepted
      - outsideDate
    );


  const outsideRegion =
    Number(
      meta
        .outside_configured_regions
      ?? 0
    );


  const duplicates =
    Number(
      meta
        .duplicate_source_records_in_file
      ?? 0
    );


  const effective =
    Math.max(
      0,
      afterDate
      - outsideRegion
      - duplicates
    );


  return [
    {
      name:
        "原始观测",
      value:
        input,
      note:
        "CSV 输入记录",
    },
    {
      name:
        "质量规则通过",
      value:
        accepted,
      note:
        `${
          formatNumber(
            input - accepted
          )
        } 条被筛除`,
    },
    {
      name:
        "日期约束后",
      value:
        afterDate,
      note:
        `${
          formatNumber(
            outsideDate
          )
        } 条超出任务日期`,
    },
    {
      name:
        "行政区落区",
      value:
        effective,
      note:
        `${
          formatNumber(
            outsideRegion
          )
        } 条位于配置区域外`,
    },
    {
      name:
        "有效任务观测",
      value:
        effective,
      note:
        "进入任务统计与评估",
    },
  ];
}



function buildMcd64Pipeline(
  run
) {

  if (!run) {
    return [];
  }


  const meta =
    run.metadata
    || {};


  const positive =
    Number(
      meta
        .positive_burn_date_pixels
      ?? run.input_count
      ?? 0
    );


  const outsideMonth =
    Number(
      meta
        .positive_values_outside_expected_month
      ?? 0
    );


  const monthValid =
    Math.max(
      0,
      positive
      - outsideMonth
    );


  const qaRejected =
    Number(
      meta
        .qa_rejected_pixels
      ?? 0
    );


  const qaValid =
    Math.max(
      0,
      monthValid
      - qaRejected
    );


  const outsideRegion =
    Number(
      meta
        .outside_configured_regions
      ?? 0
    );


  const insideRegion =
    Math.max(
      0,
      qaValid
      - outsideRegion
    );


  const effective =
    Number(
      meta
        .run_burned_pixel_count
      ?? insideRegion
    );


  return [
    {
      name:
        "正值候选",
      value:
        positive,
      note:
        "Burn Date > 0",
    },
    {
      name:
        "月份筛选",
      value:
        monthValid,
      note:
        `${
          formatNumber(
            outsideMonth
          )
        } 个超出产品月份`,
    },
    {
      name:
        "QA 筛选",
      value:
        qaValid,
      note:
        `${
          formatNumber(
            qaRejected
          )
        } 个被 QA 拒绝`,
    },
    {
      name:
        "行政区落区",
      value:
        insideRegion,
      note:
        `${
          formatNumber(
            outsideRegion
          )
        } 个位于区域外`,
    },
    {
      name:
        "有效烧毁像元",
      value:
        effective,
      note:
        "用于面积估计",
    },
  ];
}



function renderPipeline() {

  const body =
    $("pipelineBody");


  if (!body) {
    return;
  }


  const firmsRun =
    latestCompletedRun(
      state.status,
      "firms"
    );


  const mcd64Run =
    latestCompletedRun(
      state.status,
      "mcd64"
    );


  const mcd64Tab =
    document.querySelector(
      '[data-kind="mcd64"]'
    );


  if (mcd64Tab) {

    if (mcd64Run) {

      mcd64Tab.hidden =
        false;

    } else {

      mcd64Tab.hidden =
        true;


      if (
        state.pipelineKind
        === "mcd64"
      ) {

        state.pipelineKind =
          "firms";

      }

    }

  }


  const steps =
    state.pipelineKind
      === "mcd64"
      ? buildMcd64Pipeline(
          mcd64Run
        )
      : buildFirmsPipeline(
          firmsRun
        );


  if (!steps.length) {

    body.innerHTML =
      `
        <div class="v1-empty">
          当前没有可用于展示的正式处理记录。
        </div>
      `;

    return;

  }


  const maximum =
    Math.max(
      steps[0].value,
      1
    );


  body.innerHTML =
    steps
      .map(
        (
          step,
          index
        ) => {

          const percentage =
            Math.max(
              0,
              Math.min(
                100,
                step.value
                / maximum
                * 100
              )
            );


          return `
            <div
              class="v1-pipeline-step"
              style="
                --step-delay:
                ${index * 80}ms;
              "
            >

              <div class="v1-pipeline-index">
                ${index + 1}
              </div>


              <div class="v1-pipeline-label">

                <span>
                  ${
                    escapeHtml(
                      step.name
                    )
                  }
                </span>

                <strong>
                  ${
                    formatNumber(
                      step.value
                    )
                  }
                </strong>

                <small>
                  ${
                    escapeHtml(
                      step.note
                    )
                  }
                </small>

              </div>


              <div class="v1-pipeline-meter">

                <div
                  class="v1-pipeline-fill"
                  style="
                    --step-width:
                    ${percentage.toFixed(1)}%;
                  "
                >
                </div>

              </div>

            </div>
          `;

        }
      )
      .join("");


  requestAnimationFrame(
    () => {

      body
        .querySelectorAll(
          ".v1-pipeline-step"
        )
        .forEach(
          (element) =>
            element.classList.add(
              "show"
            )
        );

    }
  );

}



function shortSource(
  source
) {

  const text =
    String(
      source || ""
    )
      .replace(
        /\\/g,
        "/"
      );


  const parts =
    text.split("/");


  return (
    parts[
      parts.length - 1
    ]
    || text
  );
}



function renderStatus(
  status
) {

  const regions =
    Number(
      status?.regions || 0
    );


  const active =
    Number(
      status
        ?.active_fire
        ?.count
      || 0
    );


  const burned =
    Number(
      status
        ?.burned_pixels
        ?.count
      || 0
    );


  const source =
    $("sourceSummary");


  if (source) {

    source.innerHTML =
      `
        <div class="v1-source-pill">

          <span class="v1-dot-fire">
          </span>

          <div>
            <small>
              FIRMS 主动火点
            </small>

            <strong>
              ${
                formatNumber(
                  active
                )
              } 条
            </strong>
          </div>

        </div>


        <div class="v1-source-pill">

          <span class="v1-dot-burn">
          </span>

          <div>
            <small>
              MCD64A1 烧毁像元
            </small>

            <strong>
              ${
                formatNumber(
                  burned
                )
              } 个
            </strong>
          </div>

        </div>


        <div class="v1-source-pill">

          <span class="v1-dot-region">
          </span>

          <div>
            <small>
              行政区边界
            </small>

            <strong>
              ${
                formatNumber(
                  regions
                )
              } 个
            </strong>
          </div>

        </div>
      `;

  }


  const tbody =
    $("importRows");


  if (tbody) {

    const rows =
      (
        status?.imports
        || []
      )
        .slice(
          0,
          5
        );


    if (!rows.length) {

      tbody.innerHTML =
        `
          <tr>
            <td
              colspan="4"
              class="v1-empty"
            >
              暂无处理记录
            </td>
          </tr>
        `;

    } else {

      tbody.innerHTML =
        rows
          .map(
            (item) => `
              <tr>

                <td>
                  ${
                    item.data_kind
                    === "active_fire_observations"
                      ? "FIRMS"
                      : (
                        item.data_kind
                        === "burned_pixels_tif"
                          ? "MCD64A1"
                          : escapeHtml(
                              item.data_kind
                            )
                      )
                  }
                </td>


                <td>

                  <span
                    class="
                      v1-run-status
                      v1-run-${
                        escapeHtml(
                          item.status
                          || "unknown"
                        )
                      }
                    "
                  >
                    ${
                      escapeHtml(
                        item.status
                        || "unknown"
                      )
                    }
                  </span>

                </td>


                <td>
                  ${
                    formatNumber(
                      item.stored_count
                    )
                  }
                </td>


                <td
                  title="${
                    escapeHtml(
                      item.source_ref
                      || ""
                    )
                  }"
                >
                  ${
                    escapeHtml(
                      shortSource(
                        item.source_ref
                      )
                    )
                  }
                </td>

              </tr>
            `
          )
          .join("");

    }

  }


  renderPipeline();

}



/* ========================================================
   查询
======================================================== */


async function loadRegions() {

  const payload =
    await getJson(
      "/api/regions"
    );


  const select =
    $("regionSelect");


  if (!select) {
    return;
  }


  (
    payload.regions
    || []
  )
    .forEach(
      (region) => {

        const option =
          document
            .createElement(
              "option"
            );


        option.value =
          region.name;


        option.textContent =
          region.name;


        select.appendChild(
          option
        );

      }
    );

}



async function resetOverview() {

  const select =
    $("regionSelect");


  if (select) {

    select.value =
      "";

  }


  await refresh();

}



async function refresh() {

  const button =
    $("refreshButton");


  if (button) {

    button.disabled =
      true;


    button.textContent =
      "读取中…";

  }


  try {

    const query =
      buildQuery();


    const mapQuery =
      buildQuery({
        includeLimit:
          true,
      });


    const provinceQuery =
      buildQuery({
        includeRegion:
          false,
      });


    const selectedRegion =
      $("regionSelect")
        ?.value
      || "";


    const requests = [
      getJson(
        `/api/summary?${query}`
      ),

      getJson(
        `/api/daily?${query}`
      ),

      getJson(
        `/api/map?${mapQuery}`
      ),

      getJson(
        "/api/status"
      ),
    ];


    if (selectedRegion) {

      requests.push(
        getJson(
          `/api/summary?${provinceQuery}`
        )
      );

    }


    const results =
      await Promise.all(
        requests
      );


    state.summary =
      results[0];


    state.daily =
      results[1]?.series
      || [];


    state.map =
      results[2];


    state.status =
      results[3];


    state.provinceSummary =
      selectedRegion
        ? results[4]
        : state.summary;


    state.region =
      selectedRegion;


    renderSummary(
      state.summary,
      state.daily
    );


    renderDaily(
      state.daily
    );


    renderRegionComparison();


    renderMap(
      state.map
    );


    renderStatus(
      state.status
    );


    const exportLink =
      $("exportLink");


    if (exportLink) {

      exportLink.href =
        `/api/export.csv?${query}`;

    }

  } catch (error) {

    console.error(
      error
    );


    alert(
      `查询失败：${error.message}`
    );

  } finally {

    if (button) {

      button.disabled =
        false;


      button.textContent =
        "查询";

    }

  }

}



/* ========================================================
   初始化
======================================================== */


function setupPipelineTabs() {

  document
    .querySelectorAll(
      "[data-kind]"
    )
    .forEach(
      (button) => {

        button.addEventListener(
          "click",
          () => {

            const kind =
              button.dataset.kind;


            if (!kind) {
              return;
            }


            state.pipelineKind =
              kind;


            document
              .querySelectorAll(
                "[data-kind]"
              )
              .forEach(
                (item) => {

                  item
                    .classList
                    .toggle(
                      "active",
                      item.dataset.kind
                      === kind
                    );

                }
              );


            renderPipeline();

          }
        );

      }
    );

}



document.addEventListener(
  "DOMContentLoaded",
  async () => {

    setupMapInteraction();

    setupPipelineTabs();


    $("refreshButton")
      ?.addEventListener(
        "click",
        refresh
      );


    $("resetOverviewButton")
      ?.addEventListener(
        "click",
        resetOverview
      );


    $("mapResetButton")
      ?.addEventListener(
        "click",
        resetOverview
      );


    $("showActive")
      ?.addEventListener(
        "change",
        () => {

          if (state.map) {

            renderMap(
              state.map
            );

          }

        }
      );


    $("showBurned")
      ?.addEventListener(
        "change",
        () => {

          if (state.map) {

            renderMap(
              state.map
            );

          }

        }
      );


    try {

      await loadRegions();

      await refresh();

    } catch (error) {

      console.error(
        error
      );


      alert(
        `页面初始化失败：${error.message}`
      );

    }

  }
);