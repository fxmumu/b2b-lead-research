---
name: b2b-lead-research
version: "1.4.3"
display_name: 客户开发
display_name_en: Lead Research
description: Research, qualify, and verify B2B potential customers/leads for a product or service, producing a prioritized, sourced contact list with due-diligence notes and outreach drafts. Use when the user asks to 找客户、获客、外贸获客、开发客户、找潜在客户、客户名单、客户背调、开发信、找经销商/采购商/EPC/买家，or "find leads / lead list / find potential customers / lead generation / customer acquisition / find buyers". Reads a user-maintained config at leads.yaml in the working directory.
description_zh: 供方找需方：为外贸企业研究、筛选并背调潜在买家，产出可溯源、打分排序的客户名单与开发信草稿。
description_en: "For export businesses: research, qualify, and vet potential buyers on the demand side, excluding same-category competitors, and deliver a sourced, scored lead list with outreach drafts."
---

# B2B Lead Research

## 核心概念：供方找需方

本 skill 站在**供给侧（供方）**视角：用户是卖方，任务是找到**需方**（真正采购该产品的公司）。判定细则与信号表见 [references/segmentation.md](references/segmentation.md) §1.5；边界情形（下游分销商虽也卖货，但是采购后再卖 → 属需方）以采购关系为准，不以「是否销售」为准。

## 执行顺序

0. 配置与目标确认
1. 拆解搜索计划
2. 线索发现（含去重）
3. 资格筛选与可触达性过滤（不打分）
4. 潜在客户背调（硬闸门）
5. 联系方式获取与验证
6. 打分排序与名单定稿
7. 汇总交付

## Step 0: 配置与目标确认

先读工作目录下的 `leads.yaml`（相对当前会话工作目录，不在 skill 目录内）。它定义产品、供货能力、ICP、目标市场、打分权重和输出参数。

- 文件不存在时：把 **skill 安装目录**下的 `config/leads.yaml.example` 复制为工作目录的 `leads.yaml`，然后向用户索要关键字段，不要臆造。skill 安装目录即本 skill 所在文件夹（含 `SKILL.md` 的那一层）。`config/`、`references/`、`scripts/` 相对 skill 安装目录；`leads.yaml` 与 `lead-research/` 相对工作目录。
- 文件存在但关键字段为空时：先向用户索要，不要臆造。

**开跑前必须向用户确认**（逐项列出后等确认再进 Step 1）：

1. 配置摘要：产品/服务、目标客户类型、目标市场与地区权重、`top_n` / `backup_n`
2. 供需口径：复述「供方卖什么 → 要找谁买」；请用户补充已知同行或排除词（写入 `market.exclude_keywords`）
3. 搜索计划：来源类别与查询语言
4. 约束：`exclude_keywords`、可触达性过滤、`min_score`
5. 交付物：主名单 + 备选池 + 排除清单；是否生成开发信草稿
6. 开发信署名信息（仅当 `output.include_outreach_drafts: true`）：`company.name_zh` / `name_en` / `website` / `contact_email` / `contact_phone` / `address` 与 `supply.lead_time_days`。这些是开发信署名的必需项，缺失则草稿只能留占位符；用户暂无法提供时明确标注为待补，并在 Step 7 生成草稿前再确认一次

确认后写入 `lead-research/brief.md`（含 `leads.yaml` 修改时间作基线）。用户改了字段先落盘 `leads.yaml` 再继续。

**续跑快速路径**：若 `lead-research/brief.md` 已存在，且 `leads.yaml` 的修改时间不晚于 brief 的基线，则跳过上述逐项确认，只复述配置摘要并请用户确认一次即可进 Step 1。进度以落盘为准（见下节）。

**references 按需读取**：进入某一步时再读该步对应的那一篇，不必开跑前通读全部。只有 `references/sources.md`（查询模板）建议在 Step 1 一并看。

## 中间产物与断点续跑

全量任务跨会话，必须增量落盘。工作目录下维护：

- `lead-research/brief.md` — Step 0 确认过的任务简报
- `lead-research/candidates.jsonl` — **唯一真相源**；每家一条 JSON（schema 见 [assets/lead-schema.json](assets/lead-schema.json)）
- `lead-research/outreach/` — 开发信草稿（可选）

每完成一家的一个阶段，立即更新该条记录的 `stage` / `disposition` 及相关字段，不要攒到最后。

**落盘方式**：直接增改 `candidates.jsonl` 的行——一行一条 JSON，用文件写入工具追加新行或改写对应行即可。

- **不要生成中间脚本**（如 `_deepen.py`）去 load → patch → rewrite。它把同一份数据以源码形式重写一遍，既慢又容易引入字段名/枚举错误；jsonl 本身已是唯一真相源，无需再加一层。
- **先校准再批量**：第一条记录（或第一家跑完 Step 3–5）写完后，**立即**跑一次 `validate_candidates.py`，确认字段名与枚举无误，再按批推进。schema 理解偏差越早暴露越省事，不要等到全部跑完才校验。
- 需要批量改同一字段时，同样先改一条 → 校验通过 → 再对其余记录照做。

**阶段与去向**（字段权威定义在 schema）：

| `stage` | 含义 | 完成后应具备 |
|---|---|---|
| `discovered` | 已发现 | company, country, sources；可选 website、初步 segment |
| `screened` | 已筛选 | segment（需方）、segment_evidence、体量估算；或已标排除类 disposition |
| `diligenced` | 已背调 | risk_level、due_diligence_* |
| `verified` | 已验联系方式 | contacts（可为空数组并注明无公开邮箱） |
| `scored` | 已打分定稿 | 完整四类论据 + score；disposition ∈ {main, backup} |

| `disposition` | 含义 | 是否占 `backup_n` |
|---|---|---|
| `pending` | 仍在流水线 | — |
| `main` | 主名单 | — |
| `backup` | 有分次优备选 | 是 |
| `competitor` | 供给侧/同行 | 否（进排除清单） |
| `unreachable` | 无可触达通道 | 否（进排除清单） |
| `excluded` | 高风险、制裁、ICP 不符、供需待确认等 | 否（进排除清单） |

恢复任务：读 `candidates.jsonl`，按 `stage` 只补下一阶段；`disposition` 已为排除类的不再推进。配置以工作目录 `leads.yaml` 为准；相对 `brief.md` 基线有变更时向用户确认。进度以落盘为准。

每写完一批（4–5 家，且第一条写完后先单独跑一次）后运行：

```bash
python3 <skill安装目录>/scripts/validate_candidates.py lead-research/candidates.jsonl
# Windows 若无 python3：python <skill安装目录>/scripts/validate_candidates.py ...
```

校验失败则先修记录再继续。

## 批量与节流

逐家深挖（Step 3–5）是全程最贵的一段（实测量级：每家的 5 项背调 + 联系方式约需 5 个独立信源、十余次溯源引用）。按批推进，不要一家一家串行：

- **每批 4–5 家**。同一批内按「信源类别」并发取页（官网/About、媒体与新闻、LinkedIn、注册库/行业目录），而不是「先把 A 家全部查完，再开始 B 家」。
- **同一页面只读一次**。一个信源类别命中即止；不重复检索同一信息，不为「再确认一下」反复搜同一关键词。
- **每批结束落盘一次并跑校验**，再进下一批。
- **明确止损**：拿不到的信息（如无公开邮箱）按 [references/verification.md](references/verification.md) 的止损规则记录现状并推进，不无限扩大检索。

## Step 1: 拆解搜索计划

```bash
python3 <skill安装目录>/scripts/detect_backend.py
# Windows 若无 python3：改用 python
```

- 清楚宿主时显式传 `--host`（如 `claude-code`、`codex`、`cursor`、`zcode`、`workbuddy`）；不确定可省略。
- 严格按返回的 capability map 行动，不假设工具名。`backend: none` 按其 `note` 降级。
- 若宿主未被识别、`search` / `web_read` 被判为 `backend: none`，但当前 agent 实际具备内置搜索/读页工具，则优先使用内置工具，不要直接退回 curl/Jina；可用 `--host` 显式声明宿主，或补 `capabilities/<host>.json`。
- 仅在需要时加 `--doctor` / `--check-linkedin`。

按产品、ICP、目标市场生成并行查询；至少覆盖行业目录/展商、政府备案、项目新闻反查、官网与 LinkedIn。查询必须偏向需求侧（谁在买/用/装机/分销），与 buyer-side 词根组合，见 [references/sources.md](references/sources.md)。

## Step 2: 线索发现

并行搜索，写入候选（`stage: discovered`，`disposition: pending`）：公司名、国家、官网、初步客户类型、来源 URL。

**去重**：域名为主键（去 `www.`、小写）；无官网用公司名小写去空格。已存在则只合并 `sources`，不新建。

候选池 ≥ (`market.top_n` + `market.backup_n`) × 1.5（向下取整）。`backup_n` 越大，发现与筛选成本线性上升——按实际需要设置，不追求凑满；确实找不到更多时如实少出，不靠降低筛选标准凑数。LinkedIn 人员搜索按 capability map 的 `linkedin` 项执行。

## Step 3: 资格筛选与可触达性过滤（不打分）

按「批量与节流」分批推进。用 [references/segmentation.md](references/segmentation.md)：

1. **供给侧硬闸门**：同品类同环节 → `disposition: competitor`，填 `exclusion_reason` 与 `segment_evidence`，`stage: screened`，**不打分、不占 backup_n**
2. 归类 `segment`（标准键名）、对照 ICP；不符 → `disposition: excluded`
3. 估算年采购额（写入 `estimated_annual_procurement_usd`）
4. **廉价可触达过滤**：至少有一个潜在通道（contact 页/表单、LinkedIn 公司页、公开 info 邮箱）；皆无 → `disposition: unreachable`，不做 Step 4

通过者：`stage: screened`，`disposition: pending`。**本步不算四项得分**（`accessibility` 公式依赖 Step 5 的验证结果）。

## Step 4: 潜在客户背调（硬闸门）

用 [references/due-diligence.md](references/due-diligence.md)。输出 `risk_level`、`due_diligence_summary`、`due_diligence_checks`。

- 制裁名单命中，或真实性/经营状态查无实据且无法确认存在 → `disposition: excluded`（保留 jsonl 审计，不进交付主表/备选）
- 其他 `high` → `disposition: excluded`，`exclusion_reason` 注明「高风险，不建议触达」
- `medium` / `low` → `stage: diligenced`，继续

## Step 5: 联系方式获取与验证

用 [references/verification.md](references/verification.md)。邮箱优先；每条附 `source` + `confidence`；无公开邮箱写明，绝不猜测。完成后 `stage: verified`。

## Step 6: 打分排序与名单定稿

仅对 `disposition: pending` 且 `stage: verified`（或已 diligenced+verified）的候选，按 `scoring.weights` 与 [references/segmentation.md](references/segmentation.md) 公式计算总分，写入 `score` + `score_breakdown`（必须可复算）。

**交付语义**：

- **主名单** (`disposition: main`)：`risk_level != high`、达到 `min_score`、总分最高的前 `top_n`；不足则如实少出，不凑数
- **备选池** (`disposition: backup`)：主名单之外、**有完整得分**的次高 `backup_n` 家（含未达 `min_score` 的）；不足 `backup_n` 时同样如实少出，不凑数
- **排除清单**：所有 `competitor` / `unreachable` / `excluded`，单独汇报，**不计入 `backup_n`**

全部定稿后将入选者 `stage` 设为 `scored`。**`main` / `backup` 在通过校验前不得交付**：必须跑 `validate_candidates.py`，失败则补齐论据后再交付。

## Step 7: 汇总交付

1. 跑校验：`validate_candidates.py`（交付态论据必须通过）
2. 按 [references/delivery.md](references/delivery.md) 用渲染脚本生成人读交付物（**禁止手写另起结构**）：

```bash
python3 <skill安装目录>/scripts/render_delivery.py lead-research/candidates.jsonl \
  --config leads.yaml \
  --brief lead-research/brief.md \
  --out-dir lead-research
```

- `output.format`: `markdown` → `lead-research/delivery.md`；`html` → `delivery.html`；`both`（默认）两个都生成
- 章节与表头固定见 delivery.md；机器真相源仍是 `candidates.jsonl`

渲染 HTML 后**必须**再跑一次交付物校验，确认渲染没出问题（标签、`lang`、字体、表格滚动容器、Brief 是否残留 Markdown 标记、Contact 列取的是不是记录里的第一条联系方式）：

```bash
python3 <skill安装目录>/scripts/validate_delivery.py lead-research/delivery.html \
  --candidates lead-research/candidates.jsonl
```

`validate_candidates.py` 守的是数据，`validate_delivery.py` 守的是渲染结果，两者都要过。

3. 若 `output.include_outreach_drafts: true`，用 [references/outreach.md](references/outreach.md) 为主名单写草稿到 `lead-research/outreach/`

**交付态硬校验（`disposition` ∈ {main, backup}）**——缺一不可，由 schema + `validate_candidates.py` 强制：

1. 供需：`segment_evidence` ≥1，且至少一条 `demand_side`（含 observation + http(s) source）
2. 背调：`due_diligence_summary` 非空；`due_diligence_checks` 恰好 5 条，覆盖 authenticity / operating_status / business_relevance / risk_signals / reachability，每条含 finding + source + status
3. 打分：`score` + `score_breakdown` 五项均有 value 与非空 basis（可复算）
4. 联系方式：`contacts` 数组必填；非空则每项含 source + confidence；若为 `[]`，则 reachability 的 finding 须说明已检索且无公开通道
5. 其他：`match_reason` 非空；`main` 不得为 `risk_level: high`

`competitor` 另须：`exclusion_reason` + 至少一条 `supply_side` 的 `segment_evidence`。

汇报时指向 `delivery.md` / `delivery.html`；区分已验证 / 低置信 / 缺口；未跑完则说明进度与可续跑。

## 铁律

- 绝不编造公司、邮箱、电话或任何事实。
- 只使用公开来源；每条线索可追溯到 URL。
- 供给侧不进主名单/备选池；拿不准标 `excluded`（供需待确认），不得靠打分混过。
- high 风险必须 `excluded` 并标注，不得隐藏。
- 遵守 `market.exclude_keywords` 和地区排除项。
- 只研究并起草触达内容；未经用户明确同意不实际发送。

## 资源

- [capabilities/](capabilities/) — 各宿主能力清单
- [references/segmentation.md](references/segmentation.md) — 分类、供需判定、体量、打分公式
- [references/due-diligence.md](references/due-diligence.md) — 背调与风险分级
- [references/verification.md](references/verification.md) — 联系方式验证
- [references/sources.md](references/sources.md) — 线索来源与查询模板
- [references/tools.md](references/tools.md) — 能力后端与降级链
- [references/outreach.md](references/outreach.md) — 开发信模板
- [references/delivery.md](references/delivery.md) — 人读交付物（MD/HTML）固定版式
- [assets/lead-schema.json](assets/lead-schema.json) — 输出字段标准
- [config/leads.yaml.example](config/leads.yaml.example) — 配置模板
- [scripts/detect_backend.py](scripts/detect_backend.py) — 解析搜索/网页/LinkedIn 后端
- [scripts/validate_candidates.py](scripts/validate_candidates.py) — 校验 candidates.jsonl
- [scripts/validate_delivery.py](scripts/validate_delivery.py) — 校验渲染出的 delivery.html
- [scripts/render_delivery.py](scripts/render_delivery.py) — 渲染 delivery.md / delivery.html
- [scripts/install.sh](scripts/install.sh) — 多宿主部署

## 变更记录

- **1.4.3** — 修 `render_delivery.py` 渲染缺陷：`pick_contact()` 同渠道多条时后出现者覆盖先出现者（导致表格显示错误邮箱）；HTML `lang` 写死 `en`；中文字体未入栈；宽表在窄屏被挤成竖排表头；`brief.md` 原样倾倒导致 Markdown 标记裸露（新增 `brief_md_to_html()`，含管道表格）；补 `@media print` 防止打印裁掉右侧列。新增 `scripts/validate_delivery.py` 作为渲染结果的自动门禁。详见 [references/delivery.md](references/delivery.md#渲染约束改动-css-前先读)。
