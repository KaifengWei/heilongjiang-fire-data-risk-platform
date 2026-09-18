from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path.cwd().resolve()

REQUIRED = [
    "src/fire_monitor/app.py",
    "templates/index.html",
    "templates/tasks.html",
    "templates/task_detail.html",
    "static/product.css",
]

missing = [rel for rel in REQUIRED if not (ROOT / rel).is_file()]
if missing:
    raise SystemExit(
        "Run this script from the project root. Missing:\n- "
        + "\n- ".join(missing)
    )

# This batch is designed for the already-completed auto-analysis refactor.
app_text = (ROOT / "src/fire_monitor/app.py").read_text(encoding="utf-8")
required_app_markers = [
    '@app.post("/analyze")',
    'records=build_analysis_records(task_rows)',
    'region_feature_collection=(',
]
for marker in required_app_markers:
    if marker not in app_text:
        raise RuntimeError(
            f"Required product-refactor marker not found in app.py: {marker!r}. "
            "No UI files were changed."
        )

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = ROOT / "data" / "runtime" / f"ui_productization_backup_{stamp}"

for rel in [
    "templates/index.html",
    "templates/tasks.html",
    "templates/task_detail.html",
    "static/product.css",
]:
    src = ROOT / rel
    dst = backup_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


HELP_MODAL = r'''<div class="guide-modal" id="guideModal" hidden aria-hidden="true">
  <div class="guide-backdrop" data-close-help></div>
  <section class="guide-dialog" role="dialog" aria-modal="true" aria-labelledby="guideTitle">
    <header class="guide-header">
      <div>
        <span class="app-eyebrow">QUICK START</span>
        <h2 id="guideTitle">使用帮助</h2>
        <p>第一次使用时，从“上传数据”开始即可。软件会自动识别数据并建立独立分析记录。</p>
      </div>
      <button class="guide-close" type="button" aria-label="关闭帮助" data-close-help>×</button>
    </header>

    <div class="guide-layout">
      <nav class="guide-nav" aria-label="帮助目录">
        <button class="active" type="button" data-help-tab="start"><b>01</b><span>开始一次分析</span></button>
        <button type="button" data-help-tab="files"><b>02</b><span>支持什么数据</span></button>
        <button type="button" data-help-tab="results"><b>03</b><span>怎么看结果</span></button>
        <button type="button" data-help-tab="repeat"><b>04</b><span>重复数据处理</span></button>
        <button type="button" data-help-tab="terms"><b>05</b><span>数据口径</span></button>
      </nav>

      <div class="guide-content">
        <section class="guide-panel active" data-help-panel="start">
          <span class="guide-step-label">01 / 开始分析</span>
          <h3>选择文件后，软件会自动完成识别和分析</h3>
          <div class="guide-visual guide-visual-upload" aria-hidden="true">
            <div class="guide-mini-window">
              <div class="guide-mini-title"><span></span><span></span><span></span></div>
              <div class="guide-mini-drop"><b>＋</b><strong>选择遥感数据文件</strong><small>CSV / GeoTIFF</small></div>
              <div class="guide-mini-button">开始自动分析</div>
            </div>
          </div>
          <ol class="guide-steps-list">
            <li><b>选择数据文件</b><span>无需先填日期，也无需先选择 FIRMS / MCD64A1 类型。</span></li>
            <li><b>等待自动识别</b><span>软件读取文件类型、时间范围，执行校验、行政区落区和数据处理。</span></li>
            <li><b>查看本次结果</b><span>完成后自动进入结果页，并在“分析记录”中保留这一次分析。</span></li>
          </ol>
        </section>

        <section class="guide-panel" data-help-panel="files">
          <span class="guide-step-label">02 / 支持数据</span>
          <h3>当前支持两类遥感输入</h3>
          <div class="guide-file-cards">
            <article>
              <span class="guide-file-icon fire">CSV</span>
              <div><strong>NASA FIRMS 主动火点 CSV</strong><p>直接选择 CSV。软件从表头与记录中识别日期、坐标和卫星观测字段。</p></div>
            </article>
            <article>
              <span class="guide-file-icon burn">TIF</span>
              <div><strong>MCD64A1 GeoTIFF</strong><p>同时选择 Burn Date 与 QA 文件；当前处理流程使用 EPSG:4326 GeoTIFF。</p></div>
            </article>
          </div>
          <div class="guide-tip"><b>建议：</b>保持 NASA 下载/转换后的产品日期标识与 BurnDate、QA 文件名标识，自动识别会更稳定。</div>
        </section>

        <section class="guide-panel" data-help-panel="results">
          <span class="guide-step-label">03 / 结果阅读</span>
          <h3>结果页先回答“多少、哪里、什么时候”</h3>
          <div class="guide-result-preview" aria-hidden="true">
            <div class="guide-preview-kpis"><span></span><span></span><span></span><span></span></div>
            <div class="guide-preview-main">
              <div class="guide-preview-map"><i></i><i></i><i></i><i></i></div>
              <div class="guide-preview-bars"><em></em><em></em><em></em><em></em><em></em></div>
            </div>
          </div>
          <div class="guide-result-list">
            <div><b>结果总览</b><span>有效观测、涉及行政区、主要区域、数据类型/面积。</span></div>
            <div><b>空间分布</b><span>通过黑龙江行政区地图查看本次数据主要集中位置。</span></div>
            <div><b>区域排行</b><span>比较各市（地）在本次分析中的火点数量或烧毁像元面积。</span></div>
            <div><b>时间分布</b><span>查看哪一天出现最多的主动火点观测。</span></div>
          </div>
        </section>

        <section class="guide-panel" data-help-panel="repeat">
          <span class="guide-step-label">04 / 重复数据</span>
          <h3>相同数据再次上传时，不会把同一观测重复存储</h3>
          <div class="guide-repeat-flow">
            <div><span>第一次上传</span><strong>识别并存储规范观测</strong></div>
            <b>→</b>
            <div><span>再次上传</span><strong>检测历史重合记录</strong></div>
            <b>→</b>
            <div><span>新的分析记录</span><strong>复用已有观测并独立统计</strong></div>
          </div>
          <p class="guide-copy">因此每次上传仍然会形成独立分析记录，但底层不会为了同一规范化观测反复增加库存。</p>
        </section>

        <section class="guide-panel" data-help-panel="terms">
          <span class="guide-step-label">05 / 数据口径</span>
          <h3>结果中的几个名称分别表示什么</h3>
          <dl class="guide-terms">
            <div><dt>FIRMS 主动火点观测</dt><dd>卫星主动火点产品中的观测记录。平台按当前分析记录进行数量、时间和行政区统计。</dd></div>
            <div><dt>MCD64A1 烧毁像元面积</dt><dd>筛选后的烧毁像元面积估计之和，用于描述遥感产品中的烧毁区域信息。</dd></div>
            <div><dt>相对关注等级</dt><dd>平台在当前分析记录内部比较各行政区遥感指标得到的相对关注程度。</dd></div>
            <div><dt>分析记录</dt><dd>一次用户上传及其识别、处理和结果的独立记录。导出只针对当前记录。</dd></div>
          </dl>
        </section>
      </div>
    </div>

    <footer class="guide-footer">
      <label class="guide-dont-show"><input id="guideDontShow" type="checkbox"> 下次启动桌面软件时不再自动显示</label>
      <button class="app-button app-button-primary" id="guideStartButton" type="button">进入软件</button>
    </footer>
  </section>
</div>
'''


INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>黑龙江省火点数据检测与风险评估平台</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='product.css') }}">
</head>
<body class="app-body">
<div class="app-shell">
  <aside class="app-sidebar">
    <a class="app-brand" href="{{ url_for('index') }}">
      <span class="app-brand-mark">F</span>
      <span class="app-brand-copy"><strong>黑龙江省火点数据</strong><small>检测与风险评估平台</small></span>
    </a>

    <nav class="app-side-nav" aria-label="主导航">
      <a class="active" href="{{ url_for('index') }}"><span class="nav-icon">⌂</span><span>首页</span></a>
      <a href="#upload"><span class="nav-icon">＋</span><span>开始分析</span></a>
      <a href="{{ url_for('tasks') }}"><span class="nav-icon">▤</span><span>分析记录</span></a>
      <button type="button" data-open-help><span class="nav-icon">?</span><span>使用帮助</span></button>
    </nav>

    <div class="app-side-spacer"></div>
    <div class="app-side-footer"><span>本地桌面分析</span><b>V1.0</b></div>
  </aside>

  <div class="app-workspace">
    <header class="app-topbar">
      <div>
        <span class="app-eyebrow">HOME</span>
        <h1>首页</h1>
        <p>上传一份数据，软件自动识别并生成本次分析结果。</p>
      </div>
      <div class="app-top-actions">
        <button class="app-button app-button-ghost" type="button" data-open-help>使用教程</button>
        <a class="app-button app-button-primary" href="#upload">开始分析</a>
      </div>
    </header>

    <main class="app-main">
      {% if page_error %}
      <div class="app-alert error reveal-item">
        <strong>未能开始分析</strong><span>{{ page_error }}</span>
      </div>
      {% endif %}

      <section id="upload" class="start-card reveal-item">
        <div class="start-card-copy">
          <span class="app-chip">一次上传 · 自动分析</span>
          <h2>选择数据文件，后续步骤由软件自动完成</h2>
          <p>软件会自动识别数据类型与时间范围，完成输入校验、黑龙江行政区空间分析和重复数据检查。</p>

          <div class="start-flow">
            <div><b>01</b><span><strong>选择文件</strong><small>CSV / GeoTIFF</small></span></div>
            <i>→</i>
            <div><b>02</b><span><strong>自动识别</strong><small>类型 / 日期 / 重复</small></span></div>
            <i>→</i>
            <div><b>03</b><span><strong>查看结果</strong><small>空间 / 时间 / 区域</small></span></div>
          </div>
        </div>

        <form id="autoAnalyzeForm" class="upload-panel" method="post" action="{{ url_for('analyze_uploads') }}" enctype="multipart/form-data">
          <div class="upload-panel-head"><div><span>上传数据</span><strong>开始一次新的分析</strong></div><span class="upload-status-dot"></span></div>

          <label class="upload-dropzone" id="uploadDropzone" for="analysisFiles">
            <input id="analysisFiles" name="files" type="file" multiple accept=".csv,.tif,.tiff" required>
            <span class="upload-icon">＋</span>
            <strong>点击选择文件，或拖到这里</strong>
            <small id="selectedFileText">支持 FIRMS CSV 与 MCD64A1 GeoTIFF</small>
          </label>

          <div class="upload-format-row">
            <span><b>FIRMS</b> CSV</span>
            <span><b>MCD64A1</b> BurnDate + QA GeoTIFF</span>
          </div>

          <button id="analyzeButton" class="app-button app-button-primary upload-submit" type="submit">开始自动分析</button>

          <div id="analysisProgress" class="analysis-progress" hidden>
            <div><span></span></div>
            <p>正在读取文件并生成本次分析，请保持窗口开启…</p>
          </div>
        </form>
      </section>

      <section class="app-section reveal-item">
        <div class="section-heading">
          <div><span class="app-eyebrow">RECENT ANALYSIS</span><h2>最近分析</h2><p>按每次上传单独保存，继续上一次工作也从这里进入。</p></div>
          <a class="section-link" href="{{ url_for('tasks') }}">查看全部记录 <span>→</span></a>
        </div>

        {% if records %}
        <div class="analysis-card-grid">
          {% for record in records[:6] %}
          <article class="analysis-card">
            <div class="analysis-card-head">
              <span class="data-pill">{{ record.data_type }}</span>
              <span class="status-pill status-{{ record.status }}">{{ record.status_label }}</span>
            </div>
            <h3>{{ record.name }}</h3>
            <p class="analysis-card-period">{{ record.period }}</p>

            <div class="analysis-metrics">
              <div><span>有效火点</span><strong>{{ '{:,}'.format(record.active_fire_count) }}</strong></div>
              <div><span>涉及区域</span><strong>{{ record.affected_regions }}</strong></div>
              <div><span>主要区域</span><strong class="metric-text">{{ record.main_region }}</strong></div>
            </div>

            {% if record.has_reused_data %}
            <div class="reuse-tag">已识别 {{ '{:,}'.format(record.existing_observations) }} 条历史重合观测并复用</div>
            {% endif %}

            <div class="analysis-card-footer">
              <span>{{ (record.created_at or '')[:16]|replace('T', ' ') }}</span>
              <a href="{{ url_for('task_detail', task_id=record.task_id) }}">查看结果 <b>→</b></a>
            </div>
          </article>
          {% endfor %}
        </div>
        {% else %}
        <div class="empty-card"><span>◎</span><strong>还没有分析记录</strong><p>从上方上传第一份数据，结果会自动保存在这里。</p></div>
        {% endif %}
      </section>

      <section class="quick-guide-grid reveal-item">
        <article><span class="quick-icon">⌁</span><div><strong>自动识别</strong><p>从文件内容和产品标识读取数据类型与时间范围。</p></div></article>
        <article><span class="quick-icon">◫</span><div><strong>独立记录</strong><p>每次上传形成自己的结果，历史重合数据可复用但不重复保存。</p></div></article>
        <article><span class="quick-icon">↗</span><div><strong>结果导出</strong><p>从具体分析记录进入结果页，再导出该次分析的数据。</p></div></article>
      </section>
    </main>
  </div>
</div>

{% include '_help_modal.html' %}
<script src="{{ url_for('static', filename='product.js') }}"></script>
</body>
</html>
'''


TASKS_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>分析记录 - 黑龙江省火点数据检测与风险评估平台</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='product.css') }}">
</head>
<body class="app-body">
<span class="sr-only">创建分析任务</span>
<div class="app-shell">
  <aside class="app-sidebar">
    <a class="app-brand" href="{{ url_for('index') }}"><span class="app-brand-mark">F</span><span class="app-brand-copy"><strong>黑龙江省火点数据</strong><small>检测与风险评估平台</small></span></a>
    <nav class="app-side-nav">
      <a href="{{ url_for('index') }}"><span class="nav-icon">⌂</span><span>首页</span></a>
      <a href="{{ url_for('index') }}#upload"><span class="nav-icon">＋</span><span>开始分析</span></a>
      <a class="active" href="{{ url_for('tasks') }}"><span class="nav-icon">▤</span><span>分析记录</span></a>
      <button type="button" data-open-help><span class="nav-icon">?</span><span>使用帮助</span></button>
    </nav>
    <div class="app-side-spacer"></div><div class="app-side-footer"><span>本地桌面分析</span><b>V1.0</b></div>
  </aside>

  <div class="app-workspace">
    <header class="app-topbar">
      <div><span class="app-eyebrow">ANALYSIS RECORDS</span><h1>分析记录</h1><p>按时间查看每一次上传、分析和结果。</p></div>
      <div class="app-top-actions"><button class="app-button app-button-ghost" type="button" data-open-help>使用教程</button><a class="app-button app-button-primary" href="{{ url_for('index') }}#upload">＋ 新分析</a></div>
    </header>

    <main class="app-main">
      {% if page_error %}<div class="app-alert error"><strong>操作失败</strong><span>{{ page_error }}</span></div>{% endif %}

      {% if records %}
      <section class="record-table-card reveal-item">
        <div class="record-table-head"><span>共 {{ records|length }} 条记录</span><small>最近的分析显示在最上方</small></div>
        <div class="record-list">
          {% for record in records %}
          <article class="record-row">
            <div class="record-index"><span>{{ '%02d'|format(loop.index) }}</span></div>
            <div class="record-title">
              <div><span class="data-pill">{{ record.data_type }}</span><span class="status-pill status-{{ record.status }}">{{ record.status_label }}</span></div>
              <h2>{{ record.name }}</h2>
              <p>{{ record.period }} · {{ record.input_file_count }} 个输入文件</p>
            </div>
            <div class="record-stats"><div><span>有效火点</span><strong>{{ '{:,}'.format(record.active_fire_count) }}</strong></div><div><span>涉及区域</span><strong>{{ record.affected_regions }}</strong></div><div><span>主要区域</span><strong>{{ record.main_region }}</strong></div></div>
            <div class="record-time"><span>分析时间</span><strong>{{ (record.created_at or '')[:16]|replace('T', ' ') }}</strong></div>
            <div class="record-actions"><a class="app-button app-button-primary small" href="{{ url_for('task_detail', task_id=record.task_id) }}">查看结果</a>{% if record.processing_complete %}<a class="app-button app-button-ghost small" href="{{ url_for('export_task_csv', task_id=record.task_id) }}">导出 CSV</a>{% endif %}</div>
          </article>
          {% endfor %}
        </div>
      </section>
      {% else %}
      <div class="empty-card"><span>◎</span><strong>暂无分析记录</strong><p>点击右上角“新分析”上传数据即可开始。</p></div>
      {% endif %}
    </main>
  </div>
</div>

{% include '_help_modal.html' %}
<script src="{{ url_for('static', filename='product.js') }}"></script>
</body>
</html>
'''


TASK_DETAIL_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ task.name }} - 分析结果</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='product.css') }}">
</head>
<body class="app-body">
<div class="app-shell">
  <aside class="app-sidebar">
    <a class="app-brand" href="{{ url_for('index') }}"><span class="app-brand-mark">F</span><span class="app-brand-copy"><strong>黑龙江省火点数据</strong><small>检测与风险评估平台</small></span></a>
    <nav class="app-side-nav">
      <a href="{{ url_for('index') }}"><span class="nav-icon">⌂</span><span>首页</span></a>
      <a href="{{ url_for('index') }}#upload"><span class="nav-icon">＋</span><span>开始分析</span></a>
      <a class="active" href="{{ url_for('tasks') }}"><span class="nav-icon">▤</span><span>分析记录</span></a>
      <button type="button" data-open-help><span class="nav-icon">?</span><span>使用帮助</span></button>
    </nav>
    <div class="app-side-spacer"></div><div class="app-side-footer"><span>本地桌面分析</span><b>V1.0</b></div>
  </aside>

  <div class="app-workspace">
    <header class="app-topbar result-topbar">
      <div><a class="back-link" href="{{ url_for('tasks') }}">← 返回分析记录</a><span class="app-eyebrow">ANALYSIS RESULT</span><h1>{{ task.name }}</h1><p>{{ analysis_summary.period }} · {{ analysis_summary.data_type }}</p></div>
      <div class="app-top-actions"><button class="app-button app-button-ghost" type="button" data-open-help>怎么看结果</button>{% if analysis_summary.processing_complete %}<a class="app-button app-button-primary" href="{{ url_for('export_task_csv', task_id=task_id) }}">导出本次结果</a>{% endif %}</div>
    </header>

    <main class="app-main result-main">
      {% if page_error %}<div class="app-alert error"><strong>本次分析未完全完成</strong><span>{{ page_error }}</span></div>{% endif %}
      {% if analysis_summary.has_reused_data %}<div class="app-alert info"><strong>已识别历史重合数据</strong><span>{{ '{:,}'.format(analysis_summary.existing_observations) }} 条已存储观测被直接复用于本次分析，没有重复写入数据库。</span></div>{% endif %}

      <section class="result-kpi-grid reveal-item">
        <article><span class="kpi-icon fire">●</span><div><small>有效主动火点</small><strong>{{ '{:,}'.format(analysis_summary.active_fire_count) }}</strong><p>当前分析记录</p></div></article>
        <article><span class="kpi-icon region">◫</span><div><small>涉及行政区</small><strong>{{ analysis_summary.affected_regions }}</strong><p>市（地）</p></div></article>
        <article><span class="kpi-icon focus">◎</span><div><small>主要区域</small><strong class="kpi-text">{{ analysis_summary.main_region }}</strong><p>当前记录中最集中区域</p></div></article>
        <article><span class="kpi-icon type">▦</span><div><small>识别数据</small><strong class="kpi-text">{{ analysis_summary.data_type }}</strong><p>{{ analysis_summary.status_label }}</p></div></article>
        {% if analysis_summary.burned_area_km2 > 0 %}<article><span class="kpi-icon burn">■</span><div><small>烧毁像元面积</small><strong>{{ '%.2f'|format(analysis_summary.burned_area_km2) }}</strong><p>km²</p></div></article>{% endif %}
      </section>

      <section class="result-visual-grid reveal-item">
        <article class="app-card map-result-card">
          <div class="card-heading"><div><span class="app-eyebrow">SPATIAL DISTRIBUTION</span><h2>空间分布</h2><p>按本次分析的行政区结果显示主要集中位置。</p></div><span class="map-legend"><i></i>本次分析强度</span></div>
          <div class="task-map-stage"><canvas id="taskMapCanvas" width="900" height="520"></canvas><div class="map-empty-note" id="taskMapEmpty" hidden>本次分析暂无可用于空间展示的数据。</div></div>
        </article>

        <article class="app-card region-ranking-card">
          <div class="card-heading"><div><span class="app-eyebrow">REGIONAL RANKING</span><h2>行政区分布</h2><p>比较本次分析中各市（地）的结果。</p></div></div>
          {% set max_fire = (task_region_ranking|map(attribute='active_fire_count')|max) if task_region_ranking else 0 %}
          {% if max_fire and max_fire > 0 %}
          <div class="region-bars">
            {% for row in task_region_ranking %}{% if row.active_fire_count > 0 %}
            <div class="region-bar-row"><strong>{{ row.region_name }}</strong><div class="bar-track"><span style="--bar-width: {{ (row.active_fire_count / max_fire * 100)|round(1) }}%"></span></div><b>{{ '{:,}'.format(row.active_fire_count) }}</b></div>
            {% endif %}{% endfor %}
          </div>
          {% elif task_region_ranking %}
          {% set max_area = (task_region_ranking|map(attribute='burned_area_km2')|max) %}
          <div class="region-bars">
            {% for row in task_region_ranking %}{% if row.burned_area_km2 > 0 %}
            <div class="region-bar-row"><strong>{{ row.region_name }}</strong><div class="bar-track burn"><span style="--bar-width: {{ (row.burned_area_km2 / max_area * 100)|round(1) }}%"></span></div><b>{{ '%.2f'|format(row.burned_area_km2) }}</b></div>
            {% endif %}{% endfor %}
          </div>
          {% else %}<div class="empty-card compact"><span>◎</span><strong>暂无区域结果</strong></div>{% endif %}
        </article>
      </section>

      {% if task_daily_series and analysis_summary.active_fire_count > 0 %}
      <section class="app-card reveal-item">
        {% set peak = task_daily_series|max(attribute='active_fire_observation_count') %}
        <div class="card-heading inline"><div><span class="app-eyebrow">TIME DISTRIBUTION</span><h2>火点日期变化</h2><p>查看本次分析中火点观测随日期的变化。</p></div><div class="peak-box"><span>峰值日期</span><strong>{{ peak.date }}</strong><b>{{ '{:,}'.format(peak.active_fire_observation_count) }} 条</b></div></div>
        {% set max_day = peak.active_fire_observation_count if peak.active_fire_observation_count > 0 else 1 %}
        <div class="time-chart" aria-label="本次分析逐日火点分布">
          {% for row in task_daily_series %}<div class="time-column" title="{{ row.date }}：{{ row.active_fire_observation_count }} 条"><span style="--bar-height: {{ (row.active_fire_observation_count / max_day * 100)|round(1) }}%"></span></div>{% endfor %}
        </div>
        <div class="time-axis"><span>{{ task_daily_series[0].date }}</span><span>{{ peak.date }} · 峰值</span><span>{{ task_daily_series[-1].date }}</span></div>
      </section>
      {% endif %}

      <section class="result-info-grid reveal-item">
        <article class="app-card">
          <div class="card-heading"><div><span class="app-eyebrow">DATA IDENTIFICATION</span><h2>本次数据识别</h2></div></div>
          <div class="identify-grid"><div><span>数据类型</span><strong>{{ analysis_summary.data_type }}</strong></div><div><span>时间范围</span><strong>{{ analysis_summary.period }}</strong></div><div><span>输入文件</span><strong>{{ files|length }} 个</strong></div><div><span>分析状态</span><strong>{{ analysis_summary.status_label }}</strong></div></div>
          <div class="file-list">{% for file in files %}<div><span>{{ file.original_filename }}</span><small>{{ file_role_labels.get(file.file_role, file.file_role) }}</small></div>{% endfor %}</div>
        </article>

        {% if task_risk_assessment %}
        <article class="app-card">
          <div class="card-heading"><div><span class="app-eyebrow">RELATIVE ATTENTION</span><h2>行政区相对关注情况</h2><p>仅比较本次分析记录中的行政区结果。</p></div></div>
          <div class="attention-list">{% for row in task_risk_assessment.regions %}{% if row.relative_score is not none %}<div><strong>{{ row.region_name }}</strong><span class="attention-pill">{{ row.attention_level }}</span><small>{{ row.active_fire_count }} 条火点{% if row.burned_area_km2 > 0 %} · {{ '%.2f'|format(row.burned_area_km2) }} km²{% endif %}</small></div>{% endif %}{% endfor %}</div>
        </article>
        {% endif %}
      </section>

      <details class="tech-details reveal-item">
        <summary><span>技术信息</span><small>输入校验、处理记录和数据口径</small></summary>
        <div class="tech-content">
          <div class="tech-status"><strong>输入准备状态</strong><span>{{ 'READY' if readiness.ready else 'NOT READY' }}</span></div>
          <div class="tech-table-wrap"><table><thead><tr><th>文件</th><th>角色</th><th>校验</th><th>说明</th></tr></thead><tbody>{% for file in files %}<tr><td>{{ file.original_filename }}</td><td>{{ file_role_labels.get(file.file_role, file.file_role) }}</td><td>{{ file.validation_status }}</td><td>{{ file.validation_message or '—' }}</td></tr>{% endfor %}</tbody></table></div>
          {% if firms_runs %}<h3>FIRMS 处理记录</h3>{% for run in firms_runs %}<div class="run-line"><strong>#{{ run.id }} · {{ run.status }}</strong><span>输入 {{ run.input_count }} · 新增 {{ run.metadata.get('new_observations', 0) }} · 历史复用 {{ run.metadata.get('existing_observations', 0) }}</span></div>{% endfor %}{% endif %}
          {% if mcd64_runs %}<h3>MCD64A1 处理记录</h3>{% for run in mcd64_runs %}<div class="run-line"><strong>#{{ run.id }} · {{ run.status }}</strong><span>输入 {{ run.input_count }} · 存储 {{ run.stored_count }}</span></div>{% endfor %}{% endif %}
          {% if task_risk_assessment %}<div class="tech-definition">{{ task_risk_assessment.disclaimer }}</div>{% endif %}
        </div>
      </details>

      <script id="taskMapFeatures" type="application/json">{{ region_feature_collection|tojson }}</script>
      <script id="taskMapStats" type="application/json">{{ task_region_ranking|tojson }}</script>
    </main>
  </div>
</div>

{% include '_help_modal.html' %}
<script src="{{ url_for('static', filename='product.js') }}"></script>
</body>
</html>
'''


PRODUCT_JS = r'''(() => {
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
'''


PRODUCT_CSS = r''':root {
  --app-bg: #f3f6f8;
  --app-panel: #ffffff;
  --app-panel-soft: #f8fbfc;
  --app-ink: #123047;
  --app-muted: #6a7f8e;
  --app-line: #dce6eb;
  --app-blue: #176f8a;
  --app-blue-dark: #10556d;
  --app-teal: #20a19d;
  --app-red: #d94b3f;
  --app-green: #2c8a66;
  --app-shadow: 0 12px 32px rgba(29, 63, 84, .08);
  --sidebar-width: 226px;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body.app-body { margin: 0; min-height: 100vh; color: var(--app-ink); background: var(--app-bg); font-family: "Microsoft YaHei", "PingFang SC", system-ui, -apple-system, sans-serif; }
body.modal-open { overflow: hidden; }
a { color: inherit; }
button, input { font: inherit; }

.app-shell { display: grid; grid-template-columns: var(--sidebar-width) minmax(0, 1fr); min-height: 100vh; }
.app-sidebar { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; padding: 24px 15px 16px; border-right: 1px solid var(--app-line); background: rgba(255,255,255,.96); z-index: 20; }
.app-brand { display: flex; align-items: center; gap: 11px; padding: 4px 8px 24px; text-decoration: none; }
.app-brand-mark { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 13px; color: #fff; background: linear-gradient(145deg, #155b76, #23aaa4); box-shadow: 0 7px 18px rgba(25,117,136,.2); font-weight: 900; font-size: 19px; }
.app-brand-copy { min-width: 0; }
.app-brand-copy strong, .app-brand-copy small { display: block; }
.app-brand-copy strong { font-size: 14px; white-space: nowrap; }
.app-brand-copy small { margin-top: 3px; color: var(--app-muted); font-size: 11px; white-space: nowrap; }

.app-side-nav { display: grid; gap: 7px; }
.app-side-nav a, .app-side-nav button { width: 100%; min-height: 44px; display: flex; align-items: center; gap: 11px; padding: 8px 11px; border: 0; border-radius: 10px; color: #526b7b; background: transparent; text-decoration: none; text-align: left; cursor: pointer; font-size: 14px; font-weight: 700; transition: background .18s ease, color .18s ease, transform .18s ease; }
.app-side-nav a:hover, .app-side-nav button:hover { color: var(--app-blue); background: #edf6f8; transform: translateX(2px); }
.app-side-nav a.active { color: #0f6681; background: linear-gradient(90deg, #e3f2f6, #f2f8fa); box-shadow: inset 3px 0 #1684a0; }
.nav-icon { width: 25px; height: 25px; display: grid; place-items: center; border-radius: 8px; background: #edf2f5; font-size: 15px; font-weight: 900; }
.app-side-nav .active .nav-icon { background: #d5ebf1; }
.app-side-spacer { flex: 1; }
.app-side-footer { display: flex; justify-content: space-between; gap: 10px; padding: 13px 9px 4px; border-top: 1px solid #edf2f4; color: var(--app-muted); font-size: 11px; }
.app-side-footer b { color: #315a6e; }

.app-workspace { min-width: 0; }
.app-topbar { min-height: 104px; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 22px clamp(24px, 3vw, 44px); border-bottom: 1px solid var(--app-line); background: rgba(255,255,255,.85); backdrop-filter: blur(10px); }
.app-topbar h1 { margin: 2px 0 4px; font-size: 26px; line-height: 1.15; letter-spacing: -.02em; }
.app-topbar p { margin: 0; color: var(--app-muted); font-size: 13px; }
.app-eyebrow { display: block; color: #3d778d; font-size: 10px; font-weight: 900; letter-spacing: .14em; }
.app-top-actions { display: flex; align-items: center; gap: 9px; }
.app-main { width: min(1280px, calc(100% - 48px)); margin: 0 auto; padding: 30px 0 52px; }
.result-main { width: min(1360px, calc(100% - 48px)); }

.app-button { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; padding: 8px 15px; border: 1px solid transparent; border-radius: 9px; text-decoration: none; cursor: pointer; font-weight: 800; font-size: 13px; transition: transform .16s ease, box-shadow .16s ease, background .16s ease; }
.app-button:hover { transform: translateY(-1px); }
.app-button-primary { color: #fff; background: linear-gradient(120deg, var(--app-blue), #168aa0); box-shadow: 0 7px 16px rgba(23,111,138,.18); }
.app-button-primary:hover { box-shadow: 0 10px 22px rgba(23,111,138,.24); }
.app-button-primary:disabled { opacity: .65; cursor: wait; transform: none; }
.app-button-ghost { color: #36586a; border-color: #cddce3; background: #fff; }
.app-button.small { min-height: 34px; padding: 6px 11px; font-size: 12px; }

.app-chip, .data-pill, .status-pill, .reuse-tag, .attention-pill { display: inline-flex; align-items: center; width: fit-content; border-radius: 999px; font-weight: 800; }
.app-chip { padding: 6px 10px; color: #17667d; background: #e5f2f5; font-size: 11px; }
.data-pill { padding: 5px 8px; color: #1a6178; background: #e7f2f5; font-size: 11px; }
.status-pill { padding: 4px 8px; font-size: 11px; }
.status-ready, .status-completed { color: #217456; background: #e5f4ed; }
.status-running, .status-validating { color: #7e631c; background: #fff4cf; }
.status-created { color: #5c7181; background: #edf2f4; }
.status-failed { color: #9b3d34; background: #ffebe8; }

.app-alert { display: flex; gap: 10px; align-items: baseline; margin-bottom: 16px; padding: 12px 15px; border-radius: 10px; font-size: 13px; }
.app-alert.error { color: #80352f; border: 1px solid #f0c1bc; background: #fff3f1; }
.app-alert.info { color: #315e70; border: 1px solid #c9dfe7; background: #f0f8fa; }

.start-card { display: grid; grid-template-columns: minmax(0, .95fr) minmax(440px, .75fr); gap: 30px; align-items: stretch; padding: 30px; border: 1px solid var(--app-line); border-radius: 20px; background: linear-gradient(145deg, #fff 0%, #f6fafb 70%, #eef7f8 100%); box-shadow: var(--app-shadow); overflow: hidden; }
.start-card-copy { padding: 8px 8px 8px 4px; }
.start-card-copy h2 { max-width: 650px; margin: 14px 0 10px; font-size: clamp(27px, 3.2vw, 42px); line-height: 1.16; letter-spacing: -.04em; }
.start-card-copy > p { max-width: 680px; margin: 0; color: #5d7483; line-height: 1.8; font-size: 14px; }
.start-flow { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 26px; }
.start-flow > div { display: flex; align-items: center; gap: 9px; padding: 10px 12px; border: 1px solid #dfe8ec; border-radius: 11px; background: rgba(255,255,255,.8); }
.start-flow b { width: 27px; height: 27px; display: grid; place-items: center; border-radius: 50%; color: #fff; background: #176e88; font-size: 11px; }
.start-flow strong, .start-flow small { display: block; }
.start-flow strong { font-size: 12px; }
.start-flow small { margin-top: 2px; color: var(--app-muted); font-size: 10px; }
.start-flow i { color: #9caeb8; font-style: normal; }

.upload-panel { padding: 20px; border: 1px solid #d8e4e9; border-radius: 16px; background: rgba(255,255,255,.94); box-shadow: 0 14px 30px rgba(31,68,89,.07); }
.upload-panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; }
.upload-panel-head span, .upload-panel-head strong { display: block; }
.upload-panel-head span { color: var(--app-muted); font-size: 11px; }
.upload-panel-head strong { margin-top: 2px; font-size: 16px; }
.upload-status-dot { width: 9px; height: 9px; border-radius: 50%; background: #2fb08a; box-shadow: 0 0 0 5px rgba(47,176,138,.11); }
.upload-dropzone { min-height: 185px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 20px; border: 1.5px dashed #9fc3d0; border-radius: 14px; color: #4e6a79; background: #f8fbfc; cursor: pointer; text-align: center; transition: border-color .18s ease, background .18s ease, transform .18s ease; }
.upload-dropzone:hover, .upload-dropzone.dragging { border-color: #1a88a3; background: #eef8fa; transform: translateY(-1px); }
.upload-dropzone.has-files { border-style: solid; border-color: #69b8a2; background: #f1faf6; }
.upload-dropzone input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.upload-icon { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 13px; color: #fff; background: linear-gradient(145deg, #176f8a, #20a19d); font-size: 25px; line-height: 1; }
.upload-dropzone strong { font-size: 14px; }
.upload-dropzone small { max-width: 100%; color: var(--app-muted); font-size: 11px; overflow-wrap: anywhere; }
.upload-format-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 11px 0; }
.upload-format-row span { padding: 5px 8px; border-radius: 7px; color: #617784; background: #f1f5f6; font-size: 10px; }
.upload-format-row b { color: #315e70; }
.upload-submit { width: 100%; }
.analysis-progress { margin-top: 12px; }
.analysis-progress > div { height: 7px; overflow: hidden; border-radius: 999px; background: #e2edf0; }
.analysis-progress > div span { display: block; width: 36%; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #17718b, #2eb3a6); animation: progress-slide 1.15s ease-in-out infinite; }
.analysis-progress p { margin: 7px 0 0; color: var(--app-muted); font-size: 11px; }
@keyframes progress-slide { from { transform: translateX(-110%); } to { transform: translateX(300%); } }

.app-section { margin-top: 34px; }
.section-heading, .card-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 15px; }
.section-heading h2, .card-heading h2 { margin: 3px 0 3px; font-size: 20px; }
.section-heading p, .card-heading p { margin: 0; color: var(--app-muted); font-size: 12px; }
.section-link { color: #126b85; text-decoration: none; font-size: 12px; font-weight: 800; }
.section-link span { display: inline-block; margin-left: 3px; transition: transform .16s ease; }
.section-link:hover span { transform: translateX(3px); }

.analysis-card-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 14px; }
.analysis-card { min-width: 0; padding: 18px; border: 1px solid var(--app-line); border-radius: 14px; background: #fff; box-shadow: 0 6px 18px rgba(32,65,83,.04); transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }
.analysis-card:hover { transform: translateY(-3px); border-color: #b9d6df; box-shadow: 0 14px 30px rgba(32,65,83,.09); }
.analysis-card-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.analysis-card h3 { margin: 13px 0 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 16px; }
.analysis-card-period { margin: 0; color: var(--app-muted); font-size: 11px; }
.analysis-metrics { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 7px; margin-top: 14px; }
.analysis-metrics div { min-width: 0; padding: 10px; border-radius: 9px; background: #f6f9fa; }
.analysis-metrics span { display: block; color: var(--app-muted); font-size: 10px; }
.analysis-metrics strong { display: block; margin-top: 4px; font-size: 17px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.analysis-metrics .metric-text { font-size: 12px; }
.reuse-tag { margin-top: 10px; padding: 6px 9px; color: #476c5f; background: #eef8f3; font-size: 10px; }
.analysis-card-footer { display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-top: 14px; padding-top: 12px; border-top: 1px solid #edf1f3; color: var(--app-muted); font-size: 10px; }
.analysis-card-footer a { color: #116983; text-decoration: none; font-weight: 800; font-size: 11px; }

.quick-guide-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; margin-top: 18px; }
.quick-guide-grid article { display: flex; gap: 12px; padding: 16px; border: 1px solid var(--app-line); border-radius: 12px; background: rgba(255,255,255,.68); }
.quick-icon { width: 35px; height: 35px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 10px; color: #176f8a; background: #e8f3f6; font-weight: 900; }
.quick-guide-grid strong { font-size: 13px; }
.quick-guide-grid p { margin: 4px 0 0; color: var(--app-muted); font-size: 11px; line-height: 1.6; }
.empty-card { padding: 38px; border: 1px dashed #bdd0d9; border-radius: 14px; color: var(--app-muted); background: rgba(255,255,255,.6); text-align: center; }
.empty-card span { display: block; margin-bottom: 6px; color: #5692a6; font-size: 25px; }
.empty-card strong { color: var(--app-ink); }
.empty-card p { margin: 5px 0 0; font-size: 12px; }
.empty-card.compact { padding: 22px; }

.record-table-card { overflow: hidden; border: 1px solid var(--app-line); border-radius: 16px; background: #fff; box-shadow: var(--app-shadow); }
.record-table-head { display: flex; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--app-line); color: #496776; font-size: 12px; }
.record-table-head small { color: var(--app-muted); }
.record-list { display: grid; }
.record-row { display: grid; grid-template-columns: 52px minmax(220px,1.3fr) minmax(300px,.9fr) 150px auto; gap: 16px; align-items: center; padding: 17px 18px; border-bottom: 1px solid #edf2f4; transition: background .16s ease; }
.record-row:last-child { border-bottom: 0; }
.record-row:hover { background: #f8fbfc; }
.record-index span { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 9px; color: #4b7182; background: #edf5f7; font-size: 11px; font-weight: 900; }
.record-title > div { display: flex; gap: 6px; }
.record-title h2 { margin: 7px 0 3px; font-size: 14px; }
.record-title p { margin: 0; color: var(--app-muted); font-size: 10px; }
.record-stats { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
.record-stats span, .record-time span { display: block; color: var(--app-muted); font-size: 9px; }
.record-stats strong, .record-time strong { display: block; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.record-actions { display: flex; gap: 6px; }

.back-link { display: block; margin-bottom: 5px; color: #28788f; text-decoration: none; font-size: 11px; font-weight: 800; }
.result-topbar { align-items: flex-end; }
.result-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap: 12px; }
.result-kpi-grid article { display: flex; align-items: center; gap: 13px; min-height: 112px; padding: 18px; border: 1px solid var(--app-line); border-radius: 14px; background: #fff; box-shadow: 0 5px 18px rgba(33,66,84,.045); }
.result-kpi-grid small { display: block; color: var(--app-muted); font-size: 10px; }
.result-kpi-grid strong { display: block; margin-top: 3px; font-size: 27px; line-height: 1.08; }
.result-kpi-grid .kpi-text { font-size: 17px; }
.result-kpi-grid p { margin: 4px 0 0; color: var(--app-muted); font-size: 9px; }
.kpi-icon { width: 39px; height: 39px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 11px; font-size: 15px; }
.kpi-icon.fire { color: #d84d41; background: #fff0ed; }.kpi-icon.region { color: #28799a; background: #edf5f8; }.kpi-icon.focus { color: #8a6d31; background: #fff8e8; }.kpi-icon.type { color: #5769a0; background: #f0f1fb; }.kpi-icon.burn { color: #24825f; background: #eaf7f1; }

.app-card { margin-top: 16px; padding: 20px; border: 1px solid var(--app-line); border-radius: 14px; background: #fff; box-shadow: 0 5px 18px rgba(33,66,84,.04); }
.result-visual-grid { display: grid; grid-template-columns: minmax(0,1.35fr) minmax(350px,.65fr); gap: 16px; }
.result-visual-grid .app-card { margin-top: 16px; }
.card-heading.inline { align-items: flex-start; }
.map-legend { color: var(--app-muted); font-size: 10px; white-space: nowrap; }.map-legend i { display: inline-block; width: 8px; height: 8px; margin-right: 5px; border-radius: 50%; background: var(--app-red); }
.task-map-stage { position: relative; min-height: 430px; overflow: hidden; border: 1px solid #d9e5e9; border-radius: 12px; background: radial-gradient(circle at 25% 20%, #f6fbfc, #eef5f7); }
.task-map-stage canvas { width: 100%; height: 430px; display: block; }
.map-empty-note { position: absolute; inset: 0; display: grid; place-items: center; color: var(--app-muted); font-size: 12px; }
.region-bars { display: grid; gap: 10px; max-height: 430px; overflow-y: auto; padding-right: 3px; }
.region-bar-row { display: grid; grid-template-columns: 90px 1fr 58px; gap: 8px; align-items: center; }
.region-bar-row > strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }.region-bar-row > b { text-align: right; font-size: 11px; font-variant-numeric: tabular-nums; }
.bar-track { height: 8px; overflow: hidden; border-radius: 999px; background: #edf2f4; }.bar-track span { display: block; width: 0; height: 100%; border-radius: inherit; background: linear-gradient(90deg,#d94c40,#ef8a62); transition: width .75s cubic-bezier(.2,.8,.2,1); }.bar-track span.grow { width: var(--bar-width); }.bar-track.burn span { background: linear-gradient(90deg,#2d8965,#66b58e); }

.peak-box { padding: 8px 11px; border-radius: 9px; background: #f6f9fa; text-align: right; }.peak-box span { display: block; color: var(--app-muted); font-size: 9px; }.peak-box strong, .peak-box b { margin-left: 7px; font-size: 11px; }
.time-chart { height: 180px; display: flex; align-items: end; gap: 4px; padding: 8px 2px 0; border-bottom: 1px solid #d4e0e5; }.time-column { flex: 1 1 0; height: 100%; display: flex; align-items: end; min-width: 4px; }.time-column span { width: 100%; height: 0; min-height: 2px; border-radius: 5px 5px 0 0; background: linear-gradient(180deg,#ee8b66,#d94b3e); transition: height .65s cubic-bezier(.2,.8,.2,1); }.time-column span.grow { height: var(--bar-height); }.time-axis { display: flex; justify-content: space-between; gap: 12px; padding-top: 8px; color: var(--app-muted); font-size: 10px; }

.result-info-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; }.result-info-grid .app-card { margin-top: 16px; }
.identify-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; }.identify-grid div { padding: 10px; border-radius: 9px; background: #f6f9fa; }.identify-grid span { display: block; color: var(--app-muted); font-size: 9px; }.identify-grid strong { display: block; margin-top: 3px; font-size: 12px; }
.file-list { display: grid; gap: 6px; margin-top: 10px; }.file-list div { display: flex; justify-content: space-between; gap: 10px; padding-top: 7px; border-top: 1px solid #edf1f3; font-size: 10px; }.file-list span { word-break: break-all; }.file-list small { color: var(--app-muted); white-space: nowrap; }
.attention-list { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; }.attention-list > div { padding: 10px; border: 1px solid #e3eaed; border-radius: 9px; background: #f8fafb; }.attention-list strong { font-size: 11px; }.attention-list small { display: block; margin-top: 4px; color: var(--app-muted); font-size: 9px; }.attention-pill { margin-left: 6px; padding: 3px 6px; color: #315f70; background: #e8f1f4; font-size: 9px; }

.tech-details { margin-top: 16px; border: 1px solid var(--app-line); border-radius: 12px; background: #fff; }.tech-details summary { display: flex; justify-content: space-between; padding: 14px 16px; cursor: pointer; font-weight: 800; font-size: 12px; }.tech-details summary small { color: var(--app-muted); font-weight: 500; }.tech-content { padding: 0 16px 16px; border-top: 1px solid #edf1f3; }.tech-status { display: flex; justify-content: space-between; padding: 12px 0; font-size: 11px; }.tech-table-wrap { overflow-x: auto; }.tech-table-wrap table { width: 100%; border-collapse: collapse; font-size: 10px; }.tech-table-wrap th, .tech-table-wrap td { padding: 7px 8px; border-bottom: 1px solid #edf1f3; text-align: left; }.tech-content h3 { margin: 13px 0 6px; font-size: 11px; }.run-line { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-top: 1px solid #edf1f3; font-size: 10px; }.run-line span { color: var(--app-muted); }.tech-definition { margin-top: 12px; padding: 9px; border-radius: 8px; color: var(--app-muted); background: #f6f8f9; font-size: 10px; line-height: 1.65; }

.reveal-item { opacity: 0; transform: translateY(10px); transition: opacity .45s ease, transform .45s ease; }.reveal-item.visible { opacity: 1; transform: none; }
.sr-only { position: absolute !important; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }

/* Tutorial modal */
.guide-modal[hidden] { display: none; }.guide-modal { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 28px; }.guide-backdrop { position: absolute; inset: 0; background: rgba(21,42,56,.46); backdrop-filter: blur(3px); opacity: 0; transition: opacity .18s ease; }.guide-dialog { position: relative; width: min(1020px, calc(100vw - 48px)); max-height: min(780px, calc(100vh - 48px)); display: flex; flex-direction: column; overflow: hidden; border: 1px solid rgba(255,255,255,.9); border-radius: 18px; background: #fff; box-shadow: 0 30px 80px rgba(18,43,59,.25); transform: translateY(16px) scale(.985); opacity: 0; transition: transform .2s ease, opacity .2s ease; }.guide-modal.open .guide-backdrop { opacity: 1; }.guide-modal.open .guide-dialog { transform: none; opacity: 1; }
.guide-header { display: flex; justify-content: space-between; gap: 18px; padding: 22px 24px 17px; border-bottom: 1px solid var(--app-line); }.guide-header h2 { margin: 3px 0 4px; font-size: 22px; }.guide-header p { margin: 0; color: var(--app-muted); font-size: 11px; }.guide-close { width: 34px; height: 34px; border: 0; border-radius: 9px; color: #5c7180; background: #f2f5f6; cursor: pointer; font-size: 22px; }
.guide-layout { min-height: 0; display: grid; grid-template-columns: 210px minmax(0,1fr); flex: 1; }.guide-nav { display: grid; align-content: start; gap: 6px; padding: 16px; border-right: 1px solid var(--app-line); background: #f8fafb; }.guide-nav button { display: grid; grid-template-columns: 28px 1fr; align-items: center; gap: 8px; padding: 10px; border: 0; border-radius: 9px; color: #526a78; background: transparent; text-align: left; cursor: pointer; font-size: 11px; font-weight: 700; }.guide-nav button b { width: 26px; height: 26px; display: grid; place-items: center; border-radius: 8px; color: #4c7b8c; background: #e9f1f4; font-size: 9px; }.guide-nav button.active { color: #116a84; background: #e7f3f6; }.guide-nav button.active b { color: #fff; background: #17748e; }
.guide-content { overflow-y: auto; padding: 24px 28px; }.guide-panel { display: none; }.guide-panel.active { display: block; animation: guide-in .18s ease; }@keyframes guide-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: none; } }.guide-step-label { color: #27778e; font-size: 9px; font-weight: 900; letter-spacing: .1em; }.guide-panel h3 { margin: 7px 0 16px; font-size: 20px; }.guide-copy { color: var(--app-muted); font-size: 11px; line-height: 1.7; }
.guide-visual { margin-bottom: 18px; padding: 18px; border: 1px solid #dae6ea; border-radius: 13px; background: linear-gradient(145deg,#f6fafb,#edf6f8); }.guide-mini-window { width: min(540px,90%); margin: 0 auto; padding: 10px; border-radius: 11px; background: #fff; box-shadow: 0 12px 30px rgba(33,68,86,.1); }.guide-mini-title { display: flex; gap: 4px; padding-bottom: 7px; }.guide-mini-title span { width: 6px; height: 6px; border-radius: 50%; background: #c6d3d9; }.guide-mini-drop { min-height: 100px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1px dashed #a7c8d3; border-radius: 8px; color: #54707e; background: #f8fbfc; }.guide-mini-drop b { font-size: 18px; }.guide-mini-drop strong { margin-top: 2px; font-size: 11px; }.guide-mini-drop small { margin-top: 2px; font-size: 8px; }.guide-mini-button { width: 45%; margin: 8px auto 0; padding: 6px; border-radius: 6px; color: #fff; background: #17748e; text-align: center; font-size: 8px; font-weight: 800; }
.guide-steps-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }.guide-steps-list li { display: grid; grid-template-columns: 150px 1fr; gap: 12px; padding: 10px 12px; border-radius: 9px; background: #f7f9fa; font-size: 10px; }.guide-steps-list span { color: var(--app-muted); }
.guide-file-cards { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }.guide-file-cards article { display: flex; gap: 12px; padding: 15px; border: 1px solid var(--app-line); border-radius: 11px; }.guide-file-icon { width: 44px; height: 44px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 10px; font-size: 10px; font-weight: 900; }.guide-file-icon.fire { color: #b84339; background: #fff0ed; }.guide-file-icon.burn { color: #267a5d; background: #eaf7f1; }.guide-file-cards strong { font-size: 11px; }.guide-file-cards p { margin: 5px 0 0; color: var(--app-muted); font-size: 9px; line-height: 1.6; }.guide-tip { margin-top: 12px; padding: 10px 12px; border-radius: 9px; color: #4f6e7c; background: #edf6f8; font-size: 10px; }
.guide-result-preview { padding: 14px; border: 1px solid var(--app-line); border-radius: 12px; background: #f6f9fa; }.guide-preview-kpis { display: grid; grid-template-columns: repeat(4,1fr); gap: 6px; }.guide-preview-kpis span { height: 46px; border-radius: 7px; background: #fff; box-shadow: 0 3px 8px rgba(34,70,89,.05); }.guide-preview-main { display: grid; grid-template-columns: 1.4fr .6fr; gap: 7px; margin-top: 7px; }.guide-preview-map { position: relative; height: 150px; border-radius: 8px; background: #e6f1f4; overflow: hidden; }.guide-preview-map::before { content: ""; position: absolute; width: 100px; height: 86px; left: 34%; top: 27%; border: 2px solid #76a9bb; border-radius: 45% 55% 50% 43%; transform: rotate(13deg); }.guide-preview-map i { position: absolute; width: 8px; height: 8px; border-radius: 50%; background: #db5548; }.guide-preview-map i:nth-child(1){left:44%;top:47%}.guide-preview-map i:nth-child(2){left:48%;top:55%}.guide-preview-map i:nth-child(3){left:40%;top:61%}.guide-preview-map i:nth-child(4){left:55%;top:65%}.guide-preview-bars { display: grid; align-content: center; gap: 8px; padding: 12px; border-radius: 8px; background: #fff; }.guide-preview-bars em { height: 7px; border-radius: 999px; background: #e8eef1; position: relative; }.guide-preview-bars em::after { content: ""; display: block; height: 100%; border-radius: inherit; background: #dc6559; }.guide-preview-bars em:nth-child(1)::after{width:88%}.guide-preview-bars em:nth-child(2)::after{width:64%}.guide-preview-bars em:nth-child(3)::after{width:49%}.guide-preview-bars em:nth-child(4)::after{width:37%}.guide-preview-bars em:nth-child(5)::after{width:22%}.guide-result-list { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; margin-top: 12px; }.guide-result-list div { padding: 10px; border-radius: 8px; background: #f7f9fa; }.guide-result-list b { display: block; font-size: 10px; }.guide-result-list span { display: block; margin-top: 3px; color: var(--app-muted); font-size: 9px; line-height: 1.5; }
.guide-repeat-flow { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; align-items: center; gap: 8px; margin: 22px 0; }.guide-repeat-flow > div { min-height: 100px; display: flex; flex-direction: column; justify-content: center; padding: 14px; border: 1px solid var(--app-line); border-radius: 10px; background: #f8fafb; text-align: center; }.guide-repeat-flow span { color: var(--app-muted); font-size: 9px; }.guide-repeat-flow strong { margin-top: 5px; font-size: 10px; }.guide-repeat-flow > b { color: #7b9aa8; }
.guide-terms { display: grid; gap: 9px; margin: 0; }.guide-terms div { display: grid; grid-template-columns: 170px 1fr; gap: 16px; padding: 12px; border-radius: 9px; background: #f7f9fa; }.guide-terms dt { font-weight: 800; font-size: 10px; }.guide-terms dd { margin: 0; color: var(--app-muted); font-size: 9px; line-height: 1.6; }
.guide-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 24px; border-top: 1px solid var(--app-line); background: #fbfcfc; }.guide-dont-show { display: flex; align-items: center; gap: 7px; color: var(--app-muted); font-size: 10px; }

@media (max-width: 1120px) {
  :root { --sidebar-width: 194px; }
  .analysis-card-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .record-row { grid-template-columns: 45px 1fr auto; }.record-stats { grid-column: 2; }.record-time { display: none; }.record-actions { grid-column: 3; grid-row: 1 / span 2; flex-direction: column; }
  .result-visual-grid { grid-template-columns: 1fr; }
}

@media (max-width: 820px) {
  :root { --sidebar-width: 72px; }
  .app-sidebar { padding-inline: 10px; }.app-brand { justify-content: center; padding-inline: 0; }.app-brand-copy, .app-side-nav a span:last-child, .app-side-nav button span:last-child, .app-side-footer span { display: none; }.app-side-nav a, .app-side-nav button { justify-content: center; padding-inline: 0; }.app-side-footer { justify-content: center; }
  .start-card { grid-template-columns: 1fr; }.analysis-card-grid, .quick-guide-grid, .result-info-grid { grid-template-columns: 1fr; }
  .guide-layout { grid-template-columns: 1fr; }.guide-nav { display: flex; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--app-line); }.guide-nav button { grid-template-columns: 24px auto; white-space: nowrap; }.guide-file-cards, .guide-result-list { grid-template-columns: 1fr; }
}

@media (max-width: 620px) {
  .app-shell { grid-template-columns: 1fr; }.app-sidebar { position: sticky; top: 0; width: 100%; height: auto; flex-direction: row; align-items: center; padding: 8px 10px; border-right: 0; border-bottom: 1px solid var(--app-line); }.app-brand { padding: 0; }.app-brand-mark { width: 34px; height: 34px; }.app-side-nav { display: flex; margin-left: auto; }.app-side-nav button, .app-side-nav a { width: 38px; min-height: 38px; }.app-side-spacer, .app-side-footer { display: none; }
  .app-topbar { min-height: 90px; padding: 16px 18px; }.app-topbar h1 { font-size: 21px; }.app-topbar p { display: none; }.app-top-actions .app-button-ghost { display: none; }.app-main, .result-main { width: min(100% - 24px, 1280px); padding-top: 18px; }
  .start-card { padding: 20px; }.start-card-copy h2 { font-size: 28px; }.start-flow { display: grid; grid-template-columns: 1fr; }.start-flow i { display: none; }
  .analysis-card-grid { grid-template-columns: 1fr; }.analysis-metrics { grid-template-columns: repeat(2,minmax(0,1fr)); }.quick-guide-grid { grid-template-columns: 1fr; }
  .record-row { grid-template-columns: 36px 1fr; }.record-stats, .record-actions { grid-column: 2; }.record-actions { grid-row: auto; flex-direction: row; }.record-index span { width: 30px; height: 30px; }
  .result-kpi-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }.task-map-stage, .task-map-stage canvas { height: 330px; min-height: 330px; }.attention-list, .identify-grid { grid-template-columns: 1fr; }
  .guide-modal { padding: 10px; }.guide-dialog { width: calc(100vw - 20px); max-height: calc(100vh - 20px); }.guide-header { padding: 16px; }.guide-header p { display: none; }.guide-content { padding: 18px; }.guide-footer { padding: 12px 16px; }.guide-dont-show { max-width: 200px; }.guide-steps-list li, .guide-terms div { grid-template-columns: 1fr; }.guide-repeat-flow { grid-template-columns: 1fr; }.guide-repeat-flow > b { transform: rotate(90deg); text-align: center; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }
  .reveal-item { opacity: 1; transform: none; }
}
'''

write("templates/_help_modal.html", HELP_MODAL)
write("templates/index.html", INDEX_HTML)
write("templates/tasks.html", TASKS_HTML)
write("templates/task_detail.html", TASK_DETAIL_HTML)
write("static/product.js", PRODUCT_JS)
write("static/product.css", PRODUCT_CSS)

print("UI productization batch applied successfully.")
print("Backup directory:")
print(backup_root)
print()
print("Touched files:")
for rel in [
    "templates/_help_modal.html",
    "templates/index.html",
    "templates/tasks.html",
    "templates/task_detail.html",
    "static/product.js",
    "static/product.css",
]:
    print(" -", rel)
print()
print("Next: run pytest -q once. If all tests pass, start `python .\\main.py serve` and review the whole flow.")
