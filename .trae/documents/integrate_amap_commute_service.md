# 集成高德地图 MCP 服务获取准确通勤时间

## Context

当前 TutorMatch 的通勤时间由 LLM 估算（默认 30 分钟），不准确。需接入高德地图 MCP 服务，根据老师起点地址和机会上课地址，通过公共交通路径规划获取准确通勤时间，提升筛选排序的可靠性。

## 已有资源

- **高德 MCP 服务器**：`https://mcp.amap.com/mcp?key=012fa8b1f4ffd5874903be70c14f4e74`
- **传输协议**：`streamable_http`
- **可用工具**：`maps_geo`（地理编码）、`maps_direction_transit_integrated`（公交路径规划）等
- **LangChain 集成**：使用 `langchain-mcp-adapters` 的 `MultiServerMCPClient`

## 修改方案

### 1. 依赖更新 — `pyproject.toml`

- 添加 `langchain-mcp-adapters>=0.1.0`
- 执行 `uv add langchain-mcp-adapters` 安装

### 2. 数据模型更新 — `tutormatch/models.py`

- **TutorProfile** 新增 `home_address: str = ""` 字段
- **TutoringOpportunity** 新增 `full_address: str = ""` 字段
- `from_dict()` 做向后兼容（空字符串默认值）

### 3. 配置更新 — `tutormatch/config.py`

- 新增 `AMAP_MCP_URL` 环境变量读取（默认值：`https://mcp.amap.com/mcp?key=012fa8b1f4ffd5874903be70c14f4e74`）
- 新增 `get_amap_mcp_url()` 函数

### 4. 新增 MCP 客户端封装 — `tutormatch/amap_mcp.py`

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

async def get_commute_minutes(
    origin: str,
    destination: str,
    mcp_url: str | None = None,
) -> int | None:
    """通过高德 MCP 查询公共交通通勤时间（分钟）"""
    # 1. 连接 MCP Server
    client = MultiServerMCPClient({
        "amap": {
            "transport": "streamable_http",
            "url": mcp_url or get_amap_mcp_url(),
        }
    })
    tools = await client.get_tools()
    # 2. 工具索引
    tools_by_name = {t.name: t for t in tools}
    geo_tool = tools_by_name.get("maps_geo")
    transit_tool = tools_by_name.get("maps_direction_transit_integrated")
    # 3. 地理编码
    origin_geo = await geo_tool.ainvoke({"address": origin})
    dest_geo = await transit_tool.ainvoke({"address": destination})
    # 提取坐标
    origin_loc = origin_geo["geocodes"][0]["location"]
    dest_loc = dest_geo["geocodes"][0]["location"]
    # 4. 查询公交路径
    result = await transit_tool.ainvoke({
        "origin": origin_loc,
        "destination": dest_loc,
        "city": "",
        "cityd": "",
        "strategy": 0,  # 最快路线
    })
    # 5. 提取总时长（秒 → 分钟）
    route = result["route"]["transits"][0]
    return route["duration"] // 60
```

- 内存缓存 `(origin, destination) → minutes`，避免重复查询
- 完整错误处理：失败时返回 None，不中断流程

### 5. 交互式输入更新 — `tutormatch/interactive.py`

- `collect_profile()` 新增询问老师起点地址
- `save_profile_cache()` / `load_cached_profile()` 处理 `home_address` 持久化

### 6. LLM 解析更新 — `tutormatch/llm.py`

- `PARSE_PROMPT` 增加 `full_address` 字段提取（从原始文本提取完整上课地址）
- `parse_opportunities_from_text()` 传递 `full_address` 到 `TutoringOpportunity`

### 7. 新增 LangGraph 节点 — `tutormatch/agent.py`

- 新增 `fetch_commute_times` 节点函数（同步封装异步调用）
- 图编排：`fetch_commute_times` → `screen_with_llm` → `write_report`
- 遍历所有机会，通过 MCP 获取真实通勤时间，更新 `commute_minutes`

## 数据流

```
profile.json (含 home_address)
    ↓
collect_profile → TutorProfile（含起点地址）
    ↓
parse_opportunities_from_text → 每个 opportunity 提取 full_address
    ↓
fetch_commute_times (通过 MultiServerMCPClient 调用高德 MCP):
    maps_geo(origin) → 经纬度
    maps_geo(destination) → 经纬度
    maps_direction_transit_integrated(origin, destination) → 时长
    → 更新 opportunity.commute_minutes
    ↓
screen_opportunities_with_llm (基于准确时间筛选排序)
    ↓
write_report (展示准确时间)
```

## 错误处理

- MCP 连接失败：打印警告，跳过查询，使用估算值
- 单个机会查询失败：跳过该机会，保持估算值，继续处理其他
- 所有机会查询失败：正常输出报告，使用估算值

## 验证方式

1. 运行 `python main.py`，输入老师起点地址，粘贴机会
2. 检查报告中的通勤时间是否为高德返回的准确值
3. 不配置 MCP 可正常 fallback 使用估算值