/**
 * Power Desk — Minimalist Grid & Widget Manager using GridStack.js, Chart.js and Leaflet
 *
 * Every card shares one filter: the date range and the selected bidding zones (`$areas`), which the
 * zone map's clicks and the filter bar's chips edit.
 */

const LAYOUT_STORAGE_KEY = "power_desk_layout";
const AREA_STORAGE_KEY = "power_desk_areas";
const FALLBACK_DATE_RANGE = { start_date: "2024-03-01", end_date: "2024-03-07" }; // the seed week
// GB, FR, DE_LU, NL, BE: the first visit's selection, until the analyst picks zones
const DEFAULT_AREAS = ["10YGB----------A", "10YFR-RTE------C", "10Y1001A1001A82H", "10YNL----------L", "10YBE----------2"];
const AREA_REFRESH_DELAY_MS = 400; // lets several map clicks land before the cards re-query
const RESULT_CACHE_SIZE = 200; // query results kept in the page, so returning to a recent filter is instant
const ZONES_GEOJSON_URL = "/static/geo/bidding_zones.geojson";
const PANELS_STORAGE_KEY = "power_desk_panels"; // visible panels per `panels` card
const AXIS_TITLE_COLOR = "#64748b";
// Grey behind the time slots where some selected zones do not report (partial) or none does (missing)
const COVERAGE_FILL = { partial: "rgba(148, 163, 184, 0.10)", missing: "rgba(148, 163, 184, 0.24)" };
const BAND_COLOR = "rgba(57, 135, 229, 0.16)";
const DEFAULT_LINE_COLOR = "#38bdf8";
const CARD_BACKGROUND = "#0d1322";

let grid = null;
let layoutSignature = ""; // the cards and their default positions the saved layout was made for
const widgetInstances = new Map(); // widgetId -> { spec, chart, charts, map, dom, controller, visiblePanels }
const resultCache = new Map(); // request JSON -> query result, least recently used first
const zoneNames = new Map(); // area EIC code -> display name
let selectedAreas = loadSelectedAreas(); // EIC codes, in selection order; empty means every zone
let areaRefreshTimer = null;
let zonesGeojson = null;

function showDashboardError(message) {
  document
    .querySelector(".grid-stack")
    .insertAdjacentHTML("beforebegin", `<div class="card-error dashboard-error">${escapeHtml(message)}</div>`);
}

document.addEventListener("DOMContentLoaded", async () => {
  initGrid();
  await loadFilterOptions();
  renderAreaChips();
  await loadAndRenderWidgets();
  setupFilterEvents();
});

function initGrid() {
  grid = GridStack.init({
    cellHeight: 70,
    margin: 8,
    column: 12,
    animate: true,
    float: false,
    resizable: {
      handles: "e, se, s, sw, w"
    }
  });

  grid.on("change", saveGridLayout);
}

// A saved layout applies only to the cards it was made for: when cards or their default positions change,
// the defaults apply again (older layouts, saved without a signature, are dropped too).
function saveGridLayout() {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({ signature: layoutSignature, layout: grid.save(false) }));
  } catch {
    // the arrangement still applies to this page view
  }
}

function loadSavedLayout(widgets) {
  layoutSignature = JSON.stringify(widgets.map(widget => [widget.id, widget.grid]));
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY));
    if (saved?.signature === layoutSignature) return saved.layout;
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
  } catch {
    // no usable layout: the defaults apply
  }
  return null;
}

function resetGridLayout() {
  localStorage.removeItem(LAYOUT_STORAGE_KEY);
  window.location.reload();
}

function loadSelectedAreas() {
  try {
    const saved = JSON.parse(localStorage.getItem(AREA_STORAGE_KEY));
    return Array.isArray(saved) ? saved : [...DEFAULT_AREAS];
  } catch {
    return [...DEFAULT_AREAS];
  }
}

function setSelectedAreas(areas) {
  selectedAreas = areas;
  try {
    localStorage.setItem(AREA_STORAGE_KEY, JSON.stringify(areas));
  } catch {
    // the selection still applies to this page view
  }
  renderAreaChips();
  widgetInstances.forEach(instance => instance.map && styleZones(instance));
  clearTimeout(areaRefreshTimer);
  areaRefreshTimer = setTimeout(refreshAreaWidgets, AREA_REFRESH_DELAY_MS);
}

function toggleArea(code) {
  setSelectedAreas(selectedAreas.includes(code) ? selectedAreas.filter(a => a !== code) : [...selectedAreas, code]);
}

function renderAreaChips() {
  const chips = document.getElementById("area-chips");
  if (!selectedAreas.length) {
    chips.innerHTML = `<span class="area-chips-empty">All bidding zones</span>`;
    return;
  }
  chips.innerHTML = selectedAreas
    .map(
      code => `
      <span class="area-chip">${escapeHtml(zoneNames.get(code) || code)}
        <button class="area-chip-remove" data-area="${escapeHtml(code)}" title="Remove from the filter">&times;</button>
      </span>`
    )
    .join("");
  chips.querySelectorAll(".area-chip-remove").forEach(button =>
    button.addEventListener("click", () => toggleArea(button.dataset.area))
  );
}

async function loadFilterOptions() {
  try {
    const res = await fetch("/api/filters");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const startInput = document.getElementById("filter-start-date");
    const endInput = document.getElementById("filter-end-date");
    if (!startInput.value) startInput.value = data.default_start_date || FALLBACK_DATE_RANGE.start_date;
    if (!endInput.value) endInput.value = data.max_date || FALLBACK_DATE_RANGE.end_date;
    data.areas.forEach(area => zoneNames.set(area.area_eic_code, area.display_name));
    if (zoneNames.size) selectedAreas = selectedAreas.filter(code => zoneNames.has(code)); // zones no longer published
    document.getElementById("warehouse-stats").textContent = `${data.table_counts.bmrs__fuelinst || 0} rows`;
  } catch (err) {
    console.warn("Failed to load filter options:", err);
    showDashboardError(`Filter options unavailable: ${err.message}`);
  }
}

function setupFilterEvents() {
  document.getElementById("btn-apply-filters").addEventListener("click", refreshAllWidgets);
  document.getElementById("btn-clear-areas").addEventListener("click", () => setSelectedAreas([]));
  document.getElementById("btn-reset-layout").addEventListener("click", resetGridLayout);
  document.getElementById("btn-open-lineage").addEventListener("click", openLineageModal);
  document.getElementById("btn-close-lineage").addEventListener("click", closeLineageModal);
}

async function loadAndRenderWidgets() {
  try {
    const res = await fetch("/api/widgets");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const widgets = await res.json();
    const savedLayout = loadSavedLayout(widgets); // before adding cards: their "change" events save the default layout
    widgets.forEach(createWidgetCard);
    if (savedLayout) grid.load(savedLayout, false); // update the cards' positions, matched by id
    refreshAllWidgets();
  } catch (err) {
    console.error("Failed to load widgets:", err);
    showDashboardError(`Widgets unavailable: ${err.message}`);
  }
}

function createWidgetCard(spec) {
  const el = document.createElement("div");
  el.className = "grid-stack-item";
  el.id = `widget-${spec.id}`;
  el.setAttribute("gs-id", spec.id);
  el.setAttribute("gs-x", spec.grid.x);
  el.setAttribute("gs-y", spec.grid.y);
  el.setAttribute("gs-w", spec.grid.w);
  el.setAttribute("gs-h", spec.grid.h);
  el.setAttribute("gs-min-w", spec.grid.minW);
  el.setAttribute("gs-min-h", spec.grid.minH);

  el.innerHTML = `
    <div class="grid-stack-item-content">
      <div class="card-header">
        <div class="card-title">
          <span>${escapeHtml(spec.title)}</span>
          <span class="card-timing" id="timing-${escapeHtml(spec.id)}">-- ms</span>
        </div>
        <div class="card-actions">
          ${spec.type === "panels" ? `<div class="panel-toggles"></div>` : ""}
          <button class="card-btn" title="Refresh Query">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          </button>
        </div>
      </div>
      <div class="card-body" id="body-${escapeHtml(spec.id)}">
        <div class="card-message">Executing query...</div>
      </div>
    </div>
  `;
  el.querySelector(".card-btn").addEventListener("click", () => refreshWidget(spec.id));

  grid.addWidget(el);
  const instance = { spec, chart: null, charts: [], dom: el, visiblePanels: loadVisiblePanels(spec) };
  widgetInstances.set(spec.id, instance);
  if (spec.type === "panels") renderPanelToggles(instance);
}

function loadVisiblePanels(spec) {
  const fallback = spec.config.default_panels || spec.panels.map(panel => panel.id);
  try {
    const saved = JSON.parse(localStorage.getItem(PANELS_STORAGE_KEY))?.[spec.id];
    return Array.isArray(saved) ? saved : fallback;
  } catch {
    return fallback;
  }
}

function saveVisiblePanels(instance) {
  try {
    const saved = JSON.parse(localStorage.getItem(PANELS_STORAGE_KEY)) || {};
    localStorage.setItem(PANELS_STORAGE_KEY, JSON.stringify({ ...saved, [instance.spec.id]: instance.visiblePanels }));
  } catch {
    // the choice still applies to this page view
  }
}

function renderPanelToggles(instance) {
  const toggles = instance.dom.querySelector(".panel-toggles");
  toggles.innerHTML = instance.spec.panels
    .map(
      panel => `<button class="panel-toggle${instance.visiblePanels.includes(panel.id) ? " active" : ""}"
        data-panel="${escapeHtml(panel.id)}" title="${escapeHtml(panel.description)}">${escapeHtml(panel.title)}</button>`
    )
    .join("");
  toggles.querySelectorAll(".panel-toggle").forEach(button =>
    button.addEventListener("click", () => {
      const id = button.dataset.panel;
      const shown = instance.visiblePanels.includes(id);
      // panels keep the card's order, whatever order they were toggled in
      instance.visiblePanels = instance.spec.panels
        .map(panel => panel.id)
        .filter(panelId => (panelId === id ? !shown : instance.visiblePanels.includes(panelId)));
      saveVisiblePanels(instance);
      renderPanelToggles(instance);
      refreshWidget(instance.spec.id);
    })
  );
}

// The queries a card runs: its own, or those of its visible panels.
function widgetQueries(instance) {
  if (instance.spec.type !== "panels") return [{ id: null, sql: instance.spec.sql }];
  return instance.spec.panels
    .filter(panel => instance.visiblePanels.includes(panel.id))
    .map(panel => ({ id: panel.id, sql: panel.sql }));
}

async function refreshAllWidgets() {
  const ids = Array.from(widgetInstances.keys());
  await Promise.all(ids.map(id => refreshWidget(id)));
}

async function refreshAreaWidgets() {
  const ids = Array.from(widgetInstances.values())
    .filter(instance => widgetQueries(instance).some(query => query.sql.includes("$areas")))
    .map(instance => instance.spec.id);
  await Promise.all(ids.map(id => refreshWidget(id)));
}

// A newer refresh of the same card aborts the older one: its request is dropped (the server skips it
// if still queued) and its result never replaces newer data.
async function refreshWidget(widgetId) {
  const instance = widgetInstances.get(widgetId);
  const bodyEl = document.getElementById(`body-${widgetId}`);
  const requests = widgetQueries(instance).map(({ sql }) => ({
    sql,
    start_date: document.getElementById("filter-start-date").value,
    end_date: document.getElementById("filter-end-date").value,
    areas: sql.includes("$areas") ? selectedAreas : []
  }));
  const keys = requests.map(request => JSON.stringify(request));
  instance.controller?.abort();
  const controller = (instance.controller = new AbortController());
  if (!keys.every(key => resultCache.has(key))) setLoading(instance, true);

  try {
    const results = await Promise.all(
      requests.map((request, i) => resultCache.get(keys[i]) || fetchQuery(request, controller.signal))
    );
    results.forEach((data, i) => rememberResult(keys[i], data));
    const ms = results.reduce((total, data) => total + data.duration_ms, 0);
    const rows = results.reduce((total, data) => total + data.row_count, 0);
    document.getElementById(`timing-${widgetId}`).textContent = `${Math.round(ms * 100) / 100}ms (${rows}r)`;
    await renderWidgetContent(instance, instance.spec.type === "panels" ? results : results[0], bodyEl);
  } catch (err) {
    if (err.name === "AbortError") return;
    disposeWidgetContent(instance);
    bodyEl.innerHTML = `<div class="card-error">Error: ${escapeHtml(err.message)}</div>`;
  } finally {
    if (instance.controller === controller) {
      instance.controller = null;
      setLoading(instance, false);
    }
  }
}

async function fetchQuery(request, signal) {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Query error");
  }
  return res.json();
}

function rememberResult(key, data) {
  resultCache.delete(key); // re-insert as most recently used
  resultCache.set(key, data);
  if (resultCache.size > RESULT_CACHE_SIZE) resultCache.delete(resultCache.keys().next().value);
}

// The card keeps its current content, dimmed under a progress bar, until the new result arrives.
function setLoading(instance, loading) {
  instance.dom.classList.toggle("is-loading", loading);
  if (loading) document.getElementById(`timing-${instance.spec.id}`).textContent = "refreshing…";
  const total = widgetInstances.size;
  const pending = [...widgetInstances.values()].filter(i => i.dom.classList.contains("is-loading")).length;
  const status = document.getElementById("refresh-status");
  status.textContent = pending ? `Refreshing ${total - pending}/${total}` : "";
  status.classList.toggle("active", pending > 0);
}

const RENDERERS = {
  area_map: renderAreaMap,
  panels: renderPanels,
  kpi_cards: renderKpiCards,
  stacked_area: (instance, result, container) => renderTimeSeries(instance, result, container, { stacked: true }),
  line: (instance, result, container) => renderTimeSeries(instance, result, container, { stacked: false }),
  bar: renderBarChart,
  donut: renderDonutChart,
  table: renderTable
};

function disposeWidgetContent(instance) {
  instance.chart?.destroy();
  instance.chart = null;
  instance.charts.forEach(chart => chart.destroy());
  instance.charts = [];
  instance.mapResize?.disconnect();
  instance.map?.remove();
  instance.map = null;
}

async function renderWidgetContent(instance, queryResult, container) {
  if (instance.spec.type !== "area_map") disposeWidgetContent(instance); // the map keeps its view
  if (instance.spec.type !== "panels" && !queryResult.rows.length) {
    container.innerHTML = emptyMessage(instance.spec.config);
    return;
  }
  const render = RENDERERS[instance.spec.type];
  if (render) await render(instance, queryResult, container);
}

function emptyMessage(config) {
  return `<div class="card-message">${escapeHtml(config.empty_message || "No data for the selected zones and dates")}</div>`;
}

function createCanvasContext(container) {
  container.innerHTML = `<canvas></canvas>`;
  return container.querySelector("canvas").getContext("2d");
}

function axisTitle(text) {
  return { display: true, text, color: AXIS_TITLE_COLOR, font: { size: 10 } };
}

function columnValues(result, column, fallback) {
  const idx = result.columns.indexOf(column);
  return result.rows.map(row => (idx !== -1 ? row[idx] : fallback));
}

function formatTimeLabel(isoTimestamp, daily) {
  if (!isoTimestamp) return "";
  return daily ? isoTimestamp.substring(0, 10) : isoTimestamp.substring(5, 16).replace("T", " "); // MM-DD HH:MM
}

function rowObjects(result) {
  return result.rows.map(row => Object.fromEntries(result.columns.map((col, idx) => [col, row[idx]])));
}

// Long rows (time, series, value) -> the sorted times, and one series per distinct value of the series
// column, in order of first appearance.
function pivotSeries(result, timeColumn, seriesColumn, valueColumn) {
  const [t, s, v] = [timeColumn, seriesColumn, valueColumn].map(column => result.columns.indexOf(column));
  const times = [...new Set(result.rows.map(row => row[t]))].sort();
  const bySeries = new Map();
  result.rows.forEach(row => {
    if (row[s] === null) return; // a time slot without data
    if (!bySeries.has(row[s])) bySeries.set(row[s], new Map());
    bySeries.get(row[s]).set(row[t], row[v]);
  });
  const series = [...bySeries].map(([label, values]) => ({ label, data: times.map(time => values.get(time) ?? null) }));
  return { times, series };
}

function renderKpiCards(instance, result, container) {
  const metrics = instance.spec.config.metrics || [];
  const row = result.rows[0] || [];
  const values = Object.fromEntries(result.columns.map((col, idx) => [col, row[idx]]));

  const boxes = metrics.map(metric => {
    const value = values[metric.key] !== undefined ? values[metric.key] : "--";
    const formatted = typeof value === "number" ? value.toLocaleString() : value;
    return `
      <div class="kpi-box">
        <div class="kpi-label-row">
          <span class="kpi-label">${escapeHtml(metric.label)}</span>
          ${metric.badge ? `<span class="kpi-badge">${escapeHtml(metric.badge)}</span>` : ""}
        </div>
        <div class="kpi-value-row">
          <span class="kpi-value">${escapeHtml(formatted)}</span>
          <span class="kpi-unit">${escapeHtml(metric.unit)}</span>
        </div>
      </div>
    `;
  });
  container.innerHTML = `<div class="kpi-container">${boxes.join("")}</div>`;
}

function stackedAreaStyle(series) {
  const color = window.EnergyPalette.resolve(series.color) || window.EnergyPalette.getFuelColor(series.label);
  return { backgroundColor: color, borderColor: color, borderWidth: 1, fill: true, tension: 0.2 };
}

function lineStyle(series) {
  return {
    borderColor: window.EnergyPalette.resolve(series.color) || DEFAULT_LINE_COLOR,
    backgroundColor: window.EnergyPalette.resolve(series.color) || DEFAULT_LINE_COLOR,
    borderWidth: series.borderWidth || 2,
    borderDash: series.borderDash || [],
    fill: false,
    tension: 0.1
  };
}

// Series named in the config, or (with `series_column`) one per distinct value of that column; line
// colours then follow first appearance, which widget SQL orders by selection, and stacked areas take
// their fuel's colour.
function timeSeriesData(config, result, stacked) {
  const timeColumn = config.time_column || result.columns[0];
  if (!config.series_column) {
    const series = (config.series || []).map(spec => ({ ...spec, data: columnValues(result, spec.column, null) }));
    return { times: columnValues(result, timeColumn, ""), series };
  }
  const { times, series } = pivotSeries(result, timeColumn, config.series_column, config.value_column);
  const palette = window.EnergyPalette.series;
  return { times, series: stacked ? series : series.map((s, idx) => ({ ...s, color: palette[idx] })) };
}

// Per time slot: "ok", "partial" (some expected zones do not report) or "missing" (no value), from the
// query's coverage columns (zones_reporting, zones_expected, zones_missing) where it has them.
function timeSeriesCoverage(result, timeColumn, times, series) {
  const [t, reporting, expected, missing] = [timeColumn, "zones_reporting", "zones_expected", "zones_missing"].map(
    column => result.columns.indexOf(column)
  );
  const byTime = new Map(reporting === -1 ? [] : result.rows.map(row => [row[t], row]));
  return times.map((time, i) => {
    const row = byTime.get(time);
    const empty = series.every(s => s.data[i] === null || s.data[i] === undefined);
    if (!row) return { state: empty ? "missing" : "ok" };
    const state = empty || row[reporting] === 0 ? "missing" : row[reporting] < row[expected] ? "partial" : "ok";
    return { state, reporting: row[reporting], expected: row[expected], missing: row[missing] };
  });
}

// Grey behind the slots that are partial or missing, between the first and last slot with data: a trailing
// slot not yet published is simply empty.
const coverageShading = {
  id: "coverageShading",
  beforeDatasetsDraw(chart, args, options) {
    const coverage = options.coverage || [];
    const populated = coverage.map((c, i) => (c.state === "missing" ? -1 : i)).filter(i => i !== -1);
    if (!populated.length) return;
    const [first, last] = [populated[0], populated[populated.length - 1]];
    const { ctx, chartArea, scales } = chart;
    const step = coverage.length > 1 ? scales.x.getPixelForValue(1) - scales.x.getPixelForValue(0) : chartArea.width;
    ctx.save();
    for (let i = first; i <= last; i++) {
      const fill = COVERAGE_FILL[coverage[i].state];
      if (!fill) continue;
      ctx.fillStyle = fill;
      const x = scales.x.getPixelForValue(i) - step / 2;
      ctx.fillRect(Math.max(x, chartArea.left), chartArea.top, step, chartArea.height);
    }
    ctx.restore();
  }
};

function coverageFooter(coverage) {
  return items => {
    const slot = coverage[items[0]?.dataIndex];
    if (!slot || slot.state === "ok") return "";
    if (slot.state === "missing") return "No data";
    const names = (slot.missing || "").length > 60 ? `${slot.missing.slice(0, 57)}...` : slot.missing;
    return `${slot.expected - slot.reporting} of ${slot.expected} zones missing: ${names}`;
  };
}

// Dataset styles: fuels for stacked areas, palette or configured colours for lines; a line may fill to
// another (spread, shaded by its sign), to zero, or form a min-max band with another.
function timeSeriesDatasets(config, series, stacked) {
  const index = Object.fromEntries(series.map((s, i) => [s.column || s.label, i]));
  return series.map(s => {
    const dataset = { label: s.label, data: s.data, pointRadius: 0, ...(stacked ? stackedAreaStyle(s) : lineStyle(s)) };
    if (s.fill_to && config.spread_fill) dataset.fill = { target: index[s.fill_to], ...config.spread_fill };
    if (config.fill_origin) dataset.fill = { target: "origin", ...config.fill_origin };
    if (config.band && [config.band.lower, config.band.upper].includes(s.label)) {
      Object.assign(dataset, { borderColor: BAND_COLOR, borderWidth: 1, backgroundColor: BAND_COLOR, fill: false });
      if (s.label === config.band.upper) dataset.fill = { target: index[config.band.lower] };
    }
    return dataset;
  });
}

// A time-series chart in `container`, or a message when there is nothing to draw; returns the chart.
function buildTimeSeriesChart(config, result, container, { stacked, xTicks = true, onHover } = {}) {
  if (!result.rows.length) {
    container.innerHTML = emptyMessage(config);
    return null;
  }
  const timeColumn = config.time_column || result.columns[0];
  const { times, series } = timeSeriesData(config, result, stacked);
  if (config.max_series && series.length > config.max_series) {
    container.innerHTML = `<div class="card-message">Select up to ${config.max_series} zones to compare (${series.length} have data)</div>`;
    return null;
  }
  const coverage = timeSeriesCoverage(result, timeColumn, times, series);
  const daily = times.every(time => String(time).endsWith("T00:00:00"));
  return new Chart(createCanvasContext(container), {
    type: "line",
    data: { labels: times.map(time => formatTimeLabel(time, daily)), datasets: timeSeriesDatasets(config, series, stacked) },
    plugins: [coverageShading],
    options: {
      interaction: { mode: "index", intersect: false },
      onHover,
      plugins: {
        coverageShading: { coverage },
        tooltip: { callbacks: { footer: coverageFooter(coverage) } },
        legend: { align: "end", labels: { generateLabels: chart => legendLabels(chart, config) } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { display: xTicks, maxTicksLimit: 8, maxRotation: 0 } },
        y: { stacked, title: axisTitle(config.y_title || "MW") }
      }
    }
  });
}

// A band shows once in the legend, as "lower-upper".
function legendLabels(chart, config) {
  const labels = Chart.defaults.plugins.legend.labels.generateLabels(chart);
  if (!config.band) return labels;
  return labels
    .filter(label => label.text !== config.band.lower)
    .map(label => (label.text === config.band.upper ? { ...label, text: `${config.band.lower}-${config.band.upper}` } : label));
}

function renderTimeSeries(instance, result, container, { stacked }) {
  instance.chart = buildTimeSeriesChart(instance.spec.config, result, container, { stacked });
}

// Panels: the visible panels' charts stacked on one time axis (ticks on the bottom one), hovering one
// shows the same slot in all.
function renderPanels(instance, results, container) {
  const panels = instance.spec.panels.filter(panel => instance.visiblePanels.includes(panel.id));
  if (!panels.length) {
    container.innerHTML = `<div class="card-message">Choose panels in the card header</div>`;
    return;
  }
  container.classList.add("card-body-panels");
  container.innerHTML = `
    ${panels
      .map(
        panel => `<div class="panel">
          <div class="panel-title" title="${escapeHtml(panel.description)}">${escapeHtml(panel.title)}</div>
          <div class="panel-chart"></div>
        </div>`
      )
      .join("")}
    <div class="panel-key">
      <span class="panel-key-swatch partial"></span>some selected zones missing
      <span class="panel-key-swatch missing"></span>no data
    </div>`;
  const onHover = (event, elements, chart) => {
    const points = event.type === "mouseout" ? [] : chart.getElementsAtEventForMode(event, "index", { intersect: false }, false);
    syncPanelHover(instance.charts, chart, points.length ? points[0].index : null);
  };
  const charts = container.querySelectorAll(".panel-chart");
  instance.charts = panels
    .map((panel, i) =>
      buildTimeSeriesChart(panel.config, results[i], charts[i], {
        stacked: panel.type === "stacked_area",
        xTicks: i === panels.length - 1,
        onHover
      })
    )
    .filter(Boolean);
}

function syncPanelHover(charts, source, index) {
  charts
    .filter(chart => chart !== source)
    .forEach(chart => {
      const active =
        index === null || index >= chart.data.labels.length
          ? []
          : chart.data.datasets.map((dataset, datasetIndex) => ({ datasetIndex, index }));
      chart.setActiveElements(active);
      chart.tooltip.setActiveElements(active, { x: 0, y: 0 });
      chart.update("none");
    });
}

function renderBarChart(instance, result, container) {
  const config = instance.spec.config;
  const prefix = config.x_label_prefix || "";
  const labels = columnValues(result, config.x_column || result.columns[0], "").map(x => `${prefix}${x}`);
  const data = columnValues(result, config.y_column || result.columns[1], 0);
  const positive = window.EnergyPalette.resolve(config.color_positive) || window.EnergyPalette.DELTA_POSITIVE;
  const negative = window.EnergyPalette.resolve(config.color_negative) || window.EnergyPalette.DELTA_NEGATIVE;

  instance.chart = new Chart(createCanvasContext(container), {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: instance.spec.title,
          data,
          backgroundColor: data.map(value => (value >= 0 ? positive : negative)),
          borderRadius: 2
        }
      ]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 24 } },
        y: { title: axisTitle(config.y_title || "MW") }
      }
    }
  });
}

function renderDonutChart(instance, result, container) {
  const config = instance.spec.config;
  const labels = columnValues(result, config.label_column || result.columns[0], "");
  const data = columnValues(result, config.value_column || result.columns[1], 0);

  instance.chart = new Chart(createCanvasContext(container), {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: labels.map(label => window.EnergyPalette.getFuelColor(label)),
          borderColor: CARD_BACKGROUND,
          borderWidth: 2
        }
      ]
    },
    options: {
      cutout: "70%",
      plugins: {
        legend: {
          position: "right",
          labels: { boxWidth: 8, font: { size: 9 } }
        }
      }
    }
  });
}

function renderTable(instance, result, container) {
  const columns = instance.spec.config.columns || result.columns.map(key => ({ key, label: key }));
  const indices = columns.map(column => result.columns.indexOf(column.key));

  // text columns align left, numbers right
  const text = indices.map(idx => result.rows.some(row => typeof row[idx] === "string"));
  const header = columns.map((column, i) => `<th class="${text[i] ? "text" : ""}">${escapeHtml(column.label)}</th>`).join("");
  const body = result.rows
    .map(row => {
      const cells = indices.map((idx, i) => {
        const value = idx !== -1 ? row[idx] : "";
        const formatted = typeof value === "number" ? value.toLocaleString() : value || "--";
        return `<td class="${text[i] ? "text" : ""}">${escapeHtml(formatted)}</td>`;
      });
      return `<tr>${cells.join("")}</tr>`;
    })
    .join("");
  container.innerHTML = `<table class="analyst-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

// Zone map: every zone shaded by the chosen metric on a one-hue ramp, selected zones outlined; a click
// adds or removes the zone from the shared filter. The map persists across refreshes, keeping its view.
async function renderAreaMap(instance, result, container) {
  instance.mapRows = new Map(rowObjects(result).map(row => [row[instance.spec.config.area_column], row]));
  if (!instance.map) await createAreaMap(instance, container);
  styleZones(instance);
}

async function loadZonesGeojson() {
  if (!zonesGeojson) {
    const res = await fetch(ZONES_GEOJSON_URL);
    if (!res.ok) throw new Error(`zone shapes: HTTP ${res.status}`);
    zonesGeojson = await res.json();
  }
  return zonesGeojson;
}

async function createAreaMap(instance, container) {
  const metrics = instance.spec.config.metrics || [];
  instance.metric = instance.metric || metrics[0]?.key;
  container.classList.add("card-body-flush");
  container.innerHTML = `
    <div class="zone-map"></div>
    <select class="input-terminal zone-map-metric" title="Shade zones by">
      ${metrics.map(m => `<option value="${escapeHtml(m.key)}">${escapeHtml(m.label)}</option>`).join("")}
    </select>
    <div class="zone-map-legend"></div>
  `;
  const select = container.querySelector(".zone-map-metric");
  select.value = instance.metric;
  select.addEventListener("change", () => {
    instance.metric = select.value;
    styleZones(instance);
  });

  instance.map = L.map(container.querySelector(".zone-map"), {
    zoomSnap: 0.25,
    attributionControl: true,
    worldCopyJump: false
  });
  instance.map.attributionControl.setPrefix(false).addAttribution("Zones: entsoe-py, Natural Earth");
  instance.zoneLayer = L.geoJSON(await loadZonesGeojson(), {
    onEachFeature: (feature, layer) => {
      const code = feature.properties.area_eic_code;
      layer.on("click", () => toggleArea(code));
      layer.on("mouseover", () => layer.setStyle({ weight: 2.5 }).bringToFront());
      layer.on("mouseout", () => styleZones(instance));
      layer.bindTooltip(() => zoneTooltip(instance, code), { sticky: true, className: "zone-tooltip" });
    }
  }).addTo(instance.map);
  // Europe fills the card at whatever size GridStack gives it, now or after a resize
  const fit = () => {
    instance.map?.invalidateSize();
    instance.map?.fitBounds(instance.zoneLayer.getBounds(), { padding: [4, 4] });
  };
  fit();
  instance.mapResize = new ResizeObserver(fit);
  instance.mapResize.observe(container.querySelector(".zone-map"));
}

function zoneTooltip(instance, code) {
  const row = instance.mapRows.get(code);
  const name = zoneNames.get(code) || code;
  if (!row) return `<strong>${escapeHtml(name)}</strong><br><span class="zone-tooltip-dim">No data</span>`;
  const values = (instance.spec.config.metrics || []).map(metric => {
    const value = row[metric.key];
    const formatted = value === null || value === undefined ? "--" : `${value.toLocaleString()} ${metric.unit || ""}`;
    return `<div class="zone-tooltip-row"><span>${escapeHtml(metric.label)}</span><span>${escapeHtml(formatted)}</span></div>`;
  });
  const selected = selectedAreas.includes(code) ? "click to remove" : "click to add";
  return `<strong>${escapeHtml(name)}</strong> <span class="zone-tooltip-dim">${escapeHtml(row.name || "")}</span>
    ${values.join("")}<div class="zone-tooltip-dim">${selected}</div>`;
}

function styleZones(instance) {
  if (!instance.zoneLayer) return;
  const values = [...instance.mapRows.values()].map(row => row[instance.metric]).filter(v => typeof v === "number");
  const [min, max] = [Math.min(...values), Math.max(...values)];
  const theme = window.EnergyPalette.map;
  instance.zoneLayer.eachLayer(layer => {
    const code = layer.feature.properties.area_eic_code;
    const value = instance.mapRows.get(code)?.[instance.metric];
    const selected = selectedAreas.includes(code);
    layer.setStyle({
      fillColor: typeof value === "number" ? rampColor((value - min) / (max - min || 1)) : theme.noData,
      fillOpacity: 1,
      color: selected ? theme.selected : CARD_BACKGROUND,
      weight: selected ? 2.5 : 1
    });
    if (selected) layer.bringToFront();
  });
  const metric = (instance.spec.config.metrics || []).find(m => m.key === instance.metric) || {};
  const legend = instance.dom.querySelector(".zone-map-legend");
  legend.innerHTML = values.length
    ? `<span>${escapeHtml(min.toLocaleString())}</span>
       <span class="zone-map-ramp" style="background: linear-gradient(90deg, ${theme.ramp.join(", ")})"></span>
       <span>${escapeHtml(max.toLocaleString())} ${escapeHtml(metric.unit || "")}</span>`
    : `<span>No ${escapeHtml(metric.label || "data")} for these dates</span>`;
}

// Linear interpolation along the ramp's stops, t in [0, 1].
function rampColor(t) {
  const ramp = window.EnergyPalette.map.ramp.map(hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)));
  const position = Math.min(Math.max(t, 0), 1) * (ramp.length - 1);
  const [low, high] = [ramp[Math.floor(position)], ramp[Math.ceil(position)]];
  const mix = low.map((channel, i) => Math.round(channel + (high[i] - channel) * (position - Math.floor(position))));
  return `rgb(${mix.join(", ")})`;
}
