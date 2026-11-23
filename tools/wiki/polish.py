#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对 jpwiki/pages/*.md 做统一的排版收尾（幂等）：
  - 标题后补空行
  - 连续空行压缩
  - 行尾空白清理
  - 文件末尾补换行
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "jpwiki" / "pages"


def polish(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    for i, ln in enumerate(lines):
        ln = ln.rstrip()
        out.append(ln)
        # H1 之后紧跟非空行 -> 插入空行
        if i + 1 < len(lines) and re.match(r"^# .+", ln):
            nxt = lines[i + 1].strip()
            if nxt and not nxt.startswith("#"):
                out.append("")
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def main() -> int:
    n = 0
    for f in sorted(PAGES.glob("*.md")):
        if f.name.startswith("_"):
            continue
        src = f.read_text(encoding="utf-8")
        dst = polish(src)
        if dst != src:
            f.write_text(dst, encoding="utf-8")
            n += 1
    print(f"polished {n} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
