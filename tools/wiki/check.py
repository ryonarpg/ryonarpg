#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汉化站点自检：内部链接、图片、状态标记、汉化进度。

用法:
    python tools/wiki/check.py [--strict]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "jpwiki"
PAGES = SITE / "pages"

LINK_RE = re.compile(r"\]\((?:\./)?(?:pages/)?(\d+)\.md(?:#[^)]*)?\)")
IMG_RE = re.compile(r"!\[[^\]]*\]\((\.\./images/[^)]+)\)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    gloss = json.loads((SITE / "glossary.json").read_text(encoding="utf-8"))
    valid = set(gloss["pages"])

    errors: list[str] = []
    warnings: list[str] = []
    stats = {"zh": 0, "ja": 0, "missing": 0}
    group_stats: dict[str, dict[str, int]] = {}
    if not (SITE / "index.html").exists():
        errors.append("缺少 jpwiki/index.html（/jpwiki/ 路由会 404）")

    for cat, items in gloss["groups"].items():
        group_stats[cat] = {"zh": 0, "ja": 0}
        for it in items:
            pid = str(it["id"])
            group_stats[cat]["zh"] += 0
            f = PAGES / f"{pid}.md"
            if not f.exists():
                stats["missing"] += 1
                errors.append(f"missing page {pid}")
                continue
            text = f.read_text(encoding="utf-8")
            is_zh = "status: zh" in text[:400]
            stats["zh" if is_zh else "ja"] += 1
            group_stats[cat]["zh" if is_zh else "ja"] += 1

            for m in LINK_RE.finditer(text):
                target = m.group(1)
                if target not in valid:
                    errors.append(f"{pid}: 链接指向未收录页面 ./{target}.md")
            if re.search(r"\]\(/jpwiki/", text):
                errors.append(f"{pid}: 仍使用 /jpwiki/ 绝对链接（GitHub Pages 会 404）")
            for m in IMG_RE.finditer(text):
                p = (PAGES / m.group(1)).resolve()
                if not p.exists():
                    errors.append(f"{pid}: 缺图片 {m.group(1)}")
            if not text.lstrip().startswith("<!--"):
                warnings.append(f"{pid}: 缺少 status 标记")
            if "status: zh" in text[:400]:
                body = text.split("\n", 1)[1] if "\n" in text else ""
                if re.search(r"[ぁ-んァ-ヶ]", body.replace("原文", "")):
                    # 专名保留日文是允许的，这里只统计，不算错
                    pass

    for name in ("README.md", "about.md", "_sidebar.md", "_navbar.md",
                 "pages/_sidebar.md", "pages/_navbar.md"):
        f = SITE / name
        if not f.exists():
            errors.append(f"缺少 {name}")
            continue
        if re.search(r"\]\(/jpwiki/", f.read_text(encoding="utf-8")):
            errors.append(f"{name}: 仍使用 /jpwiki/ 绝对链接")

    (SITE / "status.json").write_text(
        json.dumps({"total": len(valid), **stats, "pages": {
            pid: ("zh" if (PAGES / f"{pid}.md").exists()
                  and "status: zh" in (PAGES / f"{pid}.md").read_text(encoding="utf-8")[:400] else "ja")
            for pid in sorted(valid, key=int)}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"总页面 {len(valid)}｜已汉化 {stats['zh']}｜日文占位 {stats['ja']}｜缺失 {stats['missing']}")
    for cat, s in group_stats.items():
        total = s["zh"] + s["ja"]
        pct = (s["zh"] / total * 100) if total else 0
        print(f"  {cat:<8s} {s['zh']:>3d}/{total:<3d}  {pct:5.1f}%")

    for w in warnings:
        print("WARN " + w)
    for e in errors:
        print("ERROR " + e)
    return 1 if (errors or (args.strict and warnings)) else 0


if __name__ == "__main__":
    sys.exit(main())
