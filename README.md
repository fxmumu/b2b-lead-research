# b2b-lead-research

Agent Skill：**供方找需方**——研究、筛选、背调 B2B 潜在客户，产出带来源、打分排序的客户名单与开发信草稿。
使用本 skill 的用户是供给侧（卖方），skill 负责找到需求侧（真正采购其产品的买家），并识别、排除与用户同品类同环节的同行。
兼容 Codex、Claude Code 与 Cursor（同一 SKILL.md 格式），其他宿主通过能力清单扩展。

## 工作流程

0. 配置与目标确认（读工作目录 `leads.yaml`，向用户列出任务简报并确认供需口径）
1. 拆解搜索计划（解析当前宿主能力后端，查询偏向需求侧）
2. 线索发现（多路搜索 + 域名去重）
3. 资格筛选（**供给侧硬闸门：同行进排除清单**）、体量估算与可触达性过滤（本步不打分）
4. 潜在客户背调（硬闸门，风险分级）
5. 联系方式获取与验证（绝不猜测邮箱）
6. 打分排序（公式固定；主名单 / 有分备选 / 排除清单三分）
7. 汇总交付（可选开发信草稿）

支持断点续跑：`lead-research/candidates.jsonl` 为唯一真相源（含 `stage` / `disposition`），可用 `scripts/validate_candidates.py` 校验。

## 安装

**装 skill 的本质**：把一个名为 `b2b-lead-research`（内含 `SKILL.md`）的目录放进宿主的 skills 目录（`~/.claude/skills/`、`~/.codex/skills/`、`~/.cursor/skills/`），仅此而已。目录名就是 skill ID，名字不对宿主就识别不了。

**`scripts/install.sh` 不是必须的**。它只服务下面方式一：为 git 仓库建 symlink，让一次 `git pull` 同时升级所有宿主。不想用脚本就直接用方式二。

**Windows**：请走**方式二**（或方式三），不要用 `install.sh`。Git Bash 下 `ln -s` 常变成复制而非真正符号链接，脚本会显示成功，但源仓库 `git pull` 不会同步到宿主 skills 目录。

命令里的 `python3` 在 Windows 上若不存在，改用 `python`。

### 方式一：git clone + symlink（macOS / Linux 推荐，需要跑 install.sh）

单一源在 git 仓库，`git pull` 即升级，各宿主共享同一份：

```bash
git clone https://github.com/fxmumu/b2b-lead-research.git ~/github.com/fxmumu/b2b-lead-research
~/github.com/fxmumu/b2b-lead-research/scripts/install.sh
```

脚本行为：
- 在 `~/.claude/skills/`、`~/.codex/skills/`、`~/.cursor/skills/` 下各建一个 symlink 指向仓库本体
- 目标位置已有其他内容时拒绝覆盖（`[conflict]`），目录名不对（如 ZIP 解压的 `-master` 后缀）时拒绝执行并给出指引
- 退出码：0 成功；1 有冲突/缺失；2 用法错误

常用选项：

```bash
scripts/install.sh --verify            # 只校验不修改
scripts/install.sh --hosts claude-code # 指定宿主（已知：claude-code, codex, cursor）
```

### 方式二：直接 clone 进宿主 skills 目录（不跑脚本；**Windows 推荐**）

不想保留独立仓库时最简单，但升级要在每个宿主里分别 pull。Windows 用户应始终用本方式，保证目录是真实副本/仓库而非假 symlink：

```bash
git clone https://github.com/fxmumu/b2b-lead-research.git ~/.claude/skills/b2b-lead-research
# codex: ~/.codex/skills/b2b-lead-research
# cursor: ~/.cursor/skills/b2b-lead-research
```

注意：若之后又在同一宿主跑方式一的 install.sh，脚本会识别出该目录就是源目录（`[source]`），不会重复建链。

### 方式三：GitHub ZIP 下载（应急）

无 git 环境时的兜底，也不需要 install.sh。ZIP 解压目录名带 `-master` 后缀，**必须先改名**：

```bash
unzip b2b-lead-research-master.zip          # 得到 b2b-lead-research-master/
mv b2b-lead-research-master b2b-lead-research
mv b2b-lead-research ~/.claude/skills/      # 或放到任意位置后跑 scripts/install.sh
```

install.sh 遇到目录名不是 `b2b-lead-research` 会拒绝执行并提示，避免装出一个宿主识别不了的 skill。缺点：无 `git pull` 升级，更新需重新下载。

### 安装后验证

在对应宿主开一个**新会话**，确认 `b2b-lead-research` 出现在 skill 列表。想接入新宿主（其他 agent CLI），加一个 `capabilities/<host>.json` 清单即可，见下方「多宿主架构」。

## 配置

配置在**任务工作目录**，不在 skill 仓库里。每个市场/项目一份：

```bash
mkdir -p ~/leads/saudi-market && cd ~/leads/saudi-market
cp <skill仓库>/config/leads.yaml.example leads.yaml
# 按你的产品填写 leads.yaml
```

- skill 运行时从当前工作目录读 `leads.yaml`；缺失时会把模板复制过来并向你索要字段。
- 配置包含公司信息、ICP 和市场策略——若工作目录在 git 仓库内，请把 `leads.yaml` 加入该仓库的 `.gitignore`。
- 中间产物在 `lead-research/candidates.jsonl`；任务简报在 `lead-research/brief.md`。

## 多宿主架构

宿主差异（工具名、调用方式、权限提示）不写死在文档里，由 `capabilities/` 下的能力清单解析：

- `SKILL.md` 与 references 只谈抽象能力（search / web_read / linkedin）
- `scripts/detect_backend.py` 运行时读取清单，输出统一的 capability map
- 新增宿主 = 新增一个 `capabilities/<host>.json`（字段受 `_schema.json` 约束），零代码改动

## 铁律

- 绝不编造公司、邮箱、电话或任何事实
- 只使用公开来源；每条线索都要能追溯到 URL
- 供给侧不进名单：与用户同品类、同环节的同行不是买家，不得进主名单/备选池
- high 风险客户必须标注并排除，不得隐藏
- 本 skill 只负责研究并起草触达内容；未经用户明确同意，不实际发送任何消息
