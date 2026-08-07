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

const crypto = require('crypto');
const jwt = require('jsonwebtoken');
const JWT_SECRET = process.env.JWT_SECRET || 'LONGVAN_MARKET_AI_JWS_SECRET_2026';

function generateAccessToken(user) {
  return jwt.sign({
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    role: user.role || 'user'
  }, JWT_SECRET, { algorithm: 'HS256', expiresIn: '15m' }); // Short-lived 15m
}

function generateRefreshToken(user) {
  return jwt.sign({
    id: user.id,
    email: user.email,
    type: 'refresh',
    jti: crypto.randomBytes(16).toString('hex')
  }, JWT_SECRET, { algorithm: 'HS256', expiresIn: '30d' }); // Long-lived 30d
}

function authenticateToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  const token = (authHeader && authHeader.split(' ')[1]) || req.query.token;

  if (!token) {
    return res.status(401).json({ error: 'Chưa đăng nhập. Vui lòng đăng nhập bằng Email doanh nghiệp @longvan.net' });
  }

  jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] }, (err, user) => {
    if (err) {
      return res.status(403).json({ error: 'Token hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại @longvan.net' });
    }
    req.user = user;
    next();
  });
}

function runAuthPy(method, argsObj, cb) {
  const { exec } = require('child_process');
  const base64Args = Buffer.from(JSON.stringify(argsObj), 'utf-8').toString('base64');
  const pyCode = `import json, base64; from core.auth_service import AuthService; auth = AuthService(); args = json.loads(base64.b64decode('${base64Args}').decode('utf-8')); res = getattr(auth, '${method}')(**args); print(json.dumps(res, ensure_ascii=False))`;
  const cmd = `python3 -X utf8 -c "${pyCode}" || python -X utf8 -c "${pyCode}"`;
  exec(cmd, { cwd: path.join(__dirname, '..'), env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }, (err, stdout) => {
    if (err && !stdout) {
      return cb(err, null);
    }
    try {
      const jsonLine = (stdout || '').trim().split('\n').filter(l => l.trim().startsWith('{')).pop();
      const parsed = JSON.parse(jsonLine);
      cb(null, parsed);
    } catch (e) {
      cb(e, null);
    }
  });
}

// Middleware
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use('/screenshots', express.static(SCREENSHOTS_DIR));

// AUTHENTICATION API ROUTES
app.post('/api/auth/register', (req, res) => {
  const { email, full_name, password } = req.body;
  runAuthPy('register', { email, full_name: full_name || 'Cán bộ Long Vân', password }, (err, result) => {
    if (err || !result) return res.status(500).json({ error: 'Lỗi hệ thống khi đăng ký tài khoản.' });
    if (result.error) return res.status(400).json(result);
    res.json(result);
  });
});

app.post('/api/auth/verify-otp', (req, res) => {
  const { email, otp_code, otp_type } = req.body;
  runAuthPy('verify_otp', { email, otp_code, otp_type: otp_type || 'REGISTRATION' }, (err, result) => {
    if (err || !result) return res.status(500).json({ error: 'Lỗi xác thực mã OTP.' });
    if (result.error) return res.status(400).json(result);
    if (result.user) {
      const accessToken = generateAccessToken(result.user);
      const refreshToken = generateRefreshToken(result.user);
      runAuthPy('save_refresh_token', { email: result.user.email, token: refreshToken }, () => { });
      result.token = accessToken;
      result.accessToken = accessToken;
      result.refreshToken = refreshToken;
    }
    res.json(result);
  });
});

app.post('/api/auth/login', (req, res) => {
  const { email, password } = req.body;
  runAuthPy('login', { email, password }, (err, result) => {
    if (err || !result) return res.status(500).json({ error: 'Lỗi hệ thống khi đăng nhập.' });
    if (result.error) return res.status(400).json(result);
    const accessToken = generateAccessToken(result.user);
    const refreshToken = generateRefreshToken(result.user);
    runAuthPy('save_refresh_token', { email: result.user.email, token: refreshToken }, () => { });
    result.token = accessToken;
    result.accessToken = accessToken;
    result.refreshToken = refreshToken;
    res.json(result);
  });
});

app.post('/api/auth/refresh', (req, res) => {
  const { refreshToken } = req.body;
  if (!refreshToken) {
    return res.status(401).json({ error: 'Thiếu Refresh Token' });
  }

  jwt.verify(refreshToken, JWT_SECRET, { algorithms: ['HS256'] }, (err, decoded) => {
    if (err || decoded.type !== 'refresh') {
      return res.status(403).json({ error: 'Refresh Token hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại.' });
    }

    runAuthPy('verify_refresh_token', { token: refreshToken }, (pyErr, result) => {
      if (pyErr || !result || result.error) {
        return res.status(403).json({ error: result?.error || 'Refresh Token bị thu hồi.' });
      }

      const newAccessToken = generateAccessToken(result.user);
      res.json({
        accessToken: newAccessToken,
        token: newAccessToken,
        user: result.user
      });
    });
  });
});

app.post('/api/auth/logout', (req, res) => {
  const { refreshToken } = req.body;
  if (refreshToken) {
    runAuthPy('revoke_refresh_token', { token: refreshToken }, () => { });
  }
  res.json({ success: true, message: 'Đã đăng xuất thành công' });
});

app.post('/api/auth/forgot-password', (req, res) => {
  const { email } = req.body;
  runAuthPy('forgot_password', { email }, (err, result) => {
    if (err || !result) return res.status(500).json({ error: 'Lỗi hệ thống khi yêu cầu quên mật khẩu.' });
    if (result.error) return res.status(400).json(result);
    res.json(result);
  });
});

app.post('/api/auth/reset-password', (req, res) => {
  const { email, otp_code, new_password } = req.body;
  runAuthPy('reset_password', { email, otp_code, new_password }, (err, result) => {
    if (err || !result) return res.status(500).json({ error: 'Lỗi hệ thống khi đặt lại mật khẩu.' });
    if (result.error) return res.status(400).json(result);
    res.json(result);
  });
});

app.get('/api/auth/me', authenticateToken, (req, res) => {
  res.json({ user: req.user });
});

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
// API ROUTES (AUTHENTICATION PROTECTED)
// ============================================================

// Get comparison data for a competitor
app.get('/api/compare/:provider', authenticateToken, (req, res) => {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  const providerKey = `${req.params.provider}_domain`;
  const result = compareDomainData(providerKey);
  res.json(result);
});

// Get AI Analysis for a provider
app.get('/api/ai-analysis/:provider', authenticateToken, (req, res) => {
  const provider = req.params.provider.toLowerCase();
  const force = req.query.force === 'true' ? 'True' : 'False';
  const providerName = provider === 'pavietnam' ? 'PA VIỆT NAM' : (provider === 'matbao' ? 'MẮT BÃO' : provider.toUpperCase());
  const { exec } = require('child_process');
  const pyScript = `import json; from core.diff_engine import DiffEngine; from core.ai_analyzer import AIAnalyzer; de = DiffEngine(); snap = de.load_last_snapshot('${provider}_domain'); diff = de.compare_domain_data('${provider}_domain', snap.get('items', []), save=False); ai = AIAnalyzer(); print(json.dumps({'analysis': ai.analyze_market_changes('${providerName}', 'domain', diff, force_refresh=${force})}, ensure_ascii=False))`;
  const pythonCmd = `python3 -X utf8 -c "${pyScript}" || python -X utf8 -c "${pyScript}"`;

  exec(pythonCmd, { cwd: path.join(__dirname, '..'), env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }, (err, stdout) => {
    if (err) {
      console.error('Lỗi gọi AI Analyzer:', err);
      return res.json({ analysis: '⚠️ Chưa thể khởi tạo phân tích AI lúc này.' });
    }
    try {
      const parsed = JSON.parse(stdout.trim());
      res.json(parsed);
    } catch (e) {
      res.json({ analysis: stdout.trim() });
    }
  });
});

// Get Long Van benchmark snapshot
app.get('/api/longvan', authenticateToken, (req, res) => {
  res.json(loadLongvanSnapshot());
});

// Get provider snapshot
app.get('/api/snapshot/:provider', authenticateToken, (req, res) => {
  res.json(loadSnapshot(`${req.params.provider}_domain`));
});

// List screenshots
app.get('/api/screenshots', authenticateToken, (req, res) => {
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
app.get('/api/config', authenticateToken, (req, res) => {
  res.json(readJSON(CONFIG_PATH) || {});
});

// Update crawler config
app.post('/api/config', authenticateToken, (req, res) => {
  if (writeJSON(CONFIG_PATH, req.body)) {
    res.json({ success: true });
  } else {
    res.status(500).json({ error: 'Failed to save config' });
  }
});

// Price history
app.get('/api/history/:provider', authenticateToken, (req, res) => {
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

const http = require('http');

function callScheduler(method, pathStr) {
  return new Promise((resolve, reject) => {
    const host = process.env.SCHEDULER_HOST || '127.0.0.1';
    const req = http.request({
      hostname: host,
      port: 5001,
      path: pathStr,
      method: method,
      timeout: 2000,
      headers: { 'Content-Type': 'application/json' }
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        if (res.statusCode === 200 || res.statusCode === 429) {
          try { resolve(JSON.parse(body)); } catch (e) { resolve({ status: 'ok' }); }
        } else {
          reject(new Error(`Scheduler API error ${res.statusCode}`));
        }
      });
    });
    req.on('error', (err) => {
      const altHost = host === '127.0.0.1' ? 'scheduler' : '127.0.0.1';
      const req2 = http.request({
        hostname: altHost,
        port: 5001,
        path: pathStr,
        method: method,
        timeout: 2000,
        headers: { 'Content-Type': 'application/json' }
      }, (res2) => {
        let body2 = '';
        res2.on('data', chunk => body2 += chunk);
        res2.on('end', () => {
          try { resolve(JSON.parse(body2)); } catch (e) { resolve({ status: 'ok' }); }
        });
      });
      req2.on('error', reject);
      req2.on('timeout', () => { req2.destroy(); reject(err); });
      req2.end();
    });
    req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
    req.end();
  });
}

let isLocalCrawlRunning = false;
let crawlStartTime = 0;

// Trigger crawler
app.post('/api/crawl', authenticateToken, async (req, res) => {
  try {
    const result = await callScheduler('POST', '/trigger/all');
    console.log('[Dashboard] Đã kích hoạt cào dữ liệu qua Scheduler API thành công:', result);
    return res.json({ status: 'started', message: 'Đã kích hoạt cào dữ liệu qua Scheduler!' });
  } catch (e) {
    console.warn('[Dashboard] Scheduler API không khả dụng, chuyển sang chạy trực tiếp main.py:', e.message);
    const { exec } = require('child_process');
    const mainScript = path.join(__dirname, '..', 'main.py');
    const cmd = `python3 "${mainScript}" --all --force || python "${mainScript}" --all --force`;

    isLocalCrawlRunning = true;
    crawlStartTime = Date.now();

    res.json({ status: 'started', message: 'Đang chạy Playwright crawler cho tất cả nhà cung cấp...' });

    exec(cmd, {
      cwd: path.join(__dirname, '..'),
      timeout: 300000,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    }, (error, stdout) => {
      isLocalCrawlRunning = false;
      if (error) console.error(`Crawler exec error: ${error.message}`);
      else console.log(`Crawler completed:\n${stdout}`);
    });
  }
});

// Crawler status (check if running)
app.get('/api/crawl/status', async (req, res) => {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  try {
    const statusData = await callScheduler('GET', '/status');
    if (statusData && statusData.running) {
      return res.json({ running: true, progress: statusData.progress || 50, message: statusData.message || 'Đang cào dữ liệu thị trường...' });
    }
  } catch (e) {}

  if (isLocalCrawlRunning) {
    const elapsed = Math.floor((Date.now() - crawlStartTime) / 1000);
    const estimatedProgress = Math.min(95, Math.floor((elapsed / 25) * 100));
    return res.json({
      running: true,
      progress: estimatedProgress,
      message: `Đang cào dữ liệu Playwright từ các nhà cung cấp (${elapsed}s)...`
    });
  }

  return res.json({ running: false, progress: 100, message: 'Hoàn tất' });
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
