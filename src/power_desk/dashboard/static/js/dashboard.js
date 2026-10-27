/**
 * Power Desk — Minimalist Grid & Widget Manager using GridStack.js and Chart.js
 */

const LAYOUT_STORAGE_KEY = "power_desk_layout";
const FALLBACK_DATE_RANGE = { start_date: "2024-03-01", end_date: "2024-03-07" }; // the seed week
const AXIS_TITLE_COLOR = "#64748b";
const DEFAULT_LINE_COLOR = "#38bdf8";
const CARD_BACKGROUND = "#0d1322";

let grid = null;
const widgetInstances = new Map(); // widgetId -> { spec, chart, dom }

function showDashboardError(message) {
  const gridEl = document.querySelector(".grid-stack");
  if (gridEl) {
    gridEl.insertAdjacentHTML("beforebegin", `<div class="card-error dashboard-error">${escapeHtml(message)}</div>`);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  initGrid();
  await loadFilterOptions();
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

function saveGridLayout() {
  const layout = grid.save(false);
  localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout));
}

function loadSavedLayout() {
  const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function resetGridLayout() {
  localStorage.removeItem(LAYOUT_STORAGE_KEY);
  window.location.reload();
}

async function loadFilterOptions() {
  try {
    const res = await fetch("/api/filters");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const startInput = document.getElementById("filter-start-date");
    const endInput = document.getElementById("filter-end-date");
    if (startInput && !startInput.value) startInput.value = data.min_date || FALLBACK_DATE_RANGE.start_date;
    if (endInput && !endInput.value) endInput.value = data.max_date || FALLBACK_DATE_RANGE.end_date;

    const tableBadge = document.getElementById("warehouse-stats");
    if (tableBadge && data.table_counts) {
      tableBadge.textContent = `${data.table_counts.bmrs__fuelinst || 0} rows`;
    }
  } catch (err) {
    console.warn("Failed to load filter options:", err);
    showDashboardError(`Filter options unavailable: ${err.message}`);
  }
}

function setupFilterEvents() {
  const applyBtn = document.getElementById("btn-apply-filters");
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      refreshAllWidgets();
    });
  }

  const resetLayoutBtn = document.getElementById("btn-reset-layout");
  if (resetLayoutBtn) {
    resetLayoutBtn.addEventListener("click", resetGridLayout);
  }

  const lineageBtn = document.getElementById("btn-open-lineage");
  if (lineageBtn) {
    lineageBtn.addEventListener("click", openLineageModal);
  }

  const closeLineageBtn = document.getElementById("btn-close-lineage");
  if (closeLineageBtn) {
    closeLineageBtn.addEventListener("click", closeLineageModal);
  }
}

async function loadAndRenderWidgets() {
  try {
    const res = await fetch("/api/widgets");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const widgets = await res.json();
    const savedLayout = loadSavedLayout();

    for (const w of widgets) {
      // Apply saved position if present
      let pos = w.grid;
      if (savedLayout) {
        const savedItem = savedLayout.find(i => i.id === w.id);
        if (savedItem) {
          pos = {
            x: savedItem.x,
            y: savedItem.y,
            w: savedItem.w,
            h: savedItem.h
          };
        }
      }
      createWidgetCard(w, pos);
    }

    // Trigger initial data load for all widgets
    refreshAllWidgets();
  } catch (err) {
    console.error("Failed to load widgets:", err);
    showDashboardError(`Widgets unavailable: ${err.message}`);
  }
}

function createWidgetCard(spec, pos) {
  const cardId = `widget-${spec.id}`;
  const el = document.createElement("div");
  el.className = "grid-stack-item";
  el.id = cardId;
  el.setAttribute("gs-id", spec.id);
  el.setAttribute("gs-x", pos.x || 0);
  el.setAttribute("gs-y", pos.y || 0);
  el.setAttribute("gs-w", pos.w || 6);
  el.setAttribute("gs-h", pos.h || 4);
  el.setAttribute("gs-min-w", pos.minW || 3);
  el.setAttribute("gs-min-h", pos.minH || 2);

  el.innerHTML = `
    <div class="grid-stack-item-content">
      <div class="card-header">
        <div class="card-title">
          <span>${escapeHtml(spec.title)}</span>
          <span class="card-timing" id="timing-${escapeHtml(spec.id)}">-- ms</span>
        </div>
        <div class="card-actions">
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
  widgetInstances.set(spec.id, { spec: { ...spec, config: spec.config || {} }, chart: null, dom: el });
}

function getFilterValues() {
  const startInput = document.getElementById("filter-start-date");
  const endInput = document.getElementById("filter-end-date");
  return {
    start_date: startInput ? startInput.value : FALLBACK_DATE_RANGE.start_date,
    end_date: endInput ? endInput.value : FALLBACK_DATE_RANGE.end_date
  };
}

async function refreshAllWidgets() {
  const ids = Array.from(widgetInstances.keys());
  await Promise.all(ids.map(id => refreshWidget(id)));
}

async function refreshWidget(widgetId) {
  const instance = widgetInstances.get(widgetId);
  if (!instance) return;

  const { spec } = instance;
  const filters = getFilterValues();
  const bodyEl = document.getElementById(`body-${widgetId}`);
  const timingEl = document.getElementById(`timing-${widgetId}`);

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sql: spec.sql,
        start_date: filters.start_date,
        end_date: filters.end_date
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Query error");
    }

    const data = await res.json();
    if (timingEl) timingEl.textContent = `${data.duration_ms}ms (${data.row_count}r)`;

    renderWidgetContent(instance, data, bodyEl);
  } catch (err) {
    if (bodyEl) {
      bodyEl.innerHTML = `<div class="card-error">Error: ${escapeHtml(err.message)}</div>`;
    }
  }
}

const RENDERERS = {
  kpi_cards: renderKpiCards,
  stacked_area: (instance, result, container) => renderTimeSeries(instance, result, container, { stacked: true }),
  line: (instance, result, container) => renderTimeSeries(instance, result, container, { stacked: false }),
  bar: renderBarChart,
  donut: renderDonutChart,
  table: renderTable
};

function renderWidgetContent(instance, queryResult, container) {
  if (instance.chart) {
    instance.chart.destroy();
    instance.chart = null;
  }
  const render = RENDERERS[instance.spec.type];
  if (render) render(instance, queryResult, container);
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

function formatTimeLabel(isoTimestamp) {
  return isoTimestamp ? isoTimestamp.substring(5, 16).replace("T", " ") : ""; // MM-DD HH:MM
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
    borderWidth: series.borderWidth || 2,
    borderDash: series.borderDash || [],
    fill: false,
    tension: 0.1
  };
}

function renderTimeSeries(instance, result, container, { stacked }) {
  const config = instance.spec.config;
  const labels = columnValues(result, config.time_column || result.columns[0], "").map(formatTimeLabel);
  const datasets = (config.series || []).map(series => ({
    label: series.label,
    data: columnValues(result, series.column, 0),
    pointRadius: 0,
    ...(stacked ? stackedAreaStyle(series) : lineStyle(series))
  }));

  instance.chart = new Chart(createCanvasContext(container), {
    type: "line",
    data: { labels, datasets },
    options: {
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
        y: { stacked, title: axisTitle(config.y_title || "MW") }
      }
    }
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

  const header = columns.map(column => `<th>${escapeHtml(column.label)}</th>`).join("");
  const body = result.rows
    .map(row => {
      const cells = indices.map(idx => {
        const value = idx !== -1 ? row[idx] : "";
        const formatted = typeof value === "number" ? value.toLocaleString() : value || "--";
        return `<td>${escapeHtml(formatted)}</td>`;
      });
      return `<tr>${cells.join("")}</tr>`;
    })
    .join("");
  container.innerHTML = `<table class="analyst-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}
