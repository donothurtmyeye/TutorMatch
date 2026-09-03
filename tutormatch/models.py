from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TutorProfile:
    name: str
    subjects: set[str]
    districts: set[str]
    min_hourly_rate: int
    max_commute_minutes: int
    available_days: set[str]
    teaching_modes: set[str]
    preferred_grades: set[str] = field(default_factory=set)
    blocked_keywords: set[str] = field(default_factory=set)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TutorProfile":
        return cls(
            name=str(data.get("name", "候选老师")),
            subjects=_lower_set(data.get("subjects", [])),
            districts=_lower_set(data.get("districts", [])),
            min_hourly_rate=int(data.get("min_hourly_rate", 0)),
            max_commute_minutes=int(data.get("max_commute_minutes", 90)),
            available_days=_lower_set(data.get("available_days", [])),
            teaching_modes=_lower_set(data.get("teaching_modes", [])),
            preferred_grades=_lower_set(data.get("preferred_grades", [])),
            blocked_keywords=_lower_set(data.get("blocked_keywords", [])),
        )


@dataclass(frozen=True)
class TutoringOpportunity:
    id: str
    title: str
    subject: str
    grade: str
    district: str
    hourly_rate: int
    commute_minutes: int
    days: set[str]
    mode: str
    description: str
    source: str = "manual"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TutoringOpportunity":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "未命名机会")),
            subject=str(data.get("subject", "")).lower(),
            grade=str(data.get("grade", "")).lower(),
            district=str(data.get("district", "")).lower(),
            hourly_rate=int(data.get("hourly_rate", 0)),
            commute_minutes=int(data.get("commute_minutes", 999)),
            days=_lower_set(data.get("days", [])),
            mode=str(data.get("mode", "")).lower(),
            description=str(data.get("description", "")),
            source=str(data.get("source", "manual")),
        )


@dataclass(frozen=True)
class MatchResult:
    opportunity: TutoringOpportunity
    score: int
    decision: str
    reasons: list[str]
    risks: list[str]
    next_action: str
    llm_summary: str = ""
    llm_questions: list[str] = field(default_factory=list)
    outreach_message: str = ""


def _lower_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.lower()}
    return {str(item).lower() for item in value}
