# 联系方式验证

## 来源优先级

1. 官网 contact 页、页脚、官方新闻稿
2. 政府/机构备案名单（如 DEWA、ADDC、商业登记）
3. 展会官方展商页
4. 权威行业目录（如 ENF Solar）
5. LinkedIn 公司页

## 置信度

- high：官方/政府来源直接给出
- medium：两个互相独立的第三方目录一致（满足 `verification.min_cross_check_sources`）
- low：单一第三方目录，或官网只有表单

## 与配置的联动

工作目录 `leads.yaml` 的 `verification` 段覆盖本文件规则，冲突时以配置为准：

- `require_official_source_for_email: true` 时，**只有 high 置信度的邮箱可用于主名单**（`disposition: main`）；medium/low 邮箱的候选最高进有分备选池（`disposition: backup`），输出中注明原因。
- `min_cross_check_sources`：判定 medium 置信度所需的独立来源数下限（默认 2）。
- `never_guess_email: true` 时严格执行下方"绝不猜测"规则，无例外。

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
