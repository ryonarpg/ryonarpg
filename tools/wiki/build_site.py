#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把抓取/转换结果装配成 docsify 的汉化路由 jpwiki/。

  - 复制附件图片到 jpwiki/images/
  - 为还没翻译的页面生成"日文原文"占位页（带提示条），保证路由完整
  - 生成 jpwiki/_sidebar.md、jpwiki/glossary.md
  - 生成 jpwiki/status.json（汉化进度）

已翻译页面（含 <!-- status: zh -->）不会被覆盖。

用法:
    python tools/wiki/build_site.py [--force-fallback]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "tools" / "cache"
SITE = ROOT / "jpwiki"
PAGES = SITE / "pages"
IMAGES = SITE / "images"

GROUP_ICON = {
    "开始": "🚩",
    "游戏系统": "⚙️",
    "数据库": "📚",
    "城镇·迷宫": "🗺️",
    "角色": "🧝",
    "制作与资料": "🛠️",
    "其他作品": "🎮",
}

NOTICE_JA = (
    "> ⚠️ **本页尚未汉化**，以下为日文原文，供对照阅读。\n"
    "> 参与翻译请见 [汉化说明](/jpwiki/about.md)。\n"
)


def load_glossary() -> dict:
    return json.loads((SITE / "glossary.json").read_text(encoding="utf-8"))


def copy_images() -> int:
    src = CACHE / "img"
    if not src.exists():
        return 0
    IMAGES.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in src.iterdir():
        if f.is_file():
            dst = IMAGES / f.name
            if not dst.exists() or dst.stat().st_size != f.stat().st_size:
                shutil.copy2(f, dst)
            n += 1
    return n


def body_of(md: str) -> str:
    """去掉转换器写的标题/原文行，只留正文。"""
    lines = md.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].startswith("# "):
        i += 1
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith(">")):
        i += 1
    return "\n".join(lines[i:]).strip()


def fallback_page(pid: str, zh: str, ja: str, url: str, cache_md: Path) -> str:
    body = body_of(cache_md.read_text(encoding="utf-8")) if cache_md.exists() else ""
    return (
        f"<!-- status: ja -->\n# {zh}\n\n"
        f"> 原文：[{ja}]({url}) ｜ 译自 RyonaRPG 勝手にwiki\n\n"
        f"{NOTICE_JA}\n{body}\n"
    )


def build_pages(gloss: dict, force_fallback: bool) -> dict:
    pages_dir = PAGES
    pages_dir.mkdir(parents=True, exist_ok=True)
    status: dict[str, str] = {}
    for pid, zh in gloss["pages"].items():
        out = pages_dir / f"{pid}.md"
        if out.exists() and not force_fallback:
            head = out.read_text(encoding="utf-8")[:200]
            status[pid] = "zh" if "status: zh" in head else "ja"
            continue
        if out.exists() and "status: zh" in out.read_text(encoding="utf-8")[:200]:
            status[pid] = "zh"
            continue
        cache_md = CACHE / "md" / f"{pid}.md"
        if not cache_md.exists():
            continue
        head = cache_md.read_text(encoding="utf-8")[:400]
        m = re.search(r"^# (.+)$", head, re.M)
        ja = m.group(1).strip() if m else zh
        url = f"https://w.atwiki.jp/ryonarpgb/pages/{pid}.html"
        out.write_text(fallback_page(pid, zh, ja, url, cache_md), encoding="utf-8", newline="\n")
        status[pid] = "ja"
    return status


def build_sidebar(gloss: dict, status: dict) -> None:
    lines = ["- [🏠 汉化版首页](/jpwiki/)", "- [📖 术语表](/jpwiki/glossary.md)", "- [ℹ️ 汉化说明](/jpwiki/about.md)", ""]
    for cat, items in gloss["groups"].items():
        lines.append(f"- **{GROUP_ICON.get(cat, '📁')} {cat}**")
        for it in items:
            pid = str(it["id"])
            mark = "" if status.get(pid) == "zh" else " <small>日</small>"
            href = "/jpwiki/" if pid == "1" else f"/jpwiki/pages/{pid}.md"
            lines.append(f"  - [{it['zh']}]({href}){mark}")
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    (SITE / "_sidebar.md").write_text(text, encoding="utf-8", newline="\n")
    # docsify 默认按当前目录找 _sidebar.md；pages/ 下再放一份，保证所有页面都能取到
    (PAGES / "_sidebar.md").write_text(text, encoding="utf-8", newline="\n")
    navbar = SITE / "_navbar.md"
    if navbar.exists():
        (PAGES / "_navbar.md").write_text(navbar.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


def build_glossary_page(gloss: dict) -> None:
    terms = gloss["terms"]
    rows = [
        "| 日文 | 中文 | 日文 | 中文 |",
        "| --- | --- | --- | --- |",
    ]
    items = sorted(terms.items(), key=lambda kv: kv[0])
    half = (len(items) + 1) // 2
    left, right = items[:half], items[half:]
    for i in range(half):
        ja1, zh1 = left[i]
        ja2, zh2 = right[i] if i < len(right) else ("", "")
        rows.append(f"| {ja1} | {zh1} | {ja2} | {zh2} |")

    pages = gloss["pages"]
    title_rows = ["| ID | 日文原名 | 中文译名 |", "| --- | --- | --- |"]
    import json as _json

    names = {str(p["id"]): p["name"] for p in _json.loads((CACHE / "pages.json").read_text(encoding="utf-8"))}
    for pid in sorted(pages, key=lambda x: int(x)):
        title_rows.append(f"| {pid} | {names.get(pid, '')} | {pages[pid]} |")

    md = (
        "# 术语表\n\n"
        "> 汉化统一用语。正文翻译遇到下列术语时必须采用对应译名。\n"
        "> 本表由 `tools/wiki/glossary_seed.py` 生成，欢迎 PR 补充。\n\n"
        "## 核心术语\n\n" + "\n".join(rows) + "\n\n"
        "## 页面标题对照\n\n" + "\n".join(title_rows) + "\n"
    )
    (SITE / "glossary.md").write_text(md, encoding="utf-8", newline="\n")


def update_progress(zh: int, total: int) -> None:
    """把汉化进度写进 README 的占位区（没有占位区就跳过）。"""
    readme = SITE / "README.md"
    if not readme.exists() or total == 0:
        return
    text = readme.read_text(encoding="utf-8")
    pct = zh / total * 100
    block = (
        "<!-- progress:start -->\n"
        f"**汉化进度：{zh} / {total} 页（{pct:.0f}%）** —— "
        "未完成的页面会显示提示条并保留日文原文。\n"
        "<!-- progress:end -->"
    )
    new = re.sub(r"<!-- progress:start -->.*?<!-- progress:end -->", block, text, flags=re.S)
    if new != text:
        readme.write_text(new, encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-fallback", action="store_true")
    args = ap.parse_args()

    gloss = load_glossary()
    n_img = copy_images()
    status = build_pages(gloss, args.force_fallback)
    build_sidebar(gloss, status)
    build_glossary_page(gloss)

    zh = sum(1 for v in status.values() if v == "zh")
    ja = sum(1 for v in status.values() if v == "ja")
    update_progress(zh, len(status))
    (SITE / "status.json").write_text(
        json.dumps({"total": len(status), "zh": zh, "ja": ja, "pages": {
                       pid: status[pid] for pid in sorted(status, key=int)}},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"images={n_img} pages={len(status)} zh={zh} ja={ja}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
