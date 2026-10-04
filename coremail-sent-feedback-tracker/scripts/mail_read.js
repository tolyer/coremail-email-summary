// 读取单封邮件。
// MODE = 'index' : 直接按 __IDX__ 点击当前列表的第 N 行
// MODE = 'key'   : 先搜索 __Q__，再定位同时包含 __KEYS__ 中所有片段的行
// 返回 { idx, header:{block,from,to}, len, body }
const MODE = __MODE__;
const IDX = parseInt(__IDX__, 10);
const Q = __Q__;
const KEYS = __KEYS__;

let idx = IDX;
if (MODE === 'key') {
  await page.fill('#lyfullsearch', Q);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(7000);
  idx = await page.evaluate((keys) => {
    const rows = Array.from(document.querySelectorAll('tr.j-mail'));
    for (let i = 0; i < rows.length; i++) {
      const t = (rows[i].innerText || '').replace(/\s+/g, ' ');
      if (keys.every(k => t.includes(k))) return i;
    }
    return -1;
  }, KEYS);
  if (idx < 0) return { error: 'not found', q: Q, keys: KEYS };
}

await page.locator('tr.j-mail').nth(idx).click();
await page.waitForTimeout(5000);

const header = await page.evaluate(() => {
  let node = null, from = '', to = '';
  document.querySelectorAll('tr').forEach(tr => {
    const t = (tr.innerText || '').replace(/\s+/g, ' ').trim();
    if (/^发件人\s*:/.test(t)) { node = tr; from = t; }
    if (/^收件人\s*:/.test(t) && !to) to = t;
  });
  let block = '';
  if (node) {
    let p = node;
    for (let i = 0; i < 5 && p.parentElement; i++) p = p.parentElement;
    block = (p.innerText || '').replace(/\n{3,}/g, '\n').slice(0, 900);
  }
  return { block, from, to };
});

let body = '';
for (const f of page.frames()) {
  if (!/viewMailHTML/.test(f.url() || '')) continue;
  try { body = await f.evaluate(() => document.body ? document.body.innerText : ''); } catch (e) {}
}
return { idx, header, len: body.length, body };
