# 开发信模板

以下为英文模板，占位符用 `{{ }}` 标出。发出前必须：

- 替换所有占位符
- `{{key_differentiator}}`（单数）：从 `company.key_differentiators` 中挑选与对方最相关的 1-2 条改写成一个短语，不要把整条列表原样塞进句子
- 至少引用一条对方公司/项目的具体事实
- 未经用户同意，不实际发送

## 通用结构

Subject: {{value_prop}} for {{company_name}}

Hi {{name}},

{{one-line value prop based on the most relevant key_differentiator}}

We provide {{product_or_service}} for {{segment}}. I noticed {{specific_fact}}.

We {{key_differentiator}} and ship from {{fob_port}}.

Would you be open to a short intro call?

Best,
{{your_name}} — {{your_company}} — {{your_email}}

## 输出约定

- 落盘：每家主名单一封草稿，写到 `lead-research/outreach/<Company>.md`（公司名空格换下划线）；并生成 `lead-research/outreach/README.md` 索引（序号 / 公司 / 收件邮箱 / 文件）。
- 署名与配置占位符（发出前必须全部替换）：
  - `{{your_name}}` / `{{your_company}}` / `{{your_email}}` ← `company.name_zh|name_en` / `contact_email`
  - `{{fob_port}}` ← `supply.fob_port`；`{{lead_time}}` ← `supply.lead_time_days`
  - `{{product_or_service}}` ← `company.product_or_service`
- 草稿头部用 HTML 注释标注收件邮箱与来源，便于核对：`<!-- To: <email> (<confidence> <source>) -->`。
- 语言按 `output.outreach_language`（默认 en）。

## 分类型差异（按 segment 标准键名，见 segmentation.md 术语表）

- `epc` / `installer`：强调项目供货、交期、标准合规
- `distributor` / `importer`：强调 MOQ、OEM/ODM、稳定供货
- `developer_owner`：先问其 EPC 或采购团队，不强推

## 跟进

未回复时 5–7 天后跟进一次，内容只加一个对方可能关心的具体点，不重复整封。
