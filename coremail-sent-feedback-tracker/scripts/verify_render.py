# -*- coding: utf-8 -*-
"""
渲染产物静态校验（交付前必跑）

覆盖 SKILL.md §7 校验清单里**可静态判定**的项：
  1. EN 页广义 CJK = 0
  2. max-height 计数 = 2（.ddlist + .todo ol）
  3. CN 页 class='sub' 计数（>0，真实数据集应上百）
  4. 负责人列 ow-nm 计数
  5. 备注模板块各出现 1 次（模板定义）
  6. 单行下拉切换器 / Open items / 烘焙位 / 进展备注 存在性
  7. JS 语法（node --check，需 node 在 PATH 或 --node 指定）
  8. 数据层字段扫描（*_en 字段 + when + qe + se + raw 无中文）

无法静态判定的两项（需真实浏览器 / 完整 DOM stub，方法见 references/04-render-spec.md §8）：
  9.  JS 运行时烟测（MAILS.length / 备注真实行数 / mset() 生效）
  10. 写回往返（写回 → 空 localStorage 重载 → 标记恢复）

用法：
    python verify_render.py <CN.html> <EN.html> [--data <data.json>] [--node <node.exe>]
    python verify_render.py outdir/ --auto          # 自动找 outdir 下的 CN/EN

退出码：0 = 全通过；1 = 有 FAIL。
"""
import io
import os
import re
import sys
import json
import glob
import subprocess

CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
CJK_NARROW = re.compile(r"[\u4e00-\u9fff]")
# 渲染器 en_clean() 会剔除「含中文」的 sub 子句，判定时需先剥离
SUB_RE = re.compile(r"<span class=['\"]sub['\"]>.*?</span>", re.S)

RESULTS = []


def ck(name, cond, got, expect=""):
    RESULTS.append((bool(cond), name, got, expect))
    flag = "PASS" if cond else "FAIL"
    print("  [%s] %-46s got=%s%s" % (flag, name, got, ("  expect=%s" % expect) if expect else ""))
    return bool(cond)


def read(p):
    return io.open(p, encoding="utf-8", errors="replace").read()


def find_pair(target):
    """从目录或文件路径解析出 (cn_path, en_path)。

    目录下可能同时存在「汇总三件套」和「单封导出」两类 HTML
    （如 HP客户问题回复汇总_CN.html 与 HP_Clarification_M15_EN.html），
    因此配对必须以 CN 文件为锚，EN 取**同前缀**的那个，不能按名字排序瞎选。
    """
    if os.path.isdir(target):
        htmls = sorted(glob.glob(os.path.join(target, "*.html")))
        cns = [p for p in htmls if p.endswith("_CN.html")]
        if not cns:
            return None, None

        def score(p):
            b = os.path.basename(p)
            # 优先「汇总 / Summary」类，其次短的（单封导出名字通常更长）
            return (0 if ("汇总" in b or "Summary" in b) else 1, len(b))

        cn = sorted(cns, key=score)[0]
        en = cn[: -len("_CN.html")] + "_EN.html"
        return cn, (en if os.path.exists(en) else None)
    return None, None


def check_html(cn_path, en_path):
    print("\n=== 1. 静态结构校验 ===")
    cn = read(cn_path)
    en = read(en_path)

    # 1. EN 页广义 CJK
    n = len(CJK.findall(en))
    ck("EN 页广义 CJK", n == 0, n, "0")
    if n:
        narrow = len(CJK_NARROW.findall(en))
        print("       提示：其中汉字 %d 个。若窄扫为 0 而广义非 0 → 是全角标点残留（见 render-spec §6.3）" % narrow)
        for m in list(re.finditer(CJK, en))[:5]:
            seg = en[max(0, m.start() - 60):m.end() + 20].replace("\n", " ")
            print("       > ...%s..." % seg)

    # 2. max-height 恰好 2 处
    mh = en.count("max-height")
    ck("EN 页 max-height 计数", mh == 2, mh, "2 (.ddlist + .todo ol)")
    if mh != 2:
        for m in re.finditer(r"max-height", en):
            seg = en[max(0, m.start() - 90):m.end() + 30].replace("\n", " ")
            print("       > ...%s..." % seg)

    # 3. CN 页 sub 计数
    sub = cn.count("class='sub'") + cn.count('class="sub"')
    ck("CN 页 class='sub' 计数", sub > 0, sub, ">0（真实数据集应上百）")
    if sub and sub < 20:
        print("       提示：数值偏低。真实数据集基线约 129；若明显偏少，检查 en_clean 是否串了语言")

    # 4. 负责人列
    ow = cn.count("ow-nm") + cn.count('class="ow')
    ck("CN 页 负责人列元素存在", ow > 0, ow)

    # 5. 备注模板块（静态各 1 次）
    for cls in ("memo-hd", "memo-pv", "memo-bd"):
        n = len(re.findall(r'class="%s' % cls, cn))
        ck("CN 页模板 .%s 各 1 次" % cls, n == 1, n, "1（模板定义，行数靠 JS 烟测）")

    # 6. 关键结构存在性
    for name, token in (
        ("单行下拉切换器 (ddOn)",  "ddOn"),
        ("Open items 清单 (todol)", 'id="todol"'),
        ("写回烘焙位 (MEMO-S)",     "MEMO-S"),
        ("备注存储 (STORE/BAKED)",  "BAKED"),
        ("渲染入口 (rows)",         "function rows("),
        ("统计刷新 (updStats)",     "function updStats("),
    ):
        ck(name, token in cn, "YES" if token in cn else "NO", "YES")

    # 进展备注 / 意见不一致 为可选，仅报信息
    print("  [INFO] 进展备注行 .prog 出现 %d 次（数据里无 note 则为 0）" % cn.count('class="prog"'))
    print("  [INFO] 意见不一致标记 cf 出现 %d 次（数据里无 cf 则为 0）" % cn.count("cf-badge"))
    return cn, en


def check_js(cn, node_exe):
    print("\n=== 2. JS 语法校验 ===")
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", cn, re.S)
    if not blocks:
        ck("存在 <script> 块", False, 0, ">0")
        return
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_verify_tmp.js")
    io.open(tmp, "w", encoding="utf-8", newline="\n").write("\n;\n".join(blocks))
    if not node_exe or not os.path.exists(node_exe):
        print("  [SKIP] 未找到 node，跳过语法校验。传 --node <node.exe> 指定")
        return
    r = subprocess.run([node_exe, "--check", tmp],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    err = (r.stderr or b"").decode("utf-8", "replace").strip()
    ck("node --check 通过（%d 个 script 块）" % len(blocks), r.returncode == 0, err[:160] or "no error")
    if r.returncode != 0:
        print("       提示：JS 语法错误在浏览器里表现为【整页白屏无 JS】。")
        print("       常见根因：Python 三引号里的 JS 转义层数（源码要写 \\\\' 才能得到 \\'）")


def check_data(data_path):
    print("\n=== 3. 数据层字段扫描 ===")
    if not data_path or not os.path.exists(data_path):
        print("  [SKIP] 未提供数据文件。传 --data <data.json> 启用")
        return
    d = json.load(io.open(data_path, encoding="utf-8"))
    bad = []      # mails 里的问题：会直接污染 EN 产物 → FAIL
    warn = []     # held 里的问题：当前不参与渲染 → WARN（但拉回主清单前必须修）
    benign = []

    def scan(label, s, allow_sub=False):
        """allow_sub=True 时，落在 <span class='sub'> 内的中文算合法。

        渲染器的 en_clean() 会**剔除「含中文」的 sub 子句**（见 render-spec §6.2），
        所以这类中文不会出现在 EN 页，属于设计允许的写法（常用于标注数据来源）。
        """
        if not s or not isinstance(s, str):
            return
        if not CJK_NARROW.search(s):
            return
        if allow_sub and not CJK_NARROW.search(SUB_RE.sub("", s)):
            benign.append(label)
            return
        (warn if label.startswith("held.") else bad).append((label, s[:70]))

    scan("subject_en", d.get("subject_en"))
    scan("window_en", d.get("window_en"))
    for bucket in ("mails", "held"):
        for m in d.get(bucket, []):
            base = "%s.%s" % (bucket, m.get("id", "?"))
            scan(base + ".sender_en", m.get("sender_en"))
            scan(base + ".subject_en", m.get("subject_en"))
            scan(base + ".sent_en", m.get("sent_en"))
            scan(base + ".note_en", m.get("note_en"))
            for k, p in (("to", m.get("to") or []), ("cc", m.get("cc") or [])):
                for i, per in enumerate(p):
                    scan("%s.%s[%d].n_en" % (base, k, i), per.get("n_en"))
            for i, it in enumerate(m.get("items") or []):
                pre = "%s.items[%d]" % (base, i)
                scan(pre + ".qe", it.get("qe"), allow_sub=True)
                scan(pre + ".se", it.get("se"), allow_sub=True)
                scan(pre + ".when", it.get("when"))   # 渲染器无 when_en，EN 页复用 when
                scan(pre + ".raw", it.get("raw"))
                cf = it.get("cf")
                if isinstance(cf, dict):
                    scan(pre + ".cf.en", cf.get("en"))
    ck("数据层 *_en / when 字段无汉字（mails，sub 内除外）", not bad, len(bad), "0")
    for label, sample in bad[:12]:
        print("       > %-34s %s" % (label, sample))
    if bad:
        print("       提示：这是 EN 页中文残留最常见的来源（见 render-spec §6.4）")
    if warn:
        print("  [WARN] %d 处中文位于 held（当前不参与渲染，不影响本次产物），" % len(warn))
        print("         但把 held 拉回主清单前必须修掉：")
        for label, sample in warn[:8]:
            print("       > %-34s %s" % (label, sample))
    if benign:
        print("  [INFO] %d 处中文位于 <span class='sub'> 内 — 渲染器会自动剔除，合法"
              % len(benign))

    # 计数自洽
    tot = sum(len(m.get("items") or []) for m in d.get("mails", []))
    memos = d.get("memos") or {}
    solved = sum(1 for v in memos.values() if isinstance(v, dict) and v.get("s"))
    print("  [INFO] 条目总数 %d · 已标记解决 %d · 未解决 %d" % (tot, solved, max(0, tot - solved)))
    print("  [INFO] memos_v = %s（每次固化必须 +1，否则烘焙值会被空 localStorage 盖掉）"
          % d.get("memos_v"))


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1

    data_path = None
    node_exe = None
    target = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--data":
            i += 1; data_path = argv[i]
        elif a == "--node":
            i += 1; node_exe = argv[i]
        elif a == "--auto":
            pass
        else:
            target = a
        i += 1

    if not node_exe:
        for cand in (
            os.path.expandvars(r"%LOCALAPPDATA%\..\..\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"),
            r"C:\Users\leonerdli\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
        ):
            if os.path.exists(cand):
                node_exe = cand
                break

    if not target:
        print("错误：请给出 outdir 或 CN.html")
        return 1

    cn_path, en_path = find_pair(target)
    if not cn_path or not en_path:
        if target.endswith(".html"):
            cn_path = en_path = target
        else:
            print("错误：目录下找不到 *_CN.html / *_EN.html")
            return 1
    if not data_path:
        guess = os.path.join(target if os.path.isdir(target) else os.path.dirname(target),
                             "..", "clarification_data.json")
        if os.path.exists(guess):
            data_path = guess

    print("CN : %s" % cn_path)
    print("EN : %s" % en_path)
    if data_path:
        print("DATA: %s" % data_path)

    cn, _ = check_html(cn_path, en_path)
    check_js(cn, node_exe)
    check_data(data_path)

    nfail = sum(1 for r in RESULTS if not r[0])
    print("\n" + "=" * 62)
    print("RESULT: %d PASS / %d FAIL" % (len(RESULTS) - nfail, nfail))
    print("仍需人工/浏览器验证：JS 运行时烟测、写回往返（见 render-spec §8）")
    print("=" * 62)
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
