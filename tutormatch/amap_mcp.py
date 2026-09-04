from __future__ import annotations

import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from tutormatch.config import get_amap_mcp_url

logger = logging.getLogger(__name__)

# 内存缓存：(origin, destination) → minutes
_commute_cache: dict[tuple[str, str], int | None] = {}


async def _get_single_commute(
    origin: str,
    destination: str,
    mcp_url: str,
) -> int | None:
    """查询单个起点-终点的公共交通通勤时间。"""
    client = MultiServerMCPClient(
        {
            "amap": {
                "transport": "streamable_http",
                "url": mcp_url,
            }
        }
    )
    try:
        tools = await client.get_tools()
        tools_by_name = {t.name: t for t in tools}

        geo_tool = tools_by_name.get("maps_geo")
        transit_tool = tools_by_name.get("maps_direction_transit_integrated")

        if not geo_tool or not transit_tool:
            logger.warning("高德 MCP 未提供 maps_geo 或 maps_direction_transit_integrated 工具")
            return None

        # 地理编码：地址 → 经纬度
        origin_result = await geo_tool.ainvoke({"address": origin})
        dest_result = await geo_tool.ainvoke({"address": destination})

        origin_geos = origin_result.get("geocodes", [])
        dest_geos = dest_result.get("geocodes", [])
        if not origin_geos or not dest_geos:
            logger.warning("地址地理编码失败: %s → %s", origin, destination)
            return None

        origin_loc = origin_geos[0]["location"]
        dest_loc = dest_geos[0]["location"]

        # 公交路径规划
        route_result = await transit_tool.ainvoke(
            {
                "origin": origin_loc,
                "destination": dest_loc,
                "city": "",
                "cityd": "",
                "strategy": 0,  # 最快路线
            }
        )

        transits = route_result.get("route", {}).get("transits", [])
        if not transits:
            logger.warning("未找到公交路线: %s → %s", origin, destination)
            return None

        duration_seconds = transits[0].get("duration", 0)
        return max(1, int(duration_seconds // 60))

    except Exception as e:
        logger.warning("高德 MCP 查询失败 (%s → %s): %s", origin, destination, e)
        return None
    finally:
        await client.aclose()


async def batch_get_commute_minutes(
    pairs: list[tuple[str, str]],
    mcp_url: str | None = None,
) -> list[int | None]:
    """批量查询多组起点-终点的通勤时间。

    Args:
        pairs: [(origin, destination), ...]
        mcp_url: 高德 MCP 服务器 URL，默认从配置读取

    Returns:
        与输入等长的列表，每个元素为分钟数或 None（查询失败）
    """
    url = mcp_url or get_amap_mcp_url()
    results: list[int | None] = []
    for origin, dest in pairs:
        if not origin or not dest:
            results.append(None)
            continue
        key = (origin, dest)
        if key in _commute_cache:
            results.append(_commute_cache[key])
        else:
            minutes = await _get_single_commute(origin, dest, url)
            _commute_cache[key] = minutes
            results.append(minutes)
    return results