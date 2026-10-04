# 02 · 五类反馈载体的提取细则

对方回一条需求，可能用完全不同的载体。**判断错载体 = 漏掉整批意见。**

| # | 载体 | 典型信号 | 状态默认值 |
|---|------|----------|-----------|
| 1 | 常规正文逐条回复 | 正文带编号 / `Re:` | 按实际内容判 |
| 2 | 表格**彩色字体**批注 | 正文是「领域 × 我方理解 × 需确认信息」的表 | `part` |
| 3 | 表格**追加列/单元格**回复 | 整张表贴回来，答案追加在 Owner 列 | `part` |
| 4 | Google Docs 评论通知 | `comments-noreply@docs.google.com` | `part` / `ok` / `fwd` |
| 5 | 会议 / 群聊 | 日历邀请、无正文 | **不建 item**，记邮件级 `note` |

---

## 载体 1 · 正文逐条回复

### 处理流程

```bash
python scripts/strip_quote.py reply.json          # reply.json = tabbit.py 的输出
python scripts/strip_quote.py reply.json 4000     # 限制输出长度
```

### 剥离规则

匹配以下标记，取**第一个位置 >60** 的切点：

- `On ... wrote:`
- `-----Original Message-----`
- `____________`
- `From: ... Sent: ...`

正文里的 `\xa0`（NBSP）统一替换为普通空格。

> ⚠️ **不做剥离就会把「自己的原始提问」当成「对方的回复」** —— 这是最高频的误判。
> 客户回复里混着整条历史，必须先剥离再总结。

### 切层与作者识别

用 `wrote:` 的文本偏移切层，比 DOM 层级可靠得多：

```python
marks = [m.start() for m in re.finditer(r'wrote\s*:', body)]
layer0 = body[:marks[0]]      # 最外层 = 最新一封的正文
# 该层末尾的 "Thanks and regards, <姓名>" 即作者
```

---

## 载体 2 · 表格彩色字体批注

### 为什么必须读颜色

`innerText` 只能拿到文字，**颜色丢失** —— 多个人（A 蓝字 / B 红字 / C 紫字）的批注会混成一团，
无法判断「谁说了什么」。

### 结构

正文在 iframe（URL 含 `viewMailHTML`）里。结构是「一个领域一行，4 个单元格」：

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

> **踩坑**：按 TreeWalker 的文本节点顺序 + 「最近的领域名」归属会出错 ——
> `Policy ( UW)` 这类名字在 DOM 里被拆成两个文本节点，匹配失败后红色批注被错归到上一个领域
> （`Ref No.`）。**必须用 `tds[0]` 整格文本做匹配。**

### 必须放进 `IGNORE` 的默认色

否则签名、外部邮件警示、我方模板色会混入：

```
rgb(0,0,0)      rgb(153,153,153)  rgb(0,121,189)   rgb(19,79,92)
rgb(7,55,99)    rgb(156,101,0)    rgb(51,51,51)    rgb(61,133,198)
```

### ⚠️ 颜色不能可靠区分人（2026-09-17 实测，重要）

同一封邮件里会叠加多层引用，**颜色会被多人共用**，不要用「颜色 → 人」的固定映射去归属：

| 颜色 | 实测对应 |
|------|----------|
| `rgb(0, 0, 255)` 蓝 | 被 **4 个人**共用（各自用默认批注色）→ **不能认定为某一人** |
| `rgb(255, 0, 0)` 红 | 本次对应**该封邮件的发件人** |
| `rgb(153, 0, 255)` 紫 | 本次稳定对应某一固定人（她在正文写了 `My comments in purple`） |

**✅ 正确的归属方法**：批注**写在哪个领域行上，就归该领域的 Owner**（表格里 `@xxx` 那一列）。

这套规则与所有观察到的批注完全自洽。**例外**：同一领域出现两条内容不同的批注时要分别归属
（如某领域既有 A 的 `Yes`（紫字）又有 B 的 `No difference…`（红字）→ 两人都记）。

### 黑色（默认色）批注同样是有效回复

只是不会被彩色提取命中 —— **必须回读纯文本正文兜底**。

实测漏项：`Sales Data Entry` 的 `user to select product group = IHP.` 和 `Dealer` 的
`No difference` 就是黑字，只看彩色批注会漏掉。

> **表格类邮件的收尾动作 = 回读纯文本正文一遍。**

### 没人用彩色批注时

回去读纯文本正文（有人把要求写在正文开头、有人只写「+ Loop in Lee」）。

---

## 载体 3 · 汇总表追加列

客户有时不逐条批注，而是把**整张表**贴回来、把答案追加在 `Owner` 列里。
这时**彩色批注提取完全失效**（答案多为默认黑字），必须走结构化路线。

### ① 逐 `<table>` 取行

`<table>` 是嵌套的，外层表会包含内层表的行：

```js
const fr = page.frames().find(f => (f.url() || '').indexOf('viewMailHTML') >= 0);
const out = await fr.evaluate(() => {
  const cl = s => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const tabs = [];
  Array.from(document.querySelectorAll('table')).forEach((tb, ti) => {
    const rows = [];
    Array.from(tb.querySelectorAll('tr')).forEach(tr => {
      const tds = Array.from(tr.children);
      if (tds.length < 4) return;
      const c = tds.map(td => cl(td.innerText));
      if (!c[0] || c[0].length > 60) return;
      rows.push(c);
    });
    if (rows.length >= 5) tabs.push({ ti, nr: rows.length, rows });
  });
  return { ntab: tabs.length, tabs };
});
```

### ② 用 `wrote:` 文本偏移切层，再按签名认作者

```python
marks = [m.start() for m in re.finditer(r'wrote\s*:', body)]
layer0 = body[:marks[0]]      # 最外层 = 最新一封的正文
# 该层末尾的 "Thanks and regards, <姓名>" 即作者
```

### ③ 用「相邻两层 diff」定位本轮新增答复

逐行比对 `layer0` 与 `layer1` 的 `Owner` 列，**只有变化的那几行才是最新发件人本轮写的**，
其余都是引用继承 —— **这是最不容易误归属的方法**。

### ④ 行内约定要用 ③ 交叉验证

`Owner` 列的行内约定是 `@nick - <该人的答复>`，但**不能只看 `@nick`**：

> **实测坑**：某两行标注 `@waiyee` 负责，实际是该层发件人在本轮新加的
> （该层末尾署名是「Thanks and regards, <另一位>」）。只看 `@waiyee` 会误判成 Wai Yee 回答。

### ⑤ 默认黑字回复一定会漏

某条此前被判「未回复」，就是因为只读了彩色批注。
**表格类邮件的收尾动作 = 回读纯文本正文一遍。**

---

## 载体 4 · Google Docs 评论通知

### 为什么必须抓

对方大量反馈**不走邮件正文**，而是在 Google Docs 里评论并 @你指派 action item，
邮箱只收到 `comments-noreply@docs.google.com` 的通知
（列表里发件人显示为 `X (Google Docs)`，主题形如 `<文档名> - <评论摘要>`）。

**这类反馈必须抓，否则会漏掉整批客户意见。**

### 抓法

用**按行索引批量读取**（列表是静态快照，连续读多封不受影响）。

### 正文解析

```
<谁> mentioned you in a comment / assigned you an action item in the following document
  → 文档名 + N comment(s)
  → 评论线程逐条（<锚点文字> / <评论人> • <时间> / 评论正文）
  → Assigned to you
```

- **先 `.split('Google LLC')[0]` 再读**，去掉页脚噪声
- 注意 `You do not have commenting rights to <doc>` —— 没权限时只能读到通知，无法回帖

### 归集规则

| 项 | 规则 |
|----|------|
| 粒度 | **一个通知 = 一条 item** |
| `raw` | 该批评论整体，多条评论用 `\n` 分隔并**编号** |
| `who` | **提出评论的人**（通常是同一个人） |
| `sum` | 逐条归纳对方诉求 |
| 状态 | 默认 `part`（待我方落实）；对方内部已互相答复闭环的可给 `ok`；纯转派他人的给 `fwd` |

### 文档 → 邮件分组的映射

按文档名归入对应的我方邮件。**同一文档可能横跨多封我方邮件**，需按内容判断。
用数据文件的 `MAILS[].docs` 字段登记映射关系。

**示例映射**（HP 项目，供参考结构）：

| 文档 | 归入 |
|------|------|
| `HP FSD Batch3-01-Used & Recond Car-0812` | M1 |
| `HP FSD Batch3-02-Main Workflow-related-0814` | M10 |
| `HP FSD Batch3-03-Individual Guarantor-0824` | M16 |
| `HP FSD Batch3-04-Dealer Maintenance-0814` | M14 |
| `HP FSD Batch3-09-OCR` | M8（在 `held` 里） |
| `HP FSD Batch3-11-Parameter` | M10（同体系，无独立我方邮件） |

> 找不到对应我方邮件的文档，归入**主题最接近**的那封，并在 `sum` 里注明「源自 <文档名> 评论」。

---

## 载体 5 · 会议 / 无正文邮件

日历邀请、会议通知等**不属于「某条问题的回复」**的进展。

- 记在**邮件级 `note` / `note_en` 字段**，渲染成浅蓝底的「进展备注 / Progress」行
- **不要硬塞进 item**
- 用途：会议邀请、我方补充动作、内部交接等

```json
{ "id": "M21", "…": "…",
  "note":    "09-25 两场会议已召开，邮件中无纪要",
  "note_en": "Two meetings held on 09-25; no minutes circulated by email" }
```

> ⚠️ 注意别和 `memo`（每条结论的手工备注）搞混 —— 后者是**条目级**的，`note` 是**邮件级**的。

---

## 附 · @昵称考证方法（完整实例）

昵称写在**邮件正文里、纯文本**，没有 href / title，邮箱地址必须**外部核对**。

### 方法：正文称呼 ↔ 收件人列表一一对应

再用邮件抬头佐证。

### 实例 A：`@Louise` = Puah Chei Fong

| 证据 | 内容 |
|------|------|
| 正文称呼 | 多封正文以 `Dear Louise, Jia Maw and Hui Wen` 开头 |
| 收件人列表 | 恰为 Puah / Lee Jia Maw / Hoi Hui Wen |
| 行内证据 | 某封第 8 条 `(@Louise)` 的实际回复人就是 Puah |

**结论**：`@Louise` → Puah Chei Fong（`cfpuah@…`）

### 实例 B：`@Kath` = Hong Kar Yean

| 证据 | 内容 |
|------|------|
| 正文称呼（09-11） | `Dear JiaMaw&Kath&Thomas&Louise&Wai Yee` |
| 收件人列表 | Lee Jia Maw / **Hong Kar Yean** / Thomas Ung / Puah / Low Wai Yee —— **一一对应** |
| 正文称呼（09-02） | `Dear JiaMaw&Kath&Thomas` |
| 收件人列表 | Lee Jia Maw / **Hong Kar Yean** / Thomas Ung —— 同样吻合 |

**结论**：`@Kath` → Hong Kar Yean（`kyhong@…`）

> **注意**：该人**不在**收件人显示名里出现 `Kath` 字样 —— 只能靠「称呼 ↔ 收件人」的**位置对应**
> 推出来。这是最容易卡住的类型，务必留档考证过程。

### 正则实现

`@` 后可能跟**多词昵称**（`@Wai Yee`），且 `@Lee` 不能吃掉 `@Leong`：

```python
_KEYS = sorted(MENTIONS.keys(), key=lambda k: (-len(k), k))      # 长键优先
_AT = re.compile(r"@(" + "|".join(re.escape(k) for k in _KEYS) + r")(?![A-Za-z0-9_])", re.I)
                                                                  # 末尾否定前瞻
```

**不要**用 `@[A-Za-z]+` 这种朴素写法（会得到 `@Wai` 这种半截结果）。

### 答复状态判定

```python
def owners_with_status(q_html, who_html, when, lang="zh"):
    owners = owners_of(q_html, lang)                          # @提及的应回复方
    replied_emails = {x["e"].lower() for x in parse_who(who_html)}
    for o in owners:
        if o["e"] and o["e"].lower() in replied_emails:
            o["replied"] = True
            o["when"] = when or ""
    known = {o["e"].lower() for o in owners if o["e"]}
    extra = [x for x in parse_who(who_html) if x["e"].lower() not in known]
    return owners, extra     # extra = 实际回复了但不在 @名单里的人
```

**特殊处理**

- **无 @提及**的行：显示一行灰色「未指定负责人」，其下照旧列出实际回复人
- **部门/团队**型 @提及（如 `@CED`）：显示 `CED（团队）` + 蓝色 `团队` 标签，**不参与「已回复」判定**
- 中英双语：`ow_yes/ow_no/ow_act/ow_team/ow_na` 五个文案在渲染器 `I18N` 里；
  **英文版的连接符必须是半角**（`；/：` → `; / :`）

---

## 附 · 状态（st）判定口径

| 值 | 中文 | 英文 | 判定标准 |
|----|------|------|----------|
| `ok` | 已确认 | Confirmed | 对方给出了明确结论，无需再追问 |
| `part` | 部分回复 | Partial | 答了一部分，或只给了方向性回应 |
| `fwd` | 转交他人 | Forwarded | 对方把问题转给了第三方/其他人 |
| `none` | 未回复 | No reply | 至今无任何回应（**注意先排除 Docs/会议渠道**） |

> ⚠️ **判定前先检查其他渠道**：某条线索「零邮件回复」很可能是因为对方在 Google Docs 评论里回了。
