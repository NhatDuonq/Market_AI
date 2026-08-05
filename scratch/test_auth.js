const path = require('path');
const { exec } = require('child_process');

function runAuthPy(method, argsObj, cb) {
  const base64Args = Buffer.from(JSON.stringify(argsObj), 'utf-8').toString('base64');
  const pyCode = `import json, base64; from core.auth_service import AuthService; auth = AuthService(); args = json.loads(base64.b64decode('${base64Args}').decode('utf-8')); res = getattr(auth, '${method}')(**args); print(json.dumps(res, ensure_ascii=False))`;
  const cmd = `python -X utf8 -c "${pyCode}"`;
  exec(cmd, { cwd: path.join(__dirname, '..'), env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }, (err, stdout, stderr) => {
    if (err && !stdout) {
      console.error('EXEC ERROR:', err, stderr);
      return cb(err, null);
    }
    try {
      const jsonLine = (stdout || '').trim().split('\n').filter(l => l.trim().startsWith('{')).pop();
      const parsed = JSON.parse(jsonLine);
      cb(null, parsed);
    } catch (e) {
      console.error('PARSE ERROR:', e, stdout);
      cb(e, null);
    }
  });
}

runAuthPy('register', { email: 'duong.test@longvan.net', full_name: 'Nhật Dương', password: 'Password123' }, (err, res) => {
  console.log('\nFINAL RESULT SUCCESS:', res);
});
