#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 atwiki 的页面 HTML 转成干净的 Markdown（日文原文稿）。

产物: tools/cache/md/{id}.md
这些是"待翻译"的日文底稿，翻译后的成稿写到 jpwiki/pages/{id}.md。

用法:
    python tools/wiki/convert.py [--only 54,55]
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import urllib.parse
from pathlib import Path

from lxml import html as LH

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "tools" / "cache"
HTML_DIR = CACHE / "html"
MD_DIR = CACHE / "md"

ATWIKI = "https://w.atwiki.jp/ryonarpgb"

DROP_TAGS = (
    "script", "style", "noscript", "form", "input", "button", "select",
    "textarea", "iframe", "link", "meta",
)
DROP_CLASS_HINTS = (
    "plugin_contents",          # 目录插件
    "atwiki_plugin_recent",     # 更新履歴
    "atwiki-page-tags",         # 页面标签
    "atwiki_plugin_comment",    # 评论插件
    "atwiki_plugin_like",
    "atwiki_plugin_share",
    "atwiki_plugin_pagetitle",
    "atwiki_plugin_tag",
    "atwiki_plugin_counter",
    "counter",
)
COMMENT_IDS = {"id_ca80e710"}
COMMENT_TEXTS = {"コメント", "一言コメント"}


# ---------------------------------------------------------------- utilities
def norm_ws(s: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", s).strip()


def T(s: str | None) -> str:
    """清洗文本节点：去掉源码里的排版换行（<br> 产生的换行不受影响）。"""
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]*\n[ \t]*", "", s)


def cell_text_escape(s: str) -> str:
    return s.replace("|", "\\|").strip()


def load_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def unescape_name(s: str) -> str:
    return html_mod.unescape(s)


class Converter:
    def __init__(self, pages: list[dict], images: dict[str, dict], glossary: dict):
        self.pages = pages
        self.images = images
        self.glossary = glossary
        self.by_id = {str(p["id"]): p for p in pages}
        self.by_name: dict[str, dict] = {}
        for p in pages:
            name = unescape_name(p["name"])
            self.by_name[name] = p
            self.by_name[urllib.parse.quote(name)] = p
        self.title_zh = {str(k): v for k, v in (glossary.get("pages") or {}).items()}
        self.exclude = {str(x) for x in (glossary.get("meta", {}).get("exclude") or [])}

    # ------------------------------------------------------------ links
    def page_link(self, href: str, label: str) -> str | None:
        href = (href or "").strip()
        label = norm_ws(label) or href
        if not href or href.startswith("#"):
            return None
        if href.startswith(("http://", "https://", "//w.atwiki.jp", "/ryonarpgb", "/")):
            m = re.search(r"/pages/(\d+)\.html", href)
            if m and m.group(1) in self.by_id:
                if m.group(1) in self.exclude:
                    return f"[{label}（日文原文）](https://w.atwiki.jp/ryonarpgb/pages/{m.group(1)}.html)"
                return f"[{label}](./{m.group(1)}.md)"
            m = re.search(r"[?&]page=([^&]+)", href)
            if m:
                name = urllib.parse.unquote(m.group(1))
                target = self.by_name.get(name)
                if target:
                    if str(target["id"]) in self.exclude:
                        return f"[{label}（日文原文）]({target['url']})"
                    return f"[{label}](./{target['id']}.md)"
                return None  # 指向不存在的页面（红链）→ 退化成纯文本
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://w.atwiki.jp" + href
            return f"[{label}]({href})"
        return f"[{label}]({href})"

    def image_src(self, src: str) -> str:
        src = (src or "").strip()
        if src.startswith("//"):
            src = "https:" + src
        src = urllib.parse.urljoin(ATWIKI + "/", src)
        meta = self.images.get(src)
        if meta:
            return f"../images/{meta['file']}"
        return src


# ------------------------------------------------------------------ 预处理
def preprocess(body) -> None:
    """删掉 atwiki 的界面插件、评论表单，并把折叠区摊平。"""
    for c in body.xpath(".//comment()"):
        if c.getparent() is not None:
            c.getparent().remove(c)

    # 折叠区：<table class="atwiki_plugin_region"> 的第三个 td 才是正文
    guard = 0
    while guard < 50:
        guard += 1
        regions = [
            t for t in body.xpath('.//table[contains(@class,"atwiki_plugin_region")]')
            if "atwiki_plugin_region_button" not in (t.get("class") or "")
        ]
        if not regions:
            break
        for tbl in regions:
            rows = tbl.xpath("./tr | ./tbody/tr")
            cells = rows[0].xpath("./td | ./th") if rows else []
            tds = [
                td for td in cells
                if "button" not in (td.get("class") or "")
                and "label" not in (td.get("class") or "")
            ]
            if not tds:
                tbl.getparent().remove(tbl)
                continue
            src = tds[-1]
            tbl.getparent().replace(tbl, src)
            src.tag = "div"
            src.attrib.pop("class", None)

    # 界面插件 / 表单
    for el in list(body.iter()):
        if not isinstance(el.tag, str):
            continue
        cls = el.get("class") or ""
        if any(h in cls for h in DROP_CLASS_HINTS) and el.getparent() is not None:
            el.drop_tree()
    for tag in DROP_TAGS:
        for el in body.xpath(f".//{tag}"):
            if el.getparent() is not None:
                el.drop_tree()


def strip_tail_sections(body) -> None:
    """删掉评论区以及它后面的所有兄弟节点（页面尾部）。"""
    targets = []
    for el in body.xpath(".//*[self::h2 or self::h3 or self::h4 or self::h5]"):
        if el.get("id") in COMMENT_IDS:
            targets.append(el)
        elif norm_ws(el.text_content()) in COMMENT_TEXTS:
            targets.append(el)
    for el in targets:
        parent = el.getparent()
        if parent is None:
            continue
        remove = False
        for child in list(parent):
            if child is el:
                remove = True
            if remove:
                parent.remove(child)


# ------------------------------------------------------------------ walker
def initial_state() -> dict:
    return {"in_cell": False}


def inner_text(node, conv: Converter, state: dict) -> str:
    parts = [T(node.text)]
    for child in node:
        if isinstance(child.tag, str) and child.tag == "br":
            parts.append("\n")
        else:
            parts.append(inner_text(child, conv, state))
        parts.append(T(child.tail))
    return "".join(parts)


def walk(node, conv: Converter, state: dict) -> str:
    tag = node.tag
    if not isinstance(tag, str):
        return ""

    if tag == "br":
        return "<br>" if state["in_cell"] else "\n"
    if tag == "hr":
        return "\n\n---\n\n"
    if tag in ("h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = norm_ws(inner_text(node, conv, state))
        return f"\n\n{'#' * level} {text}\n\n" if text else ""
    if tag == "pre":
        text = node.text_content().replace("\r\n", "\n").strip("\n")
        if not text.strip():
            return ""
        if "\n" not in text and text.lstrip().startswith("*"):
            return ""  # atwiki 的 *見出し 语法残渣
        return f"\n\n```\n{text}\n```\n\n"
    if tag == "table":
        return "\n\n" + render_table(node, conv, state) + "\n\n"
    if tag in ("ul", "ol"):
        return render_list(node, conv, state, ordered=(tag == "ol"))
    if tag in ("p", "div", "section", "article", "blockquote", "center", "td", "th"):
        parts = [T(node.text)]
        for child in node:
            parts.append(walk(child, conv, state))
            parts.append(T(child.tail))
        inner = "".join(parts).strip()
        if not inner:
            return ""
        if state["in_cell"]:
            return inner
        if tag == "blockquote":
            inner = "\n".join("> " + ln if ln.strip() else ln for ln in inner.splitlines())
        return f"\n\n{inner}\n\n"
    if tag == "a":
        label = norm_ws(inner_text(node, conv, state))
        link = conv.page_link(node.get("href") or "", label)
        return link if link else label
    if tag == "img":
        src = node.get("src") or node.get("data-src") or ""
        if not src:
            return ""
        return f"![{node.get('alt') or ''}]({conv.image_src(src)})"
    if tag in ("strong", "b"):
        inner = "".join(walk(c, conv, state) for c in node).strip()
        return f"**{inner}**" if inner else ""
    if tag in ("em", "i"):
        inner = "".join(walk(c, conv, state) for c in node).strip()
        return f"*{inner}*" if inner else ""
    if tag == "code":
        inner = "".join(walk(c, conv, state) for c in node)
        return f"`{inner}`" if inner else ""
    if tag == "span":
        inner = "".join(walk(c, conv, state) for c in node)
        m = re.search(r"color\s*:\s*([#\w(),. ]+)", (node.get("style") or "").lower())
        if m and inner.strip():
            return f'<span style="color:{m.group(1).strip()}">{inner}</span>'
        return inner
    if tag == "font":
        inner = "".join(walk(c, conv, state) for c in node)
        color = node.get("color")
        return f'<span style="color:{color}">{inner}</span>' if color and inner.strip() else inner
    if tag == "s":
        inner = "".join(walk(c, conv, state) for c in node).strip()
        return f"~~{inner}~~" if inner else ""

    parts = [T(node.text)]
    for child in node:
        parts.append(walk(child, conv, state))
        parts.append(T(child.tail))
    return "".join(parts)


def render_list(node, conv: Converter, state: dict, ordered: bool) -> str:
    lines: list[str] = []
    idx = 0
    for li in node:
        if not isinstance(li.tag, str) or li.tag != "li":
            continue
        idx += 1
        marker = f"{idx}. " if ordered else "- "
        buf = [T(li.text)]
        for child in li:
            if isinstance(child.tag, str) and child.tag in ("ul", "ol"):
                continue
            buf.append(walk(child, conv, state))
            buf.append(T(child.tail))
        text = "".join(buf).strip()
        text = re.sub(r"\n{2,}", "\n", text)
        if state["in_cell"]:
            text = text.replace("\n", "<br>")
        else:
            text = text.replace("\n", "\n  ")
        lines.append(marker + text)
        for child in li:
            if isinstance(child.tag, str) and child.tag in ("ul", "ol"):
                lines.append(render_list(child, conv, state, ordered=(child.tag == "ol")))
    if state["in_cell"]:
        return "<br>".join(x for x in lines if x.strip())
    return "\n\n" + "\n".join(lines) + "\n\n"


# ------------------------------------------------------------------ tables
def table_grid(table) -> list[list]:
    rows: list[list] = []
    pending: dict[int, tuple[int, object]] = {}
    for tr in table.xpath("./tr | ./thead/tr | ./tbody/tr | ./tfoot/tr"):
        cells = tr.xpath("./th | ./td")
        if not cells:
            continue
        row: list = []
        used = [False] * len(cells)

        def flush_pending(row=row, used=None):
            nonlocal col
            while col in pending:
                remain, val = pending[col]
                row.append(val)
                if remain <= 1:
                    del pending[col]
                else:
                    pending[col] = (remain - 1, val)
                col += 1

        col = 0
        for i, cell in enumerate(cells):
            if used[i]:
                continue
            flush_pending()
            used[i] = True
            rowspan = int(cell.get("rowspan") or 1)
            colspan = int(cell.get("colspan") or 1)
            row.append(("__CELL__", cell))
            col += 1
            for _ in range(1, colspan):
                row.append(("__CELL__", None))
                col += 1
            if rowspan > 1:
                pending[col - 1] = (rowspan - 1, ("__CELL__", cell))
        flush_pending()
        rows.append(row)

    width = max((len(r) for r in rows), default=0)
    for r in rows:
        r.extend([("__CELL__", None)] * (width - len(r)))
    return rows


def render_table(table, conv: Converter, state: dict) -> str:
    grid = table_grid(table)
    if not grid:
        return ""
    cell_state = {**state, "in_cell": True}

    def render_cell(spec) -> str:
        if not isinstance(spec, tuple):
            return cell_text_escape(str(spec))
        cell = spec[1]
        if cell is None:
            return ""
        parts = [T(cell.text)]
        for c in cell:
            parts.append(walk(c, conv, cell_state))
            parts.append(T(c.tail))
        content = "".join(parts)
        content = re.sub(r"(<br>\s*){3,}", "<br><br>", content)
        return cell_text_escape(content)

    rendered = [[render_cell(c) for c in row] for row in grid]
    header = rendered[0]
    body = rendered[1:]
    if not any(h.strip() for h in header):
        header = [" "] * len(header)
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join([" --- "] * len(header)) + "|"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# ------------------------------------------------------------------- main
def convert_page(pid: str, conv: Converter, page: dict) -> str:
    raw = (HTML_DIR / f"{pid}.html").read_bytes()
    text = raw.decode("utf-8", "replace")  # libxml2 的 charset 探测对 atwiki 不可靠
    doc = LH.fromstring(text)
    bodies = doc.xpath('//*[@id="wikibody"]')
    if not bodies:
        return ""
    body = bodies[0]

    title_ja = page["name"]
    first_h2 = body.xpath("./h2[1]")
    if first_h2:
        title_ja = norm_ws(first_h2[0].text_content()) or title_ja
        first_h2[0].getparent().remove(first_h2[0])

    preprocess(body)
    strip_tail_sections(body)

    md = walk(body, conv, initial_state())
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"[ \t]+<br>", "<br>", md)
    md = re.sub(r"\n{3,}", "\n\n", md)

    lines = [ln.rstrip() for ln in md.splitlines()]
    cleaned: list[str] = []
    for ln in lines:
        if ln.strip() in ("", "<br>", "<br><br>"):
            if cleaned and cleaned[-1] == "":
                continue
            cleaned.append("")
        else:
            cleaned.append(ln)
    md = "\n".join(cleaned).strip()

    zh = conv.title_zh.get(pid) or title_ja
    header = (
        f"# {zh}\n\n"
        f"> 原文：[{title_ja}]({page['url']}) ｜ 译自 RyonaRPG 勝手にwiki\n\n"
    )
    return header + md + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    MD_DIR.mkdir(parents=True, exist_ok=True)
    pages = load_json(CACHE / "pages.json", [])
    images = load_json(CACHE / "images.json", {})
    glossary = load_json(ROOT / "jpwiki" / "glossary.json", {})
    conv = Converter(pages, images, glossary)

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    todo = [p for p in pages if not only or str(p["id"]) in only]

    ok = 0
    for p in todo:
        pid = str(p["id"])
        if not (HTML_DIR / f"{pid}.html").exists():
            continue
        md = convert_page(pid, conv, p)
        if md.strip():
            (MD_DIR / f"{pid}.md").write_text(md, encoding="utf-8")
            ok += 1
    print(f"converted {ok}/{len(todo)} pages -> {MD_DIR}")
    sizes = sorted(((f.stat().st_size, f.stem) for f in MD_DIR.glob("*.md")), reverse=True)
    print(f"total {sum(s for s, _ in sizes)/1024:.0f} KiB; top: {[(i, round(s/1024,1)) for s,i in sizes[:8]]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
