from __future__ import annotations

import json
from pathlib import Path

from tutormatch.agent import run_screening_agent
from tutormatch.config import get_default_model
from tutormatch.llm import parse_opportunities_from_text
from tutormatch.models import TutoringOpportunity, TutorProfile


PROFILE_CACHE = Path("profile.json")


def _prompt(prompt_text: str, default: str = "") -> str:
    text = input(f"{prompt_text} ").strip()
    return text if text else default


def _split_input(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _parse_minutes(text: str) -> int:
    """解析中文时间文本为分钟数。

    支持格式：
    - "两个小时"、 "2小时"、"2小时30分钟" → 分钟数
    - "120"、"120分钟" → 分钟数
    - 默认回退到 45
    """
    import re
    text = text.strip().replace(" ", "")
    if not text:
        return 45
    # 纯数字 → 直接返回（视为分钟）
    if text.isdigit():
        return int(text)
    # 中文数字转阿拉伯数字
    cn_map = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
              "半": 0.5}
    # 匹配 "X小时" 或 "X小时Y分钟" 或 "X小时Y分"
    pattern = r"(?:(\d+(?:\.\d+)?|[一二两三四五六七八九十半]+))小(?:时|钟)(?:(\d+(?:\.\d+)?|[一二两三四五六七八九十]+)分(?:钟)?)?"
    m = re.search(pattern, text)
    if m:
        hours_str = m.group(1)
        mins_str = m.group(2)
        hours = cn_map.get(hours_str, float(hours_str)) if hours_str in cn_map else float(hours_str)
        minutes = 0
        if mins_str:
            minutes = cn_map.get(mins_str, int(mins_str)) if mins_str in cn_map else int(mins_str)
        return int(hours * 60 + minutes)
    # 匹配 "X分钟"
    m = re.search(r"(\d+)分(?:钟)?", text)
    if m:
        return int(m.group(1))
    # 匹配 "Xh" 或 "Xmin"
    m = re.search(r"(\d+(?:\.\d+)?)\s*h", text)
    if m:
        return int(float(m.group(1)) * 60)
    # 纯中文 "两小时" 等（无数字）
    for cn, num in [("两", 2), ("一", 1), ("三", 3), ("四", 4), ("五", 5)]:
        if f"{cn}小时" in text:
            return num * 60
    # 兜底尝试 int
    try:
        return int(text)
    except ValueError:
        return 45


def load_cached_profile() -> TutorProfile | None:
    if not PROFILE_CACHE.exists():
        return None
    try:
        data = json.loads(PROFILE_CACHE.read_text(encoding="utf-8"))
        return TutorProfile.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def save_profile_cache(profile: TutorProfile) -> None:
    data = {
        "name": profile.name,
        "subjects": sorted(profile.subjects),
        "districts": sorted(profile.districts),
        "min_hourly_rate": profile.min_hourly_rate,
        "max_commute_minutes": profile.max_commute_minutes,
        "available_days": sorted(profile.available_days),
        "teaching_modes": sorted(profile.teaching_modes),
        "preferred_grades": sorted(profile.preferred_grades),
        "blocked_keywords": sorted(profile.blocked_keywords),
        "home_address": profile.home_address,
    }
    PROFILE_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"老师档案已保存到 {PROFILE_CACHE}，下次运行会自动读取。")


def collect_profile() -> TutorProfile:
    print("\n===== 老师档案 =====")
    name = _prompt("姓名:", "候选老师")
    subjects = _split_input(_prompt("科目 (逗号分隔):", "数学,英语,物理"))
    districts = _split_input(_prompt("区域 (逗号分隔):", "徐汇,静安,黄浦,线上"))
    # 最低时薪支持纯数字输入
    min_hourly_rate_input = _prompt("最低时薪:", "180")
    try:
        min_hourly_rate = int(min_hourly_rate_input)
    except ValueError:
        min_hourly_rate = 180
    # 最长通勤时间支持中文时间格式（如 两个小时）
    max_commute_input = _prompt("最长通勤时间:", "45分钟")
    max_commute_minutes = _parse_minutes(max_commute_input)
    home_address = _prompt("起点地址（如: 深圳坪山区XX路XX号）:", "深圳坪山区")
    available_days = _split_input(_prompt("可授课时间 (逗号分隔):", "周二,周四,周六,周日"))
    teaching_modes = _split_input(_prompt("授课方式 (逗号分隔):", "线下,线上"))
    preferred_grades = _split_input(_prompt("期望年级 (逗号分隔):", "初中,高中"))
    blocked_keywords = _split_input(_prompt("屏蔽关键词 (逗号分隔):", "押金,先交费,长期拖欠"))
    profile = TutorProfile.from_dict(
        {
            "name": name,
            "subjects": subjects,
            "districts": districts,
            "min_hourly_rate": min_hourly_rate,
            "max_commute_minutes": max_commute_minutes,
            "available_days": available_days,
            "teaching_modes": teaching_modes,
            "preferred_grades": preferred_grades,
            "blocked_keywords": blocked_keywords,
            "home_address": home_address,
        }
    )
    save_profile_cache(profile)
    return profile


def collect_raw_text() -> str:
    print("\n===== 批量粘贴家教机会 =====")
    print("请粘贴所有机会文本，粘贴完成后在新行输入 ---end--- 结束：")
    print("=" * 50)
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "---end---":
            break
        lines.append(line)
    return "\n".join(lines)


def collect_opportunities() -> list[TutoringOpportunity]:
    from tutormatch.config import get_default_model

    raw_text = collect_raw_text()
    if not raw_text.strip():
        print("未输入任何内容，退出。")
        return []

    model = get_default_model()
    print(f"\n正在用 AI 解析机会文本（模型: {model}）...")
    opportunities = parse_opportunities_from_text(raw_text, model)
    print(f"解析完成，共识别到 {len(opportunities)} 个机会：")
    for opp in opportunities:
        print(f"  - {opp.id}: {opp.title} | {opp.subject} | {opp.grade} | {opp.district} | {opp.hourly_rate}/h")
    return opportunities


def run_interactive(top: int = 5, model: str | None = None) -> None:
    print("===== TutorMatch 交互式筛选 =====")
    # 尝试读取缓存的老师档案
    cached_profile = load_cached_profile()
    if cached_profile:
        print(f"已读取缓存的老师档案：{cached_profile.name}")
        print(f"  科目: {', '.join(sorted(cached_profile.subjects))}")
        print(f"  区域: {', '.join(sorted(cached_profile.districts))}")
        print(f"  最低时薪: {cached_profile.min_hourly_rate}")
        if cached_profile.home_address:
            print(f"  起点地址: {cached_profile.home_address}")
        print()
        refresh = _prompt("是否重新输入老师档案？(y/N):", "n")
        if refresh.lower() != "y" and refresh.lower() != "yes":
            profile = cached_profile
        else:
            profile = collect_profile()
    else:
        profile = collect_profile()

    opportunities = collect_opportunities()
    if not opportunities:
        print("未输入任何机会，退出。")
        return

    if model is None:
        model = get_default_model()

    state = run_screening_agent(
        profile=profile,
        opportunities=opportunities,
        top=top,
        llm_model=model,
    )

    print(f"\n{profile.name} 的家教兼职机会筛选完成。")
    print(state["console_summary"])
    print(f"\n完整报告已生成：{state['report_path']}")
