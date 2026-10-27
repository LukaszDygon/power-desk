/**
 * Data lineage DAG (publisher -> raw table -> dbt models -> widget) using Cytoscape.js and the Dagre layout.
 */

const LINEAGE_FIT_PADDING = 30;
const MODAL_OPEN_DELAY_MS = 100; // let the modal lay out before Cytoscape measures its container
const LINEAGE_LAYOUT = { name: "dagre", rankDir: "LR", nodeSep: 40, rankSep: 80, edgeSep: 20 };

// Cytoscape stylesheet. Node `type`s come from /api/lineage (dashboard/lineage.py). Each layer is filled with a
// faint tint of its border colour: Cytoscape ignores the alpha of rgba() colours, hence `background-opacity`.
const LINEAGE_STYLE = [
  {
    selector: "node",
    style: {
      "background-color": "#0d1322",
      "border-width": 2,
      "border-color": "#475569",
      "label": "data(label)",
      "color": "#f8fafc",
      "font-family": "JetBrains Mono, monospace",
      "font-size": "10px",
      "text-valign": "center",
      "text-halign": "center",
      "padding": "12px",
      "shape": "round-rectangle",
      "width": "label",
      "height": "32px"
    }
  },
  {
    selector: 'node[type = "source"]',
    style: { "border-color": "#10b981", "color": "#34d399", "background-color": "#10b981", "background-opacity": 0.08 }
  },
  {
    selector: 'node[type = "raw_table"]',
    style: { "border-color": "#f59e0b", "color": "#fbbf24", "background-color": "#f59e0b", "background-opacity": 0.08 }
  },
  {
    selector: 'node[type = "staging_view"]',
    style: { "border-color": "#64748b", "color": "#94a3b8", "background-color": "#64748b", "background-opacity": 0.08 }
  },
  {
    selector: 'node[type = "ods_view"]',
    style: { "border-color": "#06b6d4", "color": "#22d3ee", "background-color": "#06b6d4", "background-opacity": 0.08 }
  },
  {
    selector: 'node[type = "mart_view"]',
    style: { "border-color": "#818cf8", "color": "#a5b4fc", "background-color": "#818cf8", "background-opacity": 0.08 }
  },
  {
    selector: 'node[type = "widget"]',
    style: { "border-color": "#f43f5e", "color": "#fb7185", "background-color": "#f43f5e", "background-opacity": 0.08 }
  },
  {
    selector: "edge",
    style: {
      "width": 1.5,
      "line-color": "#334155",
      "target-arrow-color": "#475569",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.8
    }
  },
  {
    selector: "node:selected",
    style: { "border-width": 3, "border-color": "#fff", "shadow-blur": 10, "shadow-color": "rgba(255, 255, 255, 0.4)" }
  }
];

let cyLineage = null;

function toCytoscapeElements(graph) {
  const nodes = graph.nodes.map(node => ({
    group: "nodes",
    data: { id: node.id, label: node.label, type: node.type, desc: node.desc || "" }
  }));
  const edges = graph.edges.map((edge, idx) => ({
    group: "edges",
    data: { id: `edge_${idx}`, source: edge.source, target: edge.target, label: edge.label || "" }
  }));
  return [...nodes, ...edges];
}

function showNodeDetails(node) {
  document.getElementById("lineage-node-details").innerHTML = `
    <h4>${escapeHtml(node.data("label"))}</h4>
    <p class="lineage-detail-row"><span class="lineage-detail-key">Layer:</span> <code class="lineage-detail-layer">${escapeHtml(node.data("type"))}</code></p>
    <p class="lineage-detail-row"><span class="lineage-detail-key">Identifier:</span> <code>${escapeHtml(node.data("id"))}</code></p>
    <p class="lineage-detail-desc">${escapeHtml(node.data("desc") || "No detailed description.")}</p>
  `;
}

async function initLineageGraph() {
  const container = document.getElementById("cy-lineage");
  try {
    const res = await fetch("/api/lineage");
    if (!res.ok) throw new Error(`lineage request failed (HTTP ${res.status})`);
    cyLineage = cytoscape({
      container,
      elements: toCytoscapeElements(await res.json()),
      layout: LINEAGE_LAYOUT,
      style: LINEAGE_STYLE
    });
    cyLineage.on("tap", "node", evt => showNodeDetails(evt.target));
    cyLineage.fit(undefined, LINEAGE_FIT_PADDING);
  } catch (err) {
    console.error("Failed to load lineage graph:", err);
    container.innerHTML = `<div class="card-error">Lineage unavailable: ${escapeHtml(err.message)}</div>`;
  }
}

function openLineageModal() {
  document.getElementById("lineage-modal").classList.add("open");
  setTimeout(() => {
    if (!cyLineage) {
      initLineageGraph();
    } else {
      cyLineage.resize();
      cyLineage.fit(undefined, LINEAGE_FIT_PADDING);
    }
  }, MODAL_OPEN_DELAY_MS);
}

function closeLineageModal() {
  document.getElementById("lineage-modal").classList.remove("open");
}
