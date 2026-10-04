# coremail-sent-feedback-tracker

> 在 Coremail 网页版里，自动追踪「我方发出的邮件」并汇总「对方给出的反馈」。

---

## 这个技能解决什么问题

你发了一封邮件，里面列了 20 条需求 / 待确认项。接下来两周，客户在**邮件正文、彩色表格批注、汇总表、
Google Docs 评论、会议**里零散地回复。到最后：

- 哪几条已经确认了？
- 哪几条客户内部给了**互相矛盾**的答复？
- 哪几条我线下已经解决了，但邮件上看还是「未回复」？
- 我要按邮件分组重跑一遍，怎么保证上周打的标记不丢？

这个技能把上述流程固化成一条可重复执行的流水线，并产出**可直接交付给客户 / 上级的三件套**。

## 核心产出

| 文件 | 说明 |
|------|------|
| `<项目>_CN.html` | 中文版。单页签浏览，顶部下拉切换「我方发出的每一封邮件」；每封内是「问题 → 负责人 → 对方回复原文 → 中文总结」四列表 |
| `<项目>_EN.html` | 全英文版（**零中文残留**，可整封转发给客户） |
| `<项目>.md` | Markdown 总结，含手工待办 + 未解决事项清单 |

HTML 版还带：

- **可手工标记区**：每条总结下方可勾「已解决」+ 写一条「备忘 / 最终结论」，
  存在浏览器本地并**可写回 HTML 文件本身**（换电脑也不丢）
- **未解决清单（Open items）**：动态列出所有未标记解决的条目，点击跳转
- **负责人(Owner) 列**：解析正文里的 `@提及`，逐个标注「已回复 / 未回复」
- **⚠ 意见不一致标记**：对方内部答复冲突时自动打标
- 顶部统计卡片、状态筛选、关键字搜索、邮件切换器 hover 提示

---

## 安装

### 方式一：已经在用 WorkBuddy（推荐）

把本目录整个复制到用户级技能目录：

```bash
# Windows
xcopy /E /I coremail-sent-feedback-tracker "%USERPROFILE%\.workbuddy\skills\coremail-sent-feedback-tracker"

# macOS / Linux
cp -r coremail-sent-feedback-tracker ~/.workbuddy/skills/
```

复制完成后**新开一个会话**，技能即可被自动加载（描述里含触发关键词）。

### 方式二：手动使用脚本

`scripts/` 下的脚本都是独立的，不装技能也能直接跑：

```bash
python scripts/tabbit.py ensure
python scripts/render_tracker.py data.json outdir
```

---

## 前置条件

| 依赖 | 说明 |
|------|------|
| **Tabbit Browser** | 需在本机运行。未运行会报 `BROWSER_RUNTIME_UNAVAILABLE` |
| **浏览器已保存 Coremail 账号密码** | 登录页会自动填充。未保存时请先手动登录一次并勾选「记住密码」 |
| **Python 3.10+** | 推荐用托管版本：`C:/Users/leonerdli/.workbuddy/binaries/python/versions/3.13.12/python.exe` |
| **Node.js**（可选） | 只在校验阶段用（`node --check` 检查产物 JS 语法） |

> 本技能**只读优先**：默认不发送、不删除、不改状态。移动邮件是唯一允许的写操作，且有四道闸
> （目标文件夹黑名单 / 默认 dry-run / 相关性校验 / 单次上限 20 封）。

---

## 快速开始

```bash
# 0) 设定路径
PY="C:/Users/leonerdli/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SK="C:/Users/leonerdli/.workbuddy/skills/coremail-sent-feedback-tracker/scripts"

# 1) 接管 / 自动打开并登录 Coremail
"$PY" "$SK/tabbit.py" ensure
#  → {"mode":"resumed","ok":true,"task":"mail-attach", ...}
#  → 输出的 task 就是后续所有命令要用的 --task

# 2) 搜索（用 2~3 个词的短关键词，Coremail 是模糊/OR 匹配）
"$PY" "$SK/tabbit.py" --task mail-attach search "Clarification Required"

# 3) 写一段 JS 落盘，再 run（注意：run 不接受 `-` 当 stdin）
cat > /tmp/dump.js <<'JS'
const res = await page.evaluate(() => {
  const out = [];
  Array.from(document.querySelectorAll('tr.j-mail')).forEach((n, i) => {
    const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t) return;
    const cells = Array.from(n.querySelectorAll('td'))
      .map(td => (td.innerText||'').replace(/\s+/g,' ').trim()).filter(Boolean);
    out.push({ i, cells: cells.slice(0,6) });
  });
  return { n: out.length, rows: out };
});
return res;
JS
"$PY" "$SK/tabbit.py" --task mail-attach run /tmp/dump.js

# 4) 渲染三件套
"$PY" "$SK/render_tracker.py" data.json ./output

# 5) 交付前校验（退出码 0 才交付）
"$PY" "$SK/verify_render.py" ./output --data data.json

# 6) 收尾（保留标签页）
"$PY" "$SK/tabbit.py" --task mail-attach finish
```

### 想先跑通一遍流程？

技能自带一份最小示例数据，不需要邮箱也能验证渲染链路：

```bash
"$PY" "$SK/render_tracker.py" "$SK/../examples/minimal_data.json" ./demo_out
"$PY" "$SK/verify_render.py" ./demo_out --data "$SK/../examples/minimal_data.json"
# → RESULT: 15 PASS / 0 FAIL
```

---

## 首次使用要改什么

这个技能从「HP 项目客户需求澄清追踪」抽象而来，**开箱即用但需要按你的项目改三处配置**：

### 1. `scripts/owner_rules.py` 的 `MENTIONS` 字典

把示例里的 `@昵称 → 人员/邮箱` 换成你项目里的对应关系。

```python
MENTIONS = {
    "alice": dict(n="Alice Wong", n_en="Alice Wong",
                  e="alice@customer.com", org="Customer"),
    "ced":   dict(n="CED（团队）", n_en="CED (team)", e="", org="Customer"),
    ...
}
```

**怎么考证昵称对应的邮箱**：昵称在邮件正文里是**纯文本**，没有 href / title。
方法是让**正文称呼（greeting）与收件人列表一一对应**，再用邮件抬头佐证。
（`references/02-feedback-extraction.md` 里有两个完整考证案例。）

### 2. 数据文件的 `scope` 字段

```json
"scope": {
  "self_addr":   "you@yourcompany.com",     // 「我方发出」的判据
  "peer_domains": ["customer.com"],          // 「对方」的域名
  "note": "只统计本人发出的邮件"
}
```

### 3. `scripts/render_tracker.py` 的输出文件名与界面文案

- `I18N` 字典：`title` / `sub` 等界面文案
- `main()`：三个输出文件名（默认是 `HP客户问题回复汇总_CN.html` 等）
- `STORE` 里的 localStorage key 前缀（默认 `hp_memo_v2`）——
  **换了项目就换 key**，否则不同项目的标记会串

---

## 数据文件最小示例

```json
{
  "updated": "2026-10-04",
  "window": "2026-09-01 ~ 2026-10-04",
  "scope": {"self_addr": "you@yourcompany.com", "peer_domains": ["customer.com"]},
  "memos": {}, "memos_v": 0,
  "mails": [{
    "id": "M1",
    "sender": "you(你的名字)", "sender_en": "you (Your Name)",
    "subject": "Clarification Required: XXX", "subject_en": "Clarification Required: XXX",
    "sent": "2026-09-01", "sent_en": "2026-09-01",
    "from_addr": "you@yourcompany.com",
    "to": [{"n": "Alice Wong", "n_en": "Alice Wong", "e": "alice@customer.com", "org": "Customer"}],
    "cc": [],
    "items": [{
      "q":  "1. 第一条待确认项（@Alice）",
      "qe": "1. First item to confirm (@Alice)",
      "who": "Alice Wong<br>alice@customer.com",
      "when": "2026-09-03 10:22",
      "raw": "Confirmed. We will follow existing HP flow.",
      "sum": "已确认，沿用现有流程。",
      "se":  "Confirmed. Follow the existing flow.",
      "st":  "ok"
    }]
  }],
  "held": []
}
```

完整字段说明见 `references/03-data-schema.md`。

---

## 目录结构

```
coremail-sent-feedback-tracker/
├── SKILL.md                      # ★ 主入口：完整工作流 + 口径 + 踩坑
├── README.md                     # 本文件
├── CHANGELOG.md                  # 版本变更记录
├── references/
│   ├── 01-coremail-web-dom.md    # Coremail XT5 DOM 速查 / 会话遍历 / 回复全部清单
│   ├── 02-feedback-extraction.md # 五类反馈载体提取细则
│   ├── 03-data-schema.md         # 数据文件完整 schema
│   ├── 04-render-spec.md         # 三件套渲染规范
│   └── 05-pitfalls.md            # 踩坑与修复全表
└── scripts/
    ├── tabbit.py                 # ★ 浏览器封装（ensure / 搜索 / 读取 / 移动 / 分页）
    ├── guards.py                 # ★ 安全边界（JS 执行前静态扫描）
    ├── mail_*.js                 # 邮件操作模板
    ├── strip_quote.py            # 剥离引用历史
    ├── owner_rules.py            # ★ @提及 → 负责人映射
    ├── render_tracker.py         # ★ 渲染器（→ CN/EN HTML + MD）
    ├── verify_render.py          # ★ 交付前静态校验
    ├── render_report.py          # 轻量报告渲染器
    └── report_template.html      # 单文件报告骨架
examples/
└── minimal_data.json             # 最小可运行示例数据
```

---

## 安全边界（简版）

所有交给浏览器执行的 JS 在运行前都会过 `guards.py` 静态扫描，命中即拒绝执行。

- **永不放行**：删除邮件、清 Cookie/localStorage、改账号配置、读密码框、
  网络外发（`fetch`/`XHR`）、动态求值（`eval`/`new Function`）
- **需显式放行**（环境变量，仅单条命令生效）：发送邮件、下载附件、关闭标签、标记已读、点击正文链接

自己写了一段 JS 但不确定是否越界，可以先只做静态扫描、不连浏览器：

```bash
python scripts/tabbit.py guard your_script.js     # 输出 SAFE / DENY / NEED
```

---

## 常见问题

**Q：运行时提示 `Unknown task name`？**
A：任务 `finish` 之后再用同名任务就会这样。邮箱任务名**每轮换新**（如 `mail-1004`），
或重新跑 `ensure` 接管。

**Q：`ensure` 返回 `ok:false`？**
A：先看 `mode`。`login-failed` 多半是二次验证/验证码，请手动登录一次；
`not-on-site` 加 `--new` 重开；`BROWSER_RUNTIME_UNAVAILABLE` 说明 Tabbit 浏览器没运行。

**Q：搜索搜不到我要的邮件？**
A：Coremail 全文搜索是**模糊/OR 匹配**，关键词越长结果越发散。用 2~3 个词的短关键词。
另外**连续查不同关键词可能不生效**（第二次起返回同一批列表）——
要列「最近邮件」就直接读列表，不要靠搜索。

**Q：我在 HTML 里打的标记，重跑后没了？**
A：标记的键是 `邮件号 + md5(问题文本)`。**只要不修改被标记条目的 `q` / `qe` 字段，标记就不会丢。**
如果没丢但没显示，检查数据文件的 `memos_v` 是否 > 浏览器里的版本号。
详见 `SKILL.md` 的 §6.4。

**Q：英文版里出现了中文？**
A：跑一次数据层字段扫描（`SKILL.md` §6.6），比事后扫 HTML 快得多，也能精确定位是哪个字段。
最常见的三个位置：`to/cc` 的 `n_en`（直接复制了中文名）、`items[].when`（渲染器没有 `when_en`）、
新增条目 `qe` 里拼接了中文来源标注。

---

## 版本

当前 **v1.0.0**。变更记录见 [CHANGELOG.md](CHANGELOG.md)。
