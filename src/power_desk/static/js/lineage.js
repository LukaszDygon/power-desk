/**
 * Open-Source Data Lineage DAG using Cytoscape.js and Dagre Layout
 */

let cyLineage = null;

async function initLineageGraph() {
  const container = document.getElementById("cy-lineage");
  if (!container) return;

  try {
    const res = await fetch("/api/lineage");
    const data = await res.json();

    const elements = [];

    // Map Nodes
    data.nodes.forEach(node => {
      elements.push({
        group: "nodes",
        data: {
          id: node.id,
          label: node.label,
          type: node.type,
          desc: node.desc || ""
        }
      });
    });

    // Map Edges
    data.edges.forEach((edge, idx) => {
      elements.push({
        group: "edges",
        data: {
          id: `edge_${idx}`,
          source: edge.source,
          target: edge.target,
          label: edge.label || ""
        }
      });
    });

    // Initialize Cytoscape
    cyLineage = cytoscape({
      container: container,
      elements: elements,
      layout: {
        name: "dagre",
        rankDir: "LR",
        nodeSep: 40,
        rankSep: 80,
        edgeSep: 20
      },
      style: [
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
          style: {
            "border-color": "#10b981",
            "color": "#34d399",
            "background-color": "rgba(16, 185, 129, 0.08)"
          }
        },
        {
          selector: 'node[type = "raw_table"]',
          style: {
            "border-color": "#f59e0b",
            "color": "#fbbf24",
            "background-color": "rgba(245, 158, 11, 0.08)"
          }
        },
        {
          selector: 'node[type = "ods_view"]',
          style: {
            "border-color": "#06b6d4",
            "color": "#22d3ee",
            "background-color": "rgba(6, 182, 212, 0.08)"
          }
        },
        {
          selector: 'node[type = "mart_view"]',
          style: {
            "border-color": "#818cf8",
            "color": "#a5b4fc",
            "background-color": "rgba(129, 140, 248, 0.08)"
          }
        },
        {
          selector: 'node[type = "widget"]',
          style: {
            "border-color": "#f43f5e",
            "color": "#fb7185",
            "background-color": "rgba(244, 63, 94, 0.08)"
          }
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
          style: {
            "border-width": 3,
            "border-color": "#fff",
            "shadow-blur": 10,
            "shadow-color": "rgba(255, 255, 255, 0.4)"
          }
        }
      ]
    });

    // Node click inspector
    cyLineage.on("tap", "node", function(evt) {
      const node = evt.target;
      const details = document.getElementById("lineage-node-details");
      if (details) {
        details.innerHTML = `
          <h4>${node.data("label")}</h4>
          <p style="margin-bottom: 4px;"><span style="color:#64748b">Layer:</span> <code style="color:#38bdf8">${node.data("type")}</code></p>
          <p style="margin-bottom: 4px;"><span style="color:#64748b">Identifier:</span> <code>${node.data("id")}</code></p>
          <p style="color:#cbd5e1; margin-top: 6px;">${node.data("desc") || "No detailed description."}</p>
        `;
      }
    });

    cyLineage.fit(undefined, 30);
  } catch (err) {
    console.error("Failed to load lineage graph:", err);
  }
}

function openLineageModal() {
  const modal = document.getElementById("lineage-modal");
  if (modal) {
    modal.classList.add("open");
    setTimeout(() => {
      if (!cyLineage) {
        initLineageGraph();
      } else {
        cyLineage.resize();
        cyLineage.fit(undefined, 30);
      }
    }, 100);
  }
}

function closeLineageModal() {
  const modal = document.getElementById("lineage-modal");
  if (modal) {
    modal.classList.remove("open");
  }
}
