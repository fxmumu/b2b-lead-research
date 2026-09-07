# b2b-lead-research

Agent Skill：研究、筛选、背调 B2B 潜在客户，产出带来源、打分排序的客户名单与开发信草稿。
兼容 Codex 与 Claude Code（同一 SKILL.md 格式），其他宿主通过能力清单扩展。

## 工作流程

0. 配置与目标确认（读工作目录 `leads.yaml`，向用户列出任务简报并确认）
1. 拆解搜索计划（解析当前宿主能力后端）
2. 线索发现（多路搜索 + 域名去重）
3. 资格筛选、体量估算与可触达性过滤
4. 潜在客户背调（硬闸门，风险分级）
5. 联系方式获取与验证（绝不猜测邮箱）
6. 打分排序（公式固定，可复现）
7. 汇总交付（主名单 + 备选池，可选开发信草稿）

支持断点续跑：中间产物增量落盘（工作目录下 `lead-research/` 目录），任务可跨会话恢复。

## 安装

```bash
# 默认部署到 claude-code 与 codex（目录 symlink，单一源）
scripts/install.sh

# 只校验不修改
scripts/install.sh --verify

# 指定宿主
scripts/install.sh --hosts claude-code
```

安装后在两个宿主各开一个**新会话**，确认 `b2b-lead-research` 出现在 skill 列表。

## 配置

配置在**任务工作目录**，不在 skill 仓库里。每个市场/项目一个目录，一份配置：

```bash
mkdir -p ~/leads/saudi-market && cd ~/leads/saudi-market
cp <skill仓库>/config/leads.yaml.example leads.yaml
# 按你的产品填写 leads.yaml
```

- skill 运行时从当前工作目录读 `leads.yaml`；缺失时会把模板复制过来并向你索要字段。
- 配置包含公司信息、ICP 和市场策略——若工作目录在 git 仓库内，请把 `leads.yaml` 加入该仓库的 `.gitignore`。
- 配置跟随任务目录：归档、复制、交给同事都只需带走目录；任务简报会落盘到 `lead-research/brief.md`，保证续跑与审计可复现。

## 多宿主架构

宿主差异（工具名、调用方式、权限提示）不写死在文档里，由 `capabilities/` 下的能力清单解析：

- `SKILL.md` 与 references 只谈抽象能力（search / web_read / linkedin）
- `scripts/detect_backend.py` 运行时读取清单，输出统一的 capability map
- 新增宿主 = 新增一个 `capabilities/<host>.json`（字段受 `_schema.json` 约束），零代码改动

## 铁律

- 绝不编造公司、邮箱、电话或任何事实
- 只使用公开来源；每条线索都要能追溯到 URL
- high 风险客户必须标注，不得隐藏
- 本 skill 只负责研究并起草触达内容；未经用户明确同意，不实际发送任何消息
