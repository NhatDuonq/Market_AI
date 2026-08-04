const express = require('express');
const path = require('path');
const fs = require('fs');
const glob = require('glob');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const app = express();
const PORT = process.env.DASHBOARD_PORT || 3000;

// Paths
const STORAGE_DIR = path.join(__dirname, '..', 'storage');
const SNAPSHOTS_DIR = path.join(STORAGE_DIR, 'snapshots');
const SCREENSHOTS_DIR = path.join(STORAGE_DIR, 'screenshots');
const CONFIG_PATH = path.join(__dirname, '..', 'config', 'crawler_targets.json');

// Middleware
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use('/screenshots', express.static(SCREENSHOTS_DIR));

// ============================================================
// HELPER FUNCTIONS
// ============================================================

function readJSON(filepath) {
  try {
    if (fs.existsSync(filepath)) {
      return JSON.parse(fs.readFileSync(filepath, 'utf-8'));
    }
  } catch (e) {
    console.error(`Error reading ${filepath}:`, e.message);
  }
  return null;
}

function writeJSON(filepath, data) {
  try {
    fs.mkdirSync(path.dirname(filepath), { recursive: true });
    fs.writeFileSync(filepath, JSON.stringify(data, null, 2), 'utf-8');
    return true;
  } catch (e) {
    console.error(`Error writing ${filepath}:`, e.message);
    return false;
  }
}

function cleanPrice(val) {
  return parseFloat(val) || 0;
}

// ============================================================
// DIFF ENGINE (JavaScript implementation)
// ============================================================

function loadSnapshot(providerKey) {
  return readJSON(path.join(SNAPSHOTS_DIR, `${providerKey}_snapshot.json`)) || {};
}

function loadLongvanSnapshot() {
  return readJSON(path.join(SNAPSHOTS_DIR, 'longvan_domain_snapshot.json')) || {};
}

function compareDomainData(providerKey) {
  const compSnap = loadSnapshot(providerKey);
  const lvSnap = loadLongvanSnapshot();

  // Sanitize items — cap any suspiciously large transfer prices (>50M VND = corrupted data)
  // null means "not listed" — preserve that distinction vs. 0 (free)
  const sanitize = items => items.map(item => ({
    ...item,
    transfer_price: item.transfer_price === null ? null
      : (cleanPrice(item.transfer_price) > 50000000 ? null : cleanPrice(item.transfer_price)),
    register_price: item.register_price === null ? null : cleanPrice(item.register_price),
    renew_price: item.renew_price === null ? null : cleanPrice(item.renew_price),
  }));
  const compItems = sanitize(compSnap.items || []);
  const lvItems = sanitize(lvSnap.items || []);

  const lvMap = {};
  lvItems.forEach(item => { if (item.tld) lvMap[item.tld.toLowerCase()] = item; });

  const compMap = {};
  compItems.forEach(item => { if (item.tld) compMap[item.tld.toLowerCase()] = item; });

  const comparison = [];
  const fields = [
    { key: 'register_price', label: 'Giá đăng ký' },
    { key: 'renew_price', label: 'Giá gia hạn' },
    { key: 'transfer_price', label: 'Giá chuyển đổi' },
  ];

  Object.keys(compMap).forEach(tld => {
    const comp = compMap[tld];
    const lv = lvMap[tld] || {};

    fields.forEach(f => {
      const compVal = comp[f.key];
      const lvVal = lv[f.key];
      // Skip if either price is null ("not listed") — can't compare
      if (compVal === null || compVal === undefined) return;
      if (lvVal === null || lvVal === undefined) return;
      const compPrice = typeof compVal === 'number' ? compVal : cleanPrice(compVal);
      const lvPrice = typeof lvVal === 'number' ? lvVal : cleanPrice(lvVal);
      // Both must be >= 0 and at least one > 0 to compare
      if (compPrice < 0 || lvPrice < 0) return;
      if (compPrice === 0 && lvPrice === 0) return;
      const diff = compPrice - lvPrice;
      const base = Math.max(lvPrice, compPrice, 1);
      const pct = diff / base * 100;
      comparison.push({
        tld: comp.tld,
        field: f.label,
        competitor_price: compPrice,
        competitor_price_original: f.key === 'register_price' ? (comp.register_price_original || null) : null,
        longvan_price: lvPrice,
        longvan_price_original: f.key === 'register_price' ? (lv.register_price_original || null) : null,
        diff_amount: diff,
        diff_pct: Math.round(pct * 10) / 10,
        status: diff < 0 ? 'CHEAPER' : (diff > 0 ? 'EXPENSIVE' : 'EQUAL')
      });
    });

    // Tổng chi phí 2 năm (year 1 register + year 2 renew)
    const compReg = comp.register_price;
    const compRenew = comp.renew_price;
    const lvReg = lv.register_price;
    const lvRenew = lv.renew_price;
    if (compReg !== null && compReg !== undefined && compRenew !== null && compRenew !== undefined
      && lvReg !== null && lvReg !== undefined && lvRenew !== null && lvRenew !== undefined) {
      const comp2yr = compReg + compRenew;
      const lv2yr = lvReg + lvRenew;
      if (comp2yr >= 0 && lv2yr >= 0 && (comp2yr > 0 || lv2yr > 0)) {
        const diff = comp2yr - lv2yr;
        const base = Math.max(lv2yr, comp2yr, 1);
        const pct = diff / base * 100;
        comparison.push({
          tld: comp.tld,
          field: 'Tổng chi phí 2 năm',
          competitor_price: comp2yr,
          longvan_price: lv2yr,
          diff_amount: diff,
          diff_pct: Math.round(pct * 10) / 10,
          status: diff < 0 ? 'CHEAPER' : (diff > 0 ? 'EXPENSIVE' : 'EQUAL')
        });
      }
    }
  });

  const cheaper = comparison.filter(c => c.status === 'CHEAPER');
  const expensive = comparison.filter(c => c.status === 'EXPENSIVE');

  // TLD Availability
  const lvTlds = new Set(Object.keys(lvMap));
  const compTlds = new Set(Object.keys(compMap));
  const lvExclusive = [...lvTlds].filter(t => !compTlds.has(t)).sort();
  const compExclusive = [...compTlds].filter(t => !lvTlds.has(t)).sort();
  const common = [...lvTlds].filter(t => compTlds.has(t)).sort();

  // Build metric summaries for all 3 metrics
  function buildMetricSummary(filterField) {
    const filtered = comparison.filter(c => c.field === filterField);
    const cheaperItems = filtered.filter(c => c.status === 'CHEAPER');
    const expensiveItems = filtered.filter(c => c.status === 'EXPENSIVE');
    const equalItems = filtered.filter(c => c.status === 'EQUAL');
    return {
      cheaper_count: cheaperItems.length,
      expensive_count: expensiveItems.length,
      equal_count: equalItems.length,
      cheaper_tlds: cheaperItems.map(c => ({ tld: c.tld, diff: c.diff_amount, comp_price: c.competitor_price, lv_price: c.longvan_price })),
      expensive_tlds: expensiveItems.map(c => ({ tld: c.tld, diff: c.diff_amount, comp_price: c.competitor_price, lv_price: c.longvan_price })),
      equal_tlds: equalItems.map(c => c.tld),
    };
  }

  const metricSummaries = {
    register: buildMetricSummary('Giá đăng ký'),
    renew: buildMetricSummary('Giá gia hạn'),
    '2yr': buildMetricSummary('Tổng chi phí 2 năm'),
  };

  // Default tld_summary (backward compat) = 2yr
  const tld_summary = {
    total_common: common.length,
    ...metricSummaries['2yr'],
  };

  return {
    provider_key: providerKey,
    competitor_updated_at: compSnap.updated_at || '',
    longvan_updated_at: lvSnap.updated_at || '',
    competitor_url: compSnap.url || '',
    total_competitor_items: compItems.length,
    total_longvan_items: lvItems.length,
    common_tld_count: common.length,
    comparison,
    summary: {
      cheaper_count: cheaper.length,
      expensive_count: expensive.length,
      equal_count: comparison.length - cheaper.length - expensive.length,
    },
    tld_summary,
    metric_summaries: metricSummaries,
    tld_availability: {
      longvan_exclusive: lvExclusive,
      competitor_exclusive: compExclusive,
      common,
      longvan_total: lvTlds.size,
      competitor_total: compTlds.size,
    },
    competitor_items: compItems,
    longvan_items: lvItems,
  };
}

// ============================================================
// API ROUTES
// ============================================================

// Get comparison data for a competitor
app.get('/api/compare/:provider', (req, res) => {
  const providerKey = `${req.params.provider}_domain`;
  const result = compareDomainData(providerKey);
  res.json(result);
});

// Get Long Van benchmark snapshot
app.get('/api/longvan', (req, res) => {
  res.json(loadLongvanSnapshot());
});

// Get provider snapshot
app.get('/api/snapshot/:provider', (req, res) => {
  res.json(loadSnapshot(`${req.params.provider}_domain`));
});

// List screenshots
app.get('/api/screenshots', (req, res) => {
  try {
    if (!fs.existsSync(SCREENSHOTS_DIR)) {
      return res.json([]);
    }
    const files = fs.readdirSync(SCREENSHOTS_DIR)
      .filter(f => f.endsWith('.png') || f.endsWith('.jpg'))
      .map(f => ({
        filename: f,
        url: `/screenshots/${f}`,
        provider: f.split('_')[0],
        created: fs.statSync(path.join(SCREENSHOTS_DIR, f)).mtime,
      }))
      .sort((a, b) => b.created - a.created);
    res.json(files);
  } catch (e) {
    res.json([]);
  }
});

// Get crawler config
app.get('/api/config', (req, res) => {
  res.json(readJSON(CONFIG_PATH) || {});
});

// Update crawler config
app.post('/api/config', (req, res) => {
  if (writeJSON(CONFIG_PATH, req.body)) {
    res.json({ success: true });
  } else {
    res.status(500).json({ error: 'Failed to save config' });
  }
});

// Price history
app.get('/api/history/:provider', (req, res) => {
  const historyDir = path.join(SNAPSHOTS_DIR, 'history');
  if (!fs.existsSync(historyDir)) return res.json([]);

  const prefix = `${req.params.provider}_domain_`;
  try {
    const files = fs.readdirSync(historyDir)
      .filter(f => f.startsWith(prefix) && f.endsWith('.json'))
      .sort()
      .reverse()
      .slice(0, 10);

    const history = files.map(f => {
      const data = readJSON(path.join(historyDir, f));
      return {
        file: f,
        updated_at: data?.updated_at || '',
        total_items: (data?.items || []).length,
        items: data?.items || [],
      };
    });
    res.json(history);
  } catch (e) {
    res.json([]);
  }
});

// Trigger crawler
let crawlRunning = false;
app.post('/api/crawl', (req, res) => {
  if (crawlRunning) {
    return res.status(429).json({ error: 'Crawler đang chạy, vui lòng đợi...' });
  }
  crawlRunning = true;
  const { execFile } = require('child_process');
  const pythonPath = process.env.PYTHON_PATH || 'python';
  const mainScript = path.join(__dirname, '..', 'main.py');

  res.json({ status: 'started', message: 'Đang chạy crawler...' });

  execFile(pythonPath, [mainScript, '--all', '--force'], {
    cwd: path.join(__dirname, '..'),
    timeout: 300000, // 5 minutes max
    env: { ...process.env },
  }, (error, stdout, stderr) => {
    crawlRunning = false;
    if (error) {
      console.error(`Crawler error: ${error.message}`);
    } else {
      console.log(`Crawler completed:\n${stdout}`);
    }
  });
});

// Send report via Telegram and Email
app.post('/api/send-report', (req, res) => {
  const { execFile } = require('child_process');
  const pythonPath = process.env.PYTHON_PATH || 'python';
  const sendReportScript = path.join(__dirname, '..', 'scripts', 'send_report.py');

  execFile(pythonPath, [sendReportScript], {
    cwd: path.join(__dirname, '..'),
    timeout: 45000,
    env: { ...process.env },
  }, (error, stdout, stderr) => {
    if (error) {
      console.error(`Send report error: ${error.message}, stderr: ${stderr}`);
      return res.status(500).json({ error: stdout ? stdout.trim() : `Lỗi gửi báo cáo: ${error.message}` });
    }
    try {
      const result = JSON.parse(stdout.trim());
      if (result.error) {
        return res.status(400).json({ error: result.error });
      }
      res.json(result);
    } catch (e) {
      res.json({ success: true, message: stdout.trim() || 'Đã gửi báo cáo!' });
    }
  });
});

// Crawler status (check if running)
app.get('/api/crawl/status', (req, res) => {
  res.json({ running: crawlRunning });
});

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start server
app.listen(PORT, () => {
  console.log(`\n⚡ Market AI Dashboard running at http://localhost:${PORT}`);
  console.log(`📂 Snapshots: ${SNAPSHOTS_DIR}`);
  console.log(`📸 Screenshots: ${SCREENSHOTS_DIR}\n`);
});
