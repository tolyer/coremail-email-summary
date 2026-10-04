# -*- coding: utf-8 -*-
"""
HP 客户问题回复汇总 —— 固定输出格式渲染器（布局 v2 · 单页签）

输入：clarification_data.json（与本脚本同级目录的上一级）
输出（固定三件套）：
  1. HP客户问题回复汇总_CN.html   中文版 HTML
  2. HP客户问题回复汇总_EN.html   全英文版 HTML
  3. HP客户问题回复汇总.md        Markdown 总结

版式（2026-09-17 起固定）：
  - 顶部「邮件切换器」= 单行下拉列表（◀ ▶ 翻页 + 可筛选下拉）；hover 显示 完整标题 / 发件人 / 发送时间
  - 邮件级信息（发件人 / 收件人 / 抄送 / 发送时间 / 完整标题）从表格列中取出，
    上移为该组独立的「邮件头卡片」
  - 明细表固定 4 列：问题 | 负责人(Owner) | 问题回复内容 | 问题回复总结
    列宽：问题 20% / 负责人 200px / 问题回复内容 26% / 问题回复总结（自适应，最宽）
  - 回复内容不做内滚动，全文展开
  - 「负责人」列由问题里的 @提及 解析（见 owner_rules.py）：列出应回复方并逐个标注是否已回复；
    实际回复人若不在 @提及名单里，另起一行标「实际回复」
  - 「问题回复总结」列下方可手工加注：备忘 / ☑已解决 / 最终结论；
    存浏览器 localStorage，键 = 邮件号 + 问题文本哈希（中英文页共用同一份备注）
    可用「导出 / 导入备注」备份；导出的 JSON 贴回 clarification_data.json 的 "memos" 字段即可固化

用法：
  python render_clarification.py [data_json_path] [out_dir]
"""
import json, io, os, re, sys, html, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from owner_rules import owners_with_status  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(HERE), "clarification_data.json")
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(HERE)

ST_LABEL = {
    "ok":   ("已确认", "Confirmed"),
    "part": ("部分回复", "Partial"),
    "fwd":  ("转交他人", "Forwarded"),
    "none": ("未回复", "No reply"),
}
ST_ORDER = ["ok", "part", "fwd", "none"]

I18N = {
    "zh": dict(
        lang="zh", title="HP 客户问题回复汇总",
        sub="单页签浏览：顶部页签选择我方发出的邮件，页签内为该邮件的问题与 HLBB 客户回复",
        updated="更新时间", window="统计窗口",
        c_mail="我方发出邮件", c_item="问题条目", c_ok="已确认", c_part="部分回复",
        c_fwd="转交他人", c_none="未回复", c_reply="客户回复",
        th1="问题", th2="负责人", th3="问题回复内容", th4="问题回复总结",
        todo="未解决事项",
        todo_none="没有未解决条目 —— 全部已标记解决",
        search="在当前邮件内搜索问题 / 回复人 / 内容关键字…", all="全部",
        pick_ph="筛选邮件：编号 / 标题 / 发件人 / 日期…",
        prev="上一封", next="下一封", dd_empty="无匹配邮件",
        m_from="发件人", m_to="收件人", m_cc="抄送", m_sent="发送时间", m_items="条目",
        m_prog="进展备注",
        st_leg="状态 已确认/部分/转交/未回复",
        sent="发出", items="条目",
        hint="回复内容为客户端英文原文，全文展开；总结为我方解读。鼠标悬停顶部页签可查看该邮件的发件人与发送时间。",
        empty="本封邮件下无匹配结果", cnt="条",
        ago="等", ppl="人",
        ow_na="未指定负责人", ow_yes="已回复", ow_no="未回复",
        ow_act="实际回复", ow_team="团队",
        c_sol="已解决", c_open="未标记 / 未解决", c_memo="已加备注",
        m_add="＋ 备忘 / 结论", m_edit="编辑备注", m_none="未加备注",
        m_sol="标记为已解决", m_solved="已解决",
        m_note="备忘 / 最终结论", m_note_ph="随手记：例 已电话确认，客户口头接受；最终口径 允许手工录入…",
        m_chip="已解决/有备注", m_chip_open="未解决",
        m_open="未解决",
        open_tip="只看本封邮件内未标记为已解决的条目（数字为本封未解决数）",
        exp_open="导出 / 导入备注", exp_ti="手工备注数据（JSON）",
        exp_tip="备注存在本机浏览器里。重装浏览器、换电脑或重跑文件后若丢失，把这段 JSON 贴回下面点导入即可恢复；也可以直接发我，固化进数据文件。",
        exp_cp="复制", exp_dl="下载文件", exp_imp="导入这段 JSON", exp_clr="清空全部备注",
        exp_close="关闭", m_copied="已复制", m_imported="已导入并刷新", m_clred="已清空",
        m_bad="JSON 格式不对，导入已中止", m_dlfail="浏览器拦截了下载，请改用复制",
         m_file="保存到本页文件", m_file_ok="已写回本页文件",
         m_file_no="未连接本页文件，标记仍自动存在浏览器里",
         m_file_bad="页面标记位缺失，无法写回，请重新生成页面",
         m_file_dl="当前浏览器不支持直接写入，已下载更新后的副本，请用它替换原文件",
         m_file_on="已连接本页文件 · 改动自动写回", m_file_off="未连接文件（仅存本机浏览器）",
        memo_hint="每条总结下方可加备忘 / 标记已解决 / 录最终结论：改动自动存在本机浏览器；点「保存到本页文件」可把标记直接写回这个 HTML（之后改动会自动同步），也可「导出 / 导入备注」备份。",
    ),
    "en": dict(
        lang="en", title="HP Client Clarification Tracker",
        sub="Tabbed view: pick one of our outgoing emails on top; each tab shows that email's questions and the HLBB client replies",
        updated="Updated", window="Window",
        c_mail="Outgoing emails", c_item="Question items", c_ok="Confirmed", c_part="Partial",
        c_fwd="Forwarded", c_none="No reply", c_reply="Client replies",
        th1="Question", th2="Owner", th3="Reply content (verbatim)", th4="Reply summary",
        todo="Open items",
        todo_none="No open items - every row is marked resolved",
        search="Search within this email (question / responder / content)…", all="All",
        pick_ph="Filter emails: ID / subject / sender / date…",
        prev="Previous email", next="Next email", dd_empty="No matching email",
        m_from="From", m_to="To", m_cc="Cc", m_sent="Sent", m_items="items",
        m_prog="Progress",
        st_leg="Status ok/part/fwd/none",
        sent="Sent", items="items",
        hint="Reply content is the client's original English text, shown in full; summary is our interpretation. Hover a tab to see the sender and send time of that email.",
        empty="No matching rows in this email", cnt="items",
        ago="+", ppl=" more",
        ow_na="owner not specified", ow_yes="Replied", ow_no="No reply",
        ow_act="Actual reply", ow_team="team",
        c_sol="Resolved", c_open="Unmarked / unresolved", c_memo="With notes",
        m_add="+ Note / conclusion", m_edit="Edit note", m_none="no note yet",
        m_sol="Mark resolved", m_solved="Resolved",
        m_note="Note / final conclusion", m_note_ph="e.g. confirmed by phone, client agreed; agreed position: allow manual entry...",
        m_chip="Resolved / noted", m_chip_open="Unresolved",
        m_open="Unresolved",
        open_tip="Show only rows in this email that are not marked resolved (count = this email)",
        exp_open="Export / import notes", exp_ti="Manual notes (JSON)",
        exp_tip="Notes live in this browser only. If they are lost (browser reset, another PC, regenerated file), paste this JSON back and hit Import. You can also send it to me to bake into the data file.",
        exp_cp="Copy", exp_dl="Download", exp_imp="Import this JSON", exp_clr="Clear all notes",
        exp_close="Close", m_copied="Copied", m_imported="Imported", m_clred="Cleared",
        m_bad="Invalid JSON, import aborted", m_dlfail="Download blocked by the browser, please use Copy",
         m_file="Save to this file", m_file_ok="Saved into this file",
         m_file_no="Not linked to a file; notes are still kept in this browser",
         m_file_bad="Marker missing in this page; cannot write back. Please regenerate the page.",
         m_file_dl="This browser cannot write files directly; an updated copy was downloaded - replace the original with it",
         m_file_on="Linked to this file - changes auto-saved", m_file_off="Not linked to a file (browser storage only)",
        memo_hint="Under each summary you can add a note / mark it resolved / record the final conclusion. Changes are saved in this browser automatically; click Save to this file to write them into this HTML (later changes sync automatically).",
    ),
}

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f6f7f9;color:#1f2329;
  font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1680px;margin:0 auto;padding:24px 22px 70px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:#5c6470;font-size:13px;margin-bottom:14px}

.cards{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.card{background:#fff;border:1px solid #e3e6eb;border-radius:10px;padding:10px 14px;min-width:104px}
.card .n{font-size:20px;font-weight:600;line-height:1.2}
.card .l{font-size:12px;color:#5c6470;margin-top:2px}
.card.ok .n{color:#0f9d58}.card.part .n{color:#b06000}.card.fwd .n{color:#1967d2}.card.none .n{color:#9aa0a6}

.todo{background:#fff8e6;border:1px solid #fce8b2;border-radius:10px;padding:12px 16px 12px 30px;margin-bottom:14px}
.todo .th{font-weight:600;font-size:13px;margin:0 0 4px -14px;color:#8a5a00}
.todo .th .tc{color:#c5221f;font-weight:700}
.todo ol{margin:0;padding-left:16px;max-height:240px;overflow:auto}
.todo li{font-size:13px;margin:3px 0;line-height:1.5;padding:1px 6px;border-radius:5px;cursor:pointer}
.todo li:hover{background:#fff1cc}
.todo li.tnone{color:#9aa0a6;cursor:default;list-style:none;margin-left:-16px}
.todo li.tnone:hover{background:transparent}
.todo b{color:#8a5a00}

/* ---------- mail switcher (compact dropdown) ---------- */
.msel{position:sticky;top:0;z-index:8;background:#f6f7f9;padding:6px 0 8px;
  border-bottom:2px solid #dfe3ea}
.msel .row{display:flex;align-items:center;gap:8px}
.nav{flex:0 0 auto;width:34px;height:34px;border:1px solid #d6dae0;background:#fff;
  border-radius:8px;cursor:pointer;font-size:16px;line-height:1;color:#3c4043;
  font-family:inherit;display:flex;align-items:center;justify-content:center;padding:0}
.nav:hover{border-color:#2f6feb;color:#2f6feb}
.nav:disabled{opacity:.45;cursor:default;border-color:#e0e4ea;color:#9aa0a6}
.dd{position:relative;flex:1;min-width:0}
.ddbtn{width:100%;display:flex;align-items:center;gap:9px;text-align:left;cursor:pointer;
  border:1px solid #d6dae0;background:#fff;border-radius:8px;padding:7px 12px;
  font-family:inherit;font-size:13px;color:#1f2329}
.ddbtn:hover{border-color:#2f6feb}
.dd.on .ddbtn{border-color:#2f6feb;box-shadow:0 0 0 3px #e8f0fe}
.ddbtn .bid{flex:0 0 auto;background:#2f6feb;color:#fff;font-size:11.5px;font-weight:700;
  border-radius:5px;padding:2px 8px}
.ddbtn .bsm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-weight:600}
.ddbtn .bct{flex:0 0 auto;color:#5c6470;font-size:11.5px;white-space:nowrap}
.ddbtn .car{flex:0 0 auto;color:#80868b;font-size:10px}
.ddpanel{display:none;position:absolute;top:calc(100% + 5px);left:0;right:0;z-index:20;
  background:#fff;border:1px solid #d6dae0;border-radius:10px;overflow:hidden;
  box-shadow:0 10px 30px rgba(16,24,40,.16)}
.dd.on .ddpanel{display:block}
.ddf{padding:8px 10px;border-bottom:1px solid #eceff4;background:#fbfcfe}
.ddf input{width:100%;box-sizing:border-box;border:1px solid #d6dae0;border-radius:7px;
  padding:6px 10px;font-size:12.5px;outline:none;font-family:inherit}
.ddf input:focus{border-color:#2f6feb}
.ddlist{max-height:min(62vh,560px);overflow:auto}
.ddo{display:grid;grid-template-columns:38px 1fr;gap:0 9px;padding:9px 12px;
  cursor:pointer;font-size:12.5px;border-bottom:1px solid #f2f4f7}
.ddo:last-child{border-bottom:none}
.ddo:hover{background:#f1f6ff}
.ddo.on{background:#eef4ff}
.ddo .oid{grid-column:1;grid-row:1;font-weight:700;color:#2f6feb;font-size:11.5px;
  line-height:1.55;padding-top:1px}
.ddo .osb{grid-column:2;grid-row:1;color:#1f2329;line-height:1.55;font-weight:600;
  word-break:break-word;overflow-wrap:anywhere}
.ddo.on .osb{font-weight:700}
.ddo2{grid-column:2;grid-row:2;display:flex;flex-wrap:wrap;gap:3px 16px;margin-top:5px;
  font-size:11.5px;color:#5c6470}
.ddo2 .ofr{word-break:break-word;overflow-wrap:anywhere}
.ddo2 .olb{color:#9aa0a6;margin-right:5px}
.ddo2 .ost{font-family:ui-monospace,Menlo,Consolas,monospace;color:#9aa0a6}
.ddo2 .ost b{font-weight:700}
.ddo2 .ost b.n1{color:#0f9d58}
.ddo2 .ost b.n2{color:#b06000}
.ddo2 .ost b.n3{color:#1967d2}
.ddo2 .ost b.n4{color:#9aa0a6}
.ddempty{padding:16px;text-align:center;color:#9aa0a6;font-size:12.5px}

.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0 13px}
.chip{border:1px solid #d6dae0;background:#fff;border-radius:16px;padding:5px 12px;font-size:12px;
  cursor:pointer;color:#3c4043;white-space:nowrap}
.chip:hover{border-color:#2f6feb;color:#2f6feb}
.chip.on{background:#2f6feb;border-color:#2f6feb;color:#fff}
input.search{flex:1;min-width:240px;border:1px solid #d6dae0;border-radius:8px;padding:7px 12px;
  font-size:13px;outline:none}
input.search:focus{border-color:#2f6feb}

/* ---------- mail header card ---------- */
.mailcard{background:#fff;border:1px solid #dfe3ea;border-radius:0 12px 12px 12px;overflow:hidden;
  box-shadow:0 1px 2px rgba(16,24,40,.04)}
.mhead{padding:14px 18px 13px;border-bottom:2px solid #e8ecf2;
  background:linear-gradient(180deg,#ffffff 0%,#fbfcfe 100%)}
.mh-top{display:flex;gap:12px;align-items:flex-start}
.mid{flex:0 0 auto;display:inline-block;background:#2f6feb;color:#fff;font-size:12.5px;font-weight:700;
  border-radius:6px;padding:2px 9px;letter-spacing:.3px;margin-top:2px}
.mtitle{flex:1;font-size:15.5px;font-weight:700;line-height:1.45;color:#1f2329;word-break:break-word}
.mstat{flex:0 0 auto;font-size:11.5px;color:#5c6470;text-align:right;line-height:1.9;white-space:nowrap}
.mstat b{font-weight:700}
.mstat .n1 b{color:#0f9d58}.mstat .n2 b{color:#b06000}
.mstat .n3 b{color:#1967d2}.mstat .n4 b{color:#9aa0a6}.mstat .n5 b{color:#c5221f}
.mmeta{display:grid;grid-template-columns:78px 1fr;gap:5px 12px;margin-top:11px;font-size:12.5px}
.mmeta .k{color:#80868b;text-align:right;line-height:1.8}
.mmeta .v{color:#1f2329;line-height:1.8;word-break:break-word;overflow-wrap:anywhere}
.mmeta .v .who-nm{font-weight:600}
.mmeta .v .addr{color:#5c6470}
.mmeta .v .time{font-weight:600;color:#1f2329}
.prog{background:#eef4ff;border-left:3px solid #4a7fd4;padding:2px 8px;border-radius:3px;color:#2c4a7c;}
.pp{white-space:nowrap;display:inline-block;margin-right:2px}
.pp .e{color:#6b7280;font-size:11.5px}

/* ---------- owner cell ---------- */
.own{display:flex;flex-direction:column;gap:4px}
.ow{display:block;line-height:1.45}
.ow .ow-nm{font-weight:600}
.ow .ow-em{color:#5c6470;font-size:11px;display:block;word-break:break-all;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.ow .ow-st{display:inline-block;font-size:10.5px;font-weight:700;border-radius:9px;
  padding:0 7px;margin-left:4px;white-space:nowrap;vertical-align:1px}
.ow .ow-st.ok{background:#e6f4ea;color:#0f9d58}
.ow .ow-st.no{background:#f1f3f4;color:#80868b}
.ow .ow-st.team{background:#eef2ff;color:#4b5fa8}
.ow.on{border-left:2px solid #0f9d58;padding-left:7px;margin-left:-9px}
.ow.ex{border-left:2px dashed #c9ced6;padding-left:7px;margin-left:-9px}
.ow .ow-lb{font-size:10.5px;color:#80868b;display:block;letter-spacing:.2px}
.ow.non .ow-lb{color:#9aa0a6}
td.own-cell{line-height:1.5}

/* ---------- detail table ---------- */
table{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;background:#fff}
th{background:#f0f2f5;text-align:left;font-size:12px;color:#3c4043;padding:9px 12px;
  border-bottom:1px solid #e3e6eb;white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid #eef0f3;vertical-align:top;font-size:13px;
  word-break:break-word;overflow-wrap:anywhere}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f8f9fb}
td.qcol{line-height:1.55;font-weight:600}
.qsub{display:block;font-weight:400;color:#5c6470;font-size:12px;margin-top:4px;line-height:1.5}
.who .nm{font-weight:600}
.who .em{color:#5c6470;font-size:11px;word-break:break-all;display:block;margin-top:1px}
.who .dt{color:#80868b;font-size:11px;display:block;margin-top:2px}
.raw{line-height:1.58;color:#202124}
.sum{line-height:1.62;color:#202124}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;
  white-space:nowrap;margin-right:6px}
.badge.ok{background:#e6f4ea;color:#0f9d58}
.badge.part{background:#fef7e0;color:#b06000}
.badge.fwd{background:#e8f0fe;color:#1967d2}
.badge.none{background:#f1f3f4;color:#80868b}
code{background:#f1f3f4;padding:1px 5px;border-radius:4px;font-size:12px}
.warn{color:#b06000}
.cf{display:inline-block;background:#fce8e6;color:#c5221f;border:1px solid #f5c6c4;border-radius:4px;
  padding:0 6px;font-size:11px;font-weight:700;margin-right:4px;white-space:nowrap}
.cfn{color:#c5221f}
.hint{color:#80868b;font-size:12px;margin:12px 0 0}

/* ---------- manual memo (per summary row) ---------- */
.memo{margin-top:9px;border-top:1px dashed #e0e3e8;padding-top:7px}
.memo-hd{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.mchk{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;
  color:#5c6470;cursor:pointer;user-select:none;white-space:nowrap}
.mchk input{width:14px;height:14px;cursor:pointer;accent-color:#0f9d58;margin:0}
.mchk.on{color:#0f9d58}
.sbdg{display:none;font-size:10.5px;font-weight:700;background:#e6f4ea;color:#0f9d58;
  border-radius:9px;padding:0 7px}
.sbdg.on{display:inline-block}
.memo-pv{flex:1;min-width:60px;font-size:11.5px;color:#9aa0a6;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.memo-pv.has{color:#5c6470}
.mtog{border:1px solid #d7dae0;background:#fff;color:#3c4043;font-size:11px;border-radius:6px;
  padding:2px 9px;cursor:pointer;font-family:inherit;white-space:nowrap}
.mtog:hover{background:#f1f3f4;border-color:#c9ced6}
.memo-bd{display:none;margin-top:7px}
.memo.open .memo-bd{display:block}
.memo.open .memo-pv{display:none}
.memo-bd .lb{display:block;font-size:10.5px;font-weight:700;color:#80868b;
  margin:0 0 3px;letter-spacing:.03em}
.memo-bd textarea{width:100%;box-sizing:border-box;border:1px solid #d7dae0;border-radius:6px;
  padding:6px 8px;font-size:12.5px;line-height:1.6;font-family:inherit;color:#1f2329;
  background:#fcfcfd;resize:vertical;margin:0}
.memo-bd textarea:focus{outline:none;border-color:#1967d2;background:#fff;box-shadow:0 0 0 2px #e8f0fe}
tr.solved td{background:#f6fbf7}
tr.solved td.sum{box-shadow:inset 3px 0 0 #0f9d58}
.card.sol .n{color:#0f9d58}
.card.open .n{color:#c5221f}
.card.memo .n{color:#1967d2}

/* ---------- toolbar + export overlay ---------- */
.tools{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.btn{border:1px solid #d7dae0;background:#fff;color:#3c4043;font-size:12px;border-radius:7px;
  padding:5px 12px;cursor:pointer;font-family:inherit}
.btn:hover{background:#f1f3f4;border-color:#c9ced6}
.btn.dg{color:#c5221f;border-color:#f5c6c4}
.btn.dg:hover{background:#fce8e6}
.mhint{font-size:11.5px;color:#80868b}
.fst{font-size:11.5px;color:#9aa0a6}
.fst.on{color:#0f9d58;font-weight:600}
.saved{font-size:11.5px;color:#0f9d58;font-weight:600;opacity:0;transition:opacity .25s}
.saved.on{opacity:1}
.ovl{display:none;position:fixed;inset:0;background:rgba(32,33,36,.45);z-index:99;
  align-items:center;justify-content:center;padding:20px}
.ovl.on{display:flex}
.ovl-box{background:#fff;border-radius:12px;padding:18px 20px;width:min(760px,94vw);
  box-shadow:0 12px 40px rgba(0,0,0,.25)}
.ovl-box h3{margin:0 0 10px;font-size:15px;color:#1f2329}
.ovl-box textarea{width:100%;box-sizing:border-box;height:230px;font-size:11.5px;
  font-family:ui-monospace,Menlo,Consolas,monospace;border:1px solid #d7dae0;border-radius:8px;
  padding:10px;resize:vertical;color:#1f2329;background:#fcfcfd}
.ovl-box .row{display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap}
.o-tip{font-size:11.5px;color:#80868b;margin-top:9px;line-height:1.65}
"""

JS = """
var MAILS = __DATA__;
var L = __LANG__;
var ST = __ST__;
var cur = 0, fs = 'ALL', q = '';

/* ============ manual memos: note / mark resolved / final conclusion ============ */
var SKEY = 'hp_memo_v2';
var BAKED = /*MEMO-S*/__MEMO__/*MEMO-E*/;
var LS = { v: 0, d: {} }, STORE = {};
try { var _raw = localStorage.getItem(SKEY); if (_raw) { var _o = JSON.parse(_raw); if (_o && _o.d) LS = _o; } } catch (e) {}
if ((BAKED.v || 0) > (LS.v || 0)) { LS = { v: BAKED.v, d: BAKED.d || {} }; }
STORE = LS.d || {};
/* legacy data: older builds kept the note in n and the conclusion in f; both merged into n now */
for (var _mk in STORE) { var _mv = STORE[_mk];
  if (_mv && !_mv.n && _mv.f) _mv.n = _mv.f;
  if (_mv) delete _mv.f;
}
function persist() { try { localStorage.setItem(SKEY, JSON.stringify({ v: LS.v, d: STORE })); } catch (e) {} }
function mget(k) { return STORE[k] || { s: 0, n: '' }; }
function mset(k, patch) {
  var o = STORE[k] || { s: 0, n: '' };
  for (var p in patch) o[p] = patch[p];
  if (!o.s && !o.n) { delete STORE[k]; } else { STORE[k] = o; }
  persist(); flush(k); autoWrite();
}
function esct(x) { return (x || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function pvText(k) { var o = mget(k); return (o.n || '').replace(/\\s+/g, ' '); }
function memoHTML(k) {
  var o = mget(k), pv = pvText(k), has = !!o.n;
  return '<div class="memo" data-k="' + k + '">'
    + '<div class="memo-hd">'
    + '<label class="mchk' + (o.s ? ' on' : '') + '"><input type="checkbox" class="mck"' + (o.s ? ' checked' : '') + '>' + L.m_sol + '</label>'
    + '<span class="sbdg' + (o.s ? ' on' : '') + '">' + L.m_solved + '</span>'
    + '<span class="memo-pv' + (pv ? ' has' : '') + '">' + (pv ? esct(pv) : L.m_none) + '</span>'
    + '<button type="button" class="mtog">' + (has ? L.m_edit : L.m_add) + '</button>'
    + '</div>'
    + '<div class="memo-bd">'
    + '<span class="lb">' + L.m_note + '</span>'
    + '<textarea class="mnote" rows="3" spellcheck="false" placeholder="' + L.m_note_ph + '">' + esct(o.n) + '</textarea>'
    + '</div></div>';
}
function counts(m){var c={ok:0,part:0,fwd:0,none:0};m.items.forEach(function(i){c[i.st]++;});return c;}
function tip(m){
  return [m.subj, L.m_from+': '+m.sender+' <'+m.acct+'>', L.m_sent+': '+m.sent]
         .join('&#10;').replace(/"/g,'&quot;');
}
var ddOn = false, ddQ = '';
function ddToggle(ev){
  if(ev && ev.stopPropagation) ev.stopPropagation();
  ddOn = !ddOn;
  document.getElementById('tb').innerHTML = tabs();
  if(ddOn){ var f = document.getElementById('dfi'); if(f) f.focus(); }
}
function ddFilter(v){
  ddQ = (v || '').toLowerCase();
  var l = document.getElementById('ddlist');
  if(l) l.innerHTML = ddList(ddQ);
}
function ddList(qq){
  var out = '', n = 0;
  MAILS.forEach(function(m, i){
    if(qq){
      var b = (m.id + ' ' + m.subj + ' ' + m.sender + ' ' + m.sent).toLowerCase();
      if(b.indexOf(qq) < 0) return;
    }
    n++;
    var c = counts(m);
    out += '<div class="ddo' + (i === cur ? ' on' : '') + '" onclick="pick(' + i + ')" title="' + tip(m) + '">'
      + '<span class="oid">' + m.id + '</span>'
      + '<span class="osb">' + m.subj + '</span>'
      + '<span class="ddo2">'
      + '<span class="ofr"><span class="olb">' + L.m_from + '</span>' + m.sender + ' &lt;' + m.acct + '&gt;</span>'
      + '<span class="ofr"><span class="olb">' + L.m_sent + '</span>' + m.sent + '</span>'
      + '<span class="ofr"><span class="olb">' + L.m_items + '</span>' + m.items.length + '</span>'
      + '<span class="ost">' + L.st_leg + ' <b class="n1">' + c.ok + '</b>/<b class="n2">' + c.part
      + '</b>/<b class="n3">' + c.fwd + '</b>/<b class="n4">' + c.none + '</b></span>'
      + '</span>'
      + '</div>';
  });
  return n ? out : '<div class="ddempty">' + L.dd_empty + '</div>';
}
function pick(i){ ddOn = false; ddQ = ''; setCur(i); }
function step(d){
  var n = cur + d;
  if(n < 0 || n >= MAILS.length) return;
  ddOn = false; ddQ = ''; setCur(n);
}
function tabs(){
  var m = MAILS[cur];
  return '<div class="msel"><div class="row">'
    + '<button class="nav" type="button" onclick="step(-1)"' + (cur === 0 ? ' disabled' : '')
    + ' title="' + L.prev + '">&#8249;</button>'
    + '<div class="dd' + (ddOn ? ' on' : '') + '" id="dd">'
    + '<button class="ddbtn" type="button" onclick="ddToggle(event)" title="' + tip(m) + '">'
    + '<span class="bid">' + m.id + '</span>'
    + '<span class="bsm">' + m.chip + '</span>'
    + '<span class="bct">' + m.items.length + ' ' + L.m_items + ' · ' + (cur + 1) + ' / ' + MAILS.length + '</span>'
    + '<span class="car">▼</span>'
    + '</button>'
    + '<div class="ddpanel">'
    + '<div class="ddf"><input id="dfi" spellcheck="false" placeholder="' + L.pick_ph + '"'
    + ' value="' + ea(ddQ) + '" oninput="ddFilter(this.value)"></div>'
    + '<div class="ddlist" id="ddlist">' + ddList(ddQ) + '</div>'
    + '</div></div>'
    + '<button class="nav" type="button" onclick="step(1)"' + (cur === MAILS.length - 1 ? ' disabled' : '')
    + ' title="' + L.next + '">&#8250;</button>'
    + '</div></div>';
}
function ea(x){
  return (x || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}
function chips(){
  var h = '<span class="chip'+(fs==='ALL'?' on':'')+'" onclick="setS(\\'ALL\\')">'+L.all+'</span>';
  ['ok','part','fwd','none'].forEach(function(k){
    h += '<span class="chip'+(fs===k?' on':'')+'" onclick="setS(\\''+k+'\\')">'+ST[k]+'</span>';
  });
  var nk = noteKeys().length, no = mailOpen(MAILS[cur].id);
  h += '<span class="chip'+(fs==='MEMO'?' on':'')+'" onclick="setS(\\'MEMO\\')">' + L.m_chip + (nk ? ' ' + nk : '') + '</span>';
  h += '<span class="chip'+(fs==='OPEN'?' on':'')+'" title="' + L.open_tip + '" onclick="setS(\\'OPEN\\')">' + L.m_chip_open + (no ? ' ' + no : '') + '</span>';
  return h;
}
function setCur(i){ cur=i; fs='ALL'; q=''; var e=document.getElementById('si'); if(e)e.value=''; render(); }
function setS(v){ fs=v; ddOn=false; render(); }
function pp(list){
  return list.map(function(x){
    var nm = x.n ? '<span class="who-nm">'+x.n+'</span> ' : '';
    return '<span class="pp">'+nm+'<span class="e">&lt;'+x.e+'&gt;</span></span>';
  }).join(' · ');
}
function head(m, vis){
  var c = counts(m);
  return '<div class="mhead">'
    + '<div class="mh-top"><span class="mid">'+m.id+'</span>'
    + '<div class="mtitle">'+m.subj+'</div>'
    + '<div class="mstat"><div>'+vis.length+' / '+m.items.length+' '+L.cnt+'</div>'
    + '<div><span class="n1">'+ST.ok+' <b>'+c.ok+'</b></span> · <span class="n2">'+ST.part+' <b>'+c.part+'</b></span>'
    + ' · <span class="n3">'+ST.fwd+' <b>'+c.fwd+'</b></span> · <span class="n4">'+ST.none+' <b>'+c.none+'</b></span></div>'
    + '<div><span class="n5">'+L.m_open+' <b id="mopen">'+mailOpen(m.id)+'</b></span></div></div></div>'
    + '<div class="mmeta">'
    + '<div class="k">'+L.m_from+'</div><div class="v"><span class="who-nm">'+m.sender+'</span> <span class="addr">&lt;'+m.acct+'&gt;</span></div>'
    + '<div class="k">'+L.m_to+'</div><div class="v">'+pp(m.to)+'</div>'
    + '<div class="k">'+L.m_cc+'</div><div class="v">'+pp(m.cc)+'</div>'
    + '<div class="k">'+L.m_sent+'</div><div class="v"><span class="time">'+m.sent+'</span></div>'
    + (m.note ? '<div class="k">'+L.m_prog+'</div><div class="v"><span class="prog">'+m.note+'</span></div>' : '')
    + '</div></div>';
}
function rows(vis){
  return vis.map(function(it){
    var sl = mget(it.k).s ? ' class="solved"' : '';
    return '<tr'+sl+'><td class="qcol">'+it.q+'</td><td class="own-cell">'+it.own+'</td>'
      + '<td><div class="raw">'+it.raw+'</div></td>'
      + '<td class="sum"><span class="badge '+it.st+'">'+ST[it.st]+'</span>'+it.se+memoHTML(it.k)+'</td></tr>';
  }).join('');
}
function render(){
  var m = MAILS[cur];
  var vis = m.items.filter(function(it){
    var o = STORE[it.k];
    if(fs==='MEMO'){ if(!o || !(o.s || o.n)) return false; }
    else if(fs==='OPEN'){ if(o && o.s) return false; }
    else if(fs!=='ALL' && fs!==it.st) return false;
    if(q){
      var b=(it.q+' '+it.owText+' '+it.raw+' '+it.se+' '+(o?o.n:'')).toLowerCase();
      if(b.indexOf(q)<0) return false;
    }
    return true;
  });
  document.getElementById('tb').innerHTML = tabs();
  document.getElementById('host').innerHTML = vis.length
    ? '<div class="mailcard">'+head(m,vis)+'__THEAD__'+rows(vis)+'</tbody></table></div>'
    : '<div class="mailcard"><div style="text-align:center;color:#9aa0a6;padding:44px">'+L.empty+'</div></div>';
  document.getElementById('bar').innerHTML = chips();
  document.getElementById('cnt').textContent = vis.length+' / '+m.items.length+' '+L.cnt;
  updStats();
}
function noteKeys(){ return Object.keys(STORE).filter(function(k){ var o=STORE[k]; return o && (o.s || o.n); }); }
/* counters only look at the rows actually listed in this build */
function allItems(){ var n=0; for(var i=0;i<MAILS.length;i++) n += MAILS[i].items.length; return n; }
function solCount(){
  var n = 0;
  for(var i=0;i<MAILS.length;i++){ var its = MAILS[i].items;
    for(var j=0;j<its.length;j++){ var o = STORE[its[j].k]; if(o && o.s) n++; } }
  return n;
}
function openCount(){ return Math.max(0, allItems() - solCount()); }
function mailOpen(mid){
  var n = 0;
  for(var i=0;i<MAILS.length;i++){ var m = MAILS[i]; if(m.id !== mid) continue;
    for(var j=0;j<m.items.length;j++){ var o = STORE[m.items[j].k]; if(!o || !o.s) n++; } }
  return n;
}
function updStats(){
  var ks = noteKeys();
  var a=document.getElementById('nSol'), b=document.getElementById('nMemo'), c=document.getElementById('nOpen');
  if(a) a.textContent = solCount();
  if(b) b.textContent = ks.length;
  if(c) c.textContent = openCount();
  var mo = document.getElementById('mopen');
  if(mo && MAILS[cur]) mo.textContent = mailOpen(MAILS[cur].id);
  var bar=document.getElementById('bar'); if(bar) bar.innerHTML = chips();
  updTodo();
}
/* Open items: live list of the rows not yet marked resolved (same set as the KPI card) */
function updTodo(){
  var ol = document.getElementById('todol'); if(!ol) return;
  var c = document.getElementById('todoc'), out = [];
  for(var i=0;i<MAILS.length;i++){
    for(var j=0;j<MAILS[i].items.length;j++){
      var it = MAILS[i].items[j], o = STORE[it.k];
      if(o && o.s) continue;
      out.push('<li onclick="jump(' + i + ')"><b>' + MAILS[i].id + '</b> \u00b7 ' + esct(it.t) + '</li>');
    }
  }
  if(c) c.textContent = out.length ? ' ' + out.length : '';
  ol.innerHTML = out.length ? out.join('') : '<li class="tnone">' + L.todo_none + '</li>';
}
function jump(i){
  setCur(i);
  var h = document.getElementById('host');
  if(h && h.scrollIntoView){ try { h.scrollIntoView({ block: 'start' }); } catch(e) {} }
}
function flush(k){
  var box = document.querySelector('.memo[data-k="' + k + '"]');
  if(box){
    var o = mget(k), has = !!o.n, pv = pvText(k);
    var tr = box.closest('tr'); if(tr) tr.classList.toggle('solved', !!o.s);
    var ck = box.querySelector('.mchk'); if(ck) ck.classList.toggle('on', !!o.s);
    var bg = box.querySelector('.sbdg'); if(bg) bg.classList.toggle('on', !!o.s);
    var p  = box.querySelector('.memo-pv');
    if(p){ p.textContent = pv || L.m_none; p.classList.toggle('has', !!pv); }
    var tg = box.querySelector('.mtog'); if(tg) tg.textContent = has ? L.m_edit : L.m_add;
  }
  updStats();
}
var _tt;
function toast(m){
  [document.getElementById('saved'), document.getElementById('saved2')].forEach(function(e){
    if(!e) return; e.textContent = m; e.classList.add('on');
  });
  clearTimeout(_tt);
  _tt = setTimeout(function(){
    [document.getElementById('saved'), document.getElementById('saved2')].forEach(function(e){
      if(e) e.classList.remove('on');
    });
  }, 2000);
}
function ovl(open){ var e=document.getElementById('ovl'); if(e) e.classList.toggle('on', !!open); }
function expJSON(){
  var ta = document.getElementById('ovlta');
  if(ta) ta.value = JSON.stringify({ v: LS.v, d: STORE }, null, 1);
  ovl(true);
}
function dlJSON(){
  var ta = document.getElementById('ovlta'); if(!ta) return;
  try{
    var b = new Blob([ta.value], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(b); a.download = 'HP_memos_v' + LS.v + '.json';
    document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  }catch(e){ alert(L.m_dlfail); }
}
function cpJSON(){
  var ta = document.getElementById('ovlta'); if(!ta) return;
  ta.focus(); ta.select();
  try{ ta.setSelectionRange(0, 999999); document.execCommand('copy'); }catch(e){}
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(ta.value).then(function(){ toast(L.m_copied); }, function(){ toast(L.m_copied); });
  } else { toast(L.m_copied); }
}
function impJSON(){
  var ta = document.getElementById('ovlta'); if(!ta) return;
  var o = null;
  try{ o = JSON.parse(ta.value); }catch(e){ alert(L.m_bad); return; }
  var d = (o && o.d) ? o.d : o;
  if(!d || typeof d !== 'object'){ alert(L.m_bad); return; }
  for(var k in d){ if(d[k]) STORE[k] = d[k]; }
  if(o && typeof o.v === 'number' && o.v > LS.v) LS.v = o.v;
  persist(); ovl(false); render(); toast(L.m_imported);
}
function clrAll(){
  if(!confirm(L.exp_clr + ' ?')) return;
  STORE = {}; LS = { v: LS.v + 1, d: STORE }; persist(); render(); toast(L.m_clred);
}
/* ---------- write the marks back into this HTML file ---------- */
var FSA = null, _wt = null;
var MA = '/*M' + 'EMO-S*/', MB = '/*M' + 'EMO-E*/';
function fsName(){
  var p = (location.pathname || '').split('/').pop() || '';
  try { p = decodeURIComponent(p); } catch(e) {}
  return p || 'HP_clarification.html';
}
function bakeHTML(){
  var U = String.fromCharCode(92) + 'u003c';
  var j = JSON.stringify({ v: LS.v, d: STORE }).split('<').join(U);
  var s = '<!DOCTYPE html>' + String.fromCharCode(10) + document.documentElement.outerHTML;
  var a = s.indexOf(MA), b = s.indexOf(MB);
  if(a < 0 || b < 0 || b < a) return null;
  return s.slice(0, a + MA.length) + j + s.slice(b);
}
function writeBack(){
  LS.v = (LS.v || 0) + 1;
  persist();
  var t = bakeHTML();
  if(t === null) return Promise.reject(new Error('no-marker'));
  return FSA.createWritable().then(function(w){
    return w.write(t).then(function(){ return w.close(); });
  });
}
function markFst(){
  var e = document.getElementById('fst'); if(!e) return;
  e.textContent = FSA ? L.m_file_on : L.m_file_off;
  if(FSA){ e.classList.add('on'); } else { e.classList.remove('on'); }
}
function autoWrite(){
  if(!FSA) return;
  clearTimeout(_wt);
  _wt = setTimeout(function(){
    writeBack().then(function(){ toast(L.m_file_ok); }, function(){});
  }, 2000);
}
function dlHTML(){
  var t = bakeHTML();
  if(t === null){ alert(L.m_file_bad); return; }
  try{
    var b = new Blob([t], { type: 'text/html;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(b); a.download = fsName();
    document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 1500);
    toast(L.m_file_dl);
  }catch(e){ toast(L.m_file_no); }
}
function saveToFile(){
  if(!window.showSaveFilePicker){ dlHTML(); return; }
  if(FSA){
    writeBack().then(function(){ toast(L.m_file_ok); },
                     function(){ FSA = null; markFst(); dlHTML(); });
    return;
  }
  window.showSaveFilePicker({
    suggestedName: fsName(),
    types: [{ description: 'HTML', accept: { 'text/html': ['.html', '.htm'] } }]
  }).then(function(h){ FSA = h; return writeBack(); })
    .then(function(){ markFst(); toast(L.m_file_ok); })
    .catch(function(e){
      if(e && e.name === 'AbortError') return;
      FSA = null; markFst();
      if(e && String(e.message || '').indexOf('no-marker') >= 0){ alert(L.m_file_bad); return; }
      dlHTML();
    });
}
window.addEventListener('beforeunload', function(){ try{ persist(); }catch(e){} });
document.addEventListener('input', function(e){
  var el = e.target; if(!el) return;
  if(el.id === 'si'){ q = el.value.toLowerCase().trim(); ddOn = false; render(); return; }
  if(!el.classList) return;
  var box = el.closest ? el.closest('.memo') : null;
  if(!box) return;
  var k = box.getAttribute('data-k');
  if(el.classList.contains('mnote')) mset(k, { n: el.value });
});
document.addEventListener('change', function(e){
  var el = e.target;
  if(el && el.classList && el.classList.contains('mck')){
    var box = el.closest('.memo');
    if(box) mset(box.getAttribute('data-k'), { s: el.checked ? 1 : 0 });
  }
});
document.addEventListener('click', function(e){
  var el = e.target;
  if(ddOn && !(el && el.closest && el.closest('.dd'))){
    ddOn = false;
    var tb = document.getElementById('tb'); if(tb) tb.innerHTML = tabs();
  }
  if(el && el.classList && el.classList.contains('mtog')){
    var box = el.closest('.memo');
    if(box){
      box.classList.toggle('open');
      if(box.classList.contains('open')){ var t2 = box.querySelector('.mnote'); if(t2) t2.focus(); }
    }
  } else if(el && el.id === 'ovl'){ ovl(false); }
});
document.addEventListener('keydown', function(e){
  if(e.key !== 'Escape') return;
  ovl(false);
  if(ddOn){
    ddOn = false;
    var tb = document.getElementById('tb'); if(tb) tb.innerHTML = tabs();
  }
});
render();
markFst();
"""

TABLE_HEAD = ('<table><colgroup><col style="width:20%"><col style="width:200px">'
              '<col style="width:26%"><col></colgroup><thead><tr>'
              + '<th>__TH1__</th><th>__TH2__</th><th>__TH3__</th><th>__TH4__</th>'
              + '</tr></thead><tbody>')


EN_WARN = {
    r"\u26a0 各类车的 age-at-maturity 计算公式仍未给出。":
        r"\u26a0 The age-at-maturity formula per vehicle type has still not been provided.",
}


def en_clean(s):
    """英文版清洗：只剔除「含中文」的 sub 子句；行内警示换成英文。"""
    if not s:
        return s
    s = re.sub(r"\s*<span class=['\"]sub['\"]>((?:(?!</span>).)*)</span>",
               lambda m: "" if re.search(r"[\u4e00-\u9fff]", m.group(1)) else m.group(0),
               s, flags=re.S)
    s = re.sub(r"<span class=['\"]warn['\"]>(.*?)</span>",
               lambda m: '<span class="warn">' + EN_WARN.get(m.group(1).strip(), m.group(1)) + "</span>",
               s, flags=re.S)
    return s


def who_html(who, when):
    if who == "—":
        return '<span class="nm">—</span>'
    parts = who.split("<br>")
    nm = parts[0]
    em = parts[1] if len(parts) > 1 else ""
    dt = f'<span class="dt">{when}</span>' if when else ""
    return f'<span class="nm">{nm}</span><span class="em">{em}</span>{dt}'


def people(lst, lang):
    out = []
    for x in lst or []:
        nm = (x.get("n_en") or x.get("n") or "") if lang == "en" else (x.get("n") or x.get("n_en") or "")
        nm = nm.strip()
        out.append({"n": nm, "e": x.get("e", "")})
    return out


def owner_html(owners, extra, lang, t):
    """负责人列：逐个列出应回复方 + 是否已回复；实际回复人若不在名单里单独一行。"""
    rows = []
    for o in owners:
        nm = f'<span class="ow-nm">{o["n"]}</span>' if o["n"] else ""
        if o["e"]:
            em = f'<span class="ow-em">&lt;{o["e"]}&gt;</span>'
            if o["replied"]:
                st = t["ow_yes"] + (" · " + o["when"] if o["when"] else "")
                st = f'<span class="ow-st ok">{st}</span>'
                cls = " on"
            else:
                st = f'<span class="ow-st no">{t["ow_no"]}</span>'
                cls = ""
        else:
            em = ""
            st = f'<span class="ow-st team">{t["ow_team"]}</span>'
            cls = ""
        rows.append(f'<div class="ow{cls}">{nm}{st}{em}</div>')
    for x in extra:
        nm = f'<span class="ow-nm">{x["n"]}</span>' if x["n"] else ""
        rows.append(f'<div class="ow ex"><span class="ow-lb">{t["ow_act"]}</span>'
                    f'{nm}<span class="ow-em">&lt;{x["e"]}&gt;</span></div>')
    if not owners:
        rows.insert(0, f'<div class="ow non"><span class="ow-lb">{t["ow_na"]}</span></div>')
    return '<div class="own">' + "".join(rows) + "</div>"


def owner_text(owners, extra, lang, t):
    """负责人列的纯文本版本（供搜索 / Markdown 使用）。"""
    ps = []
    for o in owners:
        s = o["n"] or ""
        if o["e"]:
            s += " <" + o["e"] + ">"
            s += "（" + (t["ow_yes"] + (" " + o["when"] if o["when"] else "")
                         if o["replied"] else t["ow_no"]) + "）" if lang == "zh" else \
                 " (" + (t["ow_yes"] + (" " + o["when"] if o["when"] else "")
                         if o["replied"] else t["ow_no"]) + ")"
        else:
            s += "（" + t["ow_team"] + "）" if lang == "zh" else " (" + t["ow_team"] + ")"
        ps.append(s)
    for x in extra:
        ps.append(t["ow_act"] + (":" if lang == "en" else "：") + " "
                  + (x["n"] or "") + " <" + x["e"] + ">")
    if not owners:
        ps.insert(0, t["ow_na"])
    return ("; " if lang == "en" else "；").join(ps)


def esc_html(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def short_q(q):
    """未解决清单里的一行标题：取 <br> 前的主句，去标签、截断。

    中英两边用同一套切法：中文 q 与英文 qe 都把正文放在 <br> 后面，
    <br> 前的部分才是区分条目的标题（含「— Puah 09-10 答复」这类后缀）。
    不要再按 em dash 二次切割 —— 会把区分后缀切掉，两条未解决长得一模一样。
    """
    s = q or ""
    if "<br>" in s:
        s = s.split("<br>")[0]
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if " \u2014 " in s:
        _h, _t = s.split(" \u2014 ", 1)
        if len(_t.strip()) > 44:
            s = _h.strip()
    if len(s) > 88:
        s = s[:88].rstrip() + "\u2026"
    return s


def item_key(mid, q):
    """备注稳定键：邮件号 + 问题纯文本哈希（中英页共用，重跑/增删条目后仍能对上）。"""
    plain = re.sub(r"<[^>]+>", " ", q or "")
    plain = re.sub(r"\s+", " ", plain).strip()
    return "%s-%s" % (mid, hashlib.md5(plain.encode("utf-8")).hexdigest()[:10])


def build(data, lang):
    t = I18N[lang]
    mails = []
    for m in data["mails"]:
        sender = m["sender"] if lang == "zh" else m["sender_en"]
        subj = m["subject"] if lang == "zh" else m["subject_en"]
        sent = m["sent"] if lang == "zh" else m["sent_en"]
        acct = m["sender_en"].split("(")[0].strip() + "@webank.com"
        if m.get("from_addr") and lang == "en" and not acct.startswith(
                m["from_addr"].split("@")[0]):
            acct = m["from_addr"]
        items = []
        for it in m["items"]:
            body = it["sum"] if lang == "zh" else it["se"]
            cf = it.get("cf")
            if cf:
                note = cf["zh"] if lang == "zh" else cf["en"]
                tag = "意见不一致" if lang == "zh" else "CONFLICTING VIEWS"
                body = f"<span class='cf'>\u26a0 {tag}</span><span class='cfn'>{note}</span><br>" + body
            _own_src = it["q"] if lang == "zh" else it["qe"]
            _owners, _extra = owners_with_status(_own_src, it["who"], it["when"], lang)
            items.append(dict(
                k=item_key(m["id"], it["q"]),
                q=(it["q"] if lang == "zh" else en_clean(it["qe"])),
                t=short_q(it["q"] if lang == "zh" else it["qe"]),
                own=owner_html(_owners, _extra, lang, t),
                owText=owner_text(_owners, _extra, lang, t),
                raw=it["raw"],
                se=body,
                st=it["st"],
            ))
        mails.append(dict(
            id=m["id"],
            subj=subj,
            chip=(subj[:34] + "…") if len(subj) > 34 else subj,
            sender=sender, acct=acct, sent=sent,
            note=(m.get("note") if lang == "zh" else m.get("note_en")) or "",
            to=people(m.get("to"), lang),
            cc=people(m.get("cc"), lang),
            items=items,
        ))

    st_map = {k: (v[0] if lang == "zh" else v[1]) for k, v in ST_LABEL.items()}
    total = sum(len(x["items"]) for x in mails)
    cnt = {k: 0 for k in ST_ORDER}
    repliers, reply_mails = set(), set()
    for m in data["mails"]:
        for it in m["items"]:
            cnt[it["st"]] += 1
            if it["who"] != "—":
                p = it["who"].split("<br>")
                if len(p) > 1:
                    repliers.add(p[1])
                    reply_mails.add((p[1], it["when"]))

    cards = [
        ("", t["c_mail"], len(mails)), ("", t["c_item"], total),
        ("ok", t["c_ok"], cnt["ok"]), ("part", t["c_part"], cnt["part"]),
        ("fwd", t["c_fwd"], cnt["fwd"]), ("none", t["c_none"], cnt["none"]),
        ("", t["c_reply"], f"{len(reply_mails)} 封 / {len(repliers)} 人" if lang == "zh"
         else f"{len(reply_mails)} / {len(repliers)} people"),
    ]
    cards_html = "".join(
        f'<div class="card {c[0]}"><div class="n">{c[2]}</div><div class="l">{c[1]}</div></div>' for c in cards)
    _mk0 = data.get("memos") or {}
    _keys0 = {item_key(m["id"], it["q"]) for m in data["mails"] for it in m["items"]}
    _sol0 = sum(1 for _k, _v in _mk0.items() if _k in _keys0 and _v.get("s"))
    _memo0 = sum(1 for _k, _v in _mk0.items()
                 if _k in _keys0 and (_v.get("s") or (_v.get("n") or "").strip()))
    _open0 = max(0, total - _sol0)
    cards_html += (f'<div class="card sol"><div class="n" id="nSol">{_sol0}</div>'
                   f'<div class="l">{t["c_sol"]}</div></div>'
                   f'<div class="card open"><div class="n" id="nOpen">{_open0}</div>'
                   f'<div class="l">{t["c_open"]}</div></div>'
                   f'<div class="card memo"><div class="n" id="nMemo">{_memo0}</div>'
                   f'<div class="l">{t["c_memo"]}</div></div>')

    # 未解决清单：初始值由 Python 算好写死，之后由 JS updTodo() 每次标记后重算
    _open_now = []
    for _mi, _m in enumerate(mails):
        for _it in _m["items"]:
            if not ((data.get("memos") or {}).get(_it["k"]) or {}).get("s"):
                _open_now.append((_mi, _m["id"], _it["t"]))
    _none_li = '<li class="tnone">' + t["todo_none"] + "</li>"
    _li0 = "".join(f'<li onclick="jump({_oi})"><b>{_mid}</b> \u00b7 {esc_html(_txt)}</li>'
                   for _oi, _mid, _txt in _open_now)
    todo_html = (
        '<div class="todo">'
        + f'<div class="th">{t["todo"]}<span class="tc" id="todoc"> {len(_open_now)}</span></div>'
        + f'<ol id="todol">{_li0 or _none_li}</ol>'
        + "</div>")

    thead = (TABLE_HEAD.replace("__TH1__", t["th1"]).replace("__TH2__", t["th2"])
             .replace("__TH3__", t["th3"]).replace("__TH4__", t["th4"]))

    baked = {"v": data.get("memos_v", 0), "d": data.get("memos") or {}}
    js = (JS.replace("__DATA__", json.dumps(mails, ensure_ascii=False))
            .replace("__MEMO__", json.dumps(baked, ensure_ascii=False).replace("<", "\\u003c"))
            .replace("__LANG__", json.dumps(t, ensure_ascii=False))
            .replace("__ST__", json.dumps(st_map, ensure_ascii=False))
            .replace("__THEAD__", thead.replace("'", "\\'")))

    tools_html = (
        '<div class="bar tools">'
        f'<button class="btn" type="button" onclick="expJSON()">{t["exp_open"]}</button>'
        f'<button class="btn" type="button" onclick="saveToFile()">{t["m_file"]}</button>'
        '<span class="fst" id="fst"></span>'
        f'<span class="mhint">{t["memo_hint"]}</span>'
        '<span class="saved" id="saved"></span>'
        '</div>')
    ovl_html = (
        '<div class="ovl" id="ovl"><div class="ovl-box">'
        f'<h3>{t["exp_ti"]}</h3>'
        '<textarea id="ovlta" spellcheck="false"></textarea>'
        '<div class="row">'
        f'<button class="btn" type="button" onclick="cpJSON()">{t["exp_cp"]}</button>'
        f'<button class="btn" type="button" onclick="dlJSON()">{t["exp_dl"]}</button>'
        f'<button class="btn" type="button" onclick="impJSON()">{t["exp_imp"]}</button>'
        f'<button class="btn dg" type="button" onclick="clrAll()">{t["exp_clr"]}</button>'
        f'<button class="btn" type="button" style="margin-left:auto" onclick="ovl(false)">{t["exp_close"]}</button>'
        '<span class="saved" id="saved2"></span>'
        '</div>'
        f'<div class="o-tip">{t["exp_tip"]}</div>'
        '</div></div>')

    return f"""<!DOCTYPE html>
<html lang="{t['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t['title']}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>{t['title']}</h1>
  <div class="sub">{t['sub']}</div>
  <div class="sub">{t['updated']}: {data['updated']} · {t['window']}: {data['window'] if lang=='zh' else data['window_en']}</div>
  <div class="cards">{cards_html}</div>
  {todo_html}
  <div id="tb"></div>
  <div class="bar" id="bar"></div>
  <div class="bar"><input class="search" id="si" placeholder="{t['search']}"><span class="chip" style="cursor:default" id="cnt"></span></div>
  {tools_html}
  <div id="host"></div>
  {ovl_html}
  <p class="hint">{t['hint']}</p>
</div>
<script>{js}</script>
</body>
</html>"""


def strip_tags(s):
    s = re.sub(r"<br\s*/?>", " / ", s or "")
    s = re.sub(r"</?(b|code|span)[^>]*>", "", s)
    return html.unescape(s).strip()


def people_md(lst):
    return "、".join((f"{x['n']} " if x.get("n") else "") + f"<{x['e']}>" for x in (lst or []))


def build_md(data):
    t = I18N["zh"]
    total = sum(len(m["items"]) for m in data["mails"])
    cnt = {k: 0 for k in ST_ORDER}
    repliers, reply_mails = set(), set()
    for m in data["mails"]:
        for it in m["items"]:
            cnt[it["st"]] += 1
            if it["who"] != "—":
                p = it["who"].split("<br>")
                if len(p) > 1:
                    repliers.add(p[1])
                    reply_mails.add((p[1], it["when"]))
    L = []
    L.append("# HP 客户问题回复汇总（HP Client Clarification Tracker）\n")
    L.append(f"- **{t['updated']}**：{data['updated']}　**{t['window']}**：{data['window']}")
    L.append(f"- **我方发出邮件**：{len(data['mails'])} 封　**问题条目**：{total} 条")
    L.append(f"- **状态分布**：已确认 {cnt['ok']} / 部分回复 {cnt['part']} / 转交他人 {cnt['fwd']} / 未回复 {cnt['none']}")
    L.append(f"- **客户回复**：{len(reply_mails)} 封邮件，来自 {len(repliers)} 个 HLBB 邮箱")
    _mk = data.get("memos") or {}
    _sol = sum(1 for v in _mk.values() if v.get("s"))
    _nte = sum(1 for v in _mk.values() if (v.get("n") or "").strip())
    if _sol or _nte:
        L.append(f"- **已标记解决**：{_sol} 条（其中 {_nte} 条含最终结论，同步自英文 HTML 版）")
        _opn = max(0, total - _sol)
        L.append(f"- **未标记 / 未解决**：{_opn} 条（= 问题条目 {total} − 已标记解决 {_sol}）")
    L.append("\n> 版式固定为「一封邮件一个页签」：页签内先列邮件级信息（发件人 / 收件人 / 抄送 / 发送时间），"
             "再列明细表 **问题 | 负责人(Owner) | 问题回复内容 | 问题回复总结 | 状态 | 备忘 / 最终结论**。回复内容保留客户端英文原文，"
             "总结为我方解读；末列「备忘 / 最终结论」同步自英文 HTML 版的手工标记（✅ 已解决 + 最终结论），交互式编辑请用 HTML 版。\n")
    if data.get("todos"):
        L.append("\n## 当前待我方回应 / 跟进\n")
        for x in data["todos"]:
            L.append(f"- **{x['mail']}** — {x['zh']}")
        L.append("")

    # 与 HTML 顶部「未解决事项」同口径（未标记为已解决的条目）
    _open_md = []
    for _m in data["mails"]:
        for _it in _m["items"]:
            if ((data.get("memos") or {}).get(item_key(_m["id"], _it["q"])) or {}).get("s"):
                continue
            _open_md.append((_m["id"], strip_tags(short_q(_it["q"]))))
    if _open_md:
        L.append("\n## 未解决事项（未标记为已解决）\n")
        L.append(f"共 {len(_open_md)} 条（条目总数 {total} − 已标记解决 {_sol}）\n")
        for _mid, _tt in _open_md:
            L.append(f"- **{_mid}** {_tt}")
        L.append("")

    for m in data["mails"]:
        c = {k: 0 for k in ST_ORDER}
        for it in m["items"]:
            c[it["st"]] += 1
        L.append(f"\n## {m['id']} · {strip_tags(m['subject'])}\n")
        L.append(f"- **{t['m_from']}**：{m['sender']}（{m['sender_en']}）"
                 f"　**{t['m_sent']}**：{m['sent']}")
        L.append(f"- **{t['m_to']}**：{people_md(m.get('to'))}")
        if m.get("note"):
            L.append(f"- **{t['m_prog']}**：{strip_tags(m['note'])}")
        L.append(f"- **{t['m_cc']}**：{people_md(m.get('cc'))}")
        L.append(f"- **{t['items']}**：{len(m['items'])}　"
                 f"**状态**：已确认 {c['ok']} / 部分 {c['part']} / 转交 {c['fwd']} / 未回复 {c['none']}\n")
        L.append("| # | 问题 | 负责人（应回复方） | 问题回复内容（英文原文） | 问题回复总结 | 状态 | 备忘 / 最终结论 |")
        L.append("|---|---|---|---|---|---|---|")
        for i, it in enumerate(m["items"], 1):
            _o, _x = owners_with_status(it["q"], it["who"], it["when"], "zh")
            who = owner_text(_o, _x, "zh", I18N["zh"])
            sm = strip_tags(it["sum"]).replace("|", "\\|")
            if it.get("cf"):
                sm = "\u26a0 **意见不一致**：" + it["cf"]["zh"].replace("|", "\\|") + " / " + sm
            _mkv = (data.get("memos") or {}).get(item_key(m["id"], it["q"])) or {}
            _parts = []
            if _mkv.get("s"):
                _parts.append("\u2705 已解决")
            if (_mkv.get("n") or "").strip():
                _parts.append(strip_tags(_mkv["n"]).strip().replace("|", "\\|"))
            L.append("| {} | {} | {} | {} | {} | {} | {} |".format(
                i,
                strip_tags(it["q"]).replace("|", "\\|"),
                who.replace("|", "\\|"),
                strip_tags(it["raw"]).replace("|", "\\|"),
                sm,
                ST_LABEL[it["st"]][0],
                " \u00b7 ".join(_parts),
            ))
    L.append("\n---\n")
    L.append("_本文件由固定格式渲染器生成，每次更新邮件后重新生成即可（中文 HTML / 英文 HTML / MD 三件套）。_")
    return "\n".join(L)


def main():
    data = json.load(io.open(DATA, encoding="utf-8"))
    io.open(os.path.join(OUTDIR, "HP客户问题回复汇总_CN.html"), "w", encoding="utf-8").write(build(data, "zh"))
    io.open(os.path.join(OUTDIR, "HP客户问题回复汇总_EN.html"), "w", encoding="utf-8").write(build(data, "en"))
    io.open(os.path.join(OUTDIR, "HP客户问题回复汇总.md"), "w", encoding="utf-8").write(build_md(data))
    print("generated 3 files ->", OUTDIR)


if __name__ == "__main__":
    main()
