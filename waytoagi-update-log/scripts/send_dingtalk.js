#!/usr/bin/env node
/**
 * 发送 Markdown 内容到钉钉群机器人
 * 
 * 用法：
 *   node send_dingtalk.js "access_token" "markdown内容"
 * 
 * 示例：
 *   node send_dingtalk.js "https://oapi.dingtalk.com/robot/send?access_token=xxx" "$(cat message.md)"
 */

const https = require('https');
const http = require('http');
const url = require('url');

function sendDingTalk(webhook, markdown) {
  const parsedUrl = new URL(webhook);
  
  const postData = JSON.stringify({
    msgtype: 'markdown',
    markdown: {
      title: 'WaytoAGI 更新日报',
      text: markdown
    }
  });

  const options = {
    hostname: parsedUrl.hostname,
    path: parsedUrl.pathname + parsedUrl.search,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(postData)
    }
  };

  return new Promise((resolve, reject) => {
    const req = (parsedUrl.protocol === 'https:' ? https : http).request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          if (result.errcode === 0 || result.errmsg === 'ok') {
            resolve(result);
          } else {
            reject(new Error(`钉钉返回错误: ${result.errmsg}`));
          }
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

// 命令行调用
if (require.main === module) {
  const webhook = process.argv[2];
  const markdown = process.argv.slice(3).join(' ');

  if (!webhook || !markdown) {
    console.error('用法: node send_dingtalk.js "<webhook_url>" "<markdown_text>"');
    process.exit(1);
  }

  sendDingTalk(webhook, markdown)
    .then(res => console.log('发送成功:', JSON.stringify(res)))
    .catch(err => {
      console.error('发送失败:', err.message);
      process.exit(1);
    });
}

module.exports = { sendDingTalk };
