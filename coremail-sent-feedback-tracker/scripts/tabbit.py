#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tabbit CLI 封装层。

统一处理：
  * 跨平台定位 tabbit-cli 启动器
  * nodejs 执行（通过 stdin 重定向，不用 persistent 模式）
  * 大结果自动分页（返回值 >8KB 会变成 resourceId）
  * 常用操作 CLI：tabs / resume / search / read-idx / read-key

用法：
    python tabbit.py ensure                     # 自动接管 / 打开并登录 Coremail（首选入口）
    python tabbit.py ensure --new               # 忽略已有标签，强制新开
    python tabbit.py tabs
    python tabbit.py resume <groupId> --task mail-attach
    python tabbit.py search "Clarification Required" [--task T] [--folder 已发送]
    python tabbit.py read-idx 3            [--task T]
    python tabbit.py read-key "Clarification Required" "Rosnah" "21:49"  [--task T]
    python tabbit.py finish                [--task T]
    python tabbit.py move <目标文件夹> --q "关键词" [--idx 0,3] [--apply]
    python tabbit.py guard some.js         # 只做静态扫描，不连浏览器

安全边界见 guards.py：所有 JS 执行前强制过检，删除类操作永不放行。
"""
import argparse
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import guards  # noqa: E402  安全边界：所有 JS 执行前强制过检
DEFAULT_TASK = os.environ.get("TABBIT_TASK", "mail-attach")
DEFAULT_URL = os.environ.get("COREMAIL_URL",
                             "https://wemail.webank.com/coremail/index.jsp?cus=1")
PREFIX = "TABBIT_PLAYWRIGHT_INSTANCE="


def launcher():
    env = os.environ.get("TABBIT_CLI")
    if env:
        return env
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""),
                            "Tabbit", "LocalAgent", "bin", "tabbit-cli.exe")
    return os.path.expanduser("~/.local/bin/tabbit-cli")


def _strip(raw):
    lines = raw.splitlines()
    if lines and lines[0].startswith(PREFIX):
        lines = lines[1:]
    return "\n".join(lines)


def run(args, stdin=b"", task=None):
    """执行任意 tabbit-cli 子命令，返回解析后的 JSON；解析失败返回原始文本。"""
    p = subprocess.run([launcher()] + args, capture_output=True, input=stdin)
    if p.returncode != 0 and not p.stdout.strip():
        sys.stderr.write(p.stderr.decode("utf-8", "replace") + "\n")
        return None
    text = _strip(p.stdout.decode("utf-8", "replace"))
    try:
        return json.loads(text)
    except Exception:
        return text


def run_node(code_or_path, task=None):
    """执行一段 Playwright JS（可直接传代码，或传 .js 路径）。

    注入变量：page / context / browser。
    返回值较大时自动走 resource 分页拼接。
    """
    task = task or DEFAULT_TASK
    if len(code_or_path) < 4096 and code_or_path.endswith(".js") \
            and os.path.exists(code_or_path):
        with io.open(code_or_path, "rb") as fh:
            stdin = fh.read()
    else:
        stdin = code_or_path.encode("utf-8")

    # 安全边界：任何 JS 在执行前强制过检，命中即阻断（见 guards.py）
    try:
        guards.assert_safe(stdin.decode("utf-8", "replace"))
    except guards.GuardError as e:
        sys.stderr.write("[BLOCKED] %s\n" % e)
        return {"blocked": True, "error": "guard-blocked"}

    # tabbit-cli ≥ 某版本起 nodejs 强制要求 --request-id（否则 REQUEST_FAILED）
    try:
        import uuid
        rid = "req-%s" % uuid.uuid4().hex[:12]
    except Exception:  # pragma: no cover
        rid = "req-%d" % int(time.time() * 1000)
    p = subprocess.run([launcher(), "nodejs", "--task", task,
                        "--request-id", rid],
                       capture_output=True, input=stdin)
    text = _strip(p.stdout.decode("utf-8", "replace"))
    if not text.strip():
        sys.stderr.write(p.stderr.decode("utf-8", "replace") + "\n")
        return None
    try:
        d = json.loads(text)
    except Exception:
        return text
    r = d.get("result", {})
    if isinstance(r, dict) and "resourceId" in r:
        parts, off = [], None
        while True:
            args = ["resource", "--task", task, "--resource", r["resourceId"]]
            if off:
                args += ["--offset", str(off)]
            dd = run(args)
            if not isinstance(dd, dict):
                break
            parts.append(dd.get("data", ""))
            if dd.get("eof", True) or not dd.get("nextOffset"):
                break
            off = dd["nextOffset"]
        try:
            return json.loads("".join(parts))
        except Exception:
            return "".join(parts)
    if isinstance(r, dict) and "value" in r:
        return r["value"]
    return r


def run_js_file(name, **subs):
    """读取 scripts 目录下的模板 JS 并做占位符替换后执行。"""
    path = os.path.join(HERE, name)
    code = io.open(path, encoding="utf-8").read()
    for k, v in subs.items():
        # 一律用 json.dumps 产出合法 JS 字面量：字符串自带引号并转义，数组/数字原样
        code = code.replace("__%s__" % k, json.dumps(v, ensure_ascii=False))
    return run_node(code, subs.get("TASK") or DEFAULT_TASK)


# ---------------------------------------------------------------- 高层操作

def search(query, task=None, folder=None, limit=60):
    """全文搜索，返回 [{i, text}] 列表。folder 可填 收件箱/已发送/草稿箱 做过滤。"""
    rows = run_js_file("mail_search.js", Q=query, TASK=task or DEFAULT_TASK)
    if not isinstance(rows, list):
        return rows
    if folder:
        rows = [r for r in rows if folder in r.get("text", "")]
    return rows[:limit]


def read_index(idx, task=None):
    return run_js_file("mail_read.js", MODE="index", IDX=int(idx),
                       Q="", KEYS=[], TASK=task or DEFAULT_TASK)


def read_key(query, keys, task=None):
    """搜索 query 后，定位同时包含 keys 中所有片段的那一封并读取。"""
    return run_js_file("mail_read.js", MODE="key", Q=query,
                       KEYS=list(keys), IDX=0, TASK=task or DEFAULT_TASK)


def attach(task=None):
    return run(["tabs", "--task", task or DEFAULT_TASK])


def resume(group, task=None):
    return run(["resume", "--task", task or DEFAULT_TASK, "--group", group])


def finish(task=None, discard=False):
    args = ["finish", "--task", task or DEFAULT_TASK]
    if discard:
        args.append("--discard")
    return run(args)


def move(to, query="", idx=None, apply=False, limit=20, task=None):
    """把检索到的邮件移动到目标文件夹。

    默认 dry-run，只返回待移动清单；必须 apply=True 才真正执行。
    目标文件夹命中 guards.MOVE_FOLDER_BLACKLIST 时直接拒绝（等同删除）。
    """
    ok, msg = guards.check_move_folder(to)
    if not ok:
        return {"blocked": True, "error": "guard-blocked", "reason": msg}
    idx = [int(i) for i in (idx or [])]
    if len(idx) > limit:
        return {"blocked": True, "error": "over-limit",
                "reason": "指定 %d 封，超过单次上限 %d，请分批" % (len(idx), limit)}
    return run_js_file("mail_move.js", Q=query, TO=to, IDX=idx,
                       APPLY=bool(apply), LIMIT=int(limit),
                       TASK=task or DEFAULT_TASK)


def ensure(task=None, url=DEFAULT_URL, force_new=False):
    """保证有一个已登录的 Coremail 页面可用。

    1. 先在现有标签里找 Coremail：有 group 就 resume，无 group 就 claim；
    2. 都没有（或 --new）就用 mail_bootstrap.js 新开一个页面：goto → 点登录 → 等就绪。

    返回 {mode, ok, task, ...}；mode ∈ resumed / claimed / bootstrapped / bootstrap-failed。
    **返回的 task 必须用于后续所有命令**（resume 时用的是 group.title）。
    """
    task = task or DEFAULT_TASK
    host = urlparse(url).netloc
    if not force_new:
        tabs = attach(task)
        hit = None
        for t in (tabs or {}).get("tabs", []) if isinstance(tabs, dict) else []:
            if host and host in (t.get("url") or ""):
                hit = t
                break
        if hit:
            grp = hit.get("group") or {}
            gid, name = grp.get("groupId"), (grp.get("title") or task)
            if gid:
                r = resume(gid, name)
                if isinstance(r, dict) and r.get("ownedPageCount", 0) >= 1:
                    # 接管后再确认登录态：登录页 / 会话过期时自动补点登录，但不跳转
                    chk = run_js_file("mail_bootstrap.js", URL=url, TASK=name, GOTO=False)
                    return {"mode": "resumed", "ok": bool(isinstance(chk, dict) and chk.get("ok")),
                            "task": name, "tabId": hit.get("tabId"), "detail": chk}
            r = run(["claim", "--task", task, "--tab", str(hit.get("tabId"))])
            if isinstance(r, dict) and not r.get("error"):
                chk = run_js_file("mail_bootstrap.js", URL=url, TASK=task, GOTO=False)
                return {"mode": "claimed", "ok": bool(isinstance(chk, dict) and chk.get("ok")),
                        "task": task, "tabId": hit.get("tabId"), "detail": chk}
            # claim 常因 TAB_OWNERSHIP_CONFLICT 失败 → 落到 bootstrap

    val = run_js_file("mail_bootstrap.js", URL=url, TASK=task, GOTO=True)
    ok = isinstance(val, dict) and val.get("ok")
    return {"mode": "bootstrapped" if ok else "bootstrap-failed",
            "ok": bool(ok), "task": task, "detail": val}


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="Tabbit CLI wrapper")
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--as-json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("tabs")
    p = sub.add_parser("resume"); p.add_argument("group")
    p = sub.add_parser("finish")
    p.add_argument("--discard", action="store_true", help="关闭本次会话创建的标签页")
    p = sub.add_parser("ensure", help="自动接管/打开并登录 Coremail")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--new", action="store_true", help="忽略已有标签，强制新开")
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--folder")
    p = sub.add_parser("read-idx"); p.add_argument("idx", type=int)
    p = sub.add_parser("read-key"); p.add_argument("query"); p.add_argument("keys", nargs="+")
    p = sub.add_parser("run"); p.add_argument("jsfile")
    p = sub.add_parser("move", help="移动邮件（默认 dry-run，必须加 --apply 才执行）")
    p.add_argument("to", help="目标文件夹名")
    p.add_argument("--q", default="", help="搜索词；留空则用当前列表")
    p.add_argument("--idx", default="", help="逗号分隔的行索引；留空则移动全部匹配行")
    p.add_argument("--apply", action="store_true", help="真正执行（不加则只预演）")
    p.add_argument("--limit", type=int, default=20, help="单次移动上限，默认 20")
    p = sub.add_parser("guard", help="扫描一段 JS 是否触碰安全边界")
    p.add_argument("jsfile", nargs="?", default="-")

    a = ap.parse_args()
    if a.cmd == "tabs":
        out = attach(a.task)
    elif a.cmd == "resume":
        out = resume(a.group, a.task)
    elif a.cmd == "finish":
        out = finish(a.task, a.discard)
    elif a.cmd == "ensure":
        out = ensure(a.task, a.url, a.new)
        if isinstance(out, dict) and out.get("task") and out["task"] != a.task:
            sys.stderr.write("[ensure] 后续命令请用 --task %s\n" % out["task"])
    elif a.cmd == "search":
        out = search(a.query, a.task, a.folder)
    elif a.cmd == "read-idx":
        out = read_index(a.idx, a.task)
    elif a.cmd == "read-key":
        out = read_key(a.query, a.keys, a.task)
    elif a.cmd == "run":
        out = run_node(a.jsfile, a.task)
    elif a.cmd == "move":
        idx = [int(x) for x in a.idx.split(",") if x.strip() != ""]
        out = move(a.to, a.q, idx, a.apply, a.limit, a.task)
        if isinstance(out, dict) and out.get("status") == "dry-run":
            sys.stderr.write("[move] 预演模式，未改动任何邮件。确认清单后重跑并加 --apply\n")
    elif a.cmd == "guard":
        blockers, needs = guards.scan(
            sys.stdin.read() if a.jsfile == "-"
            else io.open(a.jsfile, encoding="utf-8").read())
        if not blockers and not needs:
            print("SAFE: 未命中任何边界规则")
            return 0
        for n, r in blockers:
            print("DENY  %-16s %s" % (n, r))
        for n, r, e in needs:
            print("NEED  %-16s %s (设 %s=1 放行)" % (n, r, e))
        return 2
    else:
        out = None

    if a.as_json or isinstance(out, (list, dict)):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(out)


if __name__ == "__main__":
    main()
