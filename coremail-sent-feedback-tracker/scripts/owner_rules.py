# -*- coding: utf-8 -*-
"""
@提及 -> 负责人(Owner) 解析规则 + 答复状态判定

数据来源
--------
邮件正文里的 Coremail @提及是**纯文本**（如 `(@Puah)` / `— @lee @kath:` / `(@Wai Yee)`），
没有 href / title，邮箱地址要靠外部交叉验证得到。本文件的昵称表通过两种证据核对：

1. 邮件抬头（收件人 / 抄送）里的 `"Display Name"<addr>` 对照；
2. 正文称呼（greeting）与收件人列表的一一对应，例如
   `Requirement Confirmation of CED two sub-features` 称呼 `Dear JiaMaw&Kath&Thomas&Louise&Wai Yee`，
   收件人恰为 Lee Jia Maw / Hong Kar Yean / Thomas Ung / Puah Chei Fong / Low Wai Yee
   -> Kath = Hong Kar Yean (kyhong@hlbb.hongleong.com.my)
   -> Louise = Puah Chei Fong (cfpuah@hlbb.hongleong.com.my)

用法
----
    from owner_rules import owners_of, parse_who, owner_cell
"""
import re

# --------------------------------------------------------------------------
# 昵称 -> 人员（键一律小写；n/n_en 取自邮箱通讯录的登记名）
# --------------------------------------------------------------------------
MENTIONS = {
    "puah":      dict(n="Puah Chei Fong",           n_en="Puah Chei Fong",
                      e="cfpuah@hlbb.hongleong.com.my",        org="HLBB"),
    "louise":    dict(n="Puah Chei Fong",           n_en="Puah Chei Fong",
                      e="cfpuah@hlbb.hongleong.com.my",        org="HLBB"),
    "rosnah":    dict(n="Rosnah Ab Hamid",          n_en="Rosnah Ab Hamid",
                      e="rosnahabhamid@hlbb.hongleong.com.my", org="HLBB"),
    "lee":       dict(n="Lee Jia Maw",              n_en="Lee Jia Maw",
                      e="jmlee@hlbb.hongleong.com.my",         org="HLBB"),
    "jiamaw":    dict(n="Lee Jia Maw",              n_en="Lee Jia Maw",
                      e="jmlee@hlbb.hongleong.com.my",         org="HLBB"),
    "kath":      dict(n="Hong Kar Yean",            n_en="Hong Kar Yean",
                      e="kyhong@hlbb.hongleong.com.my",        org="HLBB"),
    "huiwen":    dict(n="Hoi Hui Wen",              n_en="Hoi Hui Wen",
                      e="hwhoi@hlbb.hongleong.com.my",         org="HLBB"),
    "hoi":       dict(n="Hoi Hui Wen",              n_en="Hoi Hui Wen",
                      e="hwhoi@hlbb.hongleong.com.my",         org="HLBB"),
    "elynn":     dict(n="Elynn Tan Yee Lin",        n_en="Elynn Tan Yee Lin",
                      e="tanyeelin@hlbb.hongleong.com.my",     org="HLBB"),
    "waiyee":    dict(n="Low Wai Yee",              n_en="Low Wai Yee",
                      e="wylow@hlbb.hongleong.com.my",         org="HLBB"),
    "wai yee":   dict(n="Low Wai Yee",              n_en="Low Wai Yee",
                      e="wylow@hlbb.hongleong.com.my",         org="HLBB"),
    "yc":        dict(n="Yap Yuet Cheng",           n_en="Yap Yuet Cheng",
                      e="yap.yuetcheng@hlbb.hongleong.com.my", org="HLBB"),
    "howard":    dict(n="Howard Tee Wei Heng",      n_en="Howard Tee Wei Heng",
                      e="howardtee@hlbb.hongleong.com.my",     org="HLBB"),
    "sundra":    dict(n="Sundra Lingam Selvarajoo", n_en="Sundra Lingam Selvarajoo",
                      e="sundralingam@hlbb.hongleong.com.my",  org="HLBB"),
    "leong":     dict(n="Leong Tjun Mun",           n_en="Leong Tjun Mun",
                      e="tmleong@hlbb.hongleong.com.my",       org="HLBB"),
    "thomas":    dict(n="Thomas Ung Yee Teck",      n_en="Thomas Ung Yee Teck",
                      e="thomasungyt@hlbb.hongleong.com.my",   org="HLBB"),
    "leonerdli": dict(n="leonerdli(李斌)",           n_en="leonerdli (Li Bin)",
                      e="leonerdli@webank.com",                org="WeBank"),
    # 非个人：CED 是部门团队，不作为单一负责人邮箱
    "ced":       dict(n="CED（团队）",               n_en="CED (team)",
                      e="",                                    org="HLBB"),
}

# 长键优先，避免 @Lee 吃掉 @Leong；末尾否定前瞻避免 @Lee 命中 @Leexxx
_KEYS = sorted(MENTIONS.keys(), key=lambda k: (-len(k), k))
_AT = re.compile(r"@(" + "|".join(re.escape(k) for k in _KEYS) + r")(?![A-Za-z0-9_])",
                 re.I)

_EMAIL = re.compile(r"[\w\.\-\+]+@[\w\.\-]+")


def owners_of(q_html, lang="zh"):
    """从问题文本里抽取 @负责人（去重、保持出现顺序）。"""
    txt = re.sub(r"<[^>]+>", " ", q_html or "")
    out, seen = [], set()
    for m in _AT.finditer(txt):
        key = m.group(1).lower()
        if key in seen:
            continue
        seen.add(key)
        d = MENTIONS[key]
        out.append(dict(
            raw=m.group(1),
            n=d["n_en"] if lang == "en" else d["n"],
            e=d["e"],
            org=d["org"],
            replied=False,
            when="",
        ))
    return out


def parse_who(who_html):
    """把 who 字段（`姓名<br>邮箱 / 姓名<br>邮箱`）拆成 [{n,e}]。"""
    if not who_html or who_html.strip() in ("—", "-", ""):
        return []
    res, cur = [], None
    for tok in re.split(r"<br\s*/?>|/", who_html):
        tok = tok.strip()
        if not tok:
            continue
        if "@" in tok:
            if cur is None:
                cur = dict(n="", e=tok)
            else:
                cur["e"] = tok
            res.append(cur)
            cur = None
        else:
            if cur is not None and not cur["e"]:
                cur["n"] = tok
            else:
                cur = dict(n=tok, e="")
    if cur and cur["e"]:
        res.append(cur)
    return [x for x in res if x["e"]]


def owners_with_status(q_html, who_html, when, lang="zh"):
    """返回 (owners, extra_repliers)。

    owners          —— @提及的应回复方，逐个标记是否已回复（按其邮箱是否出现在 who 里判定）
    extra_repliers  —— 实际回复了、但不在 @提及名单里的人
    """
    owners = owners_of(q_html, lang)
    replied_emails = {x["e"].lower() for x in parse_who(who_html)}
    for o in owners:
        if o["e"] and o["e"].lower() in replied_emails:
            o["replied"] = True
            o["when"] = when or ""
    known = {o["e"].lower() for o in owners if o["e"]}
    extra = [x for x in parse_who(who_html) if x["e"].lower() not in known]
    return owners, extra
