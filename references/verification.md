# 联系方式验证

## 来源优先级

按序检索，命中即止（见下方「止损」）：

1. 官网 contact 页、页脚、imprint / 法务信息页、官方新闻稿
2. 政府/机构备案或公司注册库——**按目标国家取用**，例：Companies House（英）、Companies NZ（新西兰）、Handelsregister（德）、KVK（荷）、Pappers / INPI（法）、SEC EDGAR（美）、当地商业登记
3. 展会官方展商页
4. 权威行业目录或协会会员名录——**按行业取用**，例：光伏 → ENF Solar；化妆品/个护 → 行业媒体与品牌协会名录；机械 → 行业协会名录
5. 零售商 / 分销商页面上的品牌联系信息
6. LinkedIn 公司页

> 上面 2 / 4 的示例仅作格式参考，实际按 `market.target_regions` 与产品所属行业替换，不要照搬不相关行业的来源。

## 置信度

- high：官方/政府来源直接给出
- medium：两个互相独立的第三方目录一致（满足 `verification.min_cross_check_sources`）
- low：单一第三方目录，或官网只有表单

## 与配置的联动

工作目录 `leads.yaml` 的 `verification` 段覆盖本文件规则，冲突时以配置为准：

- `require_official_source_for_email: true` 时，**只有 high 置信度的邮箱可用于主名单**（`disposition: main`）；medium/low 邮箱的候选最高进有分备选池（`disposition: backup`），输出中注明原因。
- `min_cross_check_sources`：判定 medium 置信度所需的独立来源数下限（默认 2）。
- `never_guess_email: true` 时严格执行下方"绝不猜测"规则，无例外。

## 止损：不要为邮箱无限检索

邮箱验证是全程最贵的一步（小众品牌官网常常只有一个表单，`require_official_source_for_email: true` 下 high 置信度根本不可得）。必须有明确上限：

- 官方渠道（官网 contact / 页脚 / imprint、官方新闻稿、注册库）**各查一次即止**，不换关键词反复搜同一目标。
- 官方渠道查完仍无公开邮箱 → 直接按「无公开邮箱」记录（`contacts: []`，或只记官网表单渠道，并在 `reachability` 的 finding 中说明已检索过），**不再扩大检索范围**。
- `require_official_source_for_email: true` 时，靠第三方目录凑到 medium 的候选按规则进 `disposition: backup`，**不因想让它进主名单而延长检索**。
- 经验上限：一家查完「官网 + 注册库 + 一个目录」仍无结果，就结束该家、推进下一家，把时间留给还没筛过的候选。

## 邮箱域名有效性检查

拿到候选邮箱后，做一次零成本验证（有 `dig` 用前者；Windows 通常没有 `dig`，用后者）：

```bash
dig +short MX <邮箱@后的域名>
# Windows / 无 dig 时：
nslookup -type=MX <邮箱@后的域名>
```

无 MX 记录（或 NXDOMAIN）的域名说明邮箱不可能收信——保留线索但联系方式标 `confidence: low` 并注明 "domain has no MX record"。这只是域名有效性检查，不是邮箱存在性验证。`dig` / `nslookup` 都不可用时跳过本检查，不因此降低已有来源的置信度。

## 规则

- 绝不根据姓名或域名格式猜测邮箱。
- 找不到邮箱就写「无公开邮箱，建议官网表单/LinkedIn」。
- 每个联系方式附 `source` URL 和 `confidence`。
- 检查域名一致性：邮箱域名应与官网域名相同或明显关联。
- 优先找采购/商务/BD 相关联系人，其次通用 info 邮箱。

## 输出

`contacts` 数组中每项包含 channel、value、role、source、confidence。
