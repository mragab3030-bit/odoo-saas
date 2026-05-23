/* ===== Sidebar Toggle (mobile) ===== */
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebarOverlay');
const toggleBtn = document.getElementById('sidebarToggle');

function openSidebar() {
  sidebar && sidebar.classList.add('open');
  overlay && overlay.classList.add('open');
}

function closeSidebar() {
  sidebar && sidebar.classList.remove('open');
  overlay && overlay.classList.remove('open');
}

toggleBtn && toggleBtn.addEventListener('click', openSidebar);
overlay && overlay.addEventListener('click', closeSidebar);

/* ===== Active nav detection ===== */
document.querySelectorAll('.nav-item[data-path]').forEach(item => {
  const path = item.dataset.path;
  if (path && window.location.pathname.startsWith(path)) {
    item.classList.add('active');
  }
});

/* ===== Number formatting ===== */
function formatNumber(n, decimals = 0) {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(n);
}

function formatCurrency(n, symbol = '') {
  return symbol + formatNumber(n, 2);
}

/* ===== Chart defaults ===== */
if (window.Chart) {
  Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = '#64748b';
  Chart.defaults.plugins.legend.position = 'bottom';
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.padding = 16;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
}

const CHART_COLORS = [
  '#2563eb', '#22c55e', '#f59e0b', '#ef4444',
  '#06b6d4', '#a78bfa', '#ec4899', '#f97316',
];

/* ===== Build charts from data attributes ===== */
function buildChart(canvasId, type, data, options = {}) {
  const el = document.getElementById(canvasId);
  if (!el) return null;
  return new Chart(el.getContext('2d'), {
    type,
    data,
    options: {
      responsive: true,
      maintainAspectRatio: true,
      ...options,
    },
  });
}

function buildDonut(canvasId, chartData) {
  if (!chartData || !chartData.labels || !chartData.labels.length) return;
  buildChart(canvasId, 'doughnut', {
    labels: chartData.labels,
    datasets: [{
      data: chartData.values,
      backgroundColor: CHART_COLORS,
      borderWidth: 2,
      borderColor: '#fff',
      hoverBorderColor: '#fff',
    }],
  }, {
    cutout: '65%',
    plugins: {
      tooltip: {
        callbacks: {
          label: ctx => ` ${ctx.label}: ${formatNumber(ctx.raw)}`,
        },
      },
    },
  });
}

function buildBar(canvasId, chartData, yLabel = '', currency = false) {
  if (!chartData || !chartData.labels || !chartData.labels.length) return;
  buildChart(canvasId, 'bar', {
    labels: chartData.labels,
    datasets: [{
      label: yLabel,
      data: chartData.values,
      backgroundColor: CHART_COLORS[0] + 'cc',
      borderColor: CHART_COLORS[0],
      borderWidth: 1,
      borderRadius: 6,
    }],
  }, {
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => ` ${currency ? formatCurrency(ctx.raw) : formatNumber(ctx.raw)}`,
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: { color: '#f1f5f9' },
        ticks: {
          callback: v => currency ? formatCurrency(v) : formatNumber(v),
        },
      },
      x: { grid: { display: false } },
    },
  });
}

function buildHorizontalBar(canvasId, chartData) {
  if (!chartData || !chartData.labels || !chartData.labels.length) return;
  buildChart(canvasId, 'bar', {
    labels: chartData.labels,
    datasets: [{
      data: chartData.values,
      backgroundColor: CHART_COLORS,
      borderRadius: 4,
    }],
  }, {
    indexAxis: 'y',
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => ` ${formatCurrency(ctx.raw)}`,
        },
      },
    },
    scales: {
      x: {
        beginAtZero: true,
        grid: { color: '#f1f5f9' },
        ticks: { callback: v => formatCurrency(v) },
      },
      y: { grid: { display: false } },
    },
  });
}

/* ===== Export buttons loading state ===== */
document.querySelectorAll('a[data-export]').forEach(btn => {
  btn.addEventListener('click', function () {
    const original = this.innerHTML;
    this.innerHTML = '<span class="spinner" style="display:inline-block;vertical-align:middle;margin-right:6px"></span> Exporting…';
    setTimeout(() => { this.innerHTML = original; }, 4000);
  });
});

/* ===== Flash message auto-dismiss ===== */
document.querySelectorAll('.alert[data-dismiss]').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity .4s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 400);
  }, 4000);
});

/* ===== Date range defaults ===== */
document.querySelectorAll('input[type="date"][data-default-today]').forEach(el => {
  if (!el.value) el.value = new Date().toISOString().split('T')[0];
});

/* ===== Global refresh + auto-refresh ===== */
(function () {
  const INTERVAL_KEY = 'odooDash.refreshInterval';
  const VALID = ['0', '5', '15', '30'];

  const btn = document.getElementById('refreshBtn');
  const sel = document.getElementById('refreshInterval');
  const stamp = document.getElementById('refreshStamp');
  if (!btn) return;

  let autoTimer = null;

  function fmtTime(d) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function showStamp() {
    if (stamp) stamp.textContent = 'Last updated: ' + fmtTime(new Date());
  }

  function reloadNow() {
    btn.classList.add('is-spinning');
    btn.disabled = true;
    const url = new URL(window.location.href);
    url.searchParams.set('_t', Date.now().toString());
    window.location.href = url.toString();
  }

  // Manual refresh: re-probe the Odoo server for installed modules + edition
  // before reloading the page. Newly-installed modules in Odoo (e.g. mrp,
  // hr_expense) light up their sidebar tabs without a logout.
  async function manualReload() {
    btn.classList.add('is-spinning');
    btn.disabled = true;
    try {
      await fetch('/refresh-session', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
      });
    } catch (_) {
      // Network blip — fall through to a normal reload anyway.
    }
    const url = new URL(window.location.href);
    url.searchParams.set('_t', Date.now().toString());
    window.location.href = url.toString();
  }

  function scheduleAuto(minutes) {
    if (autoTimer) {
      clearTimeout(autoTimer);
      autoTimer = null;
    }
    const m = parseInt(minutes, 10);
    if (!m) return;
    // Auto-refresh re-probes modules too, so a freshly-installed Odoo module
    // shows up on the next timer tick without a manual click.
    autoTimer = setTimeout(manualReload, m * 60 * 1000);
  }

  let saved = '0';
  try { saved = localStorage.getItem(INTERVAL_KEY) || '0'; } catch (e) {}
  if (VALID.indexOf(saved) < 0) saved = '0';
  if (sel) sel.value = saved;
  scheduleAuto(saved);

  btn.addEventListener('click', manualReload);
  if (sel) {
    sel.addEventListener('change', function () {
      const v = VALID.indexOf(this.value) >= 0 ? this.value : '0';
      try { localStorage.setItem(INTERVAL_KEY, v); } catch (e) {}
      scheduleAuto(v);
    });
  }

  showStamp();
})();

/* ===== Theme switcher =====
 * Persists the chosen theme in localStorage under "olens.theme" and applies
 * it via the data-theme attribute on <html>. Also keeps Chart.js global
 * defaults (text + grid colors) in sync with the active theme and asks
 * every live chart to repaint so axes/gridlines pick up the new tokens. */
(function () {
  var STORAGE_KEY = 'olens.theme';
  var THEMES = ['dark', 'light', 'midnight'];
  var LABELS = { dark: 'Dark', light: 'Light', midnight: 'Midnight' };

  function readTheme() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return THEMES.indexOf(v) >= 0 ? v : 'dark';
    } catch (e) { return 'dark'; }
  }

  function applyChartDefaults() {
    if (!window.Chart) return;
    var style = getComputedStyle(document.documentElement);
    var text = (style.getPropertyValue('--chart-text') || '').trim() || '#475569';
    var grid = (style.getPropertyValue('--chart-grid') || '').trim() || '#e5e7eb';
    Chart.defaults.color       = text;
    Chart.defaults.borderColor = grid;
    if (Chart.defaults.scale && Chart.defaults.scale.grid) {
      Chart.defaults.scale.grid.color = grid;
    }
    // Repaint every live chart so axis labels + gridlines pick up the new
    // defaults. Charts that bake explicit colors into options keep theirs.
    if (Chart.instances) {
      try {
        Object.keys(Chart.instances).forEach(function (k) {
          var c = Chart.instances[k];
          if (c && typeof c.update === 'function') c.update('none');
        });
      } catch (e) {}
    }
  }

  function setTheme(theme, persist) {
    if (THEMES.indexOf(theme) < 0) theme = 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    if (persist !== false) {
      try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
    }
    var lbl = document.getElementById('themeTriggerCurrent');
    if (lbl) lbl.textContent = LABELS[theme];
    document.querySelectorAll('.theme-option').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-theme') === theme);
    });
    applyChartDefaults();
    document.dispatchEvent(new CustomEvent('olens:theme-change', { detail: { theme: theme } }));
  }

  // Apply on load — the inline <head> script already set the attribute, this
  // just syncs Chart defaults + popover state. Safe if called twice.
  document.addEventListener('DOMContentLoaded', function () {
    setTheme(readTheme(), false);
  });

  var trigger = document.getElementById('themeTrigger');
  var popover = document.getElementById('themePopover');
  if (trigger && popover) {
    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = !popover.hidden;
      popover.hidden = open;
      trigger.setAttribute('aria-expanded', open ? 'false' : 'true');
    });
    document.addEventListener('click', function (e) {
      if (popover.hidden) return;
      if (!popover.contains(e.target) && e.target !== trigger) {
        popover.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
      }
    });
    popover.querySelectorAll('.theme-option').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setTheme(btn.getAttribute('data-theme'), true);
        popover.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // Expose so other scripts can re-sync Chart defaults after creating a
  // chart (e.g. financial charts built after DOMContentLoaded).
  window.olensApplyChartDefaults = applyChartDefaults;
})();

/* ===== KPI card hover glow — derive shadow color from number text ===========
   For every KPI/stat/cashflow/tax/budget/asset-chart card on the page we read
   the computed `color` of its inner value element, then write
   `--card-glow-color` on the card itself. The CSS hover rule consumes that
   variable so each card glows in its own number color on hover.

   Exception: very dark numbers (rgb all < 50, i.e. effectively black) would
   produce a near-black halo on hover, which reads as a hard drop shadow.
   Those cards fall back to #6b7280 (slate-500) at the same opacity.

   Runs on DOMContentLoaded, after theme changes, after language changes, and
   exposes window.olensRefreshCardGlow() so any future AJAX flow that rerenders
   KPI cards can call it without reloading the page. ============================ */
(function () {
  var CARD_SELECTOR =
    '.stat-card, .kpi-card, .cashflow-card, .tax-card, .budget-card, .asset-chart-card';
  var VALUE_SELECTOR = '.stat-value, .kpi-value, .amount-display';
  var GLOW_OPACITY = 0.35;
  var DARK_THRESHOLD = 50;
  var FALLBACK_GREY = [107, 114, 128]; // #6b7280

  function parseRgb(s) {
    if (!s) return null;
    var m = s.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (!m) return null;
    return [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10)];
  }

  function buildShadow(rgb) {
    return (
      '0 0 30px rgba(' + rgb[0] + ', ' + rgb[1] + ', ' + rgb[2] +
      ', ' + GLOW_OPACITY + ')'
    );
  }

  function applyCardGlows(root) {
    var scope = root || document;
    var cards = scope.querySelectorAll
      ? scope.querySelectorAll(CARD_SELECTOR)
      : [];
    cards.forEach(function (card) {
      var valueEl = card.querySelector(VALUE_SELECTOR);
      if (!valueEl) return;
      var rgb = parseRgb(window.getComputedStyle(valueEl).color);
      if (!rgb) return;
      if (rgb[0] < DARK_THRESHOLD &&
          rgb[1] < DARK_THRESHOLD &&
          rgb[2] < DARK_THRESHOLD) {
        rgb = FALLBACK_GREY;
      }
      card.style.setProperty('--card-glow-color', buildShadow(rgb));

      // Active filter cards (Bill Aging / Payment Status / Fully
      // Depreciated / ...) get their border painted in the same color
      // so the selected highlight matches the number. Background
      // tint and box-shadow ring stay as the existing red because
      // the spec only changes the border. setProperty's 3rd-arg
      // 'important' beats the !important red border in the CSS.
      if (card.classList.contains('stat-card-active')) {
        var solid = 'rgb(' + rgb[0] + ', ' + rgb[1] + ', ' + rgb[2] + ')';
        card.style.setProperty('border-color', solid, 'important');
      } else {
        // Card is no longer active (rare in practice — selection flips
        // by full page reload — but cheap to keep stale borders from
        // sticking around after dynamic rerenders).
        card.style.removeProperty('border-color');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { applyCardGlows(); });
  } else {
    applyCardGlows();
  }
  // Re-run when text colors may have changed.
  document.addEventListener('olens:theme-change',    function () { applyCardGlows(); });
  document.addEventListener('olens:language-change', function () { applyCardGlows(); });

  window.olensRefreshCardGlow = applyCardGlows;
})();
