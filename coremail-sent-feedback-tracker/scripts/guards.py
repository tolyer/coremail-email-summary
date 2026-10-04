#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全边界：对即将交给浏览器执行的 JS 做静态扫描，拦截危险操作。

两级规则：

  DENY    永不放行（删除邮件 / 清空 / 清空回收站 / 清登录态 / 改账号设置…）
          这类操作即使设置环境变量也不会放行——用户明确要求禁止。
  CONFIRM 默认拒绝，必须显式设置对应环境变量才放行
          （发送/回复/转发、下载附件、点击正文链接、关闭标签页…）

由 tabbit.py 的 run_node() 强制执行，所有 JS（含技能自带模板）都要过这一关。
只有直接修改本文件才能绕过——本文件即策略的唯一真相源。

也可单独用：
    python guards.py some.js          # 扫描一个文件
    cat some.js | python guards.py -  # 扫描 stdin
"""
import io
import os
import re
import sys

LEVEL_DENY = "DENY"
LEVEL_CONFIRM = "CONFIRM"

# ---------------------------------------------------------------- 规则表
# (level, name, 需要放行的环境变量 or None, [正则...])

DENY_DELETE = [
    r"deleteMessage", r"DeleteMessage",
    r"permanentDelete", r"PermanentDelete",
    r"clearTrash", r"ClearTrash", r"emptyTrash", r"EmptyTrash",
    r"removeMessage", r"RemoveMessage", r"destroyMessage",
    r"\btrash\b", r"\bTrash\b",
    r"清空", r"彻底删除", r"永久删除", r"删除邮件", r"删除会话",
    r"deleteAll", r"DeleteAll",
    r"""page\.keyboard\.press\(\s*['"]Delete['"]""",
    # 兜底：任何形式的「删除 / delete」一律拦下（含按钮文案 text=删除）。
    # 采用 fail-closed 策略——宁可误拦，不可漏放。
    r"删除", r"\bdelete\b", r"\bDelete\b", r"\bDELETE\b",
]

DENY_SESSION = [
    r"clearCookies", r"localStorage\.clear", r"sessionStorage\.clear",
    r"context\.clearPermissions",
]

DENY_SETTINGS = [
    r"自动转发", r"autoForward", r"AutoForward",
    r"修改密码", r"账号设置", r"签名设置",
    r"\bpop3\b", r"\bPOP3\b", r"\bimap\b", r"\bIMAP\b",
]

# 凭据：登录靠浏览器自动填充，脚本不得读取/回显任何密码或 Cookie
DENY_CRED = [
    r"input#password", r"#fakePassword", r"#uid\b",
    r"""type\s*=\s*['"]password['"]""", r"type\s*==\s*['\"]password['\"]",
    r"document\.cookie", r"\bpasswd\b", r"\bpassword\b",
]

# 外泄：禁止在页面里发起任何外部请求或注入外部脚本
DENY_EXFIL = [
    r"\bfetch\s*\(", r"XMLHttpRequest", r"WebSocket",
    r"page\.request\s*\.", r"context\.request\s*\.",
    r"addScriptTag", r"addStyleTag", r"addInitScript",
    r"navigator\.sendBeacon",
]

# 动态执行：字符串代码无法静态审计，一律禁止
DENY_EVAL = [
    r"\beval\s*\(", r"new\s+Function\s*\(",
    r"setTimeout\s*\(\s*['\"]", r"setInterval\s*\(\s*['\"]",
]

CONFIRM_SEND = [
    r"SendMessage", r"sendMail", r"MessageCompose", r"compose\s*\(",
    r"ReplyMessage", r"ForwardMessage", r"\.reply\s*\(", r"\.forward\s*\(",
    r"['\"]发送['\"]", r"['\"]回复['\"]", r"['\"]转发['\"]",
    r"['\"]写信['\"]", r"['\"]新建邮件['\"]",
]

CONFIRM_ATTACH = [
    r"\bdownload\b", r"\bDownload\b",
    r"attachment", r"Attachment", r"附件",
]

CONFIRM_CLOSE = [
    r"page\.close\s*\(", r"context\.close\s*\(", r"browser\.close\s*\(",
]

# 状态改写：不动邮件本身，但会改变收件箱视图 / 影响他人可见状态
CONFIRM_MUTATE = [
    r"标记已读", r"标记未读", r"设为已读", r"设为未读",
    r"markRead", r"markUnread", r"markAsRead",
    r"星标", r"加星", r"红旗",
    r"垃圾邮件", r"举报", r"\bspam\b", r"\bSpam\b",
    r"新建标签", r"添加标签", r"移动标签",
]

RULES = [
    (LEVEL_DENY, "DELETE_MAIL", None, DENY_DELETE,
     "禁止删除任何邮件，也不允许清空/彻底删除/清空回收站"),
    (LEVEL_DENY, "WIPE_SESSION", None, DENY_SESSION,
     "禁止清除 Cookies / 本地存储（会清掉已保存的登录态，需人工重登）"),
    (LEVEL_DENY, "CHANGE_ACCOUNT", None, DENY_SETTINGS,
     "禁止改动账号设置（自动转发、密码、签名、POP3/IMAP）"),
    (LEVEL_DENY, "READ_CREDENTIAL", None, DENY_CRED,
     "禁止读取/回显任何凭据（密码框、Cookie）——登录靠浏览器自动填充"),
    (LEVEL_DENY, "EXFILTRATE", None, DENY_EXFIL,
     "禁止在页面内发起外部网络请求或注入外部脚本（防邮件内容外泄）"),
    (LEVEL_DENY, "DYNAMIC_EVAL", None, DENY_EVAL,
     "禁止动态执行字符串代码（无法静态审计）"),
    (LEVEL_CONFIRM, "SEND_MAIL", "TABBIT_ALLOW_SEND", CONFIRM_SEND,
     "外发动作不可逆，需用户明确确认后设 TABBIT_ALLOW_SEND=1"),
    (LEVEL_CONFIRM, "ATTACHMENT", "TABBIT_ALLOW_ATTACH", CONFIRM_ATTACH,
     "附件可能来自外部发件人，需用户确认后设 TABBIT_ALLOW_ATTACH=1"),
    (LEVEL_CONFIRM, "CLOSE_PAGE", "TABBIT_ALLOW_CLOSE", CONFIRM_CLOSE,
     "关闭标签页会影响用户当前浏览，需确认后设 TABBIT_ALLOW_CLOSE=1"),
    (LEVEL_CONFIRM, "MUTATE_STATE", "TABBIT_ALLOW_MUTATE", CONFIRM_MUTATE,
     "改已读/星标/标签/垃圾邮件会改变邮箱状态，需确认后设 TABBIT_ALLOW_MUTATE=1"),
    (LEVEL_CONFIRM, "CLICK_BODY_LINK", "TABBIT_ALLOW_LINK", [],
     "点击邮件正文链接有钓鱼风险，需确认后设 TABBIT_ALLOW_LINK=1"),
]

# 邮件移动的目标文件夹黑名单——移进去等于变相删除
MOVE_FOLDER_BLACKLIST = [
    "垃圾箱", "废件箱", "已删除", "已删除邮件", "删除",
    "trash", "deleted items", "deleted", "bin",
]


class GuardError(Exception):
    def __init__(self, blockers, needs):
        self.blockers = blockers
        self.needs = needs
        msg = ["安全边界拦截，未执行任何操作。"]
        for b in blockers:
            msg.append("  [DENY] %s: %s" % (b[0], b[1]))
        for n in needs:
            msg.append("  [NEED] %s: %s → 需设 %s=1" % (n[0], n[1], n[2]))
        super(GuardError, self).__init__("\n".join(msg))


def strip_comments(code):
    """去掉行首 // 注释与 /* */ 块注释，避免说明文字误触发规则。

    只处理「行首（允许空白）」的 // ，不会误伤 URL 里的 https://。
    """
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    code = re.sub(r"(?m)^\s*//.*$", "", code)
    return code


def clicks_body_link(code):
    return bool(re.search(r"a\[href", code)) and bool(re.search(r"\.click\s*\(", code))


def scan(code, env=None):
    """扫描 JS，返回 (blockers, needs)。

    blockers: [(name, reason)]  —— 永不放行
    needs:    [(name, reason, envvar)] —— 可通过设环境变量放行
    """
    env = os.environ if env is None else env
    body = strip_comments(code)
    blockers, needs = [], []
    for level, name, envvar, patterns, reason in RULES:
        hit = False
        if name == "CLICK_BODY_LINK":
            hit = clicks_body_link(body)
        else:
            for p in patterns:
                if re.search(p, body):
                    hit = True
                    break
        if not hit:
            continue
        if level == LEVEL_DENY:
            blockers.append((name, reason))
        elif not (envvar and env.get(envvar) == "1"):
            needs.append((name, reason, envvar))
    return blockers, needs


def assert_safe(code, env=None):
    blockers, needs = scan(code, env)
    if blockers or needs:
        raise GuardError(blockers, needs)
    return True


def check_move_folder(folder):
    """校验邮件移动的目标文件夹。返回 (ok, msg)。"""
    low = (folder or "").strip().lower()
    if not low:
        return False, "目标文件夹为空"
    for bad in MOVE_FOLDER_BLACKLIST:
        if bad.lower() in low:
            return False, "目标文件夹 %r 命中黑名单（等同删除），已拒绝" % folder
    return True, "ok"


def main():
    args = sys.argv[1:]
    if not args:
        sys.stderr.write(__doc__ + "\n")
        return 0
    if args[0] == "-":
        code = sys.stdin.read()
    else:
        code = io.open(args[0], encoding="utf-8").read()
    blockers, needs = scan(code)
    if not blockers and not needs:
        print("SAFE: 未命中任何边界规则")
        return 0
    for n, r in blockers:
        print("DENY  %-16s %s" % (n, r))
    for n, r, e in needs:
        print("NEED  %-16s %s (设 %s=1 放行)" % (n, r, e))
    return 2


if __name__ == "__main__":
    sys.exit(main())
