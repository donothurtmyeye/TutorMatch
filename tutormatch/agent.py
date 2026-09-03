from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph

from tutormatch.llm import screen_opportunities_with_llm
from tutormatch.models import MatchResult, TutoringOpportunity, TutorProfile
from tutormatch.report import render_console_summary, render_markdown_report


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

    graph.add_node("screen_with_llm", RunnableLambda(screen_with_llm))
    graph.add_node("write_report", RunnableLambda(write_report))

    graph.set_entry_point("screen_with_llm")
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
