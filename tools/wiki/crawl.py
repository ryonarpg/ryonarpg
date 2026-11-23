#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 RyonaRPG 勝手にwiki（w.atwiki.jp/ryonarpgb）的全部页面与附件图片。

用法:
    python tools/wiki/crawl.py [--force] [--only 54,55] [--jobs 4]

产物:
    tools/cache/pages.json          页面清单 [{id, name, url}]
    tools/cache/html/{id}.html      原始 HTML
    tools/cache/img/{sha1}{ext}     附件图片（按内容哈希去重）
    tools/cache/images.json         图片清单 {url: {file, bytes, referer}}
    tools/cache/fetch.log           抓取日志

只依赖 Python 标准库，方便在任何机器上重跑。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "tools" / "cache"
HTML_DIR = CACHE / "html"
IMG_DIR = CACHE / "img"

BASE = "https://w.atwiki.jp/ryonarpgb"
LIST_URL = BASE + "/list"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

RETRY = 4
TIMEOUT = 40
DELAY = 0.35  # 抓取间隔，别把人家 wiki 打挂


def _log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with (CACHE / "fetch.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def fetch(url: str, referer: str = BASE + "/") -> bytes:
    """带重试的 GET，返回 bytes。"""
    last: Exception | None = None
    for attempt in range(1, RETRY + 1):
        try:
            req = urllib.request.Request(url, headers={**HEADERS, "Referer": referer})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (403, 404, 429, 500, 502, 503):
                time.sleep(1.2 * attempt)
                continue
            raise
        except Exception as exc:  # noqa: BLE001 - 网络抖动统一重试
            last = exc
            time.sleep(1.2 * attempt)
    raise RuntimeError(f"fetch failed: {url} ({last})")


def decode_html(raw: bytes) -> str:
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def normalize_url(u: str) -> str:
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return "https://w.atwiki.jp" + u
    return u


def collect_pages(force: bool = False) -> list[dict]:
    out_path = CACHE / "pages.json"
    if out_path.exists() and not force:
        pages = json.loads(out_path.read_text(encoding="utf-8"))
        if pages:
            _log(f"pages.json 已存在，共 {len(pages)} 页（--force 可重抓）")
            return pages

    pages: dict[int, dict] = {}
    pp = 1
    while True:
        url = f"{LIST_URL}?pp={pp}"
        body = decode_html(fetch(url))
        found = 0
        for m in re.finditer(
            r'href="//w\.atwiki\.jp/ryonarpgb/pages/(\d+)\.html"\s+title="([^"]*?)"',
            body,
        ):
            pid = int(m.group(1))
            title = re.sub(r"\s*\(\d+d\)\s*$", "", m.group(2)).strip()
            if pid not in pages:
                pages[pid] = {
                    "id": pid,
                    "name": title,
                    "url": f"{BASE}/pages/{pid}.html",
                }
                found += 1
        _log(f"list?pp={pp}: 新增 {found} 页，累计 {len(pages)}")
        if found == 0:
            break
        pp += 1
        if pp > 10:
            break
        time.sleep(DELAY)

    result = [pages[k] for k in sorted(pages)]
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def download_page(page: dict, force: bool = False) -> dict:
    dest = HTML_DIR / f"{page['id']}.html"
    if dest.exists() and not force and dest.stat().st_size > 2000:
        return {**page, "cached": True, "bytes": dest.stat().st_size}
    raw = fetch(page["url"])
    dest.write_bytes(raw)
    return {**page, "cached": False, "bytes": len(raw)}


IMG_RE = re.compile(
    r'(?:src|data-src)="((?:https?:)?//(?:img\.atwiki\.jp|w\.atwiki\.jp)/[^"]+?\.(?:png|jpe?g|gif|webp|bmp)[^"]*)"',
    re.IGNORECASE,
)


def scan_images() -> dict[str, dict]:
    img_map_path = CACHE / "images.json"
    img_map: dict[str, dict] = (
        json.loads(img_map_path.read_text(encoding="utf-8")) if img_map_path.exists() else {}
    )

    jobs: dict[str, str] = {}  # url -> 引用页
    for html_file in sorted(HTML_DIR.glob("*.html")):
        body = decode_html(html_file.read_bytes())
        for m in IMG_RE.finditer(body):
            u = normalize_url(m.group(1))
            u = urllib.parse.urljoin(BASE + "/", u)
            if u not in img_map:
                jobs[u] = f"{BASE}/pages/{html_file.stem}.html"

    _log(f"发现未缓存图片 {len(jobs)} 张")

    def grab(item: tuple[str, str]) -> tuple[str, dict | None]:
        url, referer = item
        try:
            data = fetch(url, referer=referer)
        except Exception as exc:  # noqa: BLE001
            _log(f"IMG FAIL {url} :: {exc}")
            return url, None
        h = hashlib.sha1(data).hexdigest()
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            ext = ".png"
        name = f"{h}{ext}"
        (IMG_DIR / name).write_bytes(data)
        return url, {"file": name, "bytes": len(data), "referer": referer}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(grab, it) for it in jobs.items()]
        for fut in as_completed(futures):
            url, meta = fut.result()
            if meta:
                img_map[url] = meta
        time.sleep(0)

    img_map_path.write_text(json.dumps(img_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return img_map


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略缓存重新抓取")
    ap.add_argument("--only", default="", help="只抓指定 id，逗号分隔")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args()

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    pages = collect_pages(force=args.force)
    if args.only:
        want = {int(x) for x in args.only.split(",") if x.strip()}
        pages = [p for p in pages if p["id"] in want]

    _log(f"开始下载 {len(pages)} 页，并发 {args.jobs}")
    failed: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(download_page, p, args.force): p for p in pages}
        done = 0
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                fut.result()
                done += 1
                if done % 20 == 0:
                    _log(f"进度 {done}/{len(pages)}")
            except Exception as exc:  # noqa: BLE001
                failed.append({**p, "error": str(exc)})
                _log(f"FAIL {p['name']} ({p['id']}) :: {exc}")

    _log(f"页面完成 {len(pages) - len(failed)}/{len(pages)}，失败 {len(failed)}")
    if failed:
        (CACHE / "failed.json").write_text(
            json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if not args.no_images:
        scan_images()
    _log("done")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
