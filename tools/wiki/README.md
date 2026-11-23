# tools/wiki —— 汉化流水线

把 `https://w.atwiki.jp/ryonarpgb/` 抓下来、转成 Markdown、装配成 docsify 路由 `jpwiki/`。
只依赖 Python 标准库 + lxml。

```
抓取          转换            术语表           装配            自检
crawl.py  →  convert.py  →  glossary_seed.py → build_site.py → check.py
   ↓             ↓                                  ↓
tools/cache/  tools/cache/md/                   jpwiki/
```

## 1. 抓取

```bash
python tools/wiki/crawl.py            # 全部页面 + 附件图片
python tools/wiki/crawl.py --only 54  # 只抓某页
python tools/wiki/crawl.py --force    # 忽略缓存重抓
```

产物（`tools/cache/`，已 gitignore）：

- `pages.json` —— 页面清单 `{id, name, url}`
- `html/{id}.html` —— 原始 HTML
- `img/` —— 附件图片（按内容哈希去重）
- `images.json` —— 图片 URL → 本地文件映射

抓取带 4 并发与重试；atwiki 会拒绝没有浏览器 UA 的请求，脚本已带。

## 2. 转换

```bash
python tools/wiki/convert.py
```

把 atwiki 的页面 HTML 转成干净 Markdown，产物 `tools/cache/md/{id}.md`（日文底稿）。
处理了：目录插件、折叠区（`atwiki_plugin_region`）、评论表单、页面标签、
`rowspan/colspan` 表格、`?page=` 红链（退化为纯文本）、附件图片本地化。

被排除的系统页/旧版本页（见 `glossary.json` 的 `meta.exclude`）会转成指向 atwiki 的外链，
避免路由里出现空页。

## 3. 术语表

```bash
python tools/wiki/glossary_seed.py
```

写入 `jpwiki/glossary.json`：

- `pages`：`{id: 中文标题}`，166 个游戏相关页面
- `groups`：侧边栏分组
- `terms`：核心术语 `{日文: 中文}`，正文翻译必须遵守
- `meta.exclude`：不进入汉化路由的 atwiki 页面 id

## 4. 装配

```bash
python tools/wiki/build_site.py
```

- 复制图片到 `jpwiki/images/`
- 未翻译的页面生成带提示条的日文占位页
- 生成 `jpwiki/_sidebar.md`、`jpwiki/pages/_sidebar.md`
- 生成 `jpwiki/glossary.md`
- 更新 `jpwiki/status.json` 与首页的汉化进度

## 5. 自检

```bash
python tools/wiki/check.py
```

检查内部链接是否指向不存在的页面、图片是否缺失、`status:` 标记是否存在，并输出分组进度。

## 6. 排版收尾

```bash
python tools/wiki/polish.py
```

标题后补空行、压缩连续空行、清理行尾空白（幂等）。

## 7. 批量翻译

```bash
python tools/wiki/make_batches.py
```

按分组与体积（单批 ≤15KB、≤6 页）切批，产出 `tools/cache/batches.json`，
再用并行子代理逐批翻译。每批的提示词约定见 `jpwiki/about.md`。

## 页面状态

`jpwiki/pages/{id}.md` 首行：

- `<!-- status: zh -->` 已汉化
- `<!-- status: ja -->` 占位，正文为日文原文
