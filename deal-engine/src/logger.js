const fs = require('fs');
const path = require('path');

const LOGS_DIR = path.join(__dirname, '..', 'logs');

function getLogPath() {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return path.join(LOGS_DIR, `run_${ts}.txt`);
}

class Logger {
  constructor() {
    if (!fs.existsSync(LOGS_DIR)) fs.mkdirSync(LOGS_DIR, { recursive: true });
    this.logPath = getLogPath();
    this.lines = [];
    this._write(`=== Deal Engine Run — ${new Date().toISOString()} ===\n`);
  }

  _write(msg) {
    const line = `[${new Date().toISOString()}] ${msg}`;
    process.stdout.write(line + '\n');
    this.lines.push(line);
    fs.appendFileSync(this.logPath, line + '\n');
  }

  info(msg)  { this._write(`INFO  ${msg}`); }
  warn(msg)  { this._write(`WARN  ${msg}`); }
  error(msg) { this._write(`ERROR ${msg}`); }

  summary(draftsCreated, sources) {
    this._write(`\n--- SUMMARY ---`);
    this._write(`Drafts created: ${draftsCreated}`);
    this._write(`Sources used: ${sources.join(', ') || 'none'}`);
    this._write(`Log saved to: ${this.logPath}`);
  }
}

module.exports = { Logger };
