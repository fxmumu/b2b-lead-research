---
name: b2b-lead-research
description: Research, qualify, and verify B2B potential customers/leads for a product or service, producing a prioritized, sourced contact list with due-diligence notes and outreach drafts. Use when the user asks to 找客户、获客、开发客户、找潜在客户、客户名单、找经销商/采购商/EPC/买家，or "find leads / find potential customers / lead generation / customer acquisition / find buyers". Reads a user-maintained config at config/leads.yaml.
---

# B2B Lead Research

## 执行顺序

先读 `config/leads.yaml`。它定义产品、供货能力、目标客户画像（ICP）、目标市场、打分权重和输出参数。配置缺失或关键字段为空时，先向用户索要，不要臆造。

按以下步骤执行：

1. 拆解搜索计划
2. 线索发现（含去重）
3. 资格筛选、体量估算与可触达性过滤
4. 潜在客户背调（硬闸门）
5. 联系方式获取与验证
6. 打分排序
7. 汇总交付

## 中间产物与断点续跑

全量任务涉及数十家候选、上百次页面抓取，单次会话无法完整承载，必须增量落盘：

- 在用户工作目录下创建 `lead-research/` 目录，维护三个文件：
  - `candidates.jsonl` — 每家候选一条 JSON（schema 见 assets/lead-schema.json，可先留空未验证字段）
  - `scores.jsonl` — {company, fit, volume, activity, accessibility, region_weight, score, risk_level}
  - `outreach/` — 开发信草稿，一客户一文件
- 每完成一家候选的一个阶段（发现/筛选/背调/验证/打分），立即把该阶段结果追加写入，不要攒到最后批量写。
- 恢复任务时：先读这三个文件，跳过已有完整记录的候选；字段残缺的候选视为未完成，只补缺失阶段。
- 汇报进度时以落盘记录为准，不以本次会话记忆为准。

## Step 1: 拆解搜索计划

先解析当前执行环境的能力后端。运行：

```bash
python3 scripts/detect_backend.py
```

- 你如果清楚自己所在的宿主（如 `claude-code`、`codex`），显式传 `--host <宿主名>`，这是最可靠的识别方式；不确定就省略，脚本会从环境标记探测。
- 脚本返回统一的 capability map（`search` / `web_read` / `linkedin` 三项，各含 backend、调用方式、注意事项）。**之后严格按 capability map 行动，不假设工具名**——不同宿主的工具不同，映射关系全部由 `capabilities/` 清单解析，本 skill 正文不出现宿主专属工具名。
- 只有需要检查 Agent Reach 通道状态时才加 `--doctor`；需要真实校验 LinkedIn 登录态时加 `--check-linkedin`。
- 输出里 `backend: none` 的能力按其 `note` 的降级路径执行。

根据 `company.product_or_service`、`icp.customer_types` 和 `market.target_regions` 生成并行查询组合。至少覆盖：

- 行业目录与展商名单
- 政府/机构备案的承包商或供应商名单
- 项目新闻反查（中标、开工、招标 -> 背后的 EPC/买家）
- 公司官网与 LinkedIn

英文查询为主；对非英语市场按需补充本地语言关键词。详细来源与查询模板见 [references/sources.md](references/sources.md)。

## Step 2: 线索发现

并行执行搜索，为每个候选记录：

- 公司名、国家、官网
- 初步判断的客户类型
- 来源 URL

**去重**：多路搜索必然命中同一公司。以官网域名为主键（去 `www.`、统一小写；无官网的用公司名小写去空格做次级键），发现阶段先查 `candidates.jsonl` 中是否已有该键，命中则只合并来源 URL，不新建记录。

不在本阶段深挖，先收集足够的候选池（至少 `market.backup_n` 的 2-3 倍）。

若任务明确要求 LinkedIn 人员/职位搜索，按 capability map 的 `linkedin` 项执行；能用 LinkedIn MCP（会话已验证）就记录真实 profile URL 和职位，不能用就回退到 `search` 与公开 LinkedIn 搜索入口。

## Step 3: 资格筛选、体量估算与可触达性过滤

用 [references/segmentation.md](references/segmentation.md) 对每个候选：

- 归类客户类型
- 用员工数、营收、项目规模/数量、分销网络等公开代理指标估算年采购额
- 对照 `icp` 过滤不符合最低要求的候选
- 计算四项得分（公式见 segmentation.md，不可自行变通）

**可触达性前置过滤（廉价，先于背调）**：快速确认候选至少存在一个潜在联系通道——官网有 contact 页/表单、LinkedIn 公司页、或公开 info 邮箱。三者皆无的候选直接标 `unreachable` 移入备选池，不做 Step 4 背调（背调成本高，不要花在不可触达的线索上）。

## Step 4: 潜在客户背调（硬闸门）

用 [references/due-diligence.md](references/due-diligence.md) 检查每家的：

- 公司是否真实存在、是否仍在经营
- 业务是否真的采购目标产品
- 公开可查的诉讼、破产、制裁、负面信号
- 能否识别到采购/商务决策人

输出 `risk_level`（low/medium/high）和 `due_diligence_summary`。**high 风险的候选一律不进入主名单**，移入备选池并标注「高风险，不建议优先触达」；制裁名单命中或查无实据的直接删除，不保留。

## Step 5: 联系方式获取与验证

用 [references/verification.md](references/verification.md) 获取并验证联系方式：

- 邮箱优先，其次电话、LinkedIn、官网表单
- 每个联系方式必须附 `source` 和 `confidence`
- 找不到公开邮箱就写「无公开邮箱」，绝不根据姓名或域名格式猜测

## Step 6: 打分排序

按 `scoring.weights` 计算加权总分（公式见 segmentation.md），再按 `risk_level` 调整：high 风险移入备选池。得到主名单（`market.top_n`）和备选池（`market.backup_n`）。

**主名单/备选池语义**：主名单 = 总分最高且 `risk_level != high`、`min_score` 达标的前 `top_n` 家；备选池 = 主名单之外得分次高的 `backup_n` 家，无论其分数是否达到 `min_score`——包括被可触达性过滤或高风险规则移下来的候选。若达标候选不足 `top_n`，如实输出较少的主名单，不放宽标准凑数。

## Step 7: 汇总交付

按 [assets/lead-schema.json](assets/lead-schema.json) 输出字段，交付主表 + 备选池。若 `output.include_outreach_drafts: true`，用 [references/outreach.md](references/outreach.md) 为主名单客户生成开发信草稿，写入 `lead-research/outreach/`。

汇报时明确区分已验证信息、低置信度信息和未验证缺口。若本次会话未能跑完全部候选，如实说明已完成的数量与剩余缺口，并告知用户可继续时从落盘记录恢复。

## 铁律

- 绝不编造公司、邮箱、电话或任何事实。
- 只使用公开来源；每条线索都要能追溯到 URL。
- high 风险客户必须标注，不得隐藏。
- 遵守 `market.exclude_keywords` 和地区排除项。
- 本 skill 只负责研究并起草触达内容；未经用户明确同意，不实际发送任何消息。

## 资源

- [capabilities/](capabilities/) — 各宿主能力清单（加新宿主 = 加一个 JSON 文件）
- [references/segmentation.md](references/segmentation.md) — 客户分类、体量估算、打分公式
- [references/due-diligence.md](references/due-diligence.md) — 背调清单与风险分级
- [references/verification.md](references/verification.md) — 联系方式验证与置信度
- [references/sources.md](references/sources.md) — 线索来源与查询模板
- [references/tools.md](references/tools.md) — 能力后端解析与降级链
- [references/outreach.md](references/outreach.md) — 开发信模板
- [assets/lead-schema.json](assets/lead-schema.json) — 输出字段标准
- [config/leads.yaml](config/leads.yaml) — 你的产品与 ICP 配置
- [scripts/detect_backend.py](scripts/detect_backend.py) — 解析当前可用的搜索/网页/LinkedIn 后端
- [scripts/install.sh](scripts/install.sh) — 部署到多个宿主（symlink + 自检）
