# 人读交付物规范

机器真相源仍是 `lead-research/candidates.jsonl`。人读交付物由 `scripts/render_delivery.py` **从 jsonl 渲染生成**，禁止手写另起炉灶改列名或章节顺序。

## 输出文件（按 `output.format`）

| `output.format` | 生成文件 |
|---|---|
| `markdown` | `lead-research/delivery.md` |
| `html` | `lead-research/delivery.html` |
| `both`（默认） | 上述两个都生成 |

单文件自包含：HTML 内嵌样式，不依赖外链 CSS。

## 固定章节顺序

1. **标题与元信息** — 任务名/产品（来自 `leads.yaml` `company`）、生成时间、配置摘要一行
2. **简报** — 若存在则嵌入 `lead-research/brief.md` 正文。HTML 中由 `brief_md_to_html()` 转成真实标签（`#`/`##` → `h3`/`h4`，列表、段落、管道表格、`**粗体**`、`` `代码` ``），**不要**用 `<pre>` 原样倾倒——否则 `##`、`**`、`|` 等标记会裸露在交付物里。Markdown 版（`delivery.md`）保留原文即可
3. **主名单** — `disposition=main`，按 `priority` 升序，缺省按 `score` 降序
4. **备选池** — `disposition=backup`，同上排序
5. **排除清单** — `competitor` / `unreachable` / `excluded`，表列含 `exclusion_reason`
6. **论据附录** — 仅主名单（及可选备选）：逐家展开四类留痕，不得省略 URL

## 主名单 / 备选池表头（固定，勿增删列）

| # | Company | Country | Segment | Score | Risk | Contact | Match reason | Website |

- `Contact`：按 `output.contact_preference` 取第一条可用联系方式，格式 `channel: value (confidence)`；无则 `—`
- `Website`：有则链接，无则 `—`
- `Score`：保留两位小数

## 排除清单表头（固定）

| # | Company | Country | Disposition | Reason | Sources |

## 论据附录每家必备块

1. **供需** — `segment_evidence[]`：signal / observation / source
2. **背调** — `due_diligence_summary` + `due_diligence_checks[]`
3. **打分** — `score` + `score_breakdown` 五项 value/basis
4. **联系方式** — `contacts[]`；空数组时写明「无公开联系方式」并引用 reachability finding

## 渲染命令

先校验数据，渲染，再校验渲染结果（工作目录为任务目录）：

```bash
python3 <skill安装目录>/scripts/validate_candidates.py lead-research/candidates.jsonl --config leads.yaml
python3 <skill安装目录>/scripts/render_delivery.py lead-research/candidates.jsonl \
  --config leads.yaml \
  --brief lead-research/brief.md \
  --out-dir lead-research
python3 <skill安装目录>/scripts/validate_delivery.py lead-research/delivery.html \
  --candidates lead-research/candidates.jsonl
# Windows 若无 python3：改用 python
```

`--format` 可覆盖配置中的 `output.format`。缺省读 `leads.yaml`，再缺省则为 `both`。

`validate_delivery.py` 退出码 0 = 通过；1 = 有致命问题（逐条列出，含行号）；2 = 文件不存在。它检查的是**渲染结果**，与 `validate_candidates.py`（检查数据）互补，两个都要过。`--candidates` 会逐条核对主/备选表格的 Contact 列是否等于该记录自己的第一条邮箱。

## 交付物可能被宿主回写

在带实时预览的宿主里打开 `delivery.html`，预览面板可能把元素追踪属性（如 `data-page-node-id`）**持久化回磁盘文件**——文件体积会翻倍，且不再与一次干净渲染逐字节一致。

- 不影响浏览与渲染，但**发出前请重跑一次渲染**拿干净副本。
- `validate_delivery.py` 检测到这类属性会给出 warning（不判失败）。
- 排查「渲染结果对不上」时，先剥离 `data-page-node-id` 再比对，否则会被这几千个属性淹没。

## 渲染约束（改动 CSS 前先读）

交付物正文以中文为主，表格列多（主名单 9 列）。以下三条是踩过的坑，改动时别回退：

1. **`lang` 要跟着内容走** — `render_html()` 按标题是否含中日韩字符决定 `lang="zh-CN"` / `"en"`。写死 `en` 会让中文按英文字形与断行规则处理。中文字体要显式入栈（`Songti SC` / `Noto Serif CJK SC` / `PingFang SC`），否则落回系统默认。
2. **单元格用 `overflow-wrap: break-word`，不要用 `anywhere`** — `anywhere` 会参与 min-content 宽度计算，把单元格最小宽度压到 1 个字符，列被挤成竖排表头（`COUNTRY` 渲染成 `CO UN TR Y`）。**例外**：`exclusions` 表的 Sources 列是整段无空格 URL，只有 `anywhere` 才能把它纳入最小宽度计算，否则单个长 URL 会把整张表撑出容器——该列单独放开。
3. **宽表靠 `.table-wrap { overflow-x: auto }` 横向滚动，不要靠压缩列宽** — 配合 `table.leads { min-width: 62rem }` / `table.exclusions { min-width: 46rem }` 与关键列 `min-width`。打印时必须在 `@media print` 里把 `min-width` 全部归零，否则右侧列会被纸张裁掉。

改完 CSS 先跑 `validate_delivery.py`（前两条与 Brief 那条都能被它自动抓到），再至少目视验一次：桌面 1440px、窄屏 430px、以及 `--print-to-pdf` 导出的 PDF（检查表格右侧列没被裁）。布局类问题（列被挤成竖排、长 URL 撑出容器）只有看渲染结果才看得出来，自动校验覆盖不到。
