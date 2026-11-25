# 汉化说明

本路由 `/jpwiki/` 是对 [RyonaRPG 勝手にwiki](https://w.atwiki.jp/ryonarpgb/) 的简体中文翻译，属于**非官方粉丝汉化**。原 wiki 的文字、图片版权归原作者与 atwiki 用户社区所有；本页只做语言转换并保留原文链接。

## 翻译约定

1. **忠于原文**：只做语言转换，不增删攻略结论；不确定的地方保留日文并加 `（原文：…）`。
2. **术语统一**：人名、地名、系统术语以 [术语表](/jpwiki/glossary.md) 为准，不得自行创造第二种译法。
3. **专名对齐**：道具、装备、技能等游戏内专名优先采用当前汉化版译名；[道具 ID 表](/jpwiki/pages/161.md)保留日文原名，方便与调试工具对照。未收录于汉化版的敌人/道具专名可保留日文原名。
4. **结构不变**：标题层级、表格、链接（`./NNN.md` 指向同站页面）、图片、`<br>` 换行保持原样。
5. **标注来源**：每页顶部保留 `原文：[日文标题](atwiki 链接)`。

## 目录结构

```
jpwiki/
├─ README.md            汉化版首页
├─ _sidebar.md          侧边栏（由脚本生成）
├─ glossary.json        页面标题 + 术语表（译名唯一来源）
├─ glossary.md          术语表（由脚本生成）
├─ pages/{id}.md        各页面，id 与 atwiki 的 pages/{id}.html 对应
└─ images/              原 wiki 的附件图片
```

页面文件开头有状态标记：

- `<!-- status: zh -->`：已汉化
- `<!-- status: ja -->`：尚未汉化，正文为日文原文

## 工具链

都在 `tools/wiki/`，只依赖 Python 标准库 + lxml：

```bash
# 1. 抓取全部页面与图片（结果缓存在 tools/cache/）
python tools/wiki/crawl.py

# 2. HTML -> 日文 Markdown 底稿（tools/cache/md/）
python tools/wiki/convert.py

# 3. 生成/更新术语表
python tools/wiki/glossary_seed.py

# 4. 装配站点：补占位页、生成侧边栏与术语表页
python tools/wiki/build_site.py

# 5. 检查链接与汉化进度
python tools/wiki/check.py
```

`tools/cache/` 体积较大，已在 `.gitignore` 中忽略；重新克隆后按上面顺序跑一遍即可重建。

## 参与翻译

1. 打开任意 `jpwiki/pages/{id}.md`，把开头的 `status: ja` 改成 `status: zh`；
2. 按上面的约定把正文译成中文，保留行内链接与表格；
3. 新增术语先补 `tools/wiki/glossary_seed.py` 里的 `TERMS`，再跑 `glossary_seed.py` 与 `build_site.py`，保证全站一致；
4. 提交 PR。

## 与简中主站的关系

`/jpwiki/` 只是新增路由，主站（`/`）的原创攻略不受影响。两边内容可以互相引用：主站已有[主线攻略](/tips/mainQuest.md)、[地图篇](/map/index.md)等原创内容。

## 致谢

- 原 wiki 的所有执笔者与 atwiki 社区；
- 翻译流程参考了 [GalTransl](https://github.com/XD2333/GalTransl) 的「GPT 字典 / 术语表先行」思路，以及 [GalTransl-GalGameReverse-Skill](https://github.com/GalTransl/GalTransl-GalGameReverse-Skill) 的 skill 组织方式。
