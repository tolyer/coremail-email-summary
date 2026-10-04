// walk.js —— 在 read 视图里连点「上一封」N 次，每次提取表头
const N = %d;
const out = [];

async function expandAll() {
  return await page.evaluate(() => {
    let c = 0;
    Array.from(document.querySelectorAll('a.u-hide-info')).forEach(a => {
      if (/还有\s*\d+\s*个联系人/.test(a.innerText || '') && a.offsetParent !== null) {
        try { a.click(); c++; } catch (e) {}
      }
    });
    return c;
  });
}

async function readHdr() {
  return await page.evaluate(() => {
    function grab(re) {
      const out = [];
      const trs = Array.from(document.querySelectorAll('tr'));
      for (const tr of trs) {
        const lab = tr.querySelector('td.info-item');
        if (!lab) continue;
        const lt = (lab.innerText || '').replace(/\u00a0/g, ' ').replace(/\s+/g, '');
        if (!re.test(lt)) continue;
        const cell = tr.children[1];
        if (!cell) continue;
        Array.from(cell.querySelectorAll('span.u-email')).forEach(sp => {
          const e = sp.getAttribute('addr') || '';
          const n = sp.getAttribute('data-true-name') || '';
          if (e) out.push({ n: n, e: e });
        });
        break;
      }
      return out;
    }
    const top = document.querySelector('.mail-top') || document.querySelector('.j-mail-top');
    const ht = top ? (top.innerText || '').replace(/\u00a0/g, ' ').replace(/\n{2,}/g, '\n') : '';
    const dt = (ht.match(/\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?/) || [''])[0];
    const pg = document.querySelector('a.z-current');
    return {
      from: grab(/^发件人/), to: grab(/^收件人/), cc: grab(/^抄送/),
      date: dt, page: pg ? (pg.innerText || '').trim() : '',
      head: ht.slice(0, 260)
    };
  });
}

async function stepPrev() {
  return await page.evaluate(() => {
    const a = Array.from(document.querySelectorAll('a.u-page-prev')).find(x => x.offsetParent !== null);
    if (!a) return false;
    a.click();
    return true;
  });
}

const first = await readHdr();
out.push(first);

for (let k = 0; k < N; k++) {
  const ok = await stepPrev();
  if (!ok) { out.push({ stop: 'no-prev', at: k }); break; }
  await page.waitForTimeout(4600);
  await expandAll();
  await page.waitForTimeout(900);
  out.push(await readHdr());
}
return { n: out.length, steps: out };
