#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""剥离邮件正文里的引用历史，只保留本轮新增内容。

用法：
    python strip_quote.py reply.json            # 读取 tabbit.py read-key 的输出
    python strip_quote.py reply.json 4000      # 额外限制输出长度
也可 import：from strip_quote import clean
"""
import io
import json
import re
import sys

# Outlook / Gmail / Coremail 常见的引用起始标记
MARKERS = [
    r"On[\s\S]{0,120}?wrote\s*:",
    r"-{3,}\s*Original Message\s*-{3,}",
    r"-{3,}\s*原始邮件\s*-{3,}",
    r"_{10,}",
    r"From\s*:\s*[\s\S]{0,80}?\nSent\s*:",
    r"发件人\s*:\s*[\s\S]{0,80}?\n发送时间\s*:",
]


def clean(body, min_pos=60):
    """返回剥离引用后的正文。"""
    if not body:
        return ""
    b = body.replace("\xa0", " ").replace("\r\n", "\n")
    cuts = []
    for pat in MARKERS:
        for m in re.finditer(pat, b, re.I):
            if m.start() > min_pos:
                cuts.append(m.start())
    end = min(cuts) if cuts else len(b)
    return b[:end].strip()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    raw = io.open(sys.argv[1], encoding="utf-8").read()
    try:
        obj = json.loads(raw)
        body = obj.get("body", raw) if isinstance(obj, dict) else raw
    except Exception:
        body = raw
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    out = clean(body)
    print(out[:limit] if limit else out)


if __name__ == "__main__":
    main()
