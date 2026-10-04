# 01 · Coremail 网页版 DOM 速查与操作

适用于 **Coremail XT5**（`wemail.webank.com`，登录后 URL 形如
`.../coremail/XT/index.jsp?sid=...#mail.previewlayout|...`）。

---

## 1. 登录与就绪判据

| 目标 | 选择器 / 判据 |
|------|---------------|
| 账号 | `input#uid` |
| 密码（假框，浏览器自动填充） | `input#fakePassword`；真正的 `input#password` 是 hidden，**不要读取、不要回显、不要自己填** |
| 登录按钮 | `button.j-submit`（是 `<button>` 不是 input） |
| 别点错 | `.j-ssl-login-button`（CA 证书登录）是隐藏的 |
| 会话过期弹层按钮 | `.u-dialog button:has-text("重新登录")` —— **别用** `text=重新登录`，可能命中非按钮文本，click「成功」但弹层不消失 |
| 列表刷新按钮 | `span[data-btn="refresh"]` |
| **已登录判据** | `#lyfullsearch` 存在 **且无可见 `.u-dialog`** |

> ⚠️ **过期时 `#lyfullsearch` 仍然存在** —— 只用它判断会误报「已登录」，
> 之后所有点击被遮罩拦截、30 秒超时。

### 登录失败怎么办

| 现象 | 处理 |
|------|------|
| `BROWSER_RUNTIME_UNAVAILABLE` | Tabbit 浏览器未运行 → 请用户手动启动后重试，**不要去拉起 Runtime Service** |
| `mode: login-failed` | 多半遇到二次验证 / 短信或图形验证码 → 请用户手动登录一次，再跑 `ensure` |
| `mode: not-on-site` | 当前页不在 Coremail 域名下（脚本不会强行跳转）→ 加 `--new` 重开 |
| 登录页没自动填充密码 | 让用户先手动登录一次并勾选「记住密码」 |

---

## 2. 核心 DOM 速查

| 目标 | 选择器 / 位置 | 备注 |
|------|---------------|------|
| 全文搜索框 | `#lyfullsearch`（placeholder「邮件全文搜索」） | 填完按 Enter，**等 5–7 秒** |
| 邮件列表行 | `tr.j-mail` | 搜索视图下会混入隐藏的日期分组行 |
| **邮件正文** | **在 iframe 里**：`page.frames()` 中 URL 含 `viewMailHTML` 的那个（frame name 常为 `iFrameResizer0`） | 主页 `innerText` 只有列表，**拿不到正文** |
| 邮件头三段 | `tr > td.info-item`（文本「发件人 :」「收件人 :」「抄 送 :」），联系人在同 `tr` 的第 2 个 `td` | |
| 邮件头容器（兜底） | `div.full-info.j-full-info` | **`tr` 匹配可能返回空**，用这个 |
| 联系人折叠链接 | `a.u-hide-info`，文本 `.. [↓还有N个联系人]` | 点开后每个联系人是 `span.u-email[addr][data-true-name]` |
| 会话内翻页 | `a.u-page-prev` / `a.u-page-next`；`a.z-current` 是当前序号 | 按**搜索结果列表顺序**，不是会话顺序 |
| 打开邮件后 | 视图切到 `#mail.read\|{...}` | **左侧列表全部隐藏**（`tr.j-mail` 的 `offsetParent === null`） |
| 点击后等待 | 至少 4500–5000ms | iframe 才是新邮件的 |
| 侧栏文件夹 | 收件箱 `fid:1` / 已发送 `fid:3` | **只能点击切换**，不能拼 URL |

### 正文里的 @提及

是**纯文本**（`<span>@Puah</span>`），**没有 href / title / data-\***，拿不到邮箱地址。

要还原邮箱只能靠「**收件人列表 + 正文称呼（`Dear A&B&C`）交叉比对**」。
详见 `02-feedback-extraction.md` 的昵称考证章节。

---

## 3. 打开一封邮件（安全写法）

### 3.1 按行文本实时匹配（**首选**）

```js
const res = await page.evaluate((t) => {
  const rows = Array.from(document.querySelectorAll('tr.j-mail'));
  for (let i = 0; i < rows.length; i++) {
    const s = (rows[i].innerText || '').replace(/\s+/g, ' ');
    if (s.indexOf(t.frm) >= 0 && s.indexOf(t.time) >= 0 && s.indexOf(t.subj) >= 0) {
      rows[i].scrollIntoView({ block: 'center' });
      return { ok: true, idx: i, row: s.slice(0, 160) };
    }
  }
  return { ok: false };
}, tgt);
await page.waitForTimeout(500);
if (res.ok) { const r = await page.$$('tr.j-mail'); if (r[res.idx]) await r[res.idx].click(); }
return res;
```

**三个必须遵守的点**

1. **每次按 idx 点开前都要重新 dump 一次** —— 行索引会随新邮件到达整体位移
   （实测：同一封邮件上午 idx 4、下午 idx 5）
2. **点击脚本要回传 `row` 文本**，与期望发件人比对，不匹配就报 `EXPECT MISMATCH` ——
   否则会**默默读到完全无关的邮件**
3. **切过文件夹（如看过已发送）后，务必先切回收件箱再按 idx 读** —— 否则索引是另一个列表的

### 3.2 搜索视图：必须先按可见性过滤

```js
// 搜索视图下 querySelectorAll('tr.j-mail') 会把隐藏的日期分组容器里的行一起算进来
// 实测：114 个节点里只有 14 个可见
const vis = await page.evaluate(() =>
  Array.from(document.querySelectorAll('tr.j-mail'))
    .map((n, i) => ({ i, vis: n.offsetParent !== null,
                      t: (n.innerText||'').replace(/\s+/g,' ').trim().slice(0,120) }))
    .filter(x => x.vis));
return { n: vis.length, vis };
```

拿到可见行后，**用可见行数组的下标**去点（不是 NodeList 下标）。

### 3.3 打开后连读会话：用 `a.u-page-prev`

打开一封邮件后列表全部隐藏，**第二次按 idx 点击必然 30s 超时**。
所以不要「打开 → 返回列表 → 再打开」，改用 read 视图里的 `a.u-page-prev` 一路往回走。

```js
// mail_walk_prev.js 的核心循环（N 步，每步 ~5.5s）
const steps = 13;                        // 改这个数字控制步数
const got = [];
for (let k = 0; k < steps; k++) {
  await page.waitForTimeout(4600);       // 等 iframe 加载完
  // 展开折叠联系人
  await page.evaluate(() => {
    Array.from(document.querySelectorAll('a.u-hide-info, a.link')).forEach(a => {
      if (/还有\s*\d+\s*个联系人/.test((a.innerText||'').replace(/\s+/g,' ')) && a.offsetParent !== null) {
        try { a.click(); } catch (e) {}
      }
    });
  });
  await page.waitForTimeout(900);
  // 提取 from / to / cc（见 mail_hdr_full.js）
  got.push(await extractHeader());
  // 上一封
  const ok = await page.evaluate(() => {
    const a = document.querySelector('a.u-page-prev');
    if (a && a.offsetParent !== null) { a.click(); return true; }
    return false;
  });
  if (!ok) break;
}
return got;
```

**实测记录（2026-09-28）**：一条 14 封的会话，分 3 次 `run`（4 + 8 + 1 步）全部读完，
每步约 5.5 秒。原件收件人 12 人 + 抄送 25 人，**不点 `a.u-hide-info` 只能拿到 5 + 5**。

---

## 4. 抓邮件头（发件人 / 收件人 / 抄送）

### 4.1 结构化提取（首选）

见 `scripts/mail_hdr_full.js`。核心是 `span.u-email` 的两个属性：

```js
Array.from(cell.querySelectorAll('span.u-email')).forEach(sp => {
  const e = sp.getAttribute('addr');            // 邮箱
  const n = sp.getAttribute('data-true-name');  // 显示名
  if (e) out.push({ n, e });
});
```

### 4.2 兜底写法（`tr` 匹配返回空时）

```js
document.querySelectorAll('div,td,span,table').forEach(e => {
  const t = (e.innerText || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  if (/^发件人\s*:/.test(t) && t.length < 700) out.push(t);   // 拿到「发件人 / 收件人 / 抄送」三段
});
```

实测 `tr` 匹配在**收件箱与已发送视图都可能返回空**，改用上面写法后才拿到。

### 4.3 邮箱正则（必须限定 TLD）

Coremail 会把裸地址**连写成一行**：`shenazhang@webank.comluk.teckeng@hlbb...`

```python
EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9\-]+\.)+(?:com\.my|edu\.my|gov\.my|com|net|org|my|cn)"
)
```

贪婪回溯会自动停在 `.com` / `.com.my` 上。
**只用 `[@\w.]+` 会把两个地址粘成一个**。

### 4.4 显示名回填与去重

1. 先全局收集 `邮箱 → 显示名` 映射，再回填裸地址缺名的项
2. **名字去重要挑有效名**：同一邮箱在不同邮件里 `data-true-name` 可能是
   `carlwang(王胜军)` 或直接 `carlwang@webank.com`。
   **直接取最长会把邮箱形态选出来** → 先剔除「等于邮箱 / 等于邮箱前缀」的候选，再比长度

---

## 5. 会话过期与故障恢复

### 5.1 会话过期

**症状**：搜索跳转 / 长时间挂机后出现「会话已过期, 请重新登录」弹层（带 `.u-mask` 遮罩，
拦截一切点击，但页面 DOM 仍是邮箱）。

**处理**：**直接再跑一次 `ensure`**。它会：

1. 点弹层「重新登录」按钮（用 `.u-dialog button:has-text("重新登录")`）
2. 点登录按钮（密码由浏览器自动填充）
3. 等 `#lyfullsearch` 出现且无弹层
4. **再点一次列表「刷新」** —— 重新登录后列表是旧 DOM 快照，
   不刷新的话读到的可能是几天前的邮件列表

### 5.2 探测会话状态

长时间操作后（切文件夹、连续读多封之后最容易触发）先 probe：

```js
const st = await page.evaluate(() => ({
  dialogs: Array.from(document.querySelectorAll('.u-dialog'))
             .filter(e => e.offsetParent !== null).map(d => d.innerText.slice(0, 80)),
  masks: document.querySelectorAll('.u-mask').length
}));
return st;
```

命中「会话已过期」就重跑 `ensure`，**否则后续所有 click 都会被遮罩拦到 30 秒超时**。

### 5.3 切文件夹

```js
const h = await page.evaluateHandle(() => {
  const els = Array.from(document.querySelectorAll('a,span,div,li'));
  return els.find(e => (e.innerText || '').trim() === '已发送'
        && e.offsetParent !== null && e.children.length <= 2);
});
if (h && h.asElement()) { await h.asElement().click(); }
await page.waitForTimeout(6000);
```

> ⚠️ **不要用 `page.goto()` 切文件夹**：Coremail 文件夹是 `#mail.list|{"fid":N}` 的 **hash 路由**，
> 直接 goto 拼出来的 URL（不带 sid / 参数不全）会让页面**白屏**，`#lyfullsearch` 消失、`title` 为空，
> 之后所有 `read-idx` / `search` 全部超时。
> 恢复办法：`finish` 之后 `ensure --new` 重开一个干净标签。

### 5.4 dump 当前列表（最可靠，不依赖搜索）

```js
// dump.js
const res = await page.evaluate(() => {
  const out = [];
  Array.from(document.querySelectorAll('tr.j-mail')).forEach((n, i) => {
    const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t) return;
    const cells = Array.from(n.querySelectorAll('td'))
      .map(td => (td.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
    out.push({ i, cells: cells.slice(0, 6) });
  });
  return { url: location.href.slice(0, 140), n: out.length, rows: out };
});
return res;
```

---

## 6. 生成「回复全部」收件人清单

**场景**：需要把一条邮件会话里**出现过的所有人**（发件人 + 收件人 + 抄送）汇成一份清单，
贴进收件人栏做回复全部。

> **只读当前这一封的 header 是不够的** —— 回复里会加人、也会掉人。

### 6.1 步骤

```bash
PY="…/python.exe"; SK="…/coremail-sent-feedback-tracker/scripts"

# ① 先搜出该会话（短关键词），dump 可见行拿到下标
"$PY" "$SK/tabbit.py" --task T search "Man-Month Confirmation"
"$PY" "$SK/tabbit.py" --task T run visible_rows.js

# ② 点开会话里的任意一封（用可见行的下标）
"$PY" "$SK/tabbit.py" --task T run click_row.js

# ③ 每跑一次读 N 封：自动展开折叠 + 提取 from/to/cc（脚本内循环 a.u-page-prev）
"$PY" "$SK/tabbit.py" --task T run mail_walk_prev.js     # 把开头的步数常量改一下
```

### 6.2 合并去重

- 把人按**邮箱小写**去重，显示名按 §4.4 的规则挑有效名
- 分类统计：按域名分（如 HLBB / HLISB / 内部），便于核对人数

### 6.3 输出格式（多版本，一次给全）

| 版本 | 格式 | 适用 |
|------|------|------|
| A | `"名字" <邮箱>; …`（分号） | **Outlook 中文版**（只认分号） |
| B | `"名字" <邮箱>, …`（逗号） | Gmail / 网页邮箱 |
| C | `<邮箱>; <邮箱>; …` | 姓名含特殊字符时防解析失败 |
| D | `<邮箱>, <邮箱>, …` | 同上，逗号版 |
| E | 仅对方（去掉自己人） | 需要缩小范围时 |
| F | 去掉自己 | — |

分隔符两种都要给 —— 不同客户端行为不同。

### 6.4 实测数据（2026-09-28）

- 会话 14 封（1 发 + 客户往复 13），去重后 **49 人**（对方 19 + 对方子公司 6 + 我方 24）
- 折叠展开：原件收件人 12 + 抄送 25
- 子公司的 6 人**是后来某次回复时才带入的**，只看首封会漏

---

## 7. 已知坑（本文件相关）

| 坑 | 表现 | 解法 |
|----|------|------|
| `run` 不接受 `-` 当 stdin | 1~2 秒「成功」返回但无数据 | 先把 JS 落盘成 `.js` 再传路径 |
| Git Bash 短路径 | `Invalid regular expression flags` | 用常规绝对路径（工作区下） |
| `page.evaluate` 多参数 | `Too many arguments…` | **只接受一个参数**，多值包成对象 |
| 裸 `document` | `document is not defined` | 所有 DOM 访问包在 `await page.evaluate(...)` 里 |
| 多个 Coremail 标签 | `ensure` 只接管第一个匹配 host 的 | 需要干净会话用 `--new` |
| `claim --tab` | `TAB_OWNERSHIP_CONFLICT` | 用 `resume --group`（`ensure` 已自动处理） |
| `--task` 位置 | 报错 | **全局选项，必须写在子命令前** |
| `finish` 后用同名 task | `Unknown task name` | 换新任务名，或 `ensure` 重新接管 |
| `nodejs` 缺 `--request-id` | `{"code":"REQUEST_FAILED"}` | 用 `tabbit.py`（已自动生成）；直调 CLI 要自己补 |
| 列表是旧快照 | 时间乱序 | 读取前先刷新（`span[data-btn="refresh"]` 或重跑 `ensure`） |
| 大结果被截断 | 返回 `resourceId` | `tabbit.py` 会自动循环 `resource --offset` 拼回 |
| Bash coreutils 缺失 | `ls: command not found` | 命令开头 `export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"` |
