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
2. **简报** — 若存在则嵌入 `lead-research/brief.md` 正文（HTML 中作 `<pre>`/`blockquote` 保留）
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

先校验，再渲染（工作目录为任务目录）：

```bash
python3 <skill安装目录>/scripts/validate_candidates.py lead-research/candidates.jsonl --config leads.yaml
python3 <skill安装目录>/scripts/render_delivery.py lead-research/candidates.jsonl \
  --config leads.yaml \
  --brief lead-research/brief.md \
  --out-dir lead-research
# Windows 若无 python3：改用 python
```

`--format` 可覆盖配置中的 `output.format`。缺省读 `leads.yaml`，再缺省则为 `both`。
