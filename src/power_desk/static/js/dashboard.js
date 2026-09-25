/**
 * Power Desk — Minimalist Grid & Widget Manager using GridStack.js and Chart.js
 */

let grid = null;
const widgetInstances = new Map(); // widgetId -> { spec, chart, dom }

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

  // Save layout changes to localStorage
  grid.on("change", (event, items) => {
    saveGridLayout();
  });
}

function saveGridLayout() {
  const layout = grid.save(false);
  localStorage.setItem("power_desk_layout", JSON.stringify(layout));
}

function loadSavedLayout() {
  const raw = localStorage.getItem("power_desk_layout");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function resetGridLayout() {
  localStorage.removeItem("power_desk_layout");
  window.location.reload();
}

async function loadFilterOptions() {
  try {
    const res = await fetch("/api/filters");
    const data = await res.json();
    const startInput = document.getElementById("filter-start-date");
    const endInput = document.getElementById("filter-end-date");
    if (startInput && !startInput.value) startInput.value = data.min_date || "2024-03-01";
    if (endInput && !endInput.value) endInput.value = data.max_date || "2024-03-07";

    const tableBadge = document.getElementById("warehouse-stats");
    if (tableBadge && data.table_counts) {
      tableBadge.textContent = `${data.table_counts.raw_fuelinst || 0} rows`;
    }
  } catch (err) {
    console.warn("Failed to load filter options:", err);
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
          <span>${spec.title}</span>
          <span class="card-timing" id="timing-${spec.id}">-- ms</span>
        </div>
        <div class="card-actions">
          <button class="card-btn" title="Refresh Query" onclick="refreshWidget('${spec.id}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          </button>
        </div>
      </div>
      <div class="card-body" id="body-${spec.id}">
        <div style="display:flex;height:100%;align-items:center;justify-content:center;color:#64748b;font-family:'JetBrains Mono',monospace;font-size:11px;">
          Executing query...
        </div>
      </div>
    </div>
  `;

  grid.addWidget(el);
  widgetInstances.set(spec.id, { spec, chart: null, dom: el });
}

function getFilterValues() {
  const startInput = document.getElementById("filter-start-date");
  const endInput = document.getElementById("filter-end-date");
  return {
    start_date: startInput ? startInput.value : "2024-03-01",
    end_date: endInput ? endInput.value : "2024-03-07"
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
      bodyEl.innerHTML = `
        <div style="color:#f43f5e;font-family:'JetBrains Mono',monospace;font-size:11px;padding:8px;">
          Error: ${err.message}
        </div>
      `;
    }
  }
}

function renderWidgetContent(instance, queryResult, container) {
  const { spec } = instance;
  const { columns, rows } = queryResult;

  if (instance.chart) {
    instance.chart.destroy();
    instance.chart = null;
  }

  if (spec.type === "kpi_cards") {
    renderKpiCards(spec, queryResult, container);
  } else if (spec.type === "stacked_area") {
    renderStackedAreaChart(instance, queryResult, container);
  } else if (spec.type === "line") {
    renderLineChart(instance, queryResult, container);
  } else if (spec.type === "bar") {
    renderBarChart(instance, queryResult, container);
  } else if (spec.type === "donut") {
    renderDonutChart(instance, queryResult, container);
  } else if (spec.type === "table") {
    renderTable(spec, queryResult, container);
  }
}

function renderKpiCards(spec, result, container) {
  const metrics = (spec.config && spec.config.metrics) || [];
  const row = result.rows[0] || [];
  const colMap = {};
  result.columns.forEach((col, idx) => {
    colMap[col] = row[idx];
  });

  let html = `<div class="kpi-container">`;
  metrics.forEach(m => {
    const val = colMap[m.key] !== undefined ? colMap[m.key] : "--";
    const formatted = typeof val === "number" ? val.toLocaleString() : val;
    html += `
      <div class="kpi-box">
        <div class="kpi-label-row">
          <span class="kpi-label">${m.label}</span>
          ${m.badge ? `<span class="kpi-badge">${m.badge}</span>` : ""}
        </div>
        <div class="kpi-value-row">
          <span class="kpi-value">${formatted}</span>
          <span class="kpi-unit">${m.unit || ""}</span>
        </div>
      </div>
    `;
  });
  html += `</div>`;
  container.innerHTML = html;
}

function renderStackedAreaChart(instance, result, container) {
  container.innerHTML = `<canvas></canvas>`;
  const canvas = container.querySelector("canvas");
  const ctx = canvas.getContext("2d");

  const timeCol = instance.spec.config.time_column || result.columns[0];
  const timeIdx = result.columns.indexOf(timeCol);
  const labels = result.rows.map(r => {
    const dt = r[timeIdx];
    return dt ? dt.substring(5, 16).replace("T", " ") : "";
  });

  const series = instance.spec.config.series || [];
  const datasets = series.map(s => {
    const colIdx = result.columns.indexOf(s.column);
    const data = result.rows.map(r => (colIdx !== -1 ? r[colIdx] : 0));
    return {
      label: s.label,
      data: data,
      backgroundColor: s.color || window.EnergyPalette.getFuelColor(s.label),
      borderColor: s.color || window.EnergyPalette.getFuelColor(s.label),
      borderWidth: 1,
      fill: true,
      tension: 0.2,
      pointRadius: 0
    };
  });

  instance.chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: 12 }
        },
        y: {
          stacked: true,
          title: { display: true, text: "MW", color: "#64748b", font: { size: 10 } }
        }
      }
    }
  });
}

function renderLineChart(instance, result, container) {
  container.innerHTML = `<canvas></canvas>`;
  const canvas = container.querySelector("canvas");
  const ctx = canvas.getContext("2d");

  const timeCol = instance.spec.config.time_column || result.columns[0];
  const timeIdx = result.columns.indexOf(timeCol);
  const labels = result.rows.map(r => {
    const dt = r[timeIdx];
    return dt ? dt.substring(5, 16).replace("T", " ") : "";
  });

  const series = instance.spec.config.series || [];
  const datasets = series.map(s => {
    const colIdx = result.columns.indexOf(s.column);
    const data = result.rows.map(r => (colIdx !== -1 ? r[colIdx] : 0));
    return {
      label: s.label,
      data: data,
      borderColor: s.color || "#38bdf8",
      borderWidth: s.borderWidth || 2,
      borderDash: s.borderDash || [],
      fill: false,
      tension: 0.1,
      pointRadius: 0
    };
  });

  instance.chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: 12 }
        },
        y: {
          title: { display: true, text: "MW", color: "#64748b", font: { size: 10 } }
        }
      }
    }
  });
}

function renderBarChart(instance, result, container) {
  container.innerHTML = `<canvas></canvas>`;
  const canvas = container.querySelector("canvas");
  const ctx = canvas.getContext("2d");

  const xCol = instance.spec.config.x_column || result.columns[0];
  const yCol = instance.spec.config.y_column || result.columns[1];
  const xIdx = result.columns.indexOf(xCol);
  const yIdx = result.columns.indexOf(yCol);

  const labels = result.rows.map(r => `P${r[xIdx]}`);
  const data = result.rows.map(r => r[yIdx]);
  const colors = data.map(val => (val >= 0 ? window.EnergyPalette.DELTA_POSITIVE : window.EnergyPalette.DELTA_NEGATIVE));

  instance.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: instance.spec.title,
          data: data,
          backgroundColor: colors,
          borderRadius: 2
        }
      ]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 24 } },
        y: { title: { display: true, text: "Delta MW", color: "#64748b", font: { size: 10 } } }
      }
    }
  });
}

function renderDonutChart(instance, result, container) {
  container.innerHTML = `<canvas></canvas>`;
  const canvas = container.querySelector("canvas");
  const ctx = canvas.getContext("2d");

  const labelCol = instance.spec.config.label_column || result.columns[0];
  const valCol = instance.spec.config.value_column || result.columns[1];
  const labelIdx = result.columns.indexOf(labelCol);
  const valIdx = result.columns.indexOf(valCol);

  const labels = result.rows.map(r => r[labelIdx]);
  const data = result.rows.map(r => r[valIdx]);
  const colors = labels.map(l => window.EnergyPalette.getFuelColor(l));

  instance.chart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: data,
          backgroundColor: colors,
          borderColor: "#0d1322",
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

function renderTable(spec, result, container) {
  const cols = (spec.config && spec.config.columns) || result.columns.map(c => ({ key: c, label: c }));
  const colIndices = cols.map(c => result.columns.indexOf(c.key));

  let html = `<table class="analyst-table"><thead><tr>`;
  cols.forEach(c => {
    html += `<th>${c.label}</th>`;
  });
  html += `</tr></thead><tbody>`;

  result.rows.forEach(row => {
    html += `<tr>`;
    colIndices.forEach((idx, cIdx) => {
      const val = idx !== -1 ? row[idx] : "";
      const formatted = typeof val === "number" ? val.toLocaleString() : (val || "--");
      html += `<td>${formatted}</td>`;
    });
    html += `</tr>`;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;
}
