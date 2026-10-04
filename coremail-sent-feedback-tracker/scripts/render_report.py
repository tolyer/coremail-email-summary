#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data.json 渲染成单文件 HTML 报告（浅色主题 / 大字号 / 筛选 / hover 高亮）。

用法：
    python render_report.py data.json -o 输出.html --title "标题" \
        --meta "说明 HTML" --filter 邮件标题 \
        --card "12|提出的问题" --card "6|客户回复" \
        --source "<div class='src'><div class='s'>主题</div><div class='d'>说明</div></div>"

- data.json 是 list[dict]，键顺序即列顺序（第一版用 __HEADS__ 指定时以 heads 为准）。
- 单元格内容允许内嵌 HTML（<b>、<br>、<span class="tag t-ok">已确认</span>）。
- 单元格值若精确等于 已确认/部分回复/转交他人/未回复 等会自动渲染成彩色状态标签。
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "report_template.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--title", default="邮件问题与回复汇总")
    ap.add_argument("--meta", default="")
    ap.add_argument("--filter", dest="filter_key", default="")
    ap.add_argument("--heads", default="", help="英文逗号分隔，不填则用 data.json 首条记录的键")
    ap.add_argument("--card", action="append", default=[], help="格式 数值|标签，可重复")
    ap.add_argument("--source", action="append", default=[], help="一段 .src 的 HTML，可重复")
    a = ap.parse_args()

    rows = json.loads(io.open(a.data, encoding="utf-8").read())
    if not isinstance(rows, list) or not rows:
        sys.exit("data.json 必须是非空的 list[dict]")
    heads = [h.strip() for h in a.heads.split(",") if h.strip()] or list(rows[0].keys())

    cards = ""
    if a.card:
        items = []
        for c in a.card:
            n, _, label = c.partition("|")
            items.append('<div class="card"><div class="n">%s</div><div class="l">%s</div></div>'
                         % (n.strip(), label.strip()))
        cards = '<div class="cards">%s</div>' % "".join(items)

    sources = ""
    if a.source:
        inner = "".join('<div class="src">%s</div>' % s for s in a.source)
        sources = '<div class="panel"><h2>覆盖的邮件</h2>%s</div>' % inner

    tpl = io.open(TPL, encoding="utf-8").read()
    html = (tpl
            .replace("__TITLE__", a.title)
            .replace("__META__", a.meta)
            .replace("__CARDS__", cards)
            .replace("__SOURCES__", sources)
            .replace("__HEADS__", json.dumps(heads, ensure_ascii=False))
            .replace("__ROWS__", json.dumps(rows, ensure_ascii=False))
            .replace("__FILTER_KEY__", json.dumps(a.filter_key or "", ensure_ascii=False)))

    with io.open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("written:", a.out, "| rows:", len(rows), "| size:", len(html))


if __name__ == "__main__":
    main()
