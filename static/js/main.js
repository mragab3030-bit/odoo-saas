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
