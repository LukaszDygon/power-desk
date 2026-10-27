/**
 * Functional Energy Color System & Minimalist Analyst Chart Theme for Chart.js
 */

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// The colours are defined once, in dashboard.css (:root). Widget configs refer to them by these
// keys (e.g. "color": "WIND"); a config may also give any CSS colour.
const ENERGY_COLORS = {
  WIND: cssVar("--energy-wind"),
  SOLAR: cssVar("--energy-solar"),
  NUCLEAR: cssVar("--energy-nuclear"),
  CCGT: cssVar("--energy-gas"),
  BIOMASS: cssVar("--energy-biomass"),
  HYDRO: cssVar("--energy-hydro"),
  STORAGE: cssVar("--energy-storage"),
  COAL: cssVar("--energy-coal"),
  IMPORTS: cssVar("--energy-imports"),
  DEMAND_ACTUAL: cssVar("--energy-demand"),
  DEMAND_FORECAST: cssVar("--energy-forecast"),
  DELTA_POSITIVE: cssVar("--energy-delta-positive"),
  DELTA_NEGATIVE: cssVar("--energy-delta-negative")
};
const UNKNOWN_FUEL_COLOR = cssVar("--text-secondary");

window.EnergyPalette = {
  ...ENERGY_COLORS,

  // A palette key from ENERGY_COLORS, or the value itself as a CSS colour (undefined stays undefined).
  resolve: function(color) {
    return ENERGY_COLORS[color] || color;
  },

  // Colour for a fuel code or label from query results, e.g. "CCGT" or "Hydro / PS".
  getFuelColor: function(fuel) {
    if (!fuel) return UNKNOWN_FUEL_COLOR;
    const f = fuel.toUpperCase();
    if (f.includes("WIND")) return this.WIND;
    if (f.includes("SOLAR")) return this.SOLAR;
    if (f.includes("NUCLEAR")) return this.NUCLEAR;
    if (f.includes("CCGT") || f.includes("GAS")) return this.CCGT;
    if (f.includes("BIOMASS")) return this.BIOMASS;
    if (f.includes("HYD") || f.includes("PS")) return this.HYDRO;
    if (f.includes("COAL")) return this.COAL;
    if (f.includes("INT")) return this.IMPORTS;
    return UNKNOWN_FUEL_COLOR;
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
