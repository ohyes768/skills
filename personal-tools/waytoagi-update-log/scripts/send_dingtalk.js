#!/usr/bin/env node
/**
 * Compatibility shim: locates the public dingtalk-push CLI; never sends HTTP itself.
 *
 * Canonical source: personal-tools/dingtalk-push/scripts/dingtalk_send.py.
 * Old usage kept: node send_dingtalk.js "<webhook_url>" "<markdown>"
 * Markdown may also arrive via stdin (used by cron_runner.js): when the text
 * argument is empty and stdin is piped, stdin is forwarded to --file -.
 * The webhook argument is optional; without it the CLI falls back to this
 * skill's .env (DINGTALK_WEBHOOK), which is passed only when the file exists.
 * Dedupe uses the CLI's automatic content key, and the robot keyword is
 * asserted before POST.
 */

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const TITLE = 'WaytoAGI 更新日报';
const KEYWORD = 'WaytoAGI';

function locateScript() {
  const configured = process.env.DINGTALK_PUSH_SKILL_DIR;
  if (configured) {
    const candidate = path.join(configured, 'scripts', 'dingtalk_send.py');
    if (!fs.existsSync(candidate)) {
      console.error('DINGTALK_PUSH_SKILL_DIR must contain scripts/dingtalk_send.py');
      process.exit(2);
    }
    return candidate;
  }
  const relatives = [
    'dingtalk-push/scripts/dingtalk_send.py',
    'personal-tools/dingtalk-push/scripts/dingtalk_send.py',
  ];
  let dir = __dirname;
  for (let depth = 0; depth < 12; depth++) {
    for (const rel of relatives) {
      const candidate = path.join(dir, rel);
      if (fs.existsSync(candidate)) return candidate;
    }
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  const home = process.env.HOME || process.env.USERPROFILE || '';
  for (const root of [home + '/.hermes/skills', home + '/.codex/skills', home + '/.agents/skills']) {
    if (!root) continue;
    const candidate = path.join(root, 'dingtalk-push', 'scripts', 'dingtalk_send.py');
    if (fs.existsSync(candidate)) return candidate;
  }
  console.error('Install dingtalk-push and set DINGTALK_PUSH_SKILL_DIR to its package directory');
  process.exit(2);
}

function cliArgs(webhook) {
  const args = ['send', '--title', TITLE, '--keyword', KEYWORD, '--file', '-'];
  const envFile = path.join(__dirname, '..', '.env');
  if (fs.existsSync(envFile)) args.push('--env-file', envFile);
  if (webhook && webhook.trim()) args.push('--webhook', webhook.trim());
  return args;
}

// One bounded POST inside the CLI; do not kill this child at a parent timeout.
function sendViaStdin(markdown, webhook) {
  const python = process.env.DINGTALK_PYTHON || 'python';
  return spawnSync(python, [locateScript()].concat(cliArgs(webhook)), { input: markdown, encoding: 'utf8' });
}

if (require.main === module) {
  let markdown = process.argv.slice(3).join(' ');
  if (!markdown.trim() && !process.stdin.isTTY) {
    markdown = fs.readFileSync(0, 'utf8');
  }
  if (!markdown.trim()) {
    console.error('用法: node send_dingtalk.js "<webhook_url可选>" "<markdown_text>"；正文也可经 stdin 传入');
    process.exit(1);
  }
  const child = sendViaStdin(markdown, process.argv[2] || '');
  if (child.error) {
    console.error('无法启动公共 dingtalk-push CLI: ' + child.error.message);
    process.exit(2);
  }
  if (child.stdout) process.stdout.write(child.stdout);
  if (child.stderr) process.stderr.write(child.stderr);
  process.exit(child.status === null ? 1 : child.status);
}

module.exports = { TITLE, KEYWORD, locateScript, sendViaStdin };
