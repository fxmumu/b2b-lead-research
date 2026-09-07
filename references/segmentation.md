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
- 无法估算时标 `unknown`，不参与体量打分，但保留线索

## 3. 分档

把估算年采购额映射到 `scoring.volume_tiers_annual_usd` 四档（A/B/C/D）。估算值落在两档边界之间时取较低档。

## 4. 打分公式

四项得分各映射到 0–1，按 `scoring.weights` 加权。**公式固定如下，不得自行变通**，保证同一配置下结果可复现：

- fit：`fit = icp.type_weights[候选 segment 键名] / 5`。候选不属于 `icp.customer_types` 中任何一类时 fit = 0，直接移入备选池。
- volume：按分档取值 `A=1.0, B=0.75, C=0.5, D=0.25`；无法估算（`unknown`）时 volume = 0.25（按最低档 D 计，不参与也不豁免）。
- activity：`activity = min(近24个月可查项目/新闻数 ÷ (2 × icp.min_recent_projects), 1.0)`。即达到 min_recent_projects 的 2 倍即满分，0 条记 0。
- accessibility：`accessibility = 0.5 × contact_score + 0.5 × decision_maker_score`，其中：
  - contact_score：存在带来源且置信度 high 的联系方式 = 1.0；仅 medium = 0.6；仅 low 或只有官网表单 = 0.3；无可触达通道 = 0
  - decision_maker_score：能识别到采购/商务/BD 具体决策人 = 1.0；只能到公司层面（info 邮箱、前台电话）= 0.4；否则 0

加权总分：

```
score = (w_fit × fit + w_volume × volume + w_activity × activity + w_accessibility × accessibility)
        × region_weight
```

地区权重按 `market.region_weights` 乘到总分（不在配置中的地区取 1）。低于 `scoring.min_score` 的候选移入备选池。
