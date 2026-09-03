from __future__ import annotations

from tutormatch.models import MatchResult


def render_markdown_report(
    results: list[MatchResult],
    limit: int | None = None,
) -> str:
    visible = results[:limit] if limit else results
    lines = [
        "# 家教兼职机会筛选报告",
        "",
        f"共筛选 {len(results)} 个机会，展示 {len(visible)} 个。",
        "",
    ]

    for index, result in enumerate(visible, start=1):
        opportunity = result.opportunity
        lines.extend(
            [
                f"## {index}. {opportunity.title}",
                "",
                f"- 评分：{result.score}/100",
                f"- 结论：{result.decision}",
                f"- 基本信息：{opportunity.subject} / {opportunity.grade} / {opportunity.district} / {opportunity.hourly_rate} 元/小时 / 通勤 {opportunity.commute_minutes} 分钟",
                f"- 来源：{opportunity.source}",
                "- 大模型判断：" + (result.llm_summary or "暂无补充"),
                "- 匹配理由：" + _join_or_default(result.reasons, "暂无明显匹配点"),
                "- 风险提醒：" + _join_or_default(result.risks, "暂无明显风险"),
                "- 建议追问："
                + _join_or_default(result.llm_questions, "暂无补充问题"),
                f"- 下一步：{result.next_action}",
            ]
        )
        if result.outreach_message:
            lines.append(f"- 联系话术：{result.outreach_message}")
        lines.append("")

    return "\n".join(lines)


def render_console_summary(
    results: list[MatchResult],
    limit: int | None = None,
) -> str:
    visible = results[:limit] if limit else results
    lines = []
    for index, result in enumerate(visible, start=1):
        opportunity = result.opportunity
        lines.append(
            f"{index}. [{result.decision}] {result.score}/100 - {opportunity.title} "
            f"({opportunity.subject}, {opportunity.district}, {opportunity.hourly_rate} 元/小时)"
        )
        if result.risks:
            lines.append(f"   风险：{'; '.join(result.risks)}")
        if result.llm_summary:
            lines.append(f"   大模型判断：{result.llm_summary}")
        if result.llm_questions:
            lines.append(f"   建议追问：{'; '.join(result.llm_questions)}")
        lines.append(f"   下一步：{result.next_action}")
    return "\n".join(lines)


def _join_or_default(items: list[str], default: str) -> str:
    if not items:
        return default
    return "；".join(items)
