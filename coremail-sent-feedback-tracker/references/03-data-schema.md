# 03 · 数据文件完整 Schema

数据文件是所有渲染产物的**唯一输入**。文件名建议 `<项目>_data.json`（如 `tracker_data.json`），
放在工作目录下，渲染器通过命令行参数指定：

```bash
python scripts/render_tracker.py <data.json> <outdir>
```

---

## 1. 顶层结构

```json
{
  "updated":   "2026-09-27",
  "window":    "2026-08-22 ~ 2026-09-26",
  "window_en": "2026-08-22 ~ 2026-09-26",
  "scope":     { … },
  "todos":     [ … ],
  "held_todos":[ … ],
  "memos":     { … },
  "memos_v":   1,
  "mails":     [ … ],
  "held":      [ … ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `updated` | string | ✅ | 更新时间，显示在顶部卡片 |
| `window` | string | ✅ | 统计窗口（中文），显示在顶部卡片 |
| `window_en` | string | ✅ | 统计窗口（英文） |
| `scope` | object | ○ | 口径声明，见 §2。渲染器目前不读，但**强烈建议写**（便于追溯 + 换人接手） |
| `todos` | array\<object\> | ○ | 待我方回应清单。**HTML 不再渲染**（改为动态未解决清单），MD 版仍渲染，数据保留 |
| `held_todos` | array\<object\> | ○ | 对应 `held` 里邮件的待办 |
| `memos` | object | ○ | 固化后的手工标记，见 §5 |
| `memos_v` | int | ○ | 标记版本号，见 §5.3 |
| `mails` | array\<object\> | ✅ | **主清单**，参与统计 |
| `held` | array\<object\> | ○ | **保留区**，结构与 `mails` 完全一致，**不参与统计** |

---

## 2. `scope`（口径声明）

```json
"scope": {
  "self_addr":    "leonerdli@webank.com",
  "peer_domains": ["hlbb.hongleong.com.my", "hlisb.hongleong.com.my"],
  "note":         "只统计本人发出的邮件；其余移入 held"
}
```

| 字段 | 说明 |
|------|------|
| `self_addr` | **「我方发出」的判据** —— 比对邮件的 `from_addr` |
| `peer_domains` | 「对方」的域名列表，用于识别来件与统计分布 |
| `note` | 自由文本口径说明 |

> ⚠️ **判据是 `from_addr`，不是 `sender`。**
> 收件箱里有的邮件 `sender` 写着自己，但 `from_addr` 是对方地址（对方来件），**不算本人发出**。

---

## 3. `mails[]`（主清单项）

```json
{
  "id": "M1",
  "sender":    "leonerdli(李斌)",
  "sender_en": "leonerdli (Li Bin)",
  "subject":    "Clarification Required: System Requirements for Used, Recond, and IHP",
  "subject_en": "Clarification Required: System Requirements for Used, Recond, and IHP",
  "sent":    "2026-08-22 首轮 · 08-30 跟进 · 09-11 更新",
  "sent_en": "1st round 2026-08-22 · follow-up 08-30 · update 09-11",
  "from_addr": "leonerdli@webank.com",
  "note":    "会议进展备注（可选）",
  "note_en": "Progress note (optional)",
  "docs":    ["HP FSD Batch3-01-Used & Recond Car-0812"],
  "to": [ … ], "cc": [ … ],
  "items": [ … ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 分组编号，`M1` / `M2` / … 渲染时显示为 chip 与下拉项左列 |
| `sender` | string | ✅ | 发件人显示名（中文），建议 `账号(中文名)` 格式 |
| `sender_en` | string | ✅ | 发件人英文显示名 |
| `subject` | string | ✅ | 邮件主题（用于**下拉项完整展示**与 hover 提示第一行） |
| `subject_en` | string | ✅ | 英文主题 |
| `sent` | string | ✅ | 发送时间，多轮用 ` · ` 连接 |
| `sent_en` | string | ✅ | 英文发送时间 |
| `from_addr` | string | ✅ | ⭐ **口径判据字段** |
| `note` | string | ○ | 邮件级「进展备注」（会议、我方动作等）。**缺省不渲染** |
| `note_en` | string | ○ | 英文进展备注 |
| `docs` | array\<string\> | ○ | 关联的 Google Docs 文档名（便于追溯评论来源） |
| `to` | array\<person\> | ○ | 收件人，见 §4 |
| `cc` | array\<person\> | ○ | 抄送，见 §4 |
| `items` | array\<object\> | ✅ | 问题条目，见 §6 |

### `id` 的命名空间

`held` 与 `mails` **共用同一命名空间**。新加 `held` 条目时必须取**全局 max**：

```python
held_max = max([int(h["id"][1:]) for h in d.get("held",  []) if h["id"][1:].isdigit()] or [0])
main_max = max([int(m["id"][1:]) for m in d.get("mails", []) if m["id"][1:].isdigit()] or [0])
new_id   = "M%d" % (max(held_max, main_max) + 1)
```

> **实测坑（2026-09-27）**：只对 `held` 取 max，生成了与主清单重复的 id。

---

## 4. `person` 对象

```json
{ "n": "Puah Chei Fong", "n_en": "Puah Chei Fong",
  "e": "cfpuah@hlbb.hongleong.com.my",
  "org": "HLBB", "name_fallback": "cfpuah" }
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `n` | ✅ | 邮箱显示名（中文上下文） |
| `n_en` | ✅ | 英文显示名。**不要直接从 `n` 复制** —— 若 `n` 含中文（如 `ivanzhong(钟燕清)`），EN 页会残留中文 |
| `e` | ✅ | 邮箱地址 |
| `org` | ○ | 所属组织，用于分组显示 |
| `name_fallback` | ○ | 显示名缺失时的兜底（通常是邮箱前缀） |

**渲染行为**

- `n` 为空 → 渲染成**纯邮箱地址**
- **完整列出全部收件人与抄送人，不截断、不折叠**（单页签下一次只看一封，头部再长也只占一屏）

---

## 5. `memos` / `memos_v`（手工标记固化）

### 5.1 结构

```json
"memos": {
  "M1-873157efd8": { "s": 1, "n": "已电话确认；最终口径：允许手工录入" },
  "M10-3c9a71b2e4": { "n": "待对方补附件" }
},
"memos_v": 1
```

| 键/字段 | 说明 |
|---------|------|
| 键 | `邮件号 + '-' + md5(问题纯文本)[:10]` |
| `s` | `1` = 已解决（缺省或 `0` = 未标记） |
| `n` | 手写备忘 / 最终结论（**单字段**，中英页共用同一份） |

### 5.2 哈希口径（必须与渲染器完全一致）

```python
plain = re.sub(r"<[^>]+>", " ", q or "")     # ← 替换成「空格」，不是空串！
plain = re.sub(r"\s+", " ", plain).strip()
key   = "%s-%s" % (mid, hashlib.md5(plain.encode("utf-8")).hexdigest()[:10])
```

> **实测坑**：用 `re.sub(r"<[^>]+>", "", q)`（直接删标签）去核对，**54 条标记只对上 6 条**，
> 其余 48 条全被判成「对不上」，差点当成版本错位去排查。
> 差这一个字符哈希就完全不同。**核对前先把 `item_key()` 原文抄过来。**

### 5.3 `memos_v` 的作用（关键）

**`memos_v` 必须 > 用户浏览器里 localStorage 的 `v`**，否则烘焙值会被 localStorage 盖掉。

- 加载逻辑：`BAKED`（从数据文件注入）与 localStorage 比版本号，`BAKED.v > LS.v` 时以数据文件为准
- **每次固化标记都要把 `memos_v` +1**
- 重渲后**用空 localStorage 跑烟测**，断言 `Object.keys(STORE).length === 标记条数`，才叫真的留存住

### 5.4 红线

**不要改动被标记条目的 `q` / `qe`。**

键 = `mid + md5(q)`。改一个字哈希就变，用户所有标记当场变孤儿。

| 可改 | 不可改 |
|------|--------|
| 剔邮件、改状态、改总结（`sum`/`se`）、改 Owner、改 `when`、更新 `raw` | **`q`**、**`qe`** |

---

## 6. `items[]`（问题条目）

```json
{
  "q":  "1. 系统需求范围（@Puah）",
  "qe": "1. System requirement scope (@Puah)",
  "who":    "Puah Chei Fong<br>cfpuah@hlbb.hongleong.com.my",
  "when":   "2026-08-28 11:45",
  "raw":    "Confirmed. We will follow the existing HP flow.",
  "sum":    "已确认，沿用现有 HP 流程。",
  "se":     "Confirmed. Follow the existing HP flow.",
  "st":     "ok",
  "cf":     { "zh": "客户内部对此项答复不一致", "en": "Inconsistent answers within the client" }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | ✅ | 问题（中文 HTML）。**允许 `<b>` / `<code>` / `<br>` / `<span class='warn'>` / `<span class='sub'>`** |
| `qe` | string | ✅ | 问题英文版。**数据层必须无中文**（无法靠正则兜住） |
| `who` | string | ✅ | 回复人，格式 `姓名<br>邮箱`，多人用 `/` 分隔；**无回复填 `—`** |
| `when` | string | ✅ | 回复时间。⚠️ **渲染器没有 `when_en`，EN 页直接复用 `when`** → **`when` 本身就要写英文/中性** |
| `raw` | string | ✅ | 对方回复**原文**；无回复填 `—` |
| `sum` | string | ✅ | 中文总结 |
| `se` | string | ✅ | 英文总结 |
| `st` | string | ✅ | 状态：`ok` / `part` / `fwd` / `none` |
| `cf` | object | ○ | 意见不一致标记，见 §7 |

### 关于 `q` 里的 HTML

| 标签 | 作用 | 中文版 | 英文版 |
|------|------|--------|--------|
| `<br>` | 换行。**约定：正文放在 `<br>` 之后**（`short_q()` 依赖这个约定取主句） | 保留 | 保留 |
| `<span class='sub'>…</span>` | 中文附加子句 | 保留 | **含中文的会被剔除**，纯英文的保留 |
| `<span class='warn'>⚠ …</span>` | 警示 | 保留 | 经 `EN_WARN` 映射表换成英文 |
| `<b>` / `<code>` | 强调 | 保留 | 保留 |

### `who` 的渲染拆分

`who` 里**姓名与邮箱用 `<br>` 分隔**（多人用 `/` 分隔），渲染时按 `<br>` 拆两段。
解析实现见 `owner_rules.parse_who()`。

---

## 7. `cf`（意见不一致标记）

**用户明确要求**：当同一问题出现下列任一情况时，必须给该行加 `cf`：

1. **对方不同人对同一问题答复不一致**（A 给结论、B 要求再确认）
2. **对方答复与我方建议/理解相反**
3. **对方内部处理结论自相矛盾**（如已关闭工单却要求本批交付）

**渲染行为**

- HTML：在该行「问题回复总结」前显示红色 `⚠ 意见不一致` 标签 + 说明
- MD：前缀 `⚠ **意见不一致**：`

> **同一问题的冲突双方行都要打 `cf`**（各自标一份，说明文字可相同）。

---

## 8. `todos[]`

```json
"todos": [
  { "mail": "M6", "zh": "向对方索要 XXX 的样例文件", "en": "Ask the client for the XXX sample file" }
]
```

| 字段 | 说明 |
|------|------|
| `mail` | 关联的邮件编号（`M*`） |
| `zh` | 中文文案 |
| `en` | 英文文案 |

> ⚠️ **必须是对象数组**。追加纯字符串会直接崩：
> `TypeError: string indices must be integers, not 'str'`。

> **2026-09-17 晚起 HTML 不再渲染 `todos`**（改为动态未解决清单），数据保留 + MD 版仍渲染。

---

## 9. `held[]`（保留区）

结构与 `mails[]` **完全一致**（`items` 里的字段也一样），可直接复用同一套构造代码。

用途：**非本人发出**的邮件（客户来件、同事代发、内部转发）移入此处保留。

> **不要删掉 `held`，也不要主动把里面的邮件加回 `mails`。**
> 用户原话：「这个清单内拿掉不是我发送的邮件的统计，当我有需要的话我会喊你统计，你再处理」

---

## 10. 完整最小可运行示例

```json
{
  "updated": "2026-10-04",
  "window": "2026-09-01 ~ 2026-10-04",
  "window_en": "2026-09-01 ~ 2026-10-04",
  "scope": {
    "self_addr": "you@yourcompany.com",
    "peer_domains": ["customer.com"],
    "note": "只统计本人发出的邮件"
  },
  "todos": [],
  "held_todos": [],
  "memos": {},
  "memos_v": 0,
  "mails": [
    {
      "id": "M1",
      "sender": "you(你的名字)",
      "sender_en": "you (Your Name)",
      "subject": "Clarification Required: XXX",
      "subject_en": "Clarification Required: XXX",
      "sent": "2026-09-01",
      "sent_en": "2026-09-01",
      "from_addr": "you@yourcompany.com",
      "to": [
        { "n": "Alice Wong", "n_en": "Alice Wong",
          "e": "alice@customer.com", "org": "Customer" }
      ],
      "cc": [],
      "items": [
        {
          "q": "1. 第一条待确认项（@Alice）",
          "qe": "1. First item to confirm (@Alice)",
          "who": "Alice Wong<br>alice@customer.com",
          "when": "2026-09-03 10:22",
          "raw": "Confirmed. We will follow the existing flow.",
          "sum": "已确认，沿用现有流程。",
          "se": "Confirmed. Follow the existing flow.",
          "st": "ok"
        }
      ]
    }
  ],
  "held": []
}
```

---

## 11. 数据层的自检清单

交付前跑一遍（比事后扫 HTML 快得多，也能精确定位是哪个字段）：

| # | 检查 | 方法 |
|---|------|------|
| 1 | `*_en` 字段无中文 | 扫 `subject_en` / `sent_en` / `sender_en` / `to\|cc.n_en` / `qe` / `se` / `when` / `raw` / `cf.en` |
| 2 | 条目键无冲突 | 同一邮件内 `item_key(mid, q)` 不重复 |
| 3 | `held` 编号不撞号 | 两边 id 集合无交集 |
| 4 | `todos` 是对象数组 | 每项含 `mail` / `zh` / `en` |
| 5 | `memos` 的键都能对上条目 | 用 `item_key()` 复算一遍 |
| 6 | 全局计数自洽 | `未解决 = Σ条目 − Σ已标记解决`，不为负 |
| 7 | 每个 `st` 在枚举内 | `{ok, part, fwd, none}` |
| 8 | `to`/`cc` 每项有 `n_en` | 缺了 EN 页会用 `n` |
