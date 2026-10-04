// 自动打开 Coremail 并确保处于已登录状态。占位符：__URL__
// 流程：已登录 → goto → 点「重新登录」→ 点「登录」→ 轮询等待邮箱就绪
// 注意：账号密码由浏览器自动填充，全程不要读取 / 回显密码字段的值。
const URL = __URL__;
const ALLOW_GOTO = __GOTO__;   // false：只做登录补全，绝不跳转当前页面
const HOST = 'wemail.webank.com';

async function ready() {
  try {
    return await page.evaluate(() => {
      if (!document.querySelector('#lyfullsearch')) return false;
      // 「会话已过期」弹层出现时 #lyfullsearch 仍在 DOM 里，但遮罩(.u-mask)会拦截一切点击。
      // 有可见 .u-dialog 时不算就绪（2026-09-04 修复：此前误报 already）。
      const dlg = [...document.querySelectorAll('.u-dialog')].some(
        e => e.offsetParent !== null && getComputedStyle(e).display !== 'none');
      return !dlg;
    });
  } catch (e) { return false; }
}
async function waitReady(ms) {
  const steps = Math.max(1, Math.ceil(ms / 3000));
  for (let i = 0; i < steps; i++) {
    if (await ready()) return true;
    await page.waitForTimeout(3000);
  }
  return await ready();
}
async function snapshot() {
  try {
    return await page.evaluate(() => (document.body ? document.body.innerText : '')
      .replace(/\s+/g, ' ').slice(0, 300));
  } catch (e) { return ''; }
}

let mode = 'unknown';
let detail = '';

if (await ready()) {
  mode = 'already';
} else {
  const cur = page.url() || '';
  if (cur.indexOf(HOST) < 0) {
    if (!ALLOW_GOTO) {
      return { ok: false, mode: 'not-on-site', detail: '', url: cur, title: await page.title() };
    }
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(5000);
    mode = 'goto';
  }
  if (!(await ready())) {
    // 会话过期弹层：点弹层里的「重新登录」按钮。
    // 必须限定 .u-dialog 内的 button——纯 text=重新登录 可能命中非按钮文本，
    // click 看似成功但弹层不消失（2026-09-04 实测踩坑）。
    const relogin = page.locator('.u-dialog button:has-text("重新登录")').first();
    try {
      if (await relogin.count() > 0) {
        await relogin.click({ timeout: 5000 });
        await page.waitForTimeout(5000);
        mode = 'relogin';
      }
    } catch (e) { detail += 'relogin:' + String(e).slice(0, 80) + ' '; }

    if (!(await ready())) {
      // 账号密码已自动填充，直接点登录按钮（不要碰 #fakePassword / #password）
      const btn = page.locator('button.j-submit').first();
      let clicked = 'no';
      try {
        if (await btn.count() > 0) { await btn.click({ timeout: 15000 }); clicked = 'yes'; }
        else { clicked = 'not-found'; }
      } catch (e) { clicked = String(e).slice(0, 120); }
      detail += 'click=' + clicked;
      const ok = await waitReady(30000);
      mode = ok ? 'login' : 'login-failed';
    }
  }
}

// 重新登录后邮件列表仍是旧 DOM 快照（分组停在上次加载时刻），必须点「刷新」拉最新列表。
let refreshed = false;
if (await ready()) {
  try {
    await page.locator('span[data-btn="refresh"]').first().click({ timeout: 5000 });
    await page.waitForTimeout(3000);
    refreshed = true;
  } catch (e) { refreshed = false; }
}

return { ok: await ready(), mode: mode, detail: detail, refreshed: refreshed, url: page.url(), title: await page.title() };
