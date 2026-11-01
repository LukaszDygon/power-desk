/**
 * Functional Energy Color System & Minimalist Analyst Chart Theme for Chart.js
 */

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// The colours are defined once, in dashboard.css (:root). Widget configs refer to them by these
// keys (e.g. "color": "WIND"); a config may also give any CSS colour. SERIES_* are the categorical
// slots, in fixed order, for series that are not fuels (zones, prices).
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
  DELTA_NEGATIVE: cssVar("--energy-delta-negative"),
  SERIES_1: cssVar("--series-1"),
  SERIES_2: cssVar("--series-2"),
  SERIES_3: cssVar("--series-3"),
  SERIES_4: cssVar("--series-4"),
  SERIES_5: cssVar("--series-5"),
  SERIES_6: cssVar("--series-6"),
  SERIES_7: cssVar("--series-7"),
  SERIES_8: cssVar("--series-8")
};
const UNKNOWN_FUEL_COLOR = cssVar("--text-secondary");

window.EnergyPalette = {
  ...ENERGY_COLORS,

  series: [1, 2, 3, 4, 5, 6, 7, 8].map(slot => ENERGY_COLORS[`SERIES_${slot}`]),

  // Zone map: a one-hue ramp from low (recedes into the dark card) to high, zones without data, selection.
  map: {
    ramp: [1, 2, 3, 4, 5].map(step => cssVar(`--map-ramp-${step}`)),
    noData: cssVar("--map-no-data"),
    selected: cssVar("--map-selected")
  },

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
    if (f.includes("BIO")) return this.BIOMASS;
    if (f.includes("HYD") || f.includes("PS")) return this.HYDRO;
    if (f.includes("STORAGE")) return this.STORAGE;
    if (f.includes("COAL")) return this.COAL;
    if (f.includes("INT")) return this.IMPORTS;
    return UNKNOWN_FUEL_COLOR;
  }
};

Chart.defaults.color = "#94a3b8";
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size = 10;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.responsive = true;
Chart.defaults.animation.duration = 200;

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

Chart.defaults.plugins.legend.labels.boxWidth = 10;
Chart.defaults.plugins.legend.labels.boxHeight = 10;
Chart.defaults.plugins.legend.labels.padding = 10;
Chart.defaults.plugins.legend.labels.color = "#94a3b8";
Chart.defaults.plugins.legend.labels.font = {
  family: "'JetBrains Mono', monospace",
  size: 10
};

Chart.defaults.scale.grid.color = "rgba(30, 41, 59, 0.4)";
Chart.defaults.scale.grid.tickColor = "rgba(30, 41, 59, 0.4)";
