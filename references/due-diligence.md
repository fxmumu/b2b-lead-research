# 潜在客户背调

对通过资格筛选的候选，逐一做公开信息背调。目标是把高风险或无效线索挡在推荐名单外。

## 检查项

1. 真实性
   - 官网是否存在、内容是否正规
   - 当地商业注册/营业执照信息（按地区取本地注册库：UAE DED、沙特 CR、Companies House（UK）、Companies NZ、Pappers（FR）、Handelsregister（DE）、KVK（NL）、州务卿 / SEC（US））
   - 是否出现在政府备案、行业协会或权威目录中

2. 经营状态
   - 近 24 个月是否有项目、新闻、招聘或网站更新
   - 是否存在停业、注销、被收购、清算迹象

3. 业务相关性
   - 主营业务是否真的采购目标产品
   - 是否属于 `icp.customer_types` 中一类

4. 风险信号（只查公开信息）
   - 诉讼、仲裁、破产、制裁名单
   - 重大负面新闻
   - 频繁更名/重组

5. 触达有效性
   - 能否识别到采购/商务/BD 决策人
   - 是否存在招标/RFQ/采购需求信号

## 风险分级

- low：多项官方来源确认、有活跃项目、决策人明确
- medium：信息部分间接，或有一两项存疑
- high：疑似注销、涉及制裁、重大诉讼、明显不相关，或完全查无实据

## 处理规则

- 制裁名单命中，或真实性/经营状态完全查无实据、无法确认公司存在 → `disposition: excluded`（保留 jsonl 供审计，不进主名单/备选池）
- 其他 high → `disposition: excluded`，`exclusion_reason` 注明「高风险，不建议触达」
- medium：继续流水线，在输出中说明存疑点（总分排序时自然靠后，不另设降权系数）
- low：正常进入下一轮

每个候选输出 `risk_level` 和 `due_diligence_summary`（2–3 句，说明依据）。

## 论据留痕

背调结论必须可复核。按 `assets/lead-schema.json` 的 `due_diligence_checks` 输出逐项证据：

- 5 个检查项（authenticity / operating_status / business_relevance / risk_signals / reachability）各一条记录
- 每条含 `finding`（查到了什么）、`source`（来源 URL）、`status`（confirmed / inconclusive / negative）
- **查无实据也是结论**：某项没查到就如实标 inconclusive 并说明查了哪里，不留空、不臆测
- `risk_level` 必须能从各检查项的 status 推导出来；推导不出时说明分级有误，回头重查
