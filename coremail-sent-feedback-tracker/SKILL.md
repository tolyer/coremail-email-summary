---
name: coremail-sent-feedback-tracker
description: 在 Coremail（wemail.webank.com）网页版中，追踪「我方发出的邮件」并汇总「客户/对方给出的反馈」。适用于需求澄清、评审请求、范围确认、报价问询等一切「我方发问 → 对方逐条作答」的场景。自动接管浏览器标签、批量读取已发送与收件箱、提取正文/彩色批注/表格批注/Google Docs 评论通知四类反馈载体，输出中文 HTML + 英文 HTML + Markdown 三件套（带可手工标记的「已解决 / 备忘结论」区、未解决清单、负责人(Owner) 列）。触发关键词：Coremail、已发送、客户反馈、回复汇总、需求澄清、发出邮件追踪、逐条确认、wemail.webank.com。
metadata:
  version: "1.0.0"
---

# Coremail 发出邮件 → 对方反馈追踪

把「我发出去的邮件」和「对方回了什么」自动配成对，逐条落到一张可勾选、可批注、可导出的表里。

**一句话流程**：读已发送 → 读收件箱 → 按「一封我方邮件 = 一个分组」归集 → 逐条判状态 → 渲染三件套 → 校验 → 交付。

---

## 0. 一分钟速查

```bash
PY="C:/Users/leonerdli/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SK="C:/Users/leonerdli/.workbuddy/skills/coremail-sent-feedback-tracker/scripts"

"$PY" "$SK/tabbit.py" ensure                      # ① 接管/自动登录 Coremail
"$PY" "$SK/tabbit.py" --task T search "关键词"     # ② 搜索
"$PY" "$SK/tabbit.py" --task T run dump.js        # ③ 落盘 JS 后 run（不支持 - 当 stdin）
"$PY" "$SK/render_tracker.py" data.json outdir    # ④ 渲染三件套
"$PY" "$SK/tabbit.py" --task T finish             # ⑤ 收尾
```

**开工前必做两件事**（顺序错了会白跑一轮）：
1. 取回用户在浏览器里的最新手工标记（见 §6.4）
2. 确认清单口径（默认只留"本人发出"的邮件，其余进 `held`）

---

## 1. 数据口径（先定口径再动手）

口径一旦定下，写进数据文件的 `scope` 字段，后续每轮都按它跑。

| 维度 | 默认口径 | 可定制 |
|------|----------|--------|
| **我方发出的邮件** | `from_addr` 属于指定域（例：`leonerdli@webank.com`）；正文含编号问题/确认项并要求对方作答 | 改 `SELF_ADDR` / `SELF_DOMAIN` |
| **对方反馈** | 客户域（例：`@hlbb.hongleong.com.my` / `@hlisb.…`）的逐条回复 | 改 `PEER_DOMAINS` |
| **归集单位** | **一封我方发出的邮件 = 一个分组**（`mails[]` 的一项），其下所有问题 + 后续所有回复都并入这一组 | 不建议改 |
| **同线程合并** | 主题去掉 `Re:` / `Fwd:` / `FW:` 前缀后一致 → 首轮与跟进邮件合并为一组 | — |
| **状态** | `ok` 已确认 / `part` 部分回复 / `fwd` 转交他人 / `none` 未回复 | 四态固定 |
| **解决进度** | 手工标记的 `已解决` / `未标记·未解决`；**未解决 = 条目总数 − 已标记解决数** | — |
| **清单范围** | 默认**只保留本人发出的邮件**；其余移入数据文件 `held` 字段保留、**不参与统计** | 用户可随时喊"把 X 加回来" |

> **`held` 是保留区不是删除区**。用户原话：「这个清单内拿掉不是我发送的邮件的统计，当我有需要的话我会喊你统计，你再处理」——
> 因此**不要主动把非本人邮件加回**，也**不要删掉 `held`**。
>
> 判别看 `from_addr`，**不要看 `sender`**：收件箱里有的邮件 `sender` 写着自己，但 `from_addr` 是客户地址（客户来件），**不算本人发出**。

### 渠道提示：反馈不一定在邮件正文里

对方常在 **Google Docs 评论 / 群聊 / 会议**里反馈而不发邮件。这类要显式标注，**不要误判为「未回复」**。
详见 §4.4 / §4.5。

---

## 2. 标准流程（七步，别跳）

```
① 接管邮箱 → ② 读已发送（找新发出的邮件）→ ③ 读收件箱（找新回复）
   → ④ 增量更新数据文件 → ⑤ 抓 To/Cc（新分组必做）→ ⑥ 渲染三件套
   → ⑦ 校验 + 交付
```

| 步 | 动作 | 关键点 |
|----|------|--------|
| ① | `tabbit.py ensure` | 返回 `ok:true` 才继续；`ok:false` 见 §3.3 |
| ② | 读「已发送」 | **已发送列表第一列显示的是收件人**，别当成发件人 |
| ③ | 读「收件箱」 | 抓"我方发出的邮件"要**同时看收件箱**（CC 给自己的会进来）和已发送 |
| ④ | 更新数据文件 | **只改 `who/when/raw/sum/se/st`，绝不动 `q`/`qe`**（见 §5.3 红线） |
| ⑤ | 抓 To/Cc | 新分组必须补 `to[]` / `cc[]`，否则邮件头卡片是空的 |
| ⑥ | 渲染 | `python render_tracker.py [data.json] [outdir]` |
| ⑦ | 校验 | 跑 §7 的校验清单，**一项不过就不交付** |

### 别漏邮件的自检动作

用户最常问「××那封为什么没有」。重跑后必须确认：已发送首屏 + 收件箱首屏里，我方新发出的邮件都已在 `mails` 里。

> **最常见的漏因不是抓取失败，而是数据窗口没跟上**——上一轮窗口截止到哪天，之后发出的邮件自然不在数据里。
> 回答用户前先看数据文件的 `window` 字段再下结论。

---

## 3. 抓取层：Coremail 网页版操作

### 3.1 接管 / 自动登录

```bash
"$PY" "$SK/tabbit.py" ensure              # 有标签就接管，没有就新开 + 自动登录
"$PY" "$SK/tabbit.py" ensure --new        # 忽略已有标签，强制新开一个干净会话
```

- 浏览器会**自动填充**账号密码（前提：用户曾手动登录并勾选「记住密码」）
- 返回值 `mode`：`resumed` / `claimed` / `bootstrapped` / `bootstrap-failed`
- `detail.mode`：`already` / `goto` / `relogin` / `login` / `login-failed` / `not-on-site`
- **`ok:false` 时不要硬往下走**

### 3.2 安全边界（强制，不可绕过）

所有交给浏览器执行的 JS 都会过 `guards.py` 静态扫描，命中即拒绝。**唯一绕过方式是直接改 `guards.py`**——它就是策略的唯一真相源。

| 级别 | 规则 | 说明 |
|------|------|------|
| **DENY**（永不放行） | `DELETE_MAIL` | 禁止删除任何邮件，含清空/彻底删除/清空回收站（fail-closed，裸「删除」也拦） |
| | `WIPE_SESSION` | 清 Cookies / localStorage / sessionStorage |
| | `CHANGE_ACCOUNT` | 自动转发、改密码、签名、POP3/IMAP 设置 |
| | `READ_CREDENTIAL` | 读密码框 / `document.cookie`（登录靠浏览器自动填充） |
| | `EXFILTRATE` | `fetch` / `XMLHttpRequest` / `addScriptTag` / `page.request` |
| | `DYNAMIC_EVAL` | `eval(` / `new Function(` / 字符串版 `setTimeout` |
| **CONFIRM**（需环境变量） | `SEND_MAIL` | `TABBIT_ALLOW_SEND=1` |
| | `ATTACHMENT` | `TABBIT_ALLOW_ATTACH=1` |
| | `CLOSE_PAGE` | `TABBIT_ALLOW_CLOSE=1` |
| | `MUTATE_STATE` | `TABBIT_ALLOW_MUTATE=1` |
| | `CLICK_BODY_LINK` | `TABBIT_ALLOW_LINK=1` |

放行**只在当前命令生效**：`TABBIT_ALLOW_MUTATE=1 python tabbit.py run x.js`。**不要写进 profile 长期生效。**

拿不准一段 JS 是否越界时，只做静态扫描、不连浏览器：

```bash
"$PY" "$SK/tabbit.py" guard some.js      # 输出 SAFE / DENY / NEED
```

**移动邮件**是唯一允许的写操作，但设了四道闸：目标文件夹黑名单（垃圾箱/已删除/trash 一律拒绝）、默认 dry-run、相关性校验（行文本须命中检索词全部关键片段）、单次上限 20 封。

### 3.3 常见故障

| 现象 | 处理 |
|------|------|
| `BROWSER_RUNTIME_UNAVAILABLE` | Tabbit 浏览器未运行 → 请用户手动启动后重试 |
| `mode: login-failed` | 多半是二次验证/验证码 → 请用户手动登录一次，再跑 `ensure` |
| `mode: not-on-site` | 当前页不在 Coremail 域名下 → 加 `--new` 重开 |
| 「会话已过期」弹层 | **直接再跑一次 `ensure`**。弹层带遮罩会拦截一切点击（实测后续 click 全部 30s 超时）。注意过期时 `#lyfullsearch` 仍存在 → 会用「无可见 `.u-dialog`」二次判断 |
| 连续读多封后操作失灵 | 先 probe 会话状态（见 `references/01`），命中过期就重跑 `ensure` |

### 3.4 搜索策略

- Coremail 全文搜索是**模糊/OR 匹配**：关键词越长结果越发散。用 **2~3 个词的短关键词**，**不要**粘整句主题
- **`search` 连续查不同关键词可能不生效**（第二次起返回同一批列表，用无意义串验证也一样）→ **不要据此判断"没有新邮件"**。要列"最近邮件"就直接读列表
- 侧栏文件夹：收件箱 `fid:1` / 已发送 `fid:3`
- **不要用 `page.goto()` 切文件夹**：文件夹是 `#mail.list|{"fid":N}` 的 hash 路由，拼 URL 会让页面白屏，之后全部命令超时。**一律点击侧栏元素**

### 3.5 定位一封邮件：按行文本实时匹配，不要用行索引

邮件列表是**静态快照**，但**行索引会随新邮件到达整体位移**（实测同一封邮件上午 idx 4、下午 idx 5）。

```js
// 每次按 idx 点开前先重新 dump 一次，且点击脚本要回传 row 文本、跟期望发件人比对
const res = await page.evaluate((t) => {
  const rows = Array.from(document.querySelectorAll('tr.j-mail'));
  for (let i = 0; i < rows.length; i++) {
    const s = (rows[i].innerText || '').replace(/\s+/g, ' ');
    if (s.indexOf(t.frm) >= 0 && s.indexOf(t.time) >= 0 && s.indexOf(t.subj) >= 0) {
      rows[i].scrollIntoView({ block: 'center' });
      return { ok: true, idx: i };
    }
  }
  return { ok: false };
}, tgt);
await page.waitForTimeout(500);
if (res.ok) { const r = await page.$$('tr.j-mail'); if (r[res.idx]) await r[res.idx].click(); }
```

- 不匹配就报 `EXPECT MISMATCH` —— 否则会**默默读到完全无关的邮件**
- **切过文件夹（如看过已发送）后，务必先切回收件箱再按 idx 读**，否则索引是另一个列表的
- 打开邮件后列表全部隐藏（`tr.j-mail` 的 `offsetParent === null`），**第二次按 idx 点击必然 30s 超时** → 改用 read 视图里的 `a.u-page-prev` 连续往回走
- 搜索视图下 `querySelectorAll('tr.j-mail')` 会把隐藏的日期分组行算进来 → **先按 `offsetParent !== null` 过滤出可见行**，再用它的下标去点

### 3.6 抓邮件头（发件人 / 收件人 / 抄送）

**关键 DOM**

| 目标 | 选择器 |
|------|--------|
| 联系人折叠展开 | `a.u-hide-info`，文本 `.. [↓还有N个联系人]`，**点一下展开全部** |
| 结构化联系人 | `span.u-email[addr="邮箱"][data-true-name="显示名"]` —— 邮箱和名字都在属性里 |
| 三段行 | `tr > td.info-item`（文本「发件人 :」「收件人 :」「抄 送 :」），联系人就在同 `tr` 的第 2 个 `td` |
| 会话内翻页 | `a.u-page-prev` / `a.u-page-next`；`a.z-current` 是当前序号 |

**四个必知坑**

1. **不展开就只有半截**：超过 5 个就会被折叠，`innerText` 只给到 `.. [↓还有N个联系人]`。实测原件收件人 12 + 抄送 25，不点开只能拿到 5 + 5
2. **邮件头取 `div.full-info.j-full-info`，别用 `tr` 匹配**（`tr` 匹配在收件箱与已发送视图都可能返回空）。兜底写法：遍历 `div,td,span,table`，取 `innerText` 以 `发件人 :` 开头且长度 < 700 的元素
3. **裸地址会连写成一行**（`shenazhang@webank.comluk.teckeng@hlbb…`）→ 正则必须限定 TLD：
   `[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9\-]+\.)+(?:com\.my|edu\.my|gov\.my|com|net|org|my|cn)`。
   只用 `[@\w.]+` 会把两个地址粘成一个
4. **走多轮的主题取首轮的 To/Cc** 作为该组口径

**现成模板**：`scripts/mail_hdr_full.js`（展开折叠 + 结构化提取 from/to/cc）、`scripts/mail_walk_prev.js`（连读会话前 N 封）。
取整条会话的全部收发件人（做「回复全部」清单）见 `references/01`。

**显示名回填**：先全局收集 `邮箱 → 显示名` 映射，再回填裸地址缺名的项。名字去重要**挑有效名**——
同一邮箱在不同邮件里 `data-true-name` 可能一个是 `carlwang(王胜军)`、另一个直接是 `carlwang@webank.com`；
**取最长会把邮箱形态选出来**，要先剔除「等于邮箱 / 等于邮箱前缀」的候选再比长度。

---

## 4. 提取层：对方反馈的五种载体

对方回一条需求，可能用完全不同的载体。**判断错载体 = 漏掉整批意见**。

| # | 载体 | 典型信号 | 处理要点 |
|---|------|----------|----------|
| 1 | 常规正文逐条回复 | 正文带编号 / `Re:` | `strip_quote.py` 剥离引用历史（客户端会剥离，或只取首个切点 >60 的标记） |
| 2 | 表格**彩色字体**批注 | 正文是「领域 × 我方理解 × 需确认信息」的表 | 必须读 `getComputedStyle` 颜色，纯文本会丢信息 |
| 3 | 表格**追加列/单元格**回复 | 整张表贴回来，答案追加在 Owner 列 | 按 `<table>` 逐行取 + 「相邻两层 diff」定位本轮新增 |
| 4 | Google Docs 评论通知 | 发件人 `comments-noreply@docs.google.com`，主题带评论摘要 | 抓！否则漏整批客户意见 |
| 5 | 会议 / 群聊 | 日历邀请、无正文 | 记在**邮件级 `note` 字段**，不建 item |

### 4.1 正文逐条回复（最常规）

```bash
"$PY" "$SK/strip_quote.py" reply.json          # reply.json = tabbit.py 的输出
"$PY" "$SK/strip_quote.py" reply.json 4000     # 限制输出长度
```

匹配 `On ... wrote:` / `-----Original Message-----` / `____________` / `From:...Sent:` 等标记，取第一个位置 >60 的切点。
**不做剥离就会把"自己的原始提问"当成"对方的回复"** —— 这是最高频的误判。

### 4.2 彩色批注提取（表格类邮件）

正文在 iframe 里（URL 含 `viewMailHTML`）。按「表格行」归属，**不要按文本节点顺序**：

```js
Array.from(document.querySelectorAll('tr')).forEach(tr => {
  const tds = Array.from(tr.children);
  if (tds.length < 4) return;
  const area = AMAP[key(tds[0].innerText)];        // 第 0 格 = 领域名
  if (!area || seen.has(area)) return;             // 只取最外层（最新）那一层
  seen.add(area);
  // 逐格用 TreeWalker 取文本节点，跳过 IGNORE 里的默认色，剩余即批注
});
```

- **踩坑**：按 TreeWalker 顺序 + 「最近的领域名」归属会出错 —— `Policy ( UW)` 这类名字在 DOM 里被拆成两个文本节点，匹配失败后红色批注被错归到上一个领域。**必须用 `tds[0]` 整格文本做匹配**
- **颜色不能可靠区分人**：同一封邮件叠加多层引用，`rgb(0,0,255)` 蓝会被多人共用。**正确的归属方法是「批注写在哪个领域行上，就归该领域的 Owner」**
- **必须进 `IGNORE` 的默认色**（否则签名、外部邮件警示、我方模板色会混入）：
  `rgb(0,0,0)`、`rgb(153,153,153)`、`rgb(0,121,189)`、`rgb(19,79,92)`、`rgb(7,55,99)`、`rgb(156,101,0)`、`rgb(51,51,51)`、`rgb(61,133,198)`
- **黑色（默认色）批注同样是有效回复**，只是不会被彩色提取命中 → **收尾动作 = 回读纯文本正文一遍**
- 没人用彩色批注时，回去读纯文本（有人把要求写在正文开头，有人只写「+ Loop in Lee」）

### 4.3 汇总表追加列（整张表贴回来）

客户有时把整张表贴回来、把答案追加在 `Owner` 列。**彩色批注提取完全失效**（答案多为默认黑字），走结构化路线：

1. **逐 `<table>` 取行**（`<table>` 是嵌套的，外层表会包含内层表的行）：只取 `tds.length >= 4` 且 `c[0]` 非空且长度 ≤ 60 的行
2. **用 `wrote:` 文本偏移切层，再按签名认作者**（比 DOM 层级可靠得多）：
   ```python
   marks = [m.start() for m in re.finditer(r'wrote\s*:', body)]
   layer0 = body[:marks[0]]      # 最外层 = 最新一封的正文
   # 该层末尾的 "Thanks and regards, <姓名>" 即作者
   ```
3. **用「相邻两层 diff」定位本轮新增答复**：逐行比对 `layer0` 与 `layer1` 的 `Owner` 列，**只有变化的那几行才是最新发件人本轮写的** —— 最不容易误归属
4. `Owner` 列的行内约定是 `@nick - <该人的答复>`，但**必须再用 ③ 的 diff 交叉验证**：
   实测 `@waiyee` 负责的两行答案，实际是**另一层新加的**（看 `@waiyee` 会误判成 Wai Yee 回答）
5. **默认黑字回复一定会漏** —— 收尾必须回读纯文本

### 4.4 Google Docs 评论通知（容易整批漏掉）

对方大量反馈不走邮件正文，而是**在 Google Docs 里评论并 @你指派 action item**，邮箱只收到
`comments-noreply@docs.google.com` 的通知（列表发件人显示为 `X (Google Docs)`，主题形如
`<文档名> - <评论摘要>`）。

- 正文结构：`<谁> mentioned you in a comment / assigned you an action item in the following document`
  → 文档名 + `N comment(s)` → **评论线程逐条**（`<锚点文字>` / `<评论人> • <时间>` / 评论正文）→ `Assigned to you`
- **先 `.split('Google LLC')[0]` 再读**，去掉页脚噪声
- 注意 `You do not have commenting rights to <doc>` —— 没权限时只能读到通知，无法回帖
- **一个通知 = 一条 item**（该批评论整体作为 `raw`，多条评论用 `\n` 分隔并编号），
  `who` 填**提出评论的人**，`sum` 逐条归纳诉求。状态默认 `part`（待我方落实）；
  对方内部已互相答复闭环的可给 `ok`，纯转派他人的给 `fwd`
- **文档 → 邮件分组的映射**：按文档名归入对应的我方邮件。同一文档可能横跨多封我方邮件，
  需按内容判断；数据文件里用 `MAILS[].docs` 字段登记映射关系

### 4.5 会议 / 无正文邮件

日历邀请、会议通知等**不属于「某条问题的回复」**的进展 → 记在**邮件级 `note` / `note_en` 字段**，
渲染成浅蓝底的「进展备注 / Progress」行。**不要硬塞进 item**。

---

## 5. 数据层：`tracker_data.json`

### 5.1 schema

```json
{
  "updated": "2026-09-27",
  "window": "2026-08-22 ~ 2026-09-26",
  "window_en": "2026-08-22 ~ 2026-09-26",
  "scope": {
    "self_addr": "leonerdli@webank.com",
    "peer_domains": ["hlbb.hongleong.com.my", "hlisb.hongleong.com.my"],
    "note": "只统计本人发出的邮件"
  },
  "todos": [{"mail": "M6", "zh": "…", "en": "…"}],
  "held_todos": [{"mail": "M22", "zh": "…", "en": "…"}],
  "memos":   {"M1-873157efd8": {"s": 1, "n": "已电话确认；最终口径：允许手工录入"}},
  "memos_v": 1,
  "mails": [{
    "id": "M1",
    "sender": "leonerdli(李斌)",        "sender_en": "leonerdli (Li Bin)",
    "subject": "邮件主题（中文显示）",   "subject_en": "subject (EN)",
    "sent": "2026-08-22 首轮 · 08-30 跟进", "sent_en": "1st round 2026-08-22 · follow-up 08-30",
    "from_addr": "leonerdli@webank.com",
    "note": "会议进展备注（可选）",      "note_en": "Progress note (optional)",
    "to": [{"n": "Puah Chei Fong", "n_en": "Puah Chei Fong",
            "e": "cfpuah@hlbb.hongleong.com.my", "org": "HLBB", "name_fallback": "cfpuah"}],
    "cc": [],
    "items": [{
      "q":  "问题（中文 HTML）", "qe": "question (EN)",
      "who": "Name<br>email@hlbb...",  "when": "2026-08-28 11:45",
      "raw": "对方回复英文原文", "sum": "中文总结", "se": "summary (EN)",
      "st": "ok|part|fwd|none",
      "cf": {"zh": "意见不一致说明", "en": "conflict note"}
    }]
  }],
  "held": [ /* 同 mails 的结构，不参与统计 */ ]
}
```

**字段约定**

- `who` 为 `—` 表示无回复；`raw` 为 `—`；HTML 片段允许 `<b>` / `<code>` / `<span class='warn'>`
- `to` / `cc` 的 `n` 是邮箱显示名、`n_en` 是英文显示名；**`n` 为空时渲染成纯邮箱地址**
- 渲染时**完整列出全部收件人与抄送人，不截断、不折叠**（单页签下一次只看一封，头部再长也只占一屏）
- `held` 的 `items` 结构与 `mails` **完全一致**，可直接复用同一套构造代码

### 5.2 `cf`：意见不一致标记（用户明确要求）

当同一问题出现下列任一情况时，必须给该行加 `cf`：

1. **对方不同人对同一问题答复不一致**（A 给结论、B 要求再确认）
2. **对方答复与我方建议/理解相反**
3. **对方内部处理结论自相矛盾**（如已关闭工单却要求本批交付）

渲染后在「问题回复总结」前显示红色 `⚠ 意见不一致` 标签 + 说明；MD 里前缀 `⚠ **意见不一致**：`。
**同一问题的冲突双方行都要打 `cf`**（各自标一份，说明文字可相同）。

### 5.3 红线：不要改动被标记条目的 `q` / `qe`

备注的键 = `mid + md5(去标签后的 q)[:10]`。**改一个字哈希就变，用户所有标记当场变孤儿。**

- 可改：剔邮件 / 改状态 / 改总结 / 改 Owner / 改 `when` / 更新 `raw`
- **不可改：`q` 与 `qe`**

### 5.4 `held` 编号不能与主清单撞号

`held` 与 `mails` **共用同一命名空间**。新加 `held` 条目时若只对 `held` 取 max，会生成与主清单重复的 id。

```python
held_max = max([int(h["id"][1:]) for h in d.get("held", []) if h["id"][1:].isdigit()] or [0])
main_max = max([int(m["id"][1:]) for m in d.get("mails", []) if m["id"][1:].isdigit()] or [0])
new_id   = "M%d" % (max(held_max, main_max) + 1)     # ← 全局取 max
```

### 5.5 `todos` 必须是对象数组

结构是 `{"mail": "M15", "zh": "…", "en": "…"}`，渲染脚本按 key 取值。
**追加纯字符串会直接崩**：`TypeError: string indices must be integers, not 'str'`。

---

## 6. 渲染层：三件套

### 6.1 固定输出

| 文件 | 内容 |
|------|------|
| `<项目>_CN.html` | 中文版（问题、总结为中文；回复内容保留**原文**） |
| `<项目>_EN.html` | 全英文版（问题、总结为英文；回复内容为原文） |
| `<项目>.md` | Markdown 总结（中文，含手工待办 + 未解决事项清单） |

```bash
"$PY" "$SK/render_tracker.py" data.json outdir
```

### 6.2 版式（单页签 + 邮件头卡片）

```
┌ ‹ [M1] Clarification Required: System Req…  21 条目 · 1/16 ▼ ›  ← 单行邮件切换器（sticky ≈48px）
├──────────────────────────────────────────────────────────────┤
│ [M1] Clarification Required: …                    9 / 21 条  │ ← 邮件头卡片
│      已确认 9 · 部分 6 · 转交 3 · 未回复 1                     │
│  发件人  leonerdli(李斌) <leonerdli@webank.com>               │
│  收件人  Puah Chei Fong <cfpuah@…> · …（完整、不截断）         │
│  抄送    Ten Chee Ming <cmten@…> · …（完整、不截断）           │
│  发送时间 2026-08-22 首轮 · 08-30 跟进 · 09-11 更新            │
│  进展备注 会议已召开、邮件中无纪要                             │
├──────────────────────────────────────────────────────────────┤
│ 问题 │ 负责人(Owner) │ 问题回复内容 │ 问题回复总结            │
│                                     ☐ 已解决 ＋ 备忘/结论      │
└──────────────────────────────────────────────────────────────┘
```

**固定列（不可变更顺序）**：`问题 | 负责人(Owner) | 问题回复内容 | 问题回复总结`
**列宽**：`table-layout:fixed`，问题 20% / 负责人 200px / 回复内容 26% / 总结自适应（最宽列）

**邮件切换器**
- 单行 `position:sticky; top:0`（原多行页签最占 3 行 ≈120px+，用户要求改下拉）
- `‹` / `›` 上一封/下一封（首末封自动 `disabled`）；下拉项两行网格 `grid-template-columns:38px 1fr`
- 下拉列表项用**完整标题**（允许换行、不截断），折叠态按钮用**截断版**
- 下拉内筛选框：按 `编号 + 标题 + 发件人 + 发送时间` 过滤
- `title` 属性三段（`&#10;` 连接）：① 完整标题 ② `发件人：…` ③ `发送时间：…`；英文页对应 `From:` / `Sent:`
- 交互：`Esc` / 点外部 / 选中 / 点状态 chip / 正文搜索框输入 → 自动收起
- 关键变量：`ddOn`（展开态）、`ddQ`（筛选词）；函数：`tabs()` / `ddList(q)` / `ddToggle()` / `ddFilter()` / `pick(i)` / `step(±1)` / `ea()`

**回复内容列不做内滚动**（用户明确要求「不要内滚动」）：`.raw` **不得**设 `max-height` / `overflow-y`，
长原文必须全文展开。

**校验方式**：生成的 HTML 里 `max-height` **恰好 2 处** —— 只允许这两个：

| 位置 | 值 | 为什么允许 |
|------|-----|-----------|
| `.ddlist`（下拉面板） | `max-height:min(62vh,560px)` | 下拉面板滚动是**弹层行为**，与「回复内容不要内滚动」不冲突 |
| `.todo ol`（Open items 清单） | `max-height:240px` | 同上，避免清单把表格挤下去 |

**多于 2 处 = 有人在回复内容里加了内滚动**，必须改掉。
（2026-10-04 实测基线：CN 与 EN 页均为 2。）

### 6.3 「负责人(Owner)」列

第 2 列展示**要求谁回答** + **对方是否回答的标识**，名字用**回复人邮箱地址的名字**。

```
┌ 负责人 ────────────────────────────────────┐
│ Puah Chei Fong  [已回复 · 2026-09-17 09:51] │  ← @提及的应回复方 + 逐人状态
│ <cfpuah@hlbb.hongleong.com.my>              │
│ Lee Jia Maw     [未回复]                    │
│ <jmlee@hlbb.hongleong.com.my>               │
│ ┌ 实际回复 ────────────────────────────┐    │  ← 回复了但不在 @名单里的人
│ │ Rosnah Ab Hamid <rosnahabhamid@…>    │    │
│ └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

- 规则实现：`scripts/owner_rules.py`（`owners_of()` / `owners_with_status()` / `parse_who()`）
- 判定：`@提及的邮箱 ∈ 该行 who 里的邮箱` → **已回复**（带回复时间）；否则 **未回复**
- **无 @提及**的行：显示一行灰色「未指定负责人」，其下照旧列出实际回复人
- 部门/团队型 @提及（如 `@CED`）：显示 `CED（团队）` + 蓝色 `团队` 标签，**不参与「已回复」判定**
- 中英双语：`ow_yes/ow_no/ow_act/ow_team/ow_na` 五个文案在 `I18N` 里；
  **英文版的连接符必须是半角**（`；/：` → `; / :`）

**@昵称 → 人员映射表**（写在 `owner_rules.py` 的 `MENTIONS`，**开工前先按项目替换**）

昵称写在**邮件正文里、纯文本**，没有 href / title，邮箱地址必须外部核对。
验证方法：**正文称呼（greeting）与收件人列表一一对应**，再用邮件抬头佐证。

| @昵称 | 人员 | 邮箱 |
|---|---|---|
| `@Puah` / `@Louise` | Puah Chei Fong | cfpuah@hlbb.hongleong.com.my |
| `@Rosnah` | Rosnah Ab Hamid | rosnahabhamid@hlbb.hongleong.com.my |
| `@Lee` / `@JiaMaw` | Lee Jia Maw | jmlee@hlbb.hongleong.com.my |
| `@Kath` | Hong Kar Yean | kyhong@hlbb.hongleong.com.my |
| `@huiwen` / `@Hoi` | Hoi Hui Wen | hwhoi@hlbb.hongleong.com.my |
| `@elynn` | Elynn Tan Yee Lin | tanyeelin@hlbb.hongleong.com.my |
| `@waiyee` / `@Wai Yee` | Low Wai Yee | wylow@hlbb.hongleong.com.my |
| `@YC` | Yap Yuet Cheng | yap.yuetcheng@hlbb.hongleong.com.my |
| `@Howard` | Howard Tee Wei Heng | howardtee@hlbb.hongleong.com.my |
| `@sundra` | Sundra Lingam Selvarajoo | sundralingam@hlbb.hongleong.com.my |
| `@leong` | Leong Tjun Mun | tmleong@hlbb.hongleong.com.my |
| `@Thomas` | Thomas Ung Yee Teck | thomasungyt@hlbb.hongleong.com.my |
| `@CED` | CED（团队，非个人） | — |

**两个最容易卡住的昵称，考证过程留档**：
- `@Louise` = **Puah Chei Fong**：多封正文以 `Dear Louise, Jia Maw and Hui Wen` 开头，
  收件人恰为 Puah / Lee Jia Maw / Hoi Hui Wen；且 M1 第 8 条 `(@Louise)` 的实际回复人就是 Puah
- `@Kath` = **Hong Kar Yean**：称呼 `Dear JiaMaw&Kath&Thomas&Louise&Wai Yee`，
  收件人恰为 Lee Jia Maw / **Hong Kar Yean** / Thomas Ung / Puah / Low Wai Yee，一一对应

**正则要点**：`@` 后可能跟**多词昵称**（`@Wai Yee`），且 `@Lee` 不能吃掉 `@Leong`。
用「**长键优先 + 末尾否定前瞻**」解决：

```python
_KEYS = sorted(MENTIONS.keys(), key=lambda k: (-len(k), k))
_AT = re.compile(r"@(" + "|".join(re.escape(k) for k in _KEYS) + r")(?![A-Za-z0-9_])", re.I)
```

**不要**用 `@[A-Za-z]+` 这种朴素写法（会得到 `@Wai` 这种半截结果）。

### 6.4 「手工备注」区

**位置**：每行 `问题回复总结` 单元格内容**下方**（`td.sum` 里的 `.memo` 块），**不新增表格列**。

```
折叠态（唯一默认态）☐ 标记为已解决   [已解决]   备忘预览（灰字一行）   [＋ 备忘 / 结论]
                  ↓ 只有点按钮才展开
展开态          ☐ 标记为已解决
                备忘 / 最终结论   [textarea 3 行]
```

- **默认收起**（有内容也不再自动展开）：`memoHTML()` 恒输出 `class="memo"`，`flush()` 不因「已解决/有备注」加 `open`
- 收起时靠「已解决徽标 + 备忘预览灰字 + `tr.solved` 淡绿底」表达状态
- **输入即存**：`input` 事件 → 写 localStorage，**不重新 render**，不打断输入焦点
- **已解决**：`change` 事件写 `s:1`；该行加 `tr.solved` → 淡绿底 + 总结列左侧 3px 绿条

**存储（关键设计，别改）**

- localStorage key = `项目前缀_memo_v2`，结构 `{v: 版本号, d: {条目键: {s, n}}}`
  （`s` = 已解决，`n` = 备忘/结论**单字段**）
- **条目键 = `邮件号 + '-' + md5(问题纯文本)[:10]`**（`item_key()`）。
  用**问题文本哈希**而不是行号 → 重跑后增删条目、顺序变化，备注仍能对上；
  **中英文两页共用同一个键**（两边都拿 `q` 中文原文算哈希）→ 备注在两页互通
- 加载时 `BAKED`（Python 从数据文件 `memos` / `memos_v` 注入）与 localStorage 比版本号，
  `BAKED.v > LS.v` 时以数据文件为准

**哈希口径（必须与渲染器完全一致）**

```python
plain = re.sub(r"<[^>]+>", " ", q or "")     # ← 替换成「空格」，不是空串！
plain = re.sub(r"\s+", " ", plain).strip()
key   = "%s-%s" % (mid, hashlib.md5(plain.encode("utf-8")).hexdigest()[:10])
```

> **踩坑**：用 `re.sub(r"<[^>]+>", "", q)`（直接删标签）核对，**54 条标记只对上 6 条**，其余全被判成「对不上」。
> 差这一个字符哈希就完全不同。**核对前先把 `item_key()` 原文抄过来。**

**取回用户手写标记的判断顺序（别一上来就翻磁盘副本）**

1. 先看 HTML 的烘焙位：`grep -o '/\*MEMO-S\*/.\(0,60\)' xxx_EN.html`
   - 若是 `{"v": 0, "d": {}}` → **文件里确实没有标记**，不必再找同名副本 / 下载目录
2. 标记在**浏览器 localStorage**，键固定，且 **`file://` 源全局共用一份**（CN 页与 EN 页天然互通）
3. 取回（首选）：**用 Tabbit 打开该 `file://` 页面直接读**
   ```js
   const pg = await context.newPage();
   await pg.goto('file:///D:/…/' + encodeURIComponent('xxx_EN.html'), { waitUntil: 'domcontentloaded' });
   await pg.waitForTimeout(2500);
   const raw = await pg.evaluate(() => localStorage.getItem('hp_memo_v2'));
   return { raw: raw };
   ```
   - 路径含中文**必须 `encodeURIComponent`**；返回值常 > 8 KB，`tabbit.py run` 会自动分页拼回
   - **不要碰用户正开着的标签页**，用 `context.newPage()` 新开一个读
4. 兜底（不推荐）：Tabbit 的 leveldb 里能 grep 到记录，但记录是 UTF-16 且对齐错位，解析成本高易错 ——
   **只用来确认「标记确实存在」，取内容仍走浏览器**

**固化进数据文件（让标记在任何机器 / 任何打开方式下都不丢）**

```json
"memos":   {"M1-873157efd8": {"s": 1, "n": "no allow to change vehicle status"}},
"memos_v": 1
```

- **`memos_v` 必须 > 用户浏览器里的 v**，否则烘焙值会被 localStorage 盖掉
- 重渲后**用空 localStorage 跑烟测**，断言 `Object.keys(STORE).length === 标记条数`，才叫真的留存住

**导出 / 导入**：弹层内有 `复制` / `下载文件` / `导入这段 JSON` / `清空全部备注` / `关闭`。
**导出的 JSON 结构就等于数据文件里的 `memos` 字段**，直接写回去再重渲即可（**每次固化把 `memos_v` +1**）。

**与自动状态的关系**：`st`（已确认/部分/转交/未回复）是**从邮件分析出来的**，
手工「已解决」是**我方判断**，两者**互不覆盖、并列显示** —— 要的正是
「系统状态还是 No reply，但我线下已经解决了」这种并行记录。

**「写回本页文件」**（用户选定的保存方式）：把标记**直接写进 HTML 文件本身**，
从此换浏览器 / 换打开路径 / 清缓存 / 重装系统都不丢。

- 实现：File System Access API。点 `[保存到本页文件]` → `showSaveFilePicker({suggestedName: 当前文件名})`
  → 用户确认覆盖 → 句柄存进 `FSA`；**首次之后每次改动自动写回**（防抖 2 s）
- **刷新页面后句柄丢失**（浏览器不允许跨会话持权），需再点一次按钮重连
- **写回原理**：`document.documentElement.outerHTML` 整页序列化 → 定位并替换烘焙位
  - 用 `'/*M' + 'EMO-S*/'` **拼接后再 `indexOf`** —— 直接写完整字面量会先命中源码里自己的那串文本
  - 替换前 `JSON.stringify(...).split('<').join(U003C)`，其中 `U003C` 由
    `String.fromCharCode(92) + 'u003c'` 拼出 → 备忘里写了 `</script>` 也不会破页
- **写回时必须 `LS.v = (LS.v || 0) + 1` 再 `persist()`**（关键！）：
  否则新浏览器打开时 `BAKED.v(0) > LS.v(0)` 不成立，烘焙好的标记会被空的 localStorage 盖掉，**等于白存**
- **降级链**：`showSaveFilePicker` 不存在（Firefox / Safari）或被拒 → 自动改为**下载一份更新后的同名副本**
- **必跑的校验**：桩掉 `createWritable()` 抓写盘内容 → 落盘 → **用空 localStorage 当全新页面重新载入** →
  断言：标记能从烘焙位恢复、仍是收起态、二次写回不丢。
  只测 `bakeHTML()` 会漏掉版本号自增，**这条链路不跑通，「保存成功」就是假的**

### 6.5 统计与「未解决事项 / Open items」

**三张卡片**（**全局**，不是当前邮件）：`已解决` / `未标记 / 未解决` / `已加备注`，由 `updStats()` 刷新。

- `未解决 = 条目总数 − 已标记解决数`（JS `openCount()`）
- 卡片**初始值由 Python 侧算好写死**（`_sol0` / `_open0` / `_memo0`，用 `item_key()` 只数当前清单命中的键），
  这样脚本未执行 / 首帧也能显示真实数字，不会闪 0
- 统计**只遍历当前清单里的邮件条目**（`MAILS[i].items[j].k`），不要用 `STORE` 的键总数 ——
  历史遗留键或非清单邮件的键会把「未解决」算成负数，已用 `Math.max(0, …)` 兜底
- 每封邮件头卡片右侧多一行本封 `未解决 N`（`updStats()` 按当前邮件重算）
- MD 版同步多一行 `未标记 / 未解决：N 条（= 问题条目 X − 已标记解决 Y）`

**Open items 动态清单**（用户点名要的形态）

- 标题：中文「未解决事项」/ 英文固定 `Open items`；**只展示未标记未解决的**问题
- 结构：`<div class="todo"><div class="th">未解决事项<span class="tc" id="todoc">N</span></div><ol id="todol">…</ol></div>`
- 每行形如 `M10 · 4.2 Automatic EDD Bypass Rules`，点击 `jump(i)` 切到该邮件并滚到表格
- 初值 Python 侧算好写死；JS `updTodo()` 挂在 `updStats()` 末尾重算 —— 与顶部卡片同一集合
- `ol` 限高 240px 滚动，避免把表格挤下去
- **数据不删**：`todos`（含 `held_todos`）仍留在数据文件，只是 HTML 不再渲染；MD 版保留原小节 + 另加未解决清单
- **行标题用 `short_q()`**：先取 `<br>` 前的主句，再去标签、超 88 字截断
  - **不要按 em dash 二次切割** —— 英文标题里的 `— Puah's 09-10 reply` 正是区分两条未完项的标识，
    切掉后列表里会出现两行一模一样的 `2.1 ETB Asset Values @Puah`
  - 补充规则：` — ` 之后若超过 44 字（说明是正文而非小标题）才整段丢弃

**筛选 chip**：状态 chip 末尾多两个 —— `已解决/有备注 N`（内部 `fs==='MEMO'`）
与 `未解决 N`（内部 `fs==='OPEN'`）。
`OPEN` 的数字是**当前邮件**的未解决数（与其它状态 chip 同口径 —— 点开看到的行数和数字对得上）。
备忘文本也进了搜索关键字，可以搜备注里的内容。

### 6.6 英文版「零中文」硬规则

英文版**不允许残留任何中文字符**。渲染脚本已内置 `en_clean()`：

1. 删除问题里的中文附加子句 `<span class='sub'>…</span>`（中文版保留，英文版剔除）
2. 把 `<span class='warn'>⚠ 中文…</span>` 通过 `EN_WARN` 映射表换成英文等价表述
3. **数据层**仍需人工保证 `qe` / `se` / `raw` 里没有中文（无法靠正则兜住）

**`en_clean()` 的两条关键规则（踩过坑，别改回去）**

1. **只剔除「含中文」的 sub 子句**。部分条目的 `qe` 里 sub 子句本身就是**英文**，那是有效信息，不能删。
   实现方式是对 sub 内容做 `[\u4e00-\u9fff]` 判定，命中才删
2. **中文版的 `q` 必须原样输出**，只有英文版才过 `en_clean`。
   曾写成 `q=en_clean(it["q"]) if lang=="zh"`，导致**中文版的问题子句被静默剥掉**
   （CN 页面看不出来，但 `class='sub'` 计数从 156 掉到 2）。
   改完务必核对：**CN 页 `sub` 计数应有上百个，EN 页 CJK 应为 0**

**扫描必须对「整个文件」做，不能只扫页面正文**：中文写在 **CSS 注释 / JS 注释**里也会被命中。
**结论：`JS` / `CSS` 字符串里的所有注释一律写英文。**

```bash
"$PY" -c "
import io,re
s=io.open('xxx_EN.html',encoding='utf-8').read()
# 广义 CJK：汉字 + 中文标点(\u3000-\u303f) + 全角符号(\uff00-\uffef)
print('CJK:', len(re.findall(r'[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]', s)),
      '| max-height:', s.count('max-height'))"
```

> **只扫 `[\u4e00-\u9fff]` 会漏**：负责人列的连接符写成全角 `；` `：` 会让 EN 页残留中文标点，
> 但汉字正则返回 0。**必须带上 `\u3000-\u303f` 与 `\uff00-\uffef`**。

**已知易漏点（每次都要查）**

- `raw` 原文里对方自己夹带的中文（人名、括号注释）→ 原文原则上保持逐字，但**人名与括号注释要英文化**
- `se` 总结里的中文人名 → 英文化
- `q` 标题里的**全角括号** → 半角
- **新增分组时最易残留的两个字段**：
  1. `to` / `cc` 里的 **`n_en`** —— 若直接从 `n` 复制（如 `ivanzhong(钟燕清)`），EN 页就出中文
  2. `items[].when` —— **渲染脚本没有 `when_en`，EN 页直接复用 `when`**，所以 `when` 本身就要写英文
- **交付前先跑数据层字段扫描**（`subject_en` / `sent_en` / `sender_en` / `to|cc.n_en` / `qe` / `se` / `when` /
  `raw` / `cf.en`），比事后扫 HTML 快得多，也能精确定位是哪个 mail 的哪个字段

---

## 7. 交付前的校验清单（一项不过不交付）

**先跑自动校验**（覆盖下面 1~6、9 项）:

```bash
"$PY" "$SK/verify_render.py" <输出目录> --data <数据文件> --node "<node.exe>"
# 示例：对技能自带的 demo 数据跑一遍
"$PY" "$SK/verify_render.py" ./demo_out --data "$SK/../examples/minimal_data.json"
# 退出码 0 = 全通过；1 = 有 FAIL
```

然后把剩下需要真实浏览器的项手工过一遍：

| # | 校验 | 期望 |
|---|------|------|
| 1 | EN 页广义 CJK | **= 0** |
| 2 | `max-height` 计数 | **= 2**（`.ddlist` 与 `.todo ol` 各一处，见 §6.2） |
| 3 | CN 页 `class='sub'` 计数 | 上百（实测真实数据集 **129**）。若掉到个位数 → 中英文 `en_clean` 串了 |
| 4 | 负责人列渲染数 | `ow-nm` 计数 ≈ 有 @提及的条目数 |
| 5 | 备注模板块 | `.memo-hd` / `.memo-pv` / `.memo-bd` 在**静态 HTML 里各 1 次**（`rows()` 里的模板定义，非渲染后行数）→ **真实行数必走 JS 烟测的第 7 项** |
| 6 | JS 语法 | 抽 `<script>` → `node --check` |
| 7 | JS 烟测 | stub（`document` / `localStorage` / `navigator`）后 `eval`，断言 `MAILS.length`、备注块数、`mset()` 生效 |
| 8 | 下拉交互 | `tabs()` 里 `.nav`=2、`ddOn=true` 后选项数 = 邮件数、首末封 disabled |
| 9 | 数据层字段扫描 | `*_en` 字段无中文（`sub` 内的除外；`held` 里的降级为 WARN） |
| 10 | **写回往返** | 桩掉 `createWritable()` → 落盘 → 空 localStorage 重载 → 标记恢复 |

> **改了备注/写回逻辑，必须同时跑三样**：`node --check`（语法）、备注烟测（默认收起 + 烘焙位 + EN 零中文）、
> **写回往返**（写回后重开能恢复）。只跑前两样会漏掉「版本号不自增 = 白存」这类逻辑洞。

**烟测桩的两个细节**

- 桩元素记得带 `focus(){}`（`ddToggle` 会 focus 筛选框；缺了会报 `f.focus is not a function`，
  是**桩的问题**不是页面的）
- **断言不要写死语言**：`h15.indexOf('cf-badge')`、`/one-hour meeting/i` 这类断言在 CN 页必然 FAIL
  （是断言选错了 token，不是页面 bug）。断言要么查数据层，要么用
  `String.fromCharCode(24847,35265,19981,19968,33268)` 这种方式兼容中英，避免把中文写进 JS 文件
- **回归脚本的期望值会随数据增长失效**：硬编码「M1 未解决数 = 1」这类断言，条目从 21 涨到 23 后就 FAIL。
  改成**动态写法**（如「取消前先读取当前值再断言 `+1`」）

---

## 8. 交付与发信

1. `present_files` 交付三个文件（CN / EN / MD）
2. 用户若要求「把英文版发到我的邮箱 xxx@qq.com」→ **用 Agent Mail，不要走 Coremail**
   - 理由：Coremail 发信要 `TABBIT_ALLOW_SEND=1`，既与「AI 只出草稿、用户自己点发送」的既有约定冲突，
     公司邮箱外发也受合规约束
   - 流程：
     ```
     1) 先 GetMe 确认 alias / scope(mail:send) / 附件上限
     2) 附件名必须是 ASCII —— 先把文件复制成 ASCII 名再上传，否则中文名在 QQ 邮箱里易乱码
        cp "客户反馈汇总_EN.html" "Feedback_Summary_EN_20260927.html"
     3) agent_mail_upload_attachment(file_path=<绝对路径>) -> file_id（临时引用，会过期）
     4) SendMessage(to=[…], subject, body, body_format="PLAIN",
                   file_refs=[{file_id}], skip_confirmation=true)
        —— 仅在用户**明确点名收件人与发什么**时才用 skip_confirmation；
          若是「要不要发一下」这类模糊表述，先要一次确认
     5) 发完用 ListMessages(dir="sent", limit=3) 核对 has_attachments 与收件人，再回报
     ```
   - 注意 `ListMessages` 的 folder 参数名是 **`dir`**（不是 `folder`），传错会参数校验失败

---

## 9. 踩坑速查表

### 9.1 Tabbit / 浏览器层

| 坑 | 表现 | 解法 |
|----|------|------|
| `run` 不支持 `-` 当 stdin | 1~2 秒「成功」返回但无数据 | **一律先把 JS 落盘成 `.js` 文件再传路径** |
| `run` 传 Git Bash 短路径 | 报 `Invalid regular expression flags`（路径被当成 JS 代码） | 用工作区下的常规绝对路径 |
| `page.evaluate(fn, a, b, c)` | `Too many arguments…` | **只接受一个参数**，多值包成对象 |
| 裸 `document` 不可用 | `document is not defined` | 所有 DOM 访问必须包在 `await page.evaluate(...)` 里 |
| `claim --tab` 失败 | `TAB_OWNERSHIP_CONFLICT` | 用 `resume --group`（`ensure` 已自动处理） |
| `--task` 位置 | 报错 | **是全局选项，必须写在子命令前**：`tabbit.py --task X ensure` |
| `finish` 后再用同名 task | `Unknown task name` | 换新任务名，或 `ensure` 重新接管。**邮箱任务名每轮换新**（如 `mail-0925`） |
| `nodejs` 缺 `--request-id` | `{"code":"REQUEST_FAILED"}` | `tabbit.py` 已自动生成；**直接调 CLI 时要自己补** |
| 多个 Coremail 标签 | `ensure` 只接管第一个匹配 host 的 | 需要干净会话用 `--new` |
| 列表是旧快照 | 今天/昨天分组停在最后一次加载时刻，新邮件插进旧分组造成时间乱序 | 读取前先刷新（`span[data-btn="refresh"]` 或重跑 `ensure`） |
| Bash 工具 coreutils 缺失 | `ls: command not found` | 命令开头加 `export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"`，或改用 PowerShell |
| 切文件夹 | 用 `page.goto()` 会白屏 | **一律点击侧栏元素** |

### 9.2 数据 / 渲染层

| 坑 | 表现 | 解法 |
|----|------|------|
| 改 `q` 破坏备注键 | 用户标记全部失联 | **`q` / `qe` 碰不得** |
| `held` 撞号 | 生成与主清单重复的 id | 两边取全局 max 再 +1 |
| `memos_v` 不够大 | 烘焙值被空 localStorage 盖掉 | 每次固化 **`memos_v` +1** |
| 写回时 `LS.v` 不自增 | 看着存好了，新浏览器打开就没了 | 写回前 `LS.v = (LS.v||0)+1` 再 `persist()` |
| 并行 Edit 丢改动 | 工具返回 success 但改动没落盘（运行时才 `NameError`） | **同一文件的多个 Edit 不要放在同一条消息里并行发**，串行 + 改完 `grep` 复核 |
| Python 三引号里的 JS 转义层数 | 产物 JS 报 `Unexpected identifier` → **整页白屏无 JS** | `JS = """…"""` 是非 raw 字符串，要得到产物的 `\'` **源码必须写 `\\'`**；正则要写 `\\s`。**改完必须抽 `<script>` 跑 `node --check`** |
| CRLF 行尾 | Python 里多行 `str.replace` 的 `count==1` 断言失败 | 先 `s = s.replace('\r\n', '\n')` |
| `_tools/*.py` 被判定为二进制 | Read / Edit 报 `Cannot display content of binary file` | 用 Python 打印查看；改写用一次性补丁脚本（`str.replace` + `assert count==1`），落盘时归一为 LF |
| 含中文脚本编码 | `SyntaxError: (unicode error) 'utf-8' codec can't decode…` | 落盘后**先探测编码再归一**：`try utf-8 except gbk` → `io.open(p,'w',encoding='utf-8',newline='\n')`。源码里 `⚠`/`✅`/`—`/`·` 一律写 `\u26a0` 等转义 |
| 旧版文件混用 | 结构不一致 | 采用旧结构的历史版本文件**不要混用**，以当前 `M*` 归集格式为准 |

---

## 10. 目录结构与参考文件

```
coremail-sent-feedback-tracker/
├── SKILL.md                      ← 本文件（主入口）
├── README.md                     ← 安装 / 依赖 / 快速开始
├── CHANGELOG.md                  ← 版本变更记录
├── references/
│   ├── 01-coremail-web-dom.md    ← Coremail XT5 DOM 速查 + 会话遍历 + 回复全部清单
│   ├── 02-feedback-extraction.md ← 五类反馈载体提取细则 + 彩色批注实例
│   ├── 03-data-schema.md         ← 数据文件完整 schema + 字段口径
│   ├── 04-render-spec.md         ← 三件套渲染规范（版式 / i18n / 零中文）
│   └── 05-pitfalls.md            ← 踩坑与修复全表（含时间线）
└── scripts/
    ├── tabbit.py                 ← ★ 浏览器封装：ensure / 搜索 / 读取 / 移动 / 大结果分页
    ├── guards.py                 ← ★ 安全边界：所有 JS 执行前的静态扫描，唯一策略源
    ├── mail_bootstrap.js         ← 模板：打开 Coremail + 自动登录
    ├── mail_search.js            ← 模板：全文搜索并列出行摘要
    ├── mail_read.js              ← 模板：按索引或关键词读取单封
    ├── mail_move.js              ← 模板：移动邮件（dry-run 默认 + 相关性校验 + 失败回滚）
    ├── mail_hdr_full.js          ← 模板：展开折叠联系人 + 结构化提取 from/to/cc
    ├── mail_walk_prev.js         ← 模板：用 a.u-page-prev 连读会话前 N 封
    ├── strip_quote.py            ← 剥离引用历史，只留本轮新增内容
    ├── owner_rules.py            ← ★ @提及 → 负责人映射 + 答复状态判定（按项目替换 MENTIONS）
    ├── render_tracker.py         ← ★ 渲染器：数据文件 → CN/EN HTML + MD 三件套
    ├── verify_render.py          ← ★ 交付前静态校验（CJK / max-height / CJK 数据层 / node --check）
    ├── render_report.py          ← 轻量报告渲染器（单表版，快速出稿用）
    └── report_template.html      ← 单文件报告骨架（浅色 / 大字号 / 筛选 / hover）
examples/
└── minimal_data.json             ← 最小可运行示例数据（跑通流程 / 练手用）
```

**★ = 核心文件**。改数据口径只动 `owner_rules.MENTIONS` 与数据文件的 `scope`；
改版式只动 `render_tracker.py` 的 `CSS` 与 `I18N`。

### 环境变量速查

| 变量 | 用途 |
|------|------|
| `TABBIT_TASK` | 默认任务名（默认 `mail-attach`） |
| `TABBIT_CLI` | 启动器路径（Windows 默认 `%LOCALAPPDATA%/Tabbit/LocalAgent/bin/tabbit-cli.exe`） |
| `COREMAIL_URL` | 邮箱地址（默认 `https://wemail.webank.com`） |
| `TABBIT_ALLOW_SEND` / `_ATTACH` / `_CLOSE` / `_MUTATE` / `_LINK` | 放行对应的 CONFIRM 级操作，**只在单条命令生效** |
