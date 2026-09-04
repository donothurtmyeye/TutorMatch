from __future__ import annotations

import asyncio
import dataclasses
import logging
from pathlib import Path
from typing import TypedDict

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph

from tutormatch.amap_mcp import batch_get_commute_minutes
from tutormatch.llm import screen_opportunities_with_llm
from tutormatch.models import MatchResult, TutoringOpportunity, TutorProfile
from tutormatch.report import render_console_summary, render_markdown_report

logger = logging.getLogger(__name__)


class ScreeningState(TypedDict, total=False):
    profile: TutorProfile
    opportunities: list[TutoringOpportunity]
    top: int
    llm_model: str
    report_path: str
    results: list[MatchResult]
    markdown_report: str
    console_summary: str


def build_screening_agent():
    graph = StateGraph(ScreeningState)

    graph.add_node("fetch_commute_times", RunnableLambda(fetch_commute_times))
    graph.add_node("screen_with_llm", RunnableLambda(screen_with_llm))
    graph.add_node("write_report", RunnableLambda(write_report))

    graph.set_entry_point("fetch_commute_times")
    graph.add_edge("fetch_commute_times", "screen_with_llm")
    graph.add_edge("screen_with_llm", "write_report")
    graph.add_edge("write_report", END)

    return graph.compile()


def run_screening_agent(
    profile: TutorProfile,
    opportunities: list[TutoringOpportunity],
    report_path: str = "reports/screening_report.md",
    top: int = 5,
    llm_model: str = "openai:gpt-4o-mini",
) -> ScreeningState:
    agent = build_screening_agent()
    return agent.invoke(
        {
            "profile": profile,
            "opportunities": opportunities,
            "report_path": report_path,
            "top": top,
            "llm_model": llm_model,
        }
    )


def fetch_commute_times(state: ScreeningState) -> ScreeningState:
    """通过高德 MCP 查询每个机会的真实通勤时间，更新 commute_minutes。"""
    profile = state["profile"]
    opportunities = state["opportunities"]

    if not profile.home_address:
        logger.info("老师档案未设置起点地址，跳过 MCP 通勤查询")
        return state

    # 收集需要查询的地址对
    pairs: list[tuple[str, str]] = []
    for opp in opportunities:
        dest = opp.full_address or opp.district
        if dest:
            pairs.append((profile.home_address, dest))
        else:
            pairs.append(("", ""))

    if not pairs or all(not p[0] or not p[1] for p in pairs):
        logger.info("所有机会均无有效地址，跳过 MCP 通勤查询")
        return state

    print(f"\n正在查询 {len(pairs)} 个机会的真实通勤时间...")
    try:
        minutes_list = asyncio.run(batch_get_commute_minutes(pairs))
    except Exception as e:
        logger.warning("MCP 通勤查询失败: %s", e)
        print(f"通勤查询失败，使用估算值继续。")
        return state

    # 更新机会的通勤时间（frozen dataclass 需用 replace）
    updated: list[TutoringOpportunity] = []
    updated_count = 0
    for opp, minutes in zip(opportunities, minutes_list):
        if minutes is not None:
            updated.append(dataclasses.replace(opp, commute_minutes=minutes))
            updated_count += 1
            print(f"  {opp.title}: 通勤约 {minutes} 分钟")
        else:
            updated.append(opp)

    print(f"通勤时间查询完成，更新 {updated_count}/{len(opportunities)} 个机会。")
    return {**state, "opportunities": updated}


def screen_with_llm(state: ScreeningState) -> ScreeningState:
    results = screen_opportunities_with_llm(
        profile=state["profile"],
        opportunities=state["opportunities"],
        model_name=state.get("llm_model", "openai:gpt-4o-mini"),
    )
    results = sorted(
        results,
        key=lambda item: (item.score, item.opportunity.hourly_rate),
        reverse=True,
    )
    return {**state, "results": results}


def write_report(state: ScreeningState) -> ScreeningState:
    report_path = Path(state["report_path"])
    top = state.get("top", 5)
    results = state["results"]

    markdown_report = render_markdown_report(results, limit=top)
    console_summary = render_console_summary(results, limit=top)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown_report, encoding="utf-8")

    return {
        **state,
        "markdown_report": markdown_report,
        "console_summary": console_summary,
    }
