// read_hdr.js —— 展开全部联系人并结构化提取 发件人/收件人/抄送
// 返回 { ok, subj, date, from:[{n,e}], to:[...], cc:[...], raw }
const expand = await page.evaluate(() => {
  let clicked = 0;
  Array.from(document.querySelectorAll('a.u-hide-info, a.link')).forEach(a => {
    const t = (a.innerText || '').replace(/\s+/g, ' ');
    if (/还有\s*\d+\s*个联系人/.test(t) && a.offsetParent !== null) {
      try { a.click(); clicked++; } catch (e) {}
    }
  });
  return clicked;
});
await page.waitForTimeout(1500);

const res = await page.evaluate(() => {
  function grab(rowLabelRe) {
    const out = [];
    const trs = Array.from(document.querySelectorAll('tr'));
    for (const tr of trs) {
      const lab = tr.querySelector('td.info-item');
      if (!lab) continue;
      const lt = (lab.innerText || '').replace(/\u00a0/g, ' ').replace(/\s+/g, '');
      if (!rowLabelRe.test(lt)) continue;
      const tds = Array.from(tr.children);
      const cell = tds[1];
      if (!cell) continue;
      Array.from(cell.querySelectorAll('span.u-email')).forEach(sp => {
        const e = sp.getAttribute('addr') || '';
        const n = sp.getAttribute('data-true-name') || '';
        if (e) out.push({ n: n, e: e });
      });
      // 兜底：无 u-email 结构时取整格文本
      if (!out.length) {
        const txt = (cell.innerText || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
        if (txt) out.push({ n: '', e: '', raw: txt });
      }
      break;
    }
    return out;
  }
  const from = grab(/^发件人/);
  const to = grab(/^收件人/);
  const cc = grab(/^抄送/);
  // 主题与时间：从 mail-top 里取
  const top = document.querySelector('.mail-top') || document.querySelector('.j-mail-top');
  let headText = top ? (top.innerText || '').replace(/\u00a0/g, ' ').replace(/\n{2,}/g, '\n') : '';
  const dt = (headText.match(/\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?/) || [''])[0];
  const lines = headText.split('\n').map(s => s.trim()).filter(Boolean);
  const subj = lines.find(s => s.indexOf('[Action Required]') >= 0 || s.indexOf('Batch 3 Scope') >= 0) || '';
  return { from: from, to: to, cc: cc, date: dt, subj: subj.slice(0, 200), headText: headText.slice(0, 400) };
});
res.ok = true;
res.expanded = expand;
return res;
