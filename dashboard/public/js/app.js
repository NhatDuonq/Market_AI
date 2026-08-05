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
  const isAuthenticated = checkUserSession();
  if (isAuthenticated) {
    loadDashboard();
  } else {
    showAuthModal();
  }
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

async function fetchJSON(url, options = {}) {
  let token = localStorage.getItem('authToken');
  const headers = options.headers || {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  try {
    let res = await fetch(url, { ...options, headers });

    // Auto-refresh Access Token via Refresh Token on 401/403
    if (res.status === 401 || res.status === 403) {
      const refreshToken = localStorage.getItem('refreshToken');
      if (refreshToken) {
        const refreshRes = await fetch('/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refreshToken })
        });

        if (refreshRes.ok) {
          const refreshData = await refreshRes.json();
          if (refreshData && refreshData.accessToken) {
            localStorage.setItem('authToken', refreshData.accessToken);
            headers['Authorization'] = `Bearer ${refreshData.accessToken}`;
            res = await fetch(url, { ...options, headers });
          }
        } else {
          if (typeof showAuthModal === 'function') showAuthModal();
        }
      } else {
        if (typeof showAuthModal === 'function') showAuthModal();
      }
    }
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

  // Load AI Strategic Analysis
  loadAiSummary(competitor);
}

// In-memory Frontend AI Cache Map (lưu cache đánh giá AI theo từng đối thủ trên trình duyệt)
const aiAnalysisCache = {};

async function loadAiSummary(competitor, forceRefresh = false) {
  const container = document.getElementById('aiSummary');
  if (!container) return;

  // 1. Nếu đã có trong Frontend Cache và không ép buộc nạp lại -> Render ngay lập tức (0ms)
  if (!forceRefresh && aiAnalysisCache[competitor]) {
    renderAiAnalysisHTML(container, aiAnalysisCache[competitor]);
    return;
  }

  container.innerHTML = '<p style="color:#94a3b8; font-size:13px;">⏳ Đang phân tích dữ liệu chiến lược thị trường bằng Gemini AI...</p>';

  const url = forceRefresh ? `/api/ai-analysis/${competitor}?force=true` : `/api/ai-analysis/${competitor}`;
  const res = await fetchJSON(url);
  if (res && res.analysis) {
    aiAnalysisCache[competitor] = res.analysis; // Lưu cache trình duyệt
    renderAiAnalysisHTML(container, res.analysis);
  } else {
    container.innerHTML = '<p style="color:#ef4444; font-size:13px;">⚠️ Chưa thể lấy phân tích AI lúc này.</p>';
  }
}

async function forceRefreshAi(event) {
  if (event) event.stopPropagation();

  const competitorSelect = document.getElementById('competitorSelect');
  const competitor = competitorSelect ? competitorSelect.value : 'matbao';

  const btn = document.getElementById('btnRefreshAi');
  const icon = document.getElementById('aiRefreshIcon');
  const text = document.getElementById('aiRefreshText');

  if (icon) icon.classList.add('spinning-icon');
  if (text) text.textContent = 'Đang phân tích...';
  if (btn) btn.disabled = true;

  try {
    await loadAiSummary(competitor, true);
  } catch (err) {
    console.error('Error force refreshing AI:', err);
  } finally {
    if (icon) icon.classList.remove('spinning-icon');
    if (text) text.textContent = 'Phân tích lại';
    if (btn) btn.disabled = false;
  }
}

function renderAiAnalysisHTML(container, analysisText) {
  let text = analysisText;
  // Format markdown to clean HTML for Dark Mode
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong style="color:#38bdf8; font-weight:700;">$1</strong>');
  text = text.replace(/\*(.*?)\*/g, '<strong style="color:#60a5fa; font-weight:600;">$1</strong>');
  text = text.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.08); padding:2px 7px; border-radius:4px; font-family:monospace; color:#34d399; border:1px solid rgba(255,255,255,0.12);">$1</code>');
  text = text.replace(/\n/g, '<br>');
  container.innerHTML = `<div style="font-size:13px; line-height:1.8; color:#f1f5f9; background:rgba(15,23,42,0.4); padding:16px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);">${text}</div>`;
}

function toggleAiSummary() {
  const summaryEl = document.getElementById('aiSummary');
  const btn = document.getElementById('btnToggleAi');
  if (!summaryEl || !btn) return;

  if (summaryEl.style.display === 'none') {
    summaryEl.style.display = 'block';
    btn.innerHTML = '👁️ Thu gọn';
  } else {
    summaryEl.style.display = 'none';
    btn.innerHTML = '👁️ Mở rộng';
  }
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
    if (data.success) {
      showToast(`✅ ${data.message}`, 'success');
    } else {
      showToast(`❌ Lỗi gửi báo cáo: ${data.message || 'Thất bại'}`, 'error');
    }
  } catch (e) {
    showToast('❌ Lỗi kết nối gửi báo cáo', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">📨</span> Gửi Báo Cáo';
  }
}

// ============================================================
// AUTHENTICATION & EXPORT PDF ENGINE
// ============================================================

function showAuthModal() {
  const overlay = document.getElementById('authModalOverlay');
  if (overlay) overlay.style.display = 'flex';
  switchAuthForm('login');
}

function hideAuthModal() {
  const token = localStorage.getItem('authToken');
  if (!token) {
    showToast('⚠️ Vui lòng đăng nhập bằng Email @longvan.net để sử dụng hệ thống!', 'warning');
    return;
  }
  const overlay = document.getElementById('authModalOverlay');
  if (overlay) overlay.style.display = 'none';
}

function switchAuthForm(formType) {
  const login = document.getElementById('formLogin');
  const reg = document.getElementById('formRegister');
  const otp = document.getElementById('formOtp');
  const forgot = document.getElementById('formForgot');
  const reset = document.getElementById('formReset');

  const title = document.getElementById('authTitle');

  if (login) login.style.display = formType === 'login' ? 'block' : 'none';
  if (reg) reg.style.display = formType === 'register' ? 'block' : 'none';
  if (otp) otp.style.display = formType === 'otp' ? 'block' : 'none';
  if (forgot) forgot.style.display = formType === 'forgot' ? 'block' : 'none';
  if (reset) reset.style.display = formType === 'reset' ? 'block' : 'none';

  if (title) {
    if (formType === 'login') title.textContent = 'Đăng Nhập Doanh Nghiệp';
    if (formType === 'register') title.textContent = 'Đăng Ký Tài Khoản @longvan.net';
    if (formType === 'otp') title.textContent = 'Xác Thực Mã OTP';
    if (formType === 'forgot') title.textContent = 'Khôi Phục Mật Khẩu';
    if (formType === 'reset') title.textContent = 'Đặt Lại Mật Khẩu Mới';
  }
}

async function handleLogin() {
  const email = document.getElementById('loginEmail').value;
  const password = document.getElementById('loginPassword').value;

  if (!email || !email.endsWith('@longvan.net')) {
    return showToast('⚠️ Vui lòng nhập Email doanh nghiệp Long Vân (@longvan.net)', 'error');
  }

  const res = await fetchJSON('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });

  if (res && res.token) {
    localStorage.setItem('authToken', res.accessToken || res.token);
    if (res.refreshToken) localStorage.setItem('refreshToken', res.refreshToken);
    localStorage.setItem('authUser', JSON.stringify(res.user));
    hideAuthModal();
    checkUserSession();
    showToast(`✅ Xin chào ${res.user.full_name || res.user.email}!`, 'success');
    loadDashboard();
  } else if (res && res.error) {
    showToast(`⚠️ ${res.error}`, 'error');
  }
}

async function handleRegister() {
  const full_name = document.getElementById('regFullName').value;
  const email = document.getElementById('regEmail').value;
  const password = document.getElementById('regPassword').value;

  if (!email || !email.endsWith('@longvan.net')) {
    return showToast('⚠️ Chỉ chấp nhận Email doanh nghiệp Long Vân (@longvan.net)', 'error');
  }

  const res = await fetchJSON('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, full_name, password })
  });

  if (res && res.success) {
    document.getElementById('otpTargetEmail').textContent = email;
    switchAuthForm('otp');
    showToast(`📩 ${res.message}`, 'info');
  } else if (res && res.error) {
    showToast(`⚠️ ${res.error}`, 'error');
  }
}

async function handleVerifyOtp() {
  const email = document.getElementById('otpTargetEmail').textContent || document.getElementById('regEmail').value;
  const otp_code = document.getElementById('otpCode').value;

  const res = await fetchJSON('/api/auth/verify-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, otp_code, otp_type: 'REGISTRATION' })
  });

  if (res && res.token) {
    localStorage.setItem('authToken', res.accessToken || res.token);
    if (res.refreshToken) localStorage.setItem('refreshToken', res.refreshToken);
    localStorage.setItem('authUser', JSON.stringify(res.user));
    hideAuthModal();
    showToast('🎉 Xác thực tài khoản thành công!', 'success');
    loadDashboard();
  } else if (res && res.error) {
    showToast(`⚠️ ${res.error}`, 'error');
  }
}

async function handleForgotPassword() {
  const email = document.getElementById('forgotEmail').value;

  if (!email || !email.endsWith('@longvan.net')) {
    return showToast('⚠️ Vui lòng nhập Email doanh nghiệp Long Vân (@longvan.net)', 'error');
  }

  const res = await fetchJSON('/api/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });

  if (res && res.success) {
    switchAuthForm('reset');
    showToast(`📩 ${res.message}`, 'info');
  } else if (res && res.error) {
    showToast(`⚠️ ${res.error}`, 'error');
  }
}

async function handleResetPassword() {
  const email = document.getElementById('forgotEmail').value;
  const otp_code = document.getElementById('resetOtpCode').value;
  const new_password = document.getElementById('resetNewPassword').value;

  const res = await fetchJSON('/api/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, otp_code, new_password })
  });

  if (res && res.success) {
    switchAuthForm('login');
    showToast('🎉 Đặt lại mật khẩu thành công! Vui lòng đăng nhập.', 'success');
  } else if (res && res.error) {
    showToast(`⚠️ ${res.error}`, 'error');
  }
}

async function exportExecutivePdf() {
  const btn = document.getElementById('btnExportPdf');
  if (btn) btn.innerHTML = '⏳ Đang tạo PDF...';

  try {
    const competitorName = getCompetitorName();
    const aiSummaryEl = document.getElementById('aiSummary');
    const aiText = aiSummaryEl ? aiSummaryEl.innerText : '';

    const barCanvas = document.getElementById('barChart');
    const donutCanvas = document.getElementById('donutChart');

    const barImg = barCanvas ? barCanvas.toDataURL('image/png') : '';
    const donutImg = donutCanvas ? donutCanvas.toDataURL('image/png') : '';

    const element = document.createElement('div');
    element.style.padding = '24px';
    element.style.background = '#ffffff';
    element.style.color = '#0f172a';
    element.style.fontFamily = 'Segoe UI, Arial, sans-serif';

    element.innerHTML = `
      <div style="border-bottom: 2px solid #0284c7; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <span style="background: #0284c7; color: #fff; font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px;">LONG VÂN CLOUD SOLUTION</span>
          <h1 style="font-size: 20px; color: #0f172a; margin: 6px 0 0 0;">BÁO CÁO CẠNH TRANH GIÁ TÊN MIỀN</h1>
          <p style="font-size: 12px; color: #64748b; margin: 2px 0 0 0;">Đối thủ: <strong>${competitorName.toUpperCase()}</strong> | Ngày xuất: ${new Date().toLocaleDateString('vi-VN')}</p>
        </div>
      </div>

      <div style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 14px; border-radius: 6px; margin-bottom: 20px;">
        <h3 style="color: #0369a1; font-size: 14px; margin: 0 0 8px 0;">🧠 Phân Tích & Đề Xuất Chiến Lược Từ Gemini AI</h3>
        <div style="font-size: 11px; line-height: 1.6; color: #1e3a8a; white-space: pre-wrap;">${aiText}</div>
      </div>

      <h3 style="font-size: 14px; color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; margin-bottom: 12px;">📊 Biểu Đồ So Sánh Trực Quan</h3>
      <div style="display: flex; gap: 10px; margin-bottom: 20px;">
        ${barImg ? `<div style="flex: 1; text-align: center;"><img src="${barImg}" style="max-width: 100%; height: auto; border: 1px solid #e2e8f0; border-radius: 6px;"></div>` : ''}
        ${donutImg ? `<div style="flex: 1; text-align: center;"><img src="${donutImg}" style="max-width: 100%; height: auto; border: 1px solid #e2e8f0; border-radius: 6px;"></div>` : ''}
      </div>

      <p style="font-size: 10px; color: #94a3b8; text-align: center; margin-top: 30px;">
        Báo cáo được khởi tạo tự động bởi Market AI Engine &bull; Long Vân Cloud Solution (https://khangthost.io.vn)
      </p>
    `;

    const opt = {
      margin: 10,
      filename: `Market_AI_Bao_Cao_${getSelectedCompetitor()}_${new Date().toISOString().slice(0, 10)}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
    };

    if (window.html2pdf) {
      await html2pdf().set(opt).from(element).save();
      showToast('✅ Đã xuất báo cáo PDF thành công!');
    } else {
      showToast('⚠️ Thư viện PDF đang tải, vui lòng thử lại sau 2 giây.');
    }
  } catch (e) {
    console.error('Lỗi xuất PDF:', e);
    showToast('⚠️ Không thể xuất PDF: ' + e.message);
  } finally {
    if (btn) btn.innerHTML = '<span class="btn-icon">📄</span> Xuất PDF';
  }
}

function checkUserSession() {
  const token = localStorage.getItem('authToken');
  const userStr = localStorage.getItem('authUser');

  const badge = document.getElementById('userProfileBadge');
  const openBtn = document.getElementById('btnOpenAuth');
  const headerAuthBtn = document.getElementById('headerAuthBtn');
  const emailDisplay = document.getElementById('userEmailDisplay');

  if (token && userStr) {
    try {
      const user = JSON.parse(userStr);
      if (emailDisplay) emailDisplay.textContent = user.email || user.full_name;
      if (badge) badge.style.display = 'block';
      if (openBtn) openBtn.style.display = 'none';
      if (headerAuthBtn) headerAuthBtn.innerHTML = `👤 ${user.email || user.full_name}`;
      return true;
    } catch (e) {
      localStorage.removeItem('authToken');
      localStorage.removeItem('authUser');
    }
  }

  if (badge) badge.style.display = 'none';
  if (openBtn) openBtn.style.display = 'flex';
  if (headerAuthBtn) headerAuthBtn.innerHTML = `🔑 Đăng nhập @longvan.net`;
  return false;
}

function handleLogout() {
  const refreshToken = localStorage.getItem('refreshToken');
  if (refreshToken) {
    fetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshToken })
    });
  }
  localStorage.removeItem('authToken');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('authUser');
  showToast('👋 Đã đăng xuất tài khoản!', 'info');
  checkUserSession();
  showAuthModal();
}

// ============================================================
// SMART DISPATCH SEND REPORT MODAL & CC MANAGEMENT
// ============================================================

let dispatchCcEmails = [];

function sendReport() {
  openSendReportModal();
}

function openSendReportModal() {
  const token = localStorage.getItem('authToken');
  if (!token) {
    showToast('⚠️ Vui lòng đăng nhập bằng Email @longvan.net trước khi gửi báo cáo!', 'warning');
    showAuthModal();
    return;
  }

  dispatchCcEmails = [];
  renderCcBadges();
  toggleCcInputForm(false);

  const userStr = localStorage.getItem('authUser');
  let primaryEmail = 'Cán bộ Long Vân';
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      primaryEmail = user.email || user.full_name || 'Cán bộ Long Vân';
    } catch (e) {}
  }

  const primaryEl = document.getElementById('dispatchPrimaryEmail');
  if (primaryEl) primaryEl.textContent = primaryEmail;

  const overlay = document.getElementById('sendReportModalOverlay');
  if (overlay) overlay.style.display = 'flex';
}

function closeSendReportModal() {
  const overlay = document.getElementById('sendReportModalOverlay');
  if (overlay) overlay.style.display = 'none';
}

function toggleCcInputForm(show) {
  const inputBox = document.getElementById('dispatchCcInputBox');
  if (inputBox) inputBox.style.display = show ? 'flex' : 'none';
  if (show) {
    const input = document.getElementById('dispatchCcEmailInput');
    if (input) {
      input.value = '';
      input.focus();
    }
  }
}

function addCcEmailFromInput() {
  const input = document.getElementById('dispatchCcEmailInput');
  if (!input) return;
  const email = (input.value || '').trim().toLowerCase();

  if (!email) {
    return showToast('⚠️ Vui lòng nhập địa chỉ Email CC', 'warning');
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return showToast('⚠️ Định dạng Email không hợp lệ!', 'error');
  }

  if (dispatchCcEmails.includes(email)) {
    return showToast('⚠️ Email này đã có trong danh sách CC!', 'warning');
  }

  dispatchCcEmails.push(email);
  renderCcBadges();
  input.value = '';
  toggleCcInputForm(false);
  showToast(`✅ Đã thêm CC: ${email}`, 'success');
}

function removeCcEmail(email) {
  dispatchCcEmails = dispatchCcEmails.filter(e => e !== email);
  renderCcBadges();
}

function renderCcBadges() {
  const container = document.getElementById('dispatchCcBadges');
  if (!container) return;

  if (dispatchCcEmails.length === 0) {
    container.innerHTML = '<span style="font-size: 12px; color: #64748b; font-style: italic;">Chưa có Email CC bổ sung (Bấm ➕ Thêm CC)</span>';
    return;
  }

  container.innerHTML = dispatchCcEmails.map(email => `
    <span style="display: inline-flex; align-items: center; gap: 6px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 20px;">
      📧 ${email}
      <button type="button" onclick="removeCcEmail('${email}')" style="background: transparent; border: none; color: #f87171; font-weight: bold; cursor: pointer; font-size: 12px; margin-left: 2px;">&times;</button>
    </span>
  `).join('');
}

async function executeSendReportDispatch() {
  const btn = document.getElementById('btnConfirmSendReport');
  const channel = document.getElementById('dispatchChannelSelect').value || 'all';

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Đang phân phối báo cáo...';
  }

  try {
    const res = await fetchJSON('/api/send-report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel,
        cc_emails: dispatchCcEmails
      })
    });

    if (res && res.success) {
      showToast(`🎉 ${res.message}`, 'success');
      closeSendReportModal();
    } else if (res && res.error) {
      showToast(`⚠️ ${res.error}`, 'error');
    } else {
      showToast('⚠️ Không thể gửi báo cáo lúc này.', 'error');
    }
  } catch (e) {
    showToast('⚠️ Lỗi kết nối server khi gửi báo cáo.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '🚀 XÁC NHẬN GỬI BÁO CÁO';
    }
  }
}
