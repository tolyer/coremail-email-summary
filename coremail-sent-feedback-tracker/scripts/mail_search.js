// 全文搜索并列出邮件行摘要。占位符：__Q__
await page.fill('#lyfullsearch', __Q__);
await page.keyboard.press('Enter');
await page.waitForTimeout(7000);

const rows = await page.evaluate(() => {
  const out = [];
  Array.from(document.querySelectorAll('tr.j-mail')).forEach((n, i) => {
    const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t) return;
    out.push({ i: i, text: t.slice(0, 160) });
  });
  return out;
});
return rows;
