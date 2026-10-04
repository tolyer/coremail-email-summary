# 05 · 踩坑与修复全表

按**层面**分类，附**实测时间**。开工前扫一眼能省掉大量排查时间。

---

## A. Tabbit / 浏览器层

### A1. `tabbit.py run` 不接受 `-` 当 stdin ⭐ 高频

**实现**：`run_node()` 的判断是 `code_or_path.endswith('.js') and os.path.exists(code_or_path)`。

**症状**：传 `-` 既不满足 `.js` 后缀也不满足 `exists`，
于是**整串 `-` 被当成 JS 代码直接执行**，返回空结果
（表现为 1~2 秒就「成功」返回，但没有任何数据）。

**解法**：**一律先把 JS 落盘成 `.js` 文件再传路径。**

---

### A2. Git Bash 短路径解析失败

**症状**：报 `Invalid regular expression flags` —— 路径字符串被当成 JS 代码执行了。

**原因**：`tabbit.py run` 传 `.js` 路径时，路径必须能被 Python `os.path.exists` 解析；
Git Bash 的 `$TEMP` 短路径（`C:\Users\LEONER~1\...`）会解析失败。

**解法**：用工作区下的常规绝对路径。

---

### A3. `page.evaluate` 只接受一个参数

**症状**：`Too many arguments. If you need to pass more than 1 argument to the function wrap them in an object.`

**解法**：把多个参数包成一个对象传。

```js
await page.evaluate((t) => { … }, { frm: 'A', time: 'B', subj: 'C' });
```

---

### A4. 裸 `document` 在 `tabbit.py run` 里不可用

**症状**：`document is not defined`。

**解法**：所有 DOM 访问必须包在 `await page.evaluate(...)` 里。

---

### A5. `--task` 是全局选项，必须写在子命令前

| ✅ 正确 | ❌ 错误 |
|---|---|
| `tabbit.py --task X ensure` | `tabbit.py ensure --task X` |

---

### A6. `finish` 后再用同名 task 报 `Unknown task name`

**解法**：要么换新任务名（**邮箱任务名每轮换新**，如 `mail-0925`），
要么 `ensure` 重新接管。

**补充**：`ensure` 走 `bootstrapped` 分支时（旧标签已 `finish`）
会**自动新开干净标签并刷新列表**，可放心用。

---

### A7. `claim --tab` 在标签属于旧会话时必失败

**症状**：`TAB_OWNERSHIP_CONFLICT`。

**解法**：用 `resume --group`（`ensure` 已自动处理）。

---

### A8. tabbit-cli 升级后 `nodejs` 强制要求 `--request-id`

**症状**：`{"code":"REQUEST_FAILED","message":"nodejs requires --request-id"}`，
`ensure` 表现为 `bootstrap-failed` / `ok:false`。

**解法**：`tabbit.py` 的 `run_node()` 已自动生成 `req-<uuid12>`；
**直接调用 CLI 时**要自己补，结果可用
`tabbit-cli receipt --task X --request-id <id> --wait-ms 15000` 取回。

---

### A9. Bash 工具里 coreutils 缺失

**症状**：跑 `ls` / `head` / `find` / `file` 报 `ls: command not found`，
同时 shim 脚本报 `dirname: command not found` / `cd: null directory`。

**注意**：**不是命令写错**，是 PATH 没带上 Git 的 usr/bin。

**解法**：每条 Bash 命令开头加
`export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"`，或改用 PowerShell 工具。

---

### A10. 多个 Coremail 标签

`ensure` 只接管**第一个**匹配 host 的标签。需要干净会话就用 `--new`。

---

## B. Coremail 页面层

### B1. 「会话已过期」弹层让所有点击超时 ⭐ 高频

**症状**：弹出「会话已过期, 请重新登录」弹层（带 `.u-mask` 遮罩），
拦截一切点击，但页面 DOM 仍是邮箱 —— **`#lyfullsearch` 判断会误报已登录**。

**解法**：**直接再跑一次 `ensure`**。它会：

1. 点弹层「重新登录」按钮
   （用 `.u-dialog button:has-text("重新登录")`；**别用** `text=重新登录`，可能命中非按钮文本）
2. 点登录按钮（密码由浏览器自动填充）
3. 等 `#lyfullsearch` 出现且**无可见 `.u-dialog`**
4. **再点一次列表「刷新」** —— 重新登录后列表是旧 DOM 快照，
   不刷新的话读到的可能是几天前的邮件列表

**探测方法**（长时间操作后先跑）：

```js
const st = await page.evaluate(() => ({
  dialogs: Array.from(document.querySelectorAll('.u-dialog'))
             .filter(e => e.offsetParent !== null).map(d => d.innerText.slice(0, 80)),
  masks: document.querySelectorAll('.u-mask').length
}));
```

---

### B2. 不要用 `page.goto()` 切文件夹 ⭐

**症状**：页面变**白页**，`#lyfullsearch` 消失、`title` 为空，
之后所有 `read-idx` / `search` 全部超时。

**原因**：Coremail 文件夹是 `#mail.list|{"fid":N}` 这样的 **hash 路由**，
直接 goto 一个拼出来的 URL（不带 sid / 参数不全）会破页面。

**解法**：**一律点击侧栏元素**。恢复办法：`finish` 之后 `ensure --new` 重开干净标签。

---

### B3. `search` 连续查不同关键词可能不生效

**症状**：第二次起 `search "任意词"` 返回的仍是同一批列表，
用无意义串（如 `ZZZQQQXX`）验证也返回同样结果 —— 说明**搜索没重触发**。

**解法**：**不要据此判断"没有新邮件"**。要列「最近邮件」时，
直接读收件箱列表最可靠，再按发件人/日期筛。

---

### B4. 列表是旧快照

标签页长时间未刷新时，DOM 邮件列表停在最后一次加载时刻，
今天/昨天分组不再更新，**新邮件会插进旧分组里造成时间乱序**。

**解法**：读取列表前先确认刷新过（点 `span[data-btn="refresh"]` 或重跑 `ensure`）。

---

### B5. 列表行索引会随新邮件到达整体位移 ⭐

**实测（2026-09-25）**：同一封邮件上午在 idx 4，下午复跑落到 idx 5。
按 idx 点开前**必须先重新 dump 确认**，且点击脚本要**回传该行文本**跟期望发件人比对，
不匹配就报 `EXPECT MISMATCH` —— 否则会默默读到无关邮件
（本轮就误点到了 `webanktu` 工会邮件）。

**解法**：放弃 idx 定位，改用「按行文本实时匹配」（见 `01-coremail-web-dom.md` §3.1）。

---

### B6. 打开邮件后列表全部隐藏

**症状**：打开一封邮件后切到 `#mail.read|{...}` 视图，
左侧 `tr.j-mail` 全部 `offsetParent === null`（实测 `visRows = 0`），
**第二次 `page.$$('tr.j-mail')[i].click()` 必然 30s 超时**。

**解法**：不要「打开 → 返回列表 → 再打开」，
改用 read 视图里的 `a.u-page-prev` 一路往回走，一次 `run` 能连读十来封
（每步留 4600ms + 展开 900ms）。

---

### B7. 搜索结果里可见行 ≠ NodeList 索引

**症状**：搜索视图下 `document.querySelectorAll('tr.j-mail')`
会把隐藏的日期分组容器里的行一起算进来（实测 **114 个节点里只有 14 个可见**）。
按 `$$()` 的下标去点会点到隐藏行。

**解法**：**先按 `offsetParent !== null` 过滤出可见行，再用它的下标去点。**

---

### B8. 切过文件夹后索引对不上

`goto_sent.js` 之后再用 `read-idx` 读的是**已发送列表**，索引与收件箱完全对不上。

**解法**：**先切回收件箱再按 idx 读。**

---

### B9. 折叠联系人不展开就只有半截

收件人/抄送超过 5 个会被 `a.u-hide-info` 折叠
（文本 `.. [↓还有N个联系人]`），`innerText` 只给到折叠提示。

**实测**：原件收件人 12 人 + 抄送 25 人，**不点开只能拿到 5 + 5**。

**解法**：先点掉所有可见的 `a.u-hide-info`（可点多次），
再按 `span.u-email[addr][data-true-name]` 取结构化数据。

---

### B10. 邮件头 `tr` 匹配返回空

**实测（2026-09-17）**：`tr` 匹配在**收件箱与已发送视图都返回空**。

**解法**：改用「遍历 `div,td,span,table`，取 `innerText` 以 `发件人\s*:` 开头且长度 < 700 的元素」
的兜底写法，或直接取 `div.full-info.j-full-info`。

---

### B11. 裸地址连写成一行

**症状**：`shenazhang@webank.comluk.teckeng@hlbb...` —— 两个邮箱粘在一起。

**解法**：正则**必须限定 TLD**：

```python
r"[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9\-]+\.)+(?:com\.my|edu\.my|gov\.my|com|net|org|my|cn)"
```

贪婪回溯会自动停在 `.com` / `.com.my` 上。**只用 `[@\w.]+` 会粘地址。**

---

### B12. 名字去重选到邮箱形态

同一邮箱在不同邮件里 `data-true-name` 可能一个是 `carlwang(王胜军)`、
另一个直接是 `carlwang@webank.com`。

**错误做法**：取最长的 → 会把邮箱形态选出来。

**正确做法**：先剔除「等于邮箱 / 等于邮箱前缀」的候选再比长度。

---

## C. 数据层

### C1. 改 `q` 会让用户所有标记失联 ⭐ 红线

**原因**：备注键 = `mid + md5(去标签后的 q)[:10]`。改一个字哈希就变。

| 可改 | 不可改 |
|------|--------|
| 剔邮件、改状态、改总结、改 Owner、改 `when`、更新 `raw` | **`q`**、**`qe`** |

---

### C2. 备注键哈希口径不一致导致误判 ⭐ 隐蔽

**实测**：本机用 `re.sub(r"<[^>]+>", "", q)`（直接把标签删掉）去核对，
**54 条标记只对上 6 条**，其余 48 条全被判成「对不上」，差点当成版本错位去排查。

**原因**：渲染器 `item_key()` 用的是**替换成空格** `" "`。差这一个字符哈希就完全不同。

**解法**：核对前先把 `item_key()` 原文抄过来。

---

### C3. `held` 编号与主清单撞号

**实测（2026-09-27）**：新加 held 条目时若只对 `held` 取 max，
会生成 `M21` 与主清单的 **M21 撞号**。

**解法**：`max(所有 mails.id + held.id)` 再 +1。

---

### C4. `memos_v` 不够大 → 烘焙值被盖掉

**原因**：加载时 `BAKED.v > LS.v` 才以数据文件为准。
若 `memos_v` 没比浏览器里的 `v` 大，烘焙好的标记会被空的 localStorage 盖掉。

**解法**：**每次固化标记都把 `memos_v` +1**，
并用空 localStorage 跑烟测断言 `Object.keys(STORE).length === 标记条数`。

---

### C5. 写回时 `LS.v` 不自增 → 「保存成功」是假的 ⭐ 最容易骗过测试

**症状**：看着存好了，**新浏览器打开就没了**（烘焙位里是旧值被空 localStorage 覆盖）。

**原因**：写回前没 `LS.v = (LS.v || 0) + 1`。

**解法**：写回时必须自增再 `persist()`。
**且必须跑「写回 → 当新页面重新载入」的往返测试** —— 只测 `bakeHTML()` 会漏掉版本号自增。

---

### C6. `todos` 追加纯字符串导致崩溃

**症状**：`TypeError: string indices must be integers, not 'str'`。

**原因**：`todos` 必须是对象数组 `{"mail": "M15", "zh": "…", "en": "…"}`，
渲染脚本按 key 取值。

**解法**：追加前先确认类型一致。

---

### C7. 旧版本文件混用

旧格式（按问题组编号 ①~⑪）与新格式（`M1~M16` 归集）**不要混用**。
`_preview/` 下是版式确认用的样例，正式交付只看根目录三件套。

---

## D. 渲染 / 脚本层

### D1. Python 三引号里的 JS 转义层数 ⭐ 会导致整页白屏

`JS = """…"""` 是**非 raw** 字符串，Python 先吃掉一层反斜杠。

| 要在产物 JS 里得到 | 源码必须写 |
|---|---|
| `\'` | `\\'` |
| `\s`（正则） | `\\s` |

**症状链**：源码写 `setS(\'MEMO\')` → 产物 `setS('MEMO')` → JS 语法错误
`Unexpected identifier 'MEMO'` → 浏览器里**整页白屏无 JS**。

**解法**：**改完必须抽 `<script>` 跑 `node --check`。**

---

### D2. 同文件多编辑并行发送会静默丢改动

**实测（2026-09-24）**：同一文件的多个 `Edit` 调用放在同一条消息里并行发，
后写覆盖先写，工具仍返回 success 但改动丢失，
直到运行时 `NameError` 才暴露。

**解法**：**必须串行发送**，改完 `grep` 复核一遍再跑。

---

### D3. CRLF 行尾让断言失败

**实测（2026-09-17）**：烟测脚本是 CRLF 行尾，
Python 里对它做**多行** `str.replace` 前若不归一，
`assert count == 1` 直接失败（单行 pattern 不受影响，很难第一时间想到）。

**解法**：先 `s = s.replace('\r\n', '\n')`。

---

### D4. `_tools/*.py` 被 Read/Edit 判定为二进制

**症状**：Read 工具报 `Cannot display content of binary file`，Edit 随之报「请先 Read 最新内容」。

**原因**：历史脚本是 **UTF-8 + CRLF**，Read 工具误判。

**解法**：

- 查看：用 `python -c "import io;print(io.open('x.py',encoding='utf-8').read())"`
- 改写：写一个一次性补丁脚本（`_tools/_patch_*.py`），
  用 `str.replace()` 做定点替换 + `assert count==1` 防误伤，
  再 `io.open(p,'w',encoding='utf-8',newline='\n')` 落盘（顺便把 CRLF 归一为 LF）
- 改完立刻 `ast.parse()` 校验语法，再跑真实渲染并 diff 关键计数

---

### D5. 含中文的 Python 脚本编码问题

**症状**：`SyntaxError: (unicode error) 'utf-8' codec can't decode byte 0xbf`。

**注意**：`GBK` 装不下 `⚠`（U+26A0）等字符，会被替换成 `?`，转换后必须检查并回补。

**解法**：用 Write 工具落盘后**先探测编码再归一**，再 `ast.parse()` 校验：

```python
b = open(p, 'rb').read()
try:
    s = b.decode('utf-8'); enc = 'utf-8'
except UnicodeDecodeError:
    s = b.decode('gbk'); enc = 'gbk'
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
```

**更稳的做法**：源码里 `⚠`/`✅`/`—`/`·` 一律写 `\u26a0` / `\u2705` / `\u2014` / `\u00b7` 转义。

> 注：早期记录说「Write 工具落盘用 GBK」，但 **2026-09-24 起实测 Write 落盘就是 UTF-8**。
> 探测式写法两种都能兜住。

---

### D6. Bash heredoc 写含中文的 Python 脚本会解析失败

**实测（2026-09-17 晚）**：`cat > x.py <<'PY' … PY` 报
`unexpected EOF while looking for matching '`
（脚本里混排撇号 `don\'t` / `can't` 与中文时触发）。

**解法**：用 Write 工具落盘（见 D5）。

---

### D7. `render_single_mail.py`（单封英文版）没有备注区

它是拿去转发的干净只读副本。**交互式备注只做在汇总页（CN / EN）里，两页共用一份备注。**

---

## E. 英文版「零中文」相关

### E1. 只扫 `[\u4e00-\u9fff]` 会漏全角标点 ⭐

**实测**：负责人列的连接符写成全角 `；` `：` 让 EN 页残留中文标点，
但汉字正则返回 0。

**解法**：扫描必须用广义 CJK：

```python
r'[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]'
```

---

### E2. 中文写在 CSS / JS 注释里也会被命中

**实测**：`/* ---------- 页签 ---------- */` 这类注释让 EN 页残留 3 处 CJK；
内嵌 JS 里的中文注释同样算（加「旧数据兼容」注释时又踩了一次 31 处）。

**解法**：**`JS` / `CSS` 字符串里的所有注释一律写英文。**
扫描要对**整个文件**做，不能只扫页面正文。

---

### E3. `en_clean()` 误删英文 sub 子句

部分条目的 `qe` 里 sub 子句本身就是**英文**，那是有效信息。

**解法**：对 sub 内容做 `[\u4e00-\u9fff]` 判定，**命中才删**。

---

### E4. 中英文 `en_clean` 串了 → 中文版问题子句被静默剥掉 ⭐

**实测**：曾写成 `q = en_clean(it["q"]) if lang == "zh" else it["q"]`，
导致**中文版的问题子句被静默剥掉**（CN 页面肉眼看不出来，
但 `class='sub'` 计数从 **156 掉到 2**）。

**解法**：**中文版的 `q` 必须原样输出**，只有英文版才过 `en_clean`。
改完务必核对：**CN 页 `sub` 计数应有上百个，EN 页 CJK 应为 0**。

---

### E5. 新增分组时 EN 页 CJK 残留的三个高发点

**实测（2026-09-24，一次残留 41 处）**

| # | 位置 | 说明 |
|---|------|------|
| 1 | `to` / `cc` 的 **`n_en`** | 若直接从 `n` 复制（如 `ivanzhong(钟燕清)`），EN 页就出中文 |
| 2 | `items[].when` | **渲染脚本没有 `when_en`，EN 页直接复用 `when`** |
| 3 | 新增条目 `qe` 里拼接了中文来源标注常量 | 检查生成 `qe` 的代码 |

修法：给每个中文列配 `*_EN` 字典，`qe` 走英文版。
**交付前先跑数据层字段扫描，比事后扫 HTML 快得多。**

---

## F. 校验 / 测试层

### F1. 烟测断言写死语言

`h15.indexOf('cf-badge')`、`/one-hour meeting/i` 这类断言在 CN 页必然 FAIL ——
**是断言选错了 token，不是页面 bug**。

**解法**：断言要么查数据层，要么用
`String.fromCharCode(24847,35265,19981,19968,33268)` 这种方式兼容中英，
**避免把中文写进 JS 文件**。

---

### F2. 回归脚本期望值硬编码会随数据增长失效

**实测（2026-09-24）**：`ck('取消标记后 M1 mopen', …, 1)` 硬编码了旧的 M1 未解决数，
条目从 21 涨到 23 后就 FAIL。

**解法**：改动态写法 —— **取消前先读取当前值再断言 `+1`**。

---

### F3. 烟测桩缺 `focus()` 会误报

`ddToggle` 会 focus 筛选框；桩元素缺 `focus(){}` 会报
`f.focus is not a function` —— **是桩的问题**，不是页面的。

---

### F4. 只跑部分校验会漏掉逻辑洞

**改了备注 / 写回逻辑，必须同时跑三样**：

1. `node --check`（语法）
2. 备注烟测（默认收起 + 烘焙位 + EN 零中文）
3. **写回往返**（写回后重开能恢复）

只跑前两样会漏掉「**版本号不自增 = 白存**」这类逻辑洞。

---

### F5. 预览面板与 `file://` 不同源

内置预览面板（`127.0.0.1`）与 `file://` 不同源，localStorage 隔离 ——
**在预览面板里打的标记读不回本地文件**。

**解法**：**必须双击本地文件打开 + 点「保存到本页文件」**。

---

## G. 交付 / 发信层

### G1. 走 Coremail 发信的两个问题

1. Coremail 发信要 `TABBIT_ALLOW_SEND=1`，与「**AI 只出草稿、用户自己点发送**」的既有约定冲突
2. 公司邮箱外发受合规约束

**解法**：用 **Agent Mail** 通道。

---

### G2. 附件中文名在外部邮箱易乱码

**解法**：**先把文件复制成 ASCII 名再上传**：

```bash
cp "客户反馈汇总_EN.html" "Feedback_Summary_EN_20260927.html"
```

---

### G3. `ListMessages` 的 folder 参数名是 `dir`

传 `folder` 会参数校验失败。

---

### G4. `skip_confirmation` 的使用边界

**仅在用户明确点名收件人与发什么时才用** `skip_confirmation=true`；
若用户只是「要不要发一下」这类模糊表述，**先要一次确认**。

---

## H. 流程 / 协作层

### H1. 漏邮件的最常见原因不是抓取失败 ⭐

**而是数据窗口没跟上** —— 上一轮窗口截止到哪天，之后发出的邮件自然不在数据里。

**实测（2026-09-17）**：某封邮件 09-16 14:38 才发出，上轮窗口止于 09-15，
于是被当成「漏抓」排查了半天。

**解法**：回答用户「××那封为什么没有」前，**先看数据文件的 `window` 字段**再下结论。

---

### H2. 重跑前的两件事，顺序错了会白跑一轮

1. **取回用户在浏览器里的最新手工标记**
2. **确认清单范围**（默认只留本人发出的邮件，其余在 `held`）

---

### H3. 用户点名「不统计」的条目

用户可能指定某些条目**不计入统计**。

**处理方式**：**直接从 `items` 里删除**，同步修正引用到这些条目的 `todos` 文案与计数。

---

### H4. `held` 是保留区不是删除区

用户原话：「**这个清单内拿掉不是我发送的邮件的统计，当我有需要的话我会喊你统计，你再处理**」

**解法**：**不要主动把非本人邮件加回**，也**不要删掉 `held`**。

---

## 附 · 快速排查决策树

```
页面操作全部超时？
  └→ 先 probe 有没有 .u-dialog / .u-mask  → 有就重跑 ensure〔B1〕

读到的邮件不是想要的？
  └→ 行索引位移了 → 重 dump + 按行文本匹配 + 比对 row 文本〔B5〕
     └→ 是不是切过文件夹没切回来？〔B8〕

打开第二封就超时？
  └→ 列表已隐藏 → 改用 a.u-page-prev〔B6〕

某个联系人/邮箱没抓到？
  └→ 折叠没展开〔B9〕/ 邮箱正则没限定 TLD〔B11〕/ 名字取了邮箱形态〔B12〕

EN 页有中文？
  └→ 先扫广义 CJK 确认位置〔E1〕
     └→ 扫数据层字段找源头〔E5〕
        └→ 是 CSS/JS 注释吗〔E2〕

CN 页问题子句少了？
  └→ en_clean 串了语言〔E4〕—— 数 class='sub'

我的标记没了？
  └→ 是不是改了 q〔C1〕
     └→ 是不是 memos_v 没 +1〔C4〕
        └→ 是不是点了「保存到本页文件」却没自增 LS.v〔C5〕
           └→ 是不是在预览面板里打的（不同源）〔F5〕

页面白屏没 JS？
  └→ 抽 <script> 跑 node --check〔D1〕

容器里 ls 报 command not found？
  └→ export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"〔A9〕
```
