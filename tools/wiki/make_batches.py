#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把待翻译页面切成批次，供 workflow 分发给子代理。

产物: tools/cache/batches.json   [{ids:[...], cat, bytes}]
      tools/cache/batch_args.json {"batches": [[...]]}
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "tools" / "cache"
MD = CACHE / "md"

MAX_BYTES = 15000
MAX_PAGES = 6


def main() -> None:
    gloss = json.loads((ROOT / "jpwiki" / "glossary.json").read_text(encoding="utf-8"))
    status = json.loads((ROOT / "jpwiki" / "status.json").read_text(encoding="utf-8"))["pages"]

    todo: list[tuple[str, str, int]] = []
    for cat, items in gloss["groups"].items():
        for it in items:
            pid = str(it["id"])
            if status.get(pid) == "zh":
                continue
            f = MD / f"{pid}.md"
            if not f.exists():
                continue
            todo.append((pid, cat, f.stat().st_size))

    batches: list[dict] = []
    cur: list[str] = []
    cur_bytes = 0
    cur_cat = ""

    def flush() -> None:
        nonlocal cur, cur_bytes, cur_cat
        if cur:
            batches.append({"ids": cur, "cat": cur_cat, "bytes": cur_bytes})
        cur, cur_bytes = [], 0

    for pid, cat, size in todo:
        if cur and (cur_bytes + size > MAX_BYTES or len(cur) >= MAX_PAGES or cat != cur_cat):
            flush()
        cur.append(pid)
        cur_bytes += size
        cur_cat = cat
    flush()

    (CACHE / "batches.json").write_text(json.dumps(batches, ensure_ascii=False, indent=1), encoding="utf-8")
    (CACHE / "batch_args.json").write_text(
        json.dumps({"batches": [b["ids"] for b in batches]}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"pages={sum(len(b['ids']) for b in batches)} batches={len(batches)}")
    for b in batches:
        print(f"  {b['cat']:<6s} {b['bytes']:>6d}B  {','.join(b['ids'])}")


if __name__ == "__main__":
    main()
