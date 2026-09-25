/**
 * Functional Energy Color System & Minimalist Analyst Chart Theme for Chart.js
 */

window.EnergyPalette = {
  WIND: "#00e5a3",
  SOLAR: "#f59e0b",
  NUCLEAR: "#818cf8",
  CCGT: "#f97316",
  BIOMASS: "#84cc16",
  HYDRO: "#0ea5e9",
  COAL: "#475569",
  IMPORTS: "#94a3b8",
  DEMAND_ACTUAL: "#f8fafc",
  DEMAND_FORECAST: "#c084fc",
  DELTA_POSITIVE: "#34d399",
  DELTA_NEGATIVE: "#f43f5e",

  getFuelColor: function(fuel) {
    if (!fuel) return "#94a3b8";
    const f = fuel.toUpperCase();
    if (f.includes("WIND")) return this.WIND;
    if (f.includes("SOLAR")) return this.SOLAR;
    if (f.includes("NUCLEAR")) return this.NUCLEAR;
    if (f.includes("CCGT") || f.includes("GAS")) return this.CCGT;
    if (f.includes("BIOMASS")) return this.BIOMASS;
    if (f.includes("HYD") || f.includes("PS")) return this.HYDRO;
    if (f.includes("COAL")) return this.COAL;
    if (f.includes("INT")) return this.IMPORTS;
    return "#94a3b8";
  }
};

// Configure Global Chart.js Defaults for Analyst Terminal
if (window.Chart) {
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.font.family = "'JetBrains Mono', monospace";
  Chart.defaults.font.size = 10;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.responsive = true;
  Chart.defaults.animation.duration = 200;

  // Crisp Tooltip
  Chart.defaults.plugins.tooltip.backgroundColor = "#080c14";
  Chart.defaults.plugins.tooltip.borderColor = "#334155";
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.titleColor = "#f8fafc";
  Chart.defaults.plugins.tooltip.bodyColor = "#cbd5e1";
  Chart.defaults.plugins.tooltip.padding = 8;
  Chart.defaults.plugins.tooltip.boxPadding = 4;
  Chart.defaults.plugins.tooltip.usePointStyle = true;
  Chart.defaults.plugins.tooltip.titleFont = {
    family: "'Cabinet Grotesk', sans-serif",
    size: 11,
    weight: "700"
  };
  Chart.defaults.plugins.tooltip.bodyFont = {
    family: "'JetBrains Mono', monospace",
    size: 10
  };

  // Subtle Legend
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.padding = 10;
  Chart.defaults.plugins.legend.labels.color = "#94a3b8";
  Chart.defaults.plugins.legend.labels.font = {
    family: "'JetBrains Mono', monospace",
    size: 10
  };

  // Minimal Grid Scales
  Chart.defaults.scale.grid.color = "rgba(30, 41, 59, 0.4)";
  Chart.defaults.scale.grid.tickColor = "rgba(30, 41, 59, 0.4)";
}
