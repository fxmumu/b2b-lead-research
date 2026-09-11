# 客户分类、体量估算与打分

## 1. 客户类型

按采购路径分类。**下表是唯一标准叫法**：`leads.yaml` 的 `icp.customer_types`、`icp.type_weights` 和候选记录的 `segment` 字段都必须使用标准键名（英文）；中文别名仅供阅读和搜索。

| 标准键名 | 中文 | 行业别名 | 采购特征 |
|---|---|---|---|
| `end_user` | 最终用户自采 | 终端用户、工厂直采 | 直接采购自用，优先级高 |
| `epc` | EPC/承包商 | contractor、总包 | 项目中采购，量取决于承接项目 |
| `installer` | 安装商 | 安装公司 | 持续耗材采购 |
| `distributor` | 分销商 | 经销商、wholesaler（批发商） | 重复订单、走渠道 |
| `importer` | 进口商 | 进口贸易商 | 跨境采购后本地转售，出口业务核心类型 |
| `trading_company` | 贸易商 | trading company、代理商（agent） | 无自有渠道，赚差价/佣金 |
| `oem_buyer` | 集成商/OEM | 品牌商、integrator | 批量采购嵌入自家产品 |
| `developer_owner` | 开发商/业主 | developer、asset owner | 多转包给 EPC，直接采购少 |

这些均为外贸与工程行业通用叫法，区域习惯有差异（中东目录常称 contractor，欧美多用 EPC/installer）。**搜索时用别名扩大命中，归类时统一映射回标准键名。**

**多角色公司**：一家公司常兼具多重身份（最常见 importer + distributor）。取其采购路径的**主导角色**作为 `segment`，打分按该角色取 `type_weights`；次要角色写入 `match_reason` 说明。`type_weights` 中未出现的角色视为不属于 ICP。

## 1.5 供需判定（供给侧硬闸门）

skill 用户是**供方**；要找的是**需方**。归类客户类型前先做一次供需判定：候选与用户同品类、同环节的公司属供给侧，不是客户，按 SKILL.md Step 3 设 `disposition: competitor`（进排除清单，不打分、不占 `backup_n`）。

判定信号（公开信息）：

**供给侧信号**（命中越多越确定）：

- 官网/简介自称 manufacturer / producer / supplier / trader，且主营品类与用户一致
- 产品列表与用户产品同品类同环节（如都是光伏支架生产商）
- 官网挂着「找代理 / dealer wanted / 寻求分销」等招商页——它在建渠道，不在找货源
- 出现在同类产品出口商名录、B2B 平台卖家页（Alibaba/Made-in-China 供应商身份）

**需求侧信号**（命中即为有效需方）：

- 自称 buyer / importer / distributor / contractor / installer，且品类与用户匹配（它卖的是**采购来的**货）
- 有项目、安装、施工、门店、本地服务团队等**消耗该产品**的业务痕迹
- 官网产品页含多品牌/多来源产品线（说明它在向别处采购）
- 出现在招标、采购、招聘安装工/采购员等需求侧场景

**裁决规则**：

- 品类相同但环节不同 → 不是同行（例：用户是支架生产商，候选是支架安装商——后者是需方）
- 既是同行又是潜在客户（如竞争对手偶尔也外采该品类）→ 默认 `disposition: competitor`，在排除清单说明，由用户定夺
- 拿不准 → `disposition: excluded`，`exclusion_reason` 写「供需关系待确认」，不打分、不进主名单/备选池

**判定留痕**：每家的供需判定按 `assets/lead-schema.json` 的 `segment_evidence` 留证据——观察到的信号（demand_side / supply_side）、具体事实、来源 URL。判为需方至少要有一条 demand_side 证据；只有排除性推理（「查不到它在卖同类产品」）没有正面证据时，判定降级为待确认。

## 2. 体量估算

公开来源很少直接写年采购额，用代理指标估算：

- 员工数 + 营收：换算公司规模
- 项目规模与数量：EPC/安装商用近 2 年项目列表估算
- 分销网络：仓库、覆盖区域、产品线
- 官网/新闻中的装机量或产能数字

估算公式（启发式，不必精确；角色键名见第 1 节术语表）：

- `epc` / `installer` 年采购额 ≈ 年项目总金额 × 该类材料占比（紧固件通常 0.5%–2%，按行业调整）
- `distributor` / `importer` 年采购额 ≈ 年营收 × 该品类占比（默认 10%–30%）
- `oem_buyer` 年采购额 ≈ 年产量 × 单台用量 × 该材料占比
- 无法估算时：**省略** `estimated_annual_procurement_usd` 整段（不要写假的 min/max）；打分时 `score_breakdown.volume.tier` 设为 `unknown`，在 `volume.basis` 说明为何无法估算。不要把 unknown 写进 `match_reason`（该字段只解释客户类型匹配）。

## 3. 分档

把估算年采购额映射到 `scoring.volume_tiers_annual_usd` 四档（A/B/C/D）。估算值落在两档边界之间时取较低档。无法估算（已省略采购额字段）时不套 A–D 阈值，直接按下一节 `unknown` 计 volume。

## 4. 打分公式

四项得分各映射到 0–1，按 `scoring.weights` 加权。**公式固定如下，不得自行变通**，保证同一配置下结果可复现。

**权重预处理**：若 `scoring.weights` 四项之和不等于 1（允许浮点误差 ±0.01），先按各项 / 总和归一化，再代入公式；并在 `score_breakdown` 的某一 `basis` 中注明「weights normalized」。

- fit：`fit = icp.type_weights[候选 segment 键名] / 5`。候选不属于 `icp.customer_types` 中任何一类时 → `disposition: excluded`（ICP 不符），不打分。
- volume：按分档取值 `A=1.0, B=0.75, C=0.5, D=0.25`；无法估算（`tier: unknown`）时 volume = 0.25（按最低档 D 计，不参与也不豁免）。
- activity：`activity = min(近24个月可查项目/新闻数 ÷ (2 × icp.min_recent_projects), 1.0)`。即达到 min_recent_projects 的 2 倍即满分，0 条记 0。**计数口径按行业取代理**：工程/EPC 用中标、项目、装机；快消/品牌用上新发布、媒体报道、渠道扩张、活跃评论增长等。实际口径写进 `activity.basis`。
- accessibility：`accessibility = 0.5 × contact_score + 0.5 × decision_maker_score`，其中：
  - contact_score：存在带来源且置信度 high 的联系方式 = 1.0；仅 medium = 0.6；仅 low 或只有官网表单 = 0.3；无可触达通道 = 0
  - decision_maker_score：能识别到采购/商务/BD 具体决策人 = 1.0；只能到公司层面（info 邮箱、前台电话）= 0.4；否则 0

加权总分：

```
score = (w_fit × fit + w_volume × volume + w_activity × activity + w_accessibility × accessibility)
        × region_weight
```

`region_weight` 来自 `market.region_weights`（未命中取 1）。它是轻度地区偏好乘数，**建议配置在 1.0–1.5**（一般不超过 2.0）；过大（如 3）会把弱候选抬过 `min_score`，使门槛失效。打分在 Step 6 执行（须已完成 Step 5 联系方式验证）。低于 `scoring.min_score` 但已完整打分的候选可进入 `disposition: backup`（有分次优）；`competitor` / `unreachable` / `excluded` 不参与打分、不占 `backup_n`。
