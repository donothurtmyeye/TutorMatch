from __future__ import annotations

import json
import os
from typing import Any

from tutormatch.models import MatchResult, TutoringOpportunity, TutorProfile


SYSTEM_PROMPT = """你是一个严谨的家教兼职机会筛选 Agent。
你需要根据老师偏好和家教机会信息，判断每个机会是否值得跟进。
请综合考虑科目、年级、区域、课酬、通勤、时间、授课方式、机会描述、风险关键词和沟通成本。
只输出 JSON，不要输出 Markdown、解释文字或代码块。"""

PARSE_PROMPT = """你是一个家教兼职机会信息解析器。
请将用户输入的原始文本解析为结构化的家教机会列表。
每个机会需要提取以下字段：
- id: 机会编号，优先使用原始文本中的编号（如 F090328A），若没有则用 "opp-序号"
- title: 简洁标题，如 "南山区三年级英语"
- subject: 科目（如 数学、英语、全科）
- grade: 年级（如 二年级、初二、五年级）
- district: 区域（如 南山、龙岗、宝安），从上课地址中提取
- hourly_rate: 课酬，取范围中间值（如 100-130 取 115）；如果只有下限则取下限
- commute_minutes: 通勤时间，默认 30
- days: 上课时间，如 ["周一", "周三", "周六"]
- mode: 授课方式，默认 "线下"
- description: 合并所有其他信息，包括学员情况、时间安排、老师要求等
- source: 固定为 "手动输入"
- full_address: 完整上课地址，从原始文本中的 【上课地址】 提取，保持原样

只输出 JSON 数组，不要输出 Markdown、解释文字或代码块。"""


def screen_opportunities_with_llm(
    profile: TutorProfile,
    opportunities: list[TutoringOpportunity],
    model_name: str,
) -> list[MatchResult]:
    model = _init_model(model_name)
    response = model.invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("human", _build_screening_prompt(profile, opportunities)),
        ]
    )
    content = _message_content_to_text(response.content)
    data = _parse_json(content)
    items = data.get("results", data)
    if not isinstance(items, list):
        raise ValueError("大模型输出格式错误：顶层应为数组，或包含 results 数组。")

    opportunity_by_id = {item.id: item for item in opportunities if item.id}
    opportunity_by_title = {item.title: item for item in opportunities}
    results: list[MatchResult] = []

    for raw in items:
        if not isinstance(raw, dict):
            continue
        opportunity = _resolve_opportunity(
            raw=raw,
            opportunity_by_id=opportunity_by_id,
            opportunity_by_title=opportunity_by_title,
        )
        if opportunity is None:
            continue
        results.append(_match_result_from_llm(raw, opportunity))

    if not results:
        raise ValueError("大模型没有返回可识别的筛选结果。")
    return results


def parse_opportunities_from_text(
    raw_text: str,
    model_name: str,
) -> list[TutoringOpportunity]:
    """将非结构化的原始文本解析为结构化的 TutoringOpportunity 列表。"""
    model = _init_model(model_name)
    response = model.invoke(
        [
            ("system", PARSE_PROMPT),
            ("human", raw_text),
        ]
    )
    content = _message_content_to_text(response.content)
    data = _parse_json(content)
    items = data if isinstance(data, list) else data.get("opportunities", data.get("results", []))
    if not isinstance(items, list):
        raise ValueError("大模型输出格式错误：解析结果应为数组。")

    opportunities: list[TutoringOpportunity] = []
    for i, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        opp = TutoringOpportunity.from_dict(
            {
                "id": str(raw.get("id", f"opp-{i + 1:03d}")),
                "title": str(raw.get("title", f"机会 {i + 1}")),
                "subject": str(raw.get("subject", "")),
                "grade": str(raw.get("grade", "")),
                "district": str(raw.get("district", "")),
                "hourly_rate": int(raw.get("hourly_rate", 0)),
                "commute_minutes": int(raw.get("commute_minutes", 30)),
                "days": raw.get("days", []),
                "mode": str(raw.get("mode", "线下")),
                "description": str(raw.get("description", "")),
                "source": str(raw.get("source", "手动输入")),
                "full_address": str(raw.get("full_address", "")),
            }
        )
        opportunities.append(opp)

    if not opportunities:
        raise ValueError("大模型没有解析出任何机会。")
    return opportunities


def _init_model(model_name: str):
    from langchain.chat_models import init_chat_model

    # config.py 已经将通用 API_KEY/BASE_URL 复制到各 provider 的环境变量中
    # （OPENAI_API_KEY, DEEPSEEK_API_KEY 等），LangChain 的 init_chat_model
    # 会自动读取对应环境变量，无需显式传递。
    return init_chat_model(model_name, temperature=0)


def _build_screening_prompt(
    profile: TutorProfile,
    opportunities: list[TutoringOpportunity],
) -> str:
    return json.dumps(
        {
            "task": "筛选并排序家教兼职机会",
            "teacher_profile": {
                "name": profile.name,
                "subjects": sorted(profile.subjects),
                "districts": sorted(profile.districts),
                "min_hourly_rate": profile.min_hourly_rate,
                "max_commute_minutes": profile.max_commute_minutes,
                "available_days": sorted(profile.available_days),
                "teaching_modes": sorted(profile.teaching_modes),
                "preferred_grades": sorted(profile.preferred_grades),
                "blocked_keywords": sorted(profile.blocked_keywords),
            },
            "opportunities": [
                {
                    "id": opportunity.id,
                    "title": opportunity.title,
                    "subject": opportunity.subject,
                    "grade": opportunity.grade,
                    "district": opportunity.district,
                    "hourly_rate": opportunity.hourly_rate,
                    "commute_minutes": opportunity.commute_minutes,
                    "days": sorted(opportunity.days),
                    "mode": opportunity.mode,
                    "description": opportunity.description,
                    "source": opportunity.source,
                    "full_address": opportunity.full_address,
                }
                for opportunity in opportunities
            ],
            "output_schema": {
                "results": [
                    {
                        "id": "机会 id，必须原样返回",
                        "score": "0 到 100 的整数",
                        "decision": "强推荐 / 可跟进 / 备选 / 不建议",
                        "summary": "一句话判断",
                        "reasons": ["匹配理由"],
                        "risks": ["风险提醒，没有则返回空数组"],
                        "questions_to_ask": ["联系前建议追问的问题"],
                        "next_action": "下一步建议",
                        "outreach_message": "可直接发给家长或中介的简短中文消息",
                    }
                ]
            },
            "rules": [
                "必须为每个机会返回一条结果。",
                "score 越高越值得优先跟进。",
                "如果存在押金、先交费、长期拖欠等风险，要明显降低评分。",
                "如果课酬低于底线、时间无交集或通勤明显超限，要在 risks 里说明。",
            ],
        },
        ensure_ascii=False,
    )


def _resolve_opportunity(
    raw: dict[str, Any],
    opportunity_by_id: dict[str, TutoringOpportunity],
    opportunity_by_title: dict[str, TutoringOpportunity],
) -> TutoringOpportunity | None:
    opportunity_id = str(raw.get("id", ""))
    if opportunity_id in opportunity_by_id:
        return opportunity_by_id[opportunity_id]

    title = str(raw.get("title", ""))
    if title in opportunity_by_title:
        return opportunity_by_title[title]

    return None


def _match_result_from_llm(
    raw: dict[str, Any],
    opportunity: TutoringOpportunity,
) -> MatchResult:
    return MatchResult(
        opportunity=opportunity,
        score=_score(raw.get("score")),
        decision=_decision(raw.get("decision")),
        reasons=_string_list(raw.get("reasons", [])),
        risks=_string_list(raw.get("risks", [])),
        next_action=str(raw.get("next_action", "")).strip() or "联系前先确认关键信息。",
        llm_summary=str(raw.get("summary", "")).strip(),
        llm_questions=_string_list(raw.get("questions_to_ask", [])),
        outreach_message=str(raw.get("outreach_message", "")).strip(),
    )


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _parse_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        candidates = [index for index in [text.find("{"), text.find("[")] if index != -1]
        if not candidates:
            raise
        start = min(candidates)
        end = max(text.rfind("}"), text.rfind("]"))
        if end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, parsed))


def _decision(value: Any) -> str:
    decision = str(value or "").strip()
    if decision in {"强推荐", "可跟进", "备选", "不建议"}:
        return decision
    return "备选"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
