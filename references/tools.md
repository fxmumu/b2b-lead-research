# 能力后端解析与降级链

本 skill 不把任何宿主专属工具名写进文档。执行前先运行 detect_backend.py 得到 capability map，按其输出行动：

```bash
python3 <skill安装目录>/scripts/detect_backend.py
# Windows 若无 python3：python <skill安装目录>/scripts/detect_backend.py
```

宿主差异由 [../capabilities/](../capabilities/) 下的清单文件解析：每个宿主一个 JSON（原生工具名、调用注意事项、权限提示），`_schema.json` 约束字段。加新宿主 = 加一个清单文件，不改代码与文档。路径相对 skill 安装目录；从任意工作目录调用时用绝对路径或先定位该目录。

## 选择顺序（detect_backend.py 的解析逻辑）

1. **原生能力优先**（来自清单 `backend: native`）
   - `search`：宿主内置搜索工具
   - `web_read`：宿主内置网页读取工具
   - 需要 PDF、原始 HTML 时：`curl`、`pdftotext` 等 shell 工具

2. **原生能力缺失时，检测 CLI 层增强**（与宿主无关，所有 CLI 通用）
   - Agent Reach：`mcporter call exa.web_search_exa query="{query}" numResults=5`（Exa 语义搜索，需通道已验证）
   - 通用网页阅读：`curl -s "https://r.jina.ai/{url}"`
     - 注意：目标 URL 会发给第三方（Jina）拉取可读文本；本 skill 只应用在公开来源。免费档有速率限制，失败时可能静默返回空/错误页——失败则改用原生 `web_read` 或直接 `curl` 目标站，不要把空结果当「页面无内容」。
   - LinkedIn MCP（仅当 `--check-linkedin` 确认会话有效）：
     ```bash
     mcporter call linkedin.search_people keywords="{query}" location="{location}"
     mcporter call linkedin.get_person_profile linkedin_username="username" sections="experience"
     mcporter call linkedin.get_company_profile company_name="openai" sections="jobs"
     ```
     仅使用公开内容；不自动登录、不抓取联系方式。

3. **都不可用时回退**
   - 直接访问官网、行业目录、政府备案、新闻来源
   - 仍以公开 URL 为唯一事实来源

## 规则

- Agent Reach 缺失或未配置时，本 skill 仍应正常执行。
- 最终线索仍必须遵守联系方式验证规则，不能因为使用 CLI 增强就降低来源标准。
- LinkedIn 只用于公开线索核验和搜索入口，不猜测邮箱、个人主页 URL 或非公开联系方式。

## LinkedIn 降级链

1. 优先：LinkedIn MCP（会话已验证）
2. 会话无效或未配置时：`search` + `web_read` 找公开 LinkedIn 页面/目录/新闻
3. 仍不可用时：返回 LinkedIn 搜索 URL 和公司官网公开信息，不猜测 profile URL
4. 会话无效但用户明确需要 LinkedIn 时：停止并提示运行
   `uvx mcp-server-linkedin@latest --login --no-headless`
