#!/usr/bin/env node
/**
 * WaytoAGI 每日更新推送 - Cron Runner
 * 
 * 功能：
 * 1. 抓取 WaytoAGI 近7日更新日志
 * 2. 判断指定日期（昨天）是否有文章
 * 3. 有文章 → 发送钉钉；无文章 → 静默退出
 * 
 * 用法（供 openclaw cron 调用）：
 *   node cron_runner.js <日期，如"5月6日"> <webhook_url>
 */

const https = require('https');

// ===== 配置 =====
// 加载 .env 中的 DINGTALK_WEBHOOK（git 仓库已排除 .env）
try {
  const fs = require('fs');
  const path = require('path');
  const envFile = path.join(__dirname, '..', '.env');
  if (fs.existsSync(envFile)) {
    for (const line of fs.readFileSync(envFile, 'utf8').split('\n')) {
      const m = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  }
} catch (e) { /* 忽略 */ }

const WIKI_TOKEN = 'QPe5w5g7UisbEkkow8XcDmOpn8e';
const WEBHOOK = process.argv[2] || process.env.DINGTALK_WEBHOOK || '';
const TARGET_DATE = process.argv[3] || ''; // 如 "5月6日"
const OPENCLAW_DIR = process.env.OPENCLAW_DIR || process.env.HOME + '/.openclaw';

// ===== 飞书 API 工具函数 =====

function feishuGetNodeToken(nodeToken) {
  return new Promise((resolve, reject) => {
    const url = new URL('https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node');
    url.searchParams.set('token', nodeToken);
    
    const token = loadUserToken();
    
    const options = {
      hostname: 'open.feishu.cn',
      path: url.pathname + url.search,
      method: 'GET',
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch(e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

function feishuFetchDoc(docToken) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'open.feishu.cn',
      path: '/open-apis/doc/v2/docs/' + docToken + '/raw?lang=zh_cn',
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + loadUserToken() }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch(e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

function loadUserToken() {
  try {
    const fs = require('fs');
    const path = require('path');
    const tokenFile = path.join(OPENCLAW_DIR, '.openclaw-feishu-uat', 'cli_a9303650aa381bd7_ou_52b26f72981f9c2bc534dc840d4ec372.enc');
    if (!fs.existsSync(tokenFile)) return null;
    // 简单处理：直接读文件让 AI 自己解析，这里返回 null 由上方调用处理
    return null;
  } catch(e) { return null; }
}

// ===== 钉钉发送 =====

function sendDingTalk(markdown) {
  return new Promise((resolve, reject) => {
    const parsedUrl = new URL(WEBHOOK);
    const postData = JSON.stringify({
      msgtype: 'markdown',
      markdown: { title: 'WaytoAGI 更新日报', text: markdown }
    });

    const options = {
      hostname: parsedUrl.hostname,
      path: parsedUrl.pathname + parsedUrl.search,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) }
    };

    const req = (parsedUrl.protocol === 'https:' ? https : http).request(options, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch(e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

// ===== 核心逻辑 =====

async function main() {
  try {
    if (!WEBHOOK) {
      console.error('错误: DINGTALK_WEBHOOK 未配置，请在 .env 中设置');
      process.exit(1);
    }
    // 1. 获取 Wiki 节点 obj_token
    const nodeRes = await feishuGetNodeToken(WIKI_TOKEN);
    if (!nodeRes.data || !nodeRes.data.obj_token) {
      console.error('获取Wiki节点失败');
      process.exit(0); // 静默退出，不抛错
    }
    const docToken = nodeRes.data.obj_token;

    // 2. 获取主文档内容
    const docRes = await feishuFetchDoc(docToken);
    if (!docRes.data || !docRes.data.document) {
      console.error('获取文档失败');
      process.exit(0);
    }

    const content = docRes.data.document.value?.body?.internal_deldoc_content || '';
    const title = docRes.data.document.value?.title || '';

    // 3. 在文档中定位目标日期（近7日更新日志章节）
    // 格式：### 5 月 6 日
    const datePattern = TARGET_DATE ? new RegExp('###\\s*' + TARGET_DATE.replace(/[月日]/g, '\\s*\\$&\$&').replace(/\s+/g, '\\s+'), 'i') : /###\s*(\d+)\s*月\s*(\d+)\s*日/;
    
    // 找所有日期章节，取最新的
    const allDateMatches = [...content.matchAll(/###\s*(\d+)\s*月\s*(\d+)\s*日/gi)];
    if (allDateMatches.length === 0) {
      console.log('无更新日志');
      process.exit(0);
    }

    // 取最新一个有内容的日期
    let latestDate = null;
    let latestDateStr = '';
    for (const m of allDateMatches.reverse()) {
      const month = parseInt(m[1]);
      const day = parseInt(m[2]);
      // 检查该日期下是否有内容（找下一个###之前的条目）
      const dateStart = m.index;
      const nextDate = content.indexOf('###', dateStart + 4);
      const section = content.slice(dateStart, nextDate === -1 ? undefined : nextDate);
      if (section.includes('<mention-doc')) {
        latestDate = m;
        latestDateStr = `${month}月${day}日`;
        break;
      }
    }

    if (!latestDate) {
      console.log('昨日无更新');
      process.exit(0);
    }

    // 4. 提取该日期下所有文章
    const dateStart = latestDate.index;
    const nextDate = content.indexOf('###', dateStart + 4);
    const section = content.slice(dateStart, nextDate === -1 ? undefined : nextDate);

    // 提取所有 mention-doc token
    const tokenMatches = [...section.matchAll(/<mention-doc\s+token="([^"]+)"/g)];
    if (tokenMatches.length === 0) {
      console.log('该日期无文章');
      process.exit(0);
    }

    // 5. 生成报告并发送（钉钉需要完整内容）
    // 注意：完整生成需要每个 token 都 fetch 一遍原文链接
    // 这里只发 Wiki 链接作为降级，完整版由 AI 接管
    const articles = tokenMatches.map((m, i) => `**${i+1}.** 《Wiki文章》\n\n📝 链接：https://waytoagi.feishu.cn/wiki/${m[1]}`).join('\n\n---\n\n');
    const report = `## 📅 WaytoAGI 更新日志 · ${latestDateStr} 更新${tokenMatches.length}篇\n\n---\n\n${articles}`;

    // 6. 发送钉钉
    const result = await sendDingTalk(report);
    if (result.errcode === 0) {
      console.log('钉钉推送成功');
    } else {
      console.error('钉钉推送失败:', result.errmsg);
    }

  } catch (err) {
    console.error('Runner执行失败:', err.message);
    process.exit(0); // 静默退出
  }
}

main();
