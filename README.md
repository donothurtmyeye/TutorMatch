# TutorMatch

家教兼职机会筛选 Agent MVP1。项目使用 LangGraph 编排流程，通过 LangChain 的 `init_chat_model` 调用大模型，对家教兼职机会进行评分、排序、风险判断和话术生成。通勤时间通过高德地图 MCP 服务实时查询公共交通路线，替代人工估算。

## 功能

- **Streamlit Web 前端**：图形化界面，粘贴大量机会文本一键筛选。
- **批量粘贴**：从微信群、中介等渠道复制整块机会文本，AI 自动解析结构化。
- **高德地图 MCP 通勤查询**：自动获取老师起点到每个机会地址的公共交通通勤时间，替代人工估算。
- **老师档案持久化**：首次输入后自动保存 `profile.json`，下次运行自动读取。
- **大模型筛选**：评分、结论、匹配理由、风险提醒、建议追问和联系话术。
- **Markdown 筛选报告**：生成完整报告，支持查看详细分析。

## 项目结构

```text
TutorMatch/
  main.py                    # 终端入口（备用）
  app.py                    # Streamlit Web 前端（推荐入口）
  tutormatch/
    agent.py                # LangGraph 编排流程
    amap_mcp.py             # 高德地图 MCP 客户端（地理编码 + 公交路线规划）
    llm.py                  # 大模型调用和结果解析
    config.py               # .env 配置读取
    models.py               # 数据模型
    interactive.py          # 终端交互输入
    report.py               # 报告渲染
  tests/
    test_config.py
    test_llm.py
```

## 安装

本项目使用 Python 3.12。推荐用 `uv` 安装依赖：

```powershell
uv sync
```

## 配置

在项目根目录创建 `.env` 文件：

```text
# 大模型配置（通用字段，自动映射到 OPENAI_ 等 provider 环境变量）
API_KEY="你的 API Key"
BASE_URL="https://your-compatible-endpoint/v1"
MODEL="openai:你的模型名"

# 高德地图 MCP 配置
AMAP_MCP_URL=https://mcp.amap.com/mcp?key=你的高德APIKey
```

**大模型**：`init_chat_model` 要求模型名格式为 `provider:model-name`，如 `openai:gpt-4o-mini`、`openai:qwen3.7-max-2026-06-08`。程序启动时自动把通用 `API_KEY`/`BASE_URL` 复制到对应 provider 的环境变量，LangChain 直接读取。

**高德地图**：需要在高德开放平台申请 API Key，在 `.env` 中配置 `AMAP_MCP_URL`。不配置则跳过通勤时间查询，使用原始机会数据中的通勤时间。

## 运行

### Web 前端（推荐）

```powershell
.venv\Scripts\streamlit.exe run app.py
```

浏览器打开 `http://localhost:8501`，界面引导式操作：填写老师档案 → 粘贴机会文本 → 点击筛选 → 查看结果卡片。

### 终端交互（备用）

```powershell
uv run python main.py
```

按提示输入老师档案，然后粘贴机会文本，输入 `---end---` 结束。

## 筛选流程

```text
用户粘贴机会文本
       ↓
AI 解析 → 结构化 TutoringOpportunity
       ↓
高德 MCP 查询通勤时间
  ├─ maps_geo（地址 → 经纬度）
  └─ maps_direction_transit_integrated（公交路线 → 时长）
       ↓
LLM 评分排序（匹配度、风险、话术）
       ↓
生成 Markdown 报告 + 终端摘要
```

## Agent 节点

LangGraph 编排 3 个节点：

1. `fetch_commute_times`：高德 MCP 查询公共交通通勤时间，更新每个机会的 `commute_minutes`。
2. `screen_with_llm`：调用大模型完成筛选、评分、风险判断和话术生成。
3. `write_report`：生成 Markdown 报告和终端摘要。
