// ============================================================
// MARKET AI DASHBOARD - Frontend Application
// ============================================================

const COMPETITOR_NAMES = {
  matbao: 'Mắt Bão',
  pavietnam: 'PA Việt Nam',
};

let currentData = null;
let barChartInstance = null;
let donutChartInstance = null;
let currentMetric = '2yr'; // default metric

const METRIC_LABELS = {
  '2yr': 'Tổng Chi Phí 2 Năm',
  'register': 'Giá Đăng Ký Năm 1',
  'renew': 'Giá Gia Hạn Hàng Năm',
};

const METRIC_FIELDS = {
  '2yr': 'Tổng chi phí 2 năm',
  'register': 'Giá đăng ký',
  'renew': 'Giá gia hạn',
};

// ============================================================
// INIT
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();
  setupCompetitorSelect();
  setupMetricSelect();
  setupTableFilters();
  setupScreenshotFilter();
  loadDashboard();
});

// ============================================================
// NAVIGATION
// ============================================================

function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');

      const pageId = item.dataset.page;
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      document.getElementById(`page-${pageId}`).classList.add('active');

      // Load page-specific data
      if (pageId === 'screenshots') loadScreenshots();
      if (pageId === 'settings') loadSettings();
    });
  });
}

function setupCompetitorSelect() {
  const select = document.getElementById('competitorSelect');
  select.addEventListener('change', () => loadDashboard());
}

function setupMetricSelect() {
  const select = document.getElementById('metricSelect');
  select.addEventListener('change', () => {
    currentMetric = select.value;
    if (currentData) {
      updateMetricView();
    }
  });
}

function getSelectedCompetitor() {
  return document.getElementById('competitorSelect').value;
}

function getCompetitorName() {
  return COMPETITOR_NAMES[getSelectedCompetitor()] || getSelectedCompetitor();
}

// ============================================================
// API HELPERS
// ============================================================

async function fetchJSON(url) {
  try {
    const res = await fetch(url);
    return await res.json();
  } catch (e) {
    console.error(`API Error (${url}):`, e);
    return null;
  }
}

function formatVND(value) {
  return new Intl.NumberFormat('vi-VN').format(Math.round(value)) + 'đ';
}

function formatPct(value) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}

function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => { toast.className = 'toast'; }, 3500);
}

// ============================================================
// DASHBOARD PAGE
// ============================================================

async function loadDashboard() {
  const competitor = getSelectedCompetitor();
  const competitorName = getCompetitorName();

  // Update header
  document.getElementById('headerCompetitorName').textContent = competitorName;

  const data = await fetchJSON(`/api/compare/${competitor}`);
  if (!data) return;
  currentData = data;

  // Update time
  const times = [];
  if (data.competitor_updated_at) times.push(`${competitorName}: ${data.competitor_updated_at}`);
  if (data.longvan_updated_at) times.push(`Long Vân: ${data.longvan_updated_at}`);
  document.getElementById('updateTime').textContent = times.length
    ? `🕐 Cập nhật: ${times.join(' | ')}`
    : '';

  // Render everything based on current metric
  updateMetricView();

  // Risk table (always 2yr)
  renderRiskTable(data, competitorName);

  // Also update TLD page & detail table
  renderTLDPage(data, competitorName);
  renderFullTable(data, competitorName);
}

function updateMetricView() {
  const data = currentData;
  if (!data) return;
  const competitorName = getCompetitorName();
  const metric = currentMetric;
  const metricLabel = METRIC_LABELS[metric];

  // Update sublabel
  document.getElementById('kpiMetricSublabel').textContent = `(Tiêu chí: ${metricLabel})`;

  // Get metric summary
  const ms = (data.metric_summaries || {})[metric] || data.tld_summary || {};

  // KPI Cards
  document.getElementById('kpiTotalTLD').textContent = data.tld_summary?.total_common || 0;
  document.getElementById('kpiCheaper').textContent = ms.cheaper_count || 0;
  document.getElementById('kpiExpensive').textContent = ms.expensive_count || 0;
  document.getElementById('kpiMissing').textContent = data.tld_availability?.competitor_exclusive?.length || 0;

  // KPI Tooltips
  buildKpiTooltip('tooltipCheaper', '⚠️ Đối thủ giá thấp hơn', ms.cheaper_tlds || [], true);
  buildKpiTooltip('tooltipExpensive', '✅ Long Vân giá thấp hơn', ms.expensive_tlds || [], false);

  // Chart titles
  document.getElementById('barChartTitle').textContent = `So Sánh ${metricLabel} Theo TLD`;
  document.getElementById('donutChartTitle').textContent = `Vị Thế Giá (${metricLabel})`;

  // Charts
  renderBarChart(data, competitorName, metric);
  renderDonutChart(data, metric);
}

function buildKpiTooltip(elementId, title, tldList, isCheaper) {
  const el = document.getElementById(elementId);
  if (!tldList.length) {
    el.innerHTML = `<div class="tooltip-title">${title}</div><div style="color:#64748b">Không có</div>`;
    return;
  }
  const rows = tldList.map(t => {
    const tld = typeof t === 'string' ? t : t.tld;
    const diff = typeof t === 'object' ? t.diff : 0;
    const diffClass = isCheaper ? 'tooltip-diff-neg' : 'tooltip-diff-pos';
    const diffText = diff !== 0 ? formatVND(Math.abs(diff)) : '';
    const sign = isCheaper ? '-' : '+';
    return `<div class="tooltip-row">
      <span class="tooltip-tld">${tld}</span>
      <span class="${diffClass}">${sign}${diffText}</span>
    </div>`;
  }).join('');
  el.innerHTML = `<div class="tooltip-title">${title}</div>${rows}`;
}

// ============================================================
// BAR CHART
// ============================================================

function renderBarChart(data, competitorName, metric) {
  const canvas = document.getElementById('barChart');
  if (barChartInstance) barChartInstance.destroy();

  const fieldName = METRIC_FIELDS[metric || currentMetric];
  const items = data.comparison
    .filter(c => c.field === fieldName)
    .sort((a, b) => a.diff_amount - b.diff_amount)
    .slice(0, 15);

  if (!items.length) {
    document.getElementById('barChartTitle').textContent = 'Chưa có dữ liệu biểu đồ';
    return;
  }

  const labels = items.map(c => c.tld);
  const compPrices = items.map(c => c.competitor_price);
  const lvPrices = items.map(c => c.longvan_price);

  barChartInstance = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: competitorName,
          data: compPrices,
          backgroundColor: 'rgba(248, 113, 113, 0.75)',
          borderColor: 'rgba(248, 113, 113, 1)',
          borderWidth: 1,
          borderRadius: 4,
        },
        {
          label: 'Long Vân',
          data: lvPrices,
          backgroundColor: 'rgba(96, 165, 250, 0.75)',
          borderColor: 'rgba(96, 165, 250, 1)',
          borderWidth: 1,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 } },
        },
        tooltip: {
          callbacks: {
            afterBody: (tooltipItems) => {
              const idx = tooltipItems[0].dataIndex;
              const item = items[idx];
              const diff = item.diff_amount;
              const who = diff < 0 ? `Đối thủ giá thấp hơn: ${formatVND(Math.abs(diff))}` : (diff > 0 ? `Long Vân giá thấp hơn: ${formatVND(diff)}` : 'Bằng giá');
              return [`Chênh lệch: ${who}`];
            },
            label: ctx => `${ctx.dataset.label}: ${formatVND(ctx.raw)}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#64748b', font: { size: 11 } },
          grid: { color: 'rgba(255,255,255,0.03)' },
        },
        y: {
          ticks: {
            color: '#64748b',
            font: { size: 11 },
            callback: v => new Intl.NumberFormat('vi-VN', { notation: 'compact' }).format(v),
          },
          grid: { color: 'rgba(255,255,255,0.04)' },
        },
      },
    },
  });
}

// ============================================================
// DONUT CHART
// ============================================================

function renderDonutChart(data, metric) {
  const canvas = document.getElementById('donutChart');
  if (donutChartInstance) donutChartInstance.destroy();

  // Use metric_summaries for selected metric
  const ms = (data.metric_summaries || {})[metric || currentMetric] || data.tld_summary || {};
  const tldCheaper = ms.cheaper_count || 0;
  const tldExpensive = ms.expensive_count || 0;
  const tldEqual = ms.equal_count || 0;

  const values = [tldCheaper, tldExpensive, tldEqual];
  const hasData = values.some(v => v > 0);

  if (!hasData) {
    document.getElementById('donutLegend').innerHTML = '<span style="color:#64748b">Chưa có dữ liệu so sánh</span>';
    return;
  }

  // Build TLD detail lists for custom tooltip
  const cheaperTlds = (ms.cheaper_tlds || []).map(t => typeof t === 'string' ? t : t.tld);
  const expensiveTlds = (ms.expensive_tlds || []).map(t => typeof t === 'string' ? t : t.tld);
  const equalTlds = ms.equal_tlds || [];
  const tldLists = [cheaperTlds, expensiveTlds, equalTlds];

  donutChartInstance = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Đối thủ giá thấp hơn', 'Long Vân giá thấp hơn', 'Bằng giá'],
      datasets: [{
        data: values,
        backgroundColor: [
          'rgba(248, 113, 113, 0.85)',
          'rgba(52, 211, 153, 0.85)',
          'rgba(100, 116, 139, 0.5)',
        ],
        borderColor: 'transparent',
        borderWidth: 0,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.label}: ${ctx.raw} TLD`,
            afterLabel: ctx => {
              const list = tldLists[ctx.dataIndex] || [];
              return list.length ? list.join(', ') : '';
            },
          },
        },
      },
    },
  });

  // Legend
  const legend = document.getElementById('donutLegend');
  legend.innerHTML = `
    <span><span style="color:#f87171">●</span> Đối thủ giá thấp hơn: ${tldCheaper}</span>
    <span><span style="color:#34d399">●</span> LV giá thấp hơn: ${tldExpensive}</span>
    <span><span style="color:#64748b">●</span> Bằng giá: ${tldEqual}</span>
  `;
}

// ============================================================
// RISK TABLE (Top items where competitor is cheaper)
// ============================================================

function renderRiskTable(data, competitorName) {
  const tbody = document.querySelector('#riskTable tbody');
  const risks = data.comparison
    .filter(c => c.status === 'CHEAPER')
    .sort((a, b) => a.diff_amount - b.diff_amount)
    .slice(0, 10);

  if (!risks.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:24px;">✅ Long Vân không có rủi ro cạnh tranh nào! Tuyệt vời!</td></tr>';
    return;
  }

  tbody.innerHTML = risks.map(r => `
    <tr>
      <td><strong>${r.tld}</strong></td>
      <td>${r.field}</td>
      <td>${formatVND(r.competitor_price)}</td>
      <td>${formatVND(r.longvan_price)}</td>
      <td class="status-cheaper">${formatVND(r.diff_amount)}</td>
      <td class="status-cheaper">${formatPct(r.diff_pct)}</td>
    </tr>
  `).join('');
}

// ============================================================
// TLD AVAILABILITY PAGE
// ============================================================

function renderTLDPage(data, competitorName) {
  const avail = data.tld_availability;

  document.getElementById('tldLvTotal').textContent = avail.longvan_total;
  document.getElementById('tldCompTotal').textContent = avail.competitor_total;
  document.getElementById('tldCompLabel').textContent = `${competitorName} TLD`;
  document.getElementById('tldCommon').textContent = avail.common.length;

  // LV Exclusive badges
  const lvContainer = document.getElementById('badgesLvExclusive');
  lvContainer.innerHTML = avail.longvan_exclusive.length
    ? avail.longvan_exclusive.map(t => `<span class="badge badge-green">${t}</span>`).join('')
    : '<div class="badge-empty">Tất cả TLD Long Vân đều có ở đối thủ</div>';

  // Competitor Exclusive badges
  const compContainer = document.getElementById('badgesCompExclusive');
  compContainer.innerHTML = avail.competitor_exclusive.length
    ? avail.competitor_exclusive.map(t => `<span class="badge badge-red">${t}</span>`).join('')
    : '<div class="badge-empty">Long Vân đã phủ hết các TLD của đối thủ 🎉</div>';

  // Common badges
  const commonContainer = document.getElementById('badgesCommon');
  commonContainer.innerHTML = avail.common.length
    ? avail.common.map(t => `<span class="badge badge-gray">${t}</span>`).join('')
    : '';
}

// ============================================================
// FULL COMPARISON TABLE
// ============================================================

function setupTableFilters() {
  ['filterField', 'filterStatus', 'searchTLD'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      if (currentData) renderFullTable(currentData, getCompetitorName());
    });
    document.getElementById(id).addEventListener('change', () => {
      if (currentData) renderFullTable(currentData, getCompetitorName());
    });
  });
}

function renderFullTable(data, competitorName) {
  const filterField = document.getElementById('filterField').value;
  const filterStatus = document.getElementById('filterStatus').value;
  const search = document.getElementById('searchTLD').value.toLowerCase();

  let items = data.comparison;

  if (filterField !== 'all') items = items.filter(c => c.field === filterField);
  if (filterStatus !== 'all') items = items.filter(c => c.status === filterStatus);
  if (search) items = items.filter(c => c.tld.toLowerCase().includes(search));

  const tbody = document.querySelector('#fullTable tbody');

  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#64748b;padding:24px;">Không tìm thấy kết quả</td></tr>';
    document.getElementById('tableCount').textContent = '';
    return;
  }

  tbody.innerHTML = items.map(c => {
    const statusClass = c.status === 'CHEAPER' ? 'status-cheaper' : (c.status === 'EXPENSIVE' ? 'status-expensive' : 'status-equal');
    const statusText = c.status === 'CHEAPER' ? '⚠️ Đối thủ giá thấp hơn'
      : (c.status === 'EXPENSIVE' ? '✅ LV giá thấp hơn' : '⚖️ Bằng giá');

    const fmtComp = c.competitor_price_original && c.competitor_price_original !== c.competitor_price
      ? `<del style="color:#64748b;font-size:11px">${formatVND(c.competitor_price_original)}</del><br>${formatVND(c.competitor_price)}`
      : formatVND(c.competitor_price);

    const fmtLV = c.longvan_price_original && c.longvan_price_original !== c.longvan_price
      ? `<del style="color:#64748b;font-size:11px">${formatVND(c.longvan_price_original)}</del><br>${formatVND(c.longvan_price)}`
      : formatVND(c.longvan_price);

    return `<tr>
      <td><strong>${c.tld}</strong></td>
      <td>${c.field}</td>
      <td>${fmtComp}</td>
      <td>${fmtLV}</td>
      <td class="${statusClass}">${c.diff_amount > 0 ? '+' : ''}${formatVND(c.diff_amount)}</td>
      <td class="${statusClass}">${formatPct(c.diff_pct)}</td>
      <td class="${statusClass}">${statusText}</td>
    </tr>`;
  }).join('');

  document.getElementById('tableCount').textContent = `Hiển thị ${items.length} / ${data.comparison.length} mục`;
}

// ============================================================
// SCREENSHOTS PAGE
// ============================================================

function setupScreenshotFilter() {
  document.getElementById('screenshotFilter').addEventListener('change', loadScreenshots);
}

async function loadScreenshots() {
  const filter = document.getElementById('screenshotFilter').value;
  const screenshots = await fetchJSON('/api/screenshots');
  const grid = document.getElementById('screenshotGrid');

  if (!screenshots || !screenshots.length) {
    grid.innerHTML = '<div class="screenshot-empty">📷 Chưa có ảnh chụp. Chạy crawler để tạo ảnh đối soát.</div>';
    return;
  }

  let filtered = screenshots;
  if (filter !== 'all') {
    filtered = screenshots.filter(s => s.provider === filter);
  }

  if (!filtered.length) {
    grid.innerHTML = '<div class="screenshot-empty">Không tìm thấy ảnh phù hợp bộ lọc.</div>';
    return;
  }

  grid.innerHTML = filtered.map(s => {
    const providerLabel = COMPETITOR_NAMES[s.provider] || s.provider;
    const date = new Date(s.created).toLocaleString('vi-VN');
    return `
      <div class="screenshot-item">
        <img src="${s.url}" alt="${s.filename}" loading="lazy">
        <div class="screenshot-info">
          <strong>${providerLabel}</strong><br>
          ${s.filename}<br>
          📅 ${date}
        </div>
      </div>
    `;
  }).join('');
}

// ============================================================
// SETTINGS PAGE
// ============================================================

async function loadSettings() {
  const config = await fetchJSON('/api/config');
  if (!config) return;

  const container = document.getElementById('crawlerToggles');
  container.innerHTML = '';

  Object.entries(config).forEach(([pKey, pInfo]) => {
    const products = pInfo.products || {};
    Object.entries(products).forEach(([prodKey, prodInfo]) => {
      const id = `toggle_${pKey}_${prodKey}`;
      const row = document.createElement('div');
      row.className = 'toggle-row';
      row.innerHTML = `
        <div>
          <div class="toggle-label">${pInfo.name}</div>
          <div class="toggle-sub">${prodInfo.name} (${prodKey})</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" id="${id}" ${prodInfo.enabled ? 'checked' : ''}>
          <span class="toggle-slider"></span>
        </label>
      `;
      container.appendChild(row);

      row.querySelector('input').addEventListener('change', async (e) => {
        config[pKey].products[prodKey].enabled = e.target.checked;
        await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        });
      });
    });
  });

  // System info
  const infoGrid = document.getElementById('systemInfo');
  infoGrid.innerHTML = `
    <div class="info-item">
      <div class="info-label">Nhà cung cấp theo dõi</div>
      <div class="info-value">${Object.keys(config).length} bên</div>
    </div>
    <div class="info-item">
      <div class="info-label">Sản phẩm</div>
      <div class="info-value">Tên miền (Domain)</div>
    </div>
    <div class="info-item">
      <div class="info-label">Dashboard Port</div>
      <div class="info-value">3000</div>
    </div>
    <div class="info-item">
      <div class="info-label">Dữ liệu Engine</div>
      <div class="info-value">JSON Snapshots</div>
    </div>
  `;
}

// ============================================================
// CRAWLER & REPORT ACTIONS
// ============================================================

async function triggerCrawl() {
  const btn = document.getElementById('btnCrawl');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Đang cào...';
  showToast('🔄 Đang chạy crawler, vui lòng chờ...', 'info');

  try {
    const res = await fetch('/api/crawl', { method: 'POST' });
    const data = await res.json();

    if (res.status === 429) {
      showToast('⚠️ Crawler đang chạy, vui lòng đợi!', 'error');
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-icon">🔄</span> Crawler Ngay';
      return;
    }

    // Poll for completion
    const pollInterval = setInterval(async () => {
      const status = await fetchJSON('/api/crawl/status');
      if (status && !status.running) {
        clearInterval(pollInterval);
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🔄</span> Crawler Ngay';
        showToast('✅ Crawler hoàn tất! Đang cập nhật dữ liệu...', 'success');
        // Auto-refresh dashboard
        await loadDashboard();
      }
    }, 3000);

    // Safety timeout: 5 minutes max
    setTimeout(() => {
      clearInterval(pollInterval);
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-icon">🔄</span> Crawler Ngay';
    }, 300000);

  } catch (e) {
    showToast('❌ Lỗi kết nối crawler', 'error');
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">🔄</span> Crawler Ngay';
  }
}

async function sendReport() {
  const btn = document.getElementById('btnReport');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Đang gửi...';

  try {
    const res = await fetch('/api/send-report', { method: 'POST' });
    const data = await res.json();

    if (data.error) {
      showToast(`⚠️ ${data.error}`, 'error');
    } else {
      showToast('✅ Đã gửi báo cáo thành công!', 'success');
    }
  } catch (e) {
    showToast('❌ Lỗi gửi báo cáo', 'error');
  }

  btn.disabled = false;
  btn.innerHTML = '<span class="btn-icon">📨</span> Gửi Báo Cáo';
}
