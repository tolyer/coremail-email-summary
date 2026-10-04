// 把检索到的邮件移动到指定文件夹。
// 占位符：__Q__（搜索词，空字符串表示用当前列表）、__TO__（目标文件夹名）、
//         __IDX__（要移动的行索引数组，空数组 = 全部匹配行）、__APPLY__（false = 只预演）、__LIMIT__（单次上限）
//
// 安全约束（由外层 tabbit.py / guards.py 保证，本脚本不重复实现）：
//   * 不会执行任何形式的删除
//   * 目标文件夹若命中「垃圾箱 / 已删除」等黑名单，外层直接拒绝
//   * APPLY=false 时只返回清单，不改动任何邮件
const Q = __Q__;
const TO = __TO__;
const IDX = __IDX__;
const APPLY = __APPLY__;
const LIMIT = __LIMIT__;

await page.setViewportSize({ width: 1600, height: 1000 });
await page.waitForTimeout(700);

if (Q) {
  await page.fill('#lyfullsearch', Q);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(7000);
}

const all = await page.evaluate(() => {
  const out = [];
  Array.from(document.querySelectorAll('tr.j-mail')).forEach((n, i) => {
    const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
    if (t) out.push({ i: i, text: t.slice(0, 160) });
  });
  return out;
});

// 相关性校验：Coremail 全文检索是 OR/模糊匹配，列表里会混进大量无关邮件
// （实测搜 "Clarification Required" 时前几行是日历通知）。
// 因此移动前强制要求：行文本必须命中检索词的关键片段，否则视为误伤，直接剔除。
function relevant(row) {
  if (!Q) return true;
  const toks = Q.split(/\s+/).filter(t => t.length >= 3);
  const keys = toks.length ? toks : [Q];
  const low = row.text.toLowerCase();
  return keys.every(k => low.indexOf(k.toLowerCase()) >= 0);
}
const matched = Q ? all.filter(relevant) : all;
const targets = IDX.length ? matched.filter(r => IDX.indexOf(r.i) >= 0) : matched;
const dropped = (IDX.length ? all.filter(r => IDX.indexOf(r.i) >= 0) : all).length - targets.length;

const plan = {
  query: Q,
  to: TO,
  apply: APPLY,
  total: all.length,
  matched: matched.length,
  droppedUnrelated: dropped,   // 因不命中检索词而被剔除的数量
  selected: targets.length,
  limit: LIMIT,
  items: targets.map(r => ({ i: r.i, text: r.text }))
};

if (targets.length === 0) {
  plan.status = 'no-match';
  plan.reason = Q
    ? '没有邮件同时命中检索词「' + Q + '」的全部关键片段（已剔除 '
      + dropped + ' 条无关项），未改动任何邮件'
    : '没有匹配的邮件';
  return plan;
}
if (targets.length > LIMIT) {
  plan.status = 'over-limit';
  plan.reason = '选中 ' + targets.length + ' 封，超过单次上限 ' + LIMIT + '，请缩小范围或分批';
  return plan;
}

if (!APPLY) {
  plan.status = 'dry-run';
  plan.reason = '仅预演，未改动任何邮件；确认无误后加 --apply 执行';
  return plan;
}

// ---------------- 真正执行移动 ----------------
const cbOf = i => page.locator('tr.j-mail').nth(i).locator('span.mail-check').first();

const picked = [];
for (const r of targets) {
  try {
    await cbOf(r.i).click({ force: true, timeout: 6000 });
    picked.push(r.i);
  } catch (e) {
    plan.pickError = plan.pickError || [];
    plan.pickError.push({ i: r.i, err: String(e).slice(0, 90) });
  }
}
await page.waitForTimeout(1200);

const checkedCount = await page.evaluate(() =>
  Array.from(document.querySelectorAll('tr.j-mail input.rc-hidden')).filter(c => c.checked).length);
plan.checkedCount = checkedCount;

if (checkedCount === 0) {
  plan.status = 'not-checked';
  plan.reason = '没有任何邮件被勾选，已中止，未改动任何邮件';
  return plan;
}

// 点工具栏「移动到」
const mv = page.locator('span.u-btn:has-text("移动到")').first();
try {
  await mv.click({ timeout: 8000 });
  plan.menuOpened = 'yes';
} catch (e) {
  plan.status = 'menu-failed';
  plan.reason = '无法打开「移动到」菜单：' + String(e).slice(0, 90);
  return plan;
}
await page.waitForTimeout(2200);

// 定位可见的下拉层（页面上有多个 .u-menu-dropdown，只有一个是可见的）
plan.folder = await page.evaluate((to) => {
  const dds = Array.from(document.querySelectorAll('.u-menu-dropdown'))
    .filter(n => getComputedStyle(n).display !== 'none');
  for (const dd of dds) {
    const links = Array.from(dd.querySelectorAll('a.f-csp'));
    const hit = links.find(a => (a.innerText || '').trim() === to);
    if (hit) {
      hit.click();
      return { found: true, count: links.length, options: links.slice(0, 20).map(a => (a.innerText || '').trim()) };
    }
  }
  const allOpts = [];
  dds.forEach(dd => Array.from(dd.querySelectorAll('a.f-csp')).forEach(a => allOpts.push((a.innerText || '').trim())));
  return { found: false, visibleDd: dds.length, options: allOpts.slice(0, 60) };
}, TO);

await page.waitForTimeout(3000);

if (!plan.folder || !plan.folder.found) {
  // 没找到目标文件夹 → 收起菜单，取消所有勾选，保持原状
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);
  for (const i of picked) {
    await cbOf(i).click({ force: true, timeout: 4000 }).catch(() => {});
  }
  plan.status = 'folder-not-found';
  plan.reason = '菜单里没找到目标文件夹「' + TO + '」，已取消勾选，未改动任何邮件';
  return plan;
}

plan.status = 'moved';
plan.moved = picked.length;
plan.reason = '已提交移动到「' + TO + '」，请在浏览器里确认结果';
return plan;
