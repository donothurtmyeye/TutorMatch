import streamlit as st
from pathlib import Path

from tutormatch.config import get_default_model, load_runtime_config

# 加载 .env 环境变量（API_KEY / BASE_URL 等）
load_runtime_config()

from tutormatch.models import TutorProfile, TutoringOpportunity
from tutormatch.llm import parse_opportunities_from_text
from tutormatch.agent import run_screening_agent
from tutormatch.interactive import load_cached_profile, save_profile_cache, _parse_minutes, _split_input

st.set_page_config(
    page_title="TutorMatch 家教筛选",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Session State
# ============================================================
if "profile" not in st.session_state:
    st.session_state.profile = load_cached_profile()
if "results" not in st.session_state:
    st.session_state.results = None
if "edit_profile" not in st.session_state:
    st.session_state.edit_profile = False
if "opportunities_text" not in st.session_state:
    st.session_state.opportunities_text = ""
if "processing" not in st.session_state:
    st.session_state.processing = False
if "parsed_opportunities" not in st.session_state:
    st.session_state.parsed_opportunities = None

# ============================================================
# 侧边栏：老师档案
# ============================================================
with st.sidebar:
    st.header("📋 老师档案")

    profile = st.session_state.profile

    if profile and not st.session_state.edit_profile:
        st.markdown(f"**姓名**: {profile.name}")
        st.markdown(f"**科目**: {', '.join(profile.subjects)}")
        st.markdown(f"**区域**: {', '.join(profile.districts)}")
        st.markdown(f"**最低时薪**: {profile.min_hourly_rate} 元/小时")
        st.markdown(f"**最长通勤**: {profile.max_commute_minutes} 分钟")
        st.markdown(f"**起点地址**: {profile.home_address or '（未设置）'}")
        if profile.blocked_keywords:
            st.markdown(f"**屏蔽关键词**: {', '.join(profile.blocked_keywords)}")

        if st.button("✏️ 编辑档案", use_container_width=True):
            st.session_state.edit_profile = True
            st.rerun()

    if not profile or st.session_state.edit_profile:
        with st.form("profile_form", clear_on_submit=False):
            default = profile if profile else TutorProfile.from_dict({})
            name = st.text_input("姓名", value=default.name)
            subjects = st.text_input("科目（逗号分隔）", value=", ".join(default.subjects))
            districts = st.text_input("区域（逗号分隔）", value=", ".join(default.districts))
            min_rate = st.number_input("最低时薪", min_value=0, value=default.min_hourly_rate, step=10)
            commute = st.text_input("最长通勤时间", value=f"{default.max_commute_minutes}分钟")
            home_addr = st.text_input("起点地址", value=default.home_address)
            days = st.text_input("可授课时间（逗号分隔）", value=", ".join(default.available_days))
            modes = st.text_input("授课方式（逗号分隔）", value=", ".join(default.teaching_modes))
            grades = st.text_input("期望年级（逗号分隔）", value=", ".join(default.preferred_grades))
            keywords = st.text_input("屏蔽关键词（逗号分隔）", value=", ".join(default.blocked_keywords))

            col1, col2 = st.columns(2)
            with col1:
                saved = st.form_submit_button("💾 保存", use_container_width=True, type="primary")
            with col2:
                canceled = st.form_submit_button("取消", use_container_width=True)

            if saved:
                new_profile = TutorProfile.from_dict({
                    "name": name,
                    "subjects": _split_input(subjects),
                    "districts": _split_input(districts),
                    "min_hourly_rate": int(min_rate),
                    "max_commute_minutes": _parse_minutes(commute),
                    "home_address": home_addr,
                    "available_days": _split_input(days),
                    "teaching_modes": _split_input(modes),
                    "preferred_grades": _split_input(grades),
                    "blocked_keywords": _split_input(keywords),
                })
                st.session_state.profile = new_profile
                save_profile_cache(new_profile)
                st.session_state.edit_profile = False
                st.rerun()
            if canceled:
                st.session_state.edit_profile = False
                st.rerun()

# ============================================================
# 主区域
# ============================================================
st.title("🔍 TutorMatch 家教兼职机会筛选")
st.caption("粘贴家教机会文本 → AI 自动解析 → 高德 MCP 查通勤时间 → LLM 评分排序 → 生成报告")

# 顶部配置栏
config_col1, config_col2 = st.columns([2, 1])
with config_col1:
    model_name = st.text_input(
        "模型",
        value=get_default_model(),
        help="格式: provider:model-name，如 openai:gpt-4o-mini",
    )
with config_col2:
    top_n = st.number_input(
        "Top N 结果",
        min_value=1,
        max_value=50,
        value=5,
        help="展示评分最高的前 N 个机会",
    )

# 机会输入
st.subheader("📝 粘贴家教机会")
opportunities_text = st.text_area(
    "将家教机会文本粘贴到下方",
    value=st.session_state.opportunities_text,
    height=300,
    placeholder="示例：\n深圳F090328A\n【上课地址】：龙岗区XXXX\n【年级科目】：二年级全科\n【老师课费】：100-130/h\n\n把全部机会文本粘贴进来即可，然后点击下方的「开始筛选」",
    label_visibility="collapsed",
)

# 操作按钮
btn_col1, btn_col2, _ = st.columns([1, 1, 4])
with btn_col1:
    run_btn = st.button(
        "🚀 开始筛选",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.processing or not opportunities_text.strip(),
    )
with btn_col2:
    if st.session_state.results:
        if st.button("🔄 重新筛选", use_container_width=True):
            st.session_state.results = None
            st.session_state.parsed_opportunities = None
            st.rerun()

# 显示已解析的机会（如果有）
if st.session_state.parsed_opportunities and not st.session_state.processing:
    opps = st.session_state.parsed_opportunities
    with st.expander(f"📋 已识别 {len(opps)} 个机会", expanded=False):
        for opp in opps:
            st.markdown(
                f"- **{opp.id}**: {opp.title} | {opp.subject} | {opp.grade} | "
                f"{opp.district} | {opp.hourly_rate}/h | {opp.mode}"
            )

# ============================================================
# 筛选处理
# ============================================================
if run_btn and not st.session_state.processing:
    st.session_state.opportunities_text = opportunities_text
    st.session_state.processing = True
    st.session_state.results = None
    st.session_state.parsed_opportunities = None
    st.rerun()

if st.session_state.processing:
    profile = st.session_state.profile
    if not profile:
        st.error("❌ 请先在侧边栏填写老师档案")
        st.session_state.processing = False
        st.stop()

    # 用 status 容器显示进度
    status = st.status("准备中...", expanded=True)
    progress_bar = st.progress(0, text="准备中...")

    try:
        # Step 1: AI 解析机会文本
        status.update(label="📖 正在用 AI 解析机会文本...", state="running")
        opportunities = parse_opportunities_from_text(
            st.session_state.opportunities_text, model_name
        )
        progress_bar.progress(0.25, text=f"解析完成，识别到 {len(opportunities)} 个机会")

        if not opportunities:
            raise ValueError("未识别到任何机会，请检查输入文本格式")

        st.session_state.parsed_opportunities = opportunities
        status.write(f"✅ 识别到 {len(opportunities)} 个机会")

        # Step 2: 运行筛选 Agent（MCP 通勤 + LLM 评分 + 报告）
        status.update(
            label="🤖 正在筛选（查询通勤时间 → LLM 评分排序 → 生成报告）",
            state="running",
        )
        progress_bar.progress(0.5, text="正在查询通勤时间并筛选...")

        state = run_screening_agent(
            profile=profile,
            opportunities=opportunities,
            top=top_n,
            llm_model=model_name,
        )

        progress_bar.progress(0.9, text="筛选完成，生成报告...")
        st.session_state.results = state

        progress_bar.progress(1.0, text="✅ 完成！")
        status.update(label="✅ 筛选完成！", state="complete", expanded=False)

    except Exception as e:
        status.update(label="❌ 筛选过程出错", state="error")
        st.exception(e)
    finally:
        st.session_state.processing = False

# ============================================================
# 显示结果
# ============================================================
if st.session_state.results and not st.session_state.processing:
    state = st.session_state.results
    opportunities = state["opportunities"]
    results = state["results"]
    report_path = state.get("report_path")

    # 统计信息
    total = len(results)
    top_results = results[:top_n]
    st.subheader(f"📊 筛选结果（共 {total} 个，展示 Top {len(top_results)}）")

    # 表格概览
    table_data = []
    for i, r in enumerate(top_results, 1):
        opp = r.opportunity
        score_emoji = "🟢" if r.score >= 80 else ("🟡" if r.score >= 60 else "🔴")
        table_data.append({
            "排名": i,
            "评分": f"{score_emoji} {r.score}/100",
            "结论": r.decision,
            "标题": opp.title,
            "科目": opp.subject,
            "年级": opp.grade,
            "区域": opp.district,
            "时薪": f"{opp.hourly_rate}/h",
            "通勤": f"{opp.commute_minutes}分钟",
            "来源": opp.source,
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)

    # 详细卡片
    for i, r in enumerate(top_results, 1):
        opp = r.opportunity
        with st.container(border=True):
            cols = st.columns([1, 12])
            with cols[0]:
                score_color = (
                    "#00a67e" if r.score >= 80
                    else "#e6a700" if r.score >= 60
                    else "#d32f2f"
                )
                st.markdown(
                    f"<div style='text-align:center; font-size:2rem; "
                    f"font-weight:bold; color:{score_color};'>{i}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center; color:{score_color};'>"
                    f"{r.score}/100</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                cols_inner = st.columns([3, 1, 1])
                with cols_inner[0]:
                    st.markdown(f"**{opp.title}**")
                with cols_inner[1]:
                    st.markdown(f"**{r.decision}**")
                with cols_inner[2]:
                    st.markdown(f"🚇 {opp.commute_minutes}分钟")

                tab1, tab2, tab3, tab4 = st.tabs(["基本信息", "匹配分析", "风险提示", "联系话术"])

                with tab1:
                    st.markdown(
                        f"- **科目**: {opp.subject}  |  **年级**: {opp.grade}  "
                        f"|  **区域**: {opp.district}"
                    )
                    st.markdown(
                        f"- **时薪**: {opp.hourly_rate}/h  |  **上课方式**: {opp.mode}  "
                        f"|  **来源**: {opp.source}"
                    )
                    if opp.full_address:
                        st.markdown(f"- **地址**: {opp.full_address}")
                    if opp.days:
                        st.markdown(f"- **上课时间**: {', '.join(opp.days)}")

                with tab2:
                    if r.reasons:
                        for reason in r.reasons:
                            st.markdown(f"- ✅ {reason}")
                    else:
                        st.markdown("暂无明显匹配点")
                    if r.llm_summary:
                        st.divider()
                        st.markdown(f"**大模型判断**: {r.llm_summary}")
                    if r.llm_questions:
                        st.divider()
                        for q in r.llm_questions:
                            st.markdown(f"- ❓ {q}")

                with tab3:
                    if r.risks:
                        for risk in r.risks:
                            st.markdown(f"- ⚠️ {risk}")
                    else:
                        st.markdown("暂无明显风险")

                with tab4:
                    if r.next_action:
                        st.markdown(f"**下一步**: {r.next_action}")
                    if r.outreach_message:
                        st.divider()
                        st.markdown(f"**话术建议**:")
                        st.info(r.outreach_message)

    # 完整报告
    if report_path and Path(report_path).exists():
        with st.expander("📄 查看完整 Markdown 报告"):
            report_content = Path(report_path).read_text(encoding="utf-8")
            st.markdown(report_content, unsafe_allow_html=True)

    # 终端摘要
    with st.expander("💻 终端摘要"):
        console_summary = state.get("console_summary", "")
        st.code(console_summary, language="text")