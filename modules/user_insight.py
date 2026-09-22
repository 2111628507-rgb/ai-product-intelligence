"""用户洞察模块：从用户反馈中提炼痛点、需求、情绪、场景与产品机会。"""

from __future__ import annotations

import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services import llm_service
from utils import analytics, ui
from utils.data_loader import append_feedback, load_feedback, next_feedback_id

PLOT_CONFIG = {"displayModeBar": False}


def _bar_chart(categories, values, color: str, text_suffix: str = "") -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=values,
            y=categories,
            orientation="h",
            marker=dict(color=color, cornerradius=4),
            text=[f"{v}{text_suffix}" for v in values],
            textposition="outside",
            textfont=dict(size=11, color="#475569"),
            hovertemplate="%{y}：%{x}" + text_suffix + "<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        margin=dict(l=10, r=40, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='-apple-system, "Microsoft YaHei", sans-serif', size=12, color="#475569"),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef1f6", zeroline=False)
    fig.update_yaxes(showgrid=False)
    return fig


def _donut(labels, values) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker=dict(colors=["#2f5bff", "#6b8bff", "#9db2ff", "#c8d4ff", "#e6ebff", "#f0f3ff"]),
            textinfo="percent",
            textfont=dict(size=11),
            hovertemplate="%{label}：%{value} 条（%{percent}）<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family='-apple-system, "Microsoft YaHei", sans-serif', size=12, color="#475569"),
        showlegend=True,
        legend=dict(orientation="v", x=1, y=0.5, font=dict(size=11)),
    )
    return fig


def _feedback_intake(feedback) -> None:
    """支持手动录入单条反馈，以及批量导入 CSV。"""
    user_type_options = sorted(feedback["user_type"].unique().tolist())
    scene_options = sorted(feedback["scene"].unique().tolist())
    feature_options = sorted(feedback["feature"].unique().tolist())
    category_options = ["自动识别"] + sorted(feedback["issue_category"].unique().tolist())

    tab_manual, tab_batch = st.tabs(["手动录入单条", "批量导入 CSV"])

    with tab_manual:
        with st.form("add_feedback", clear_on_submit=True):
            text = st.text_area(
                "反馈内容",
                height=80,
                placeholder="例如：回答本身没问题，就是太长了，我只想要一个结论",
            )
            col1, col2, col3 = st.columns(3)
            rating = col1.slider("评分（1-5）", 1, 5, 4)
            user_type = col2.selectbox("用户类型", user_type_options)
            scene = col3.selectbox("使用场景", scene_options)
            col4, col5 = st.columns(2)
            feature = col4.selectbox("功能模块", feature_options)
            category = col5.selectbox("问题类型", category_options)
            submitted = st.form_submit_button("录入反馈", type="primary")

        if submitted:
            if not text or not text.strip():
                st.error("反馈内容不能为空。")
            else:
                content = text.strip()
                final_category = (
                    analytics.classify_feedback(content) if category == "自动识别" else category
                )
                row = {
                    "feedback_id": f"F{next_feedback_id()}",
                    "user_id": f"MANUAL-{pd.Timestamp.now().strftime('%H%M%S')}",
                    "date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                    "user_type": user_type,
                    "scene": scene,
                    "feature": feature,
                    "feedback": content,
                    "issue_category": final_category,
                    "rating": rating,
                    "session_duration": 300,
                    "retention": 1 if rating >= 4 else 0,
                    "is_new_user": 0,
                }
                added, duplicated = append_feedback([row])
                if added:
                    st.success(f"已录入反馈，自动归类为「{final_category}」（评分 {rating} 分）。")
                    st.rerun()
                else:
                    st.warning("这条反馈已经存在，未重复写入。")

    with tab_batch:
        st.caption("必需列：feedback、rating；可选列：user_type、scene、feature、issue_category、date。缺失列会自动补默认值，问题类型留空时自动识别。")
        uploaded = st.file_uploader("上传反馈 CSV 文件", type=["csv"])
        if uploaded is not None:
            try:
                raw = uploaded.getvalue()
                try:
                    preview = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
                except UnicodeDecodeError:
                    preview = pd.read_csv(io.BytesIO(raw), encoding="gbk")
            except Exception as exc:  # noqa: BLE001
                st.error(f"文件读取失败：{exc}")
                preview = None

            if preview is not None:
                missing = [c for c in ["feedback", "rating"] if c not in preview.columns]
                if missing:
                    st.error(f"缺少必需列：{', '.join(missing)}")
                else:
                    st.caption(f"共读取到 {len(preview)} 条反馈，预览前 5 条：")
                    st.dataframe(preview.head(5), width="stretch", hide_index=True)
                    if st.button("确认导入", type="primary"):
                        rows = []
                        base_id = int(next_feedback_id())
                        for i, item in enumerate(preview.to_dict("records")):
                            content = str(item.get("feedback", "")).strip()
                            if not content:
                                continue
                            try:
                                score = int(float(item.get("rating", 4)))
                            except (TypeError, ValueError):
                                score = 4
                            score = max(1, min(5, score))
                            category = str(item.get("issue_category") or "").strip()
                            if not category or category.lower() == "nan":
                                category = analytics.classify_feedback(content)
                            rows.append(
                                {
                                    "feedback_id": f"F{base_id + i}",
                                    "user_id": str(item.get("user_id") or f"IMPORT-{i + 1}"),
                                    "date": str(item.get("date") or pd.Timestamp.now().strftime("%Y-%m-%d")),
                                    "user_type": str(item.get("user_type") or "职场用户"),
                                    "scene": str(item.get("scene") or "办公"),
                                    "feature": str(item.get("feature") or "对话问答"),
                                    "feedback": content,
                                    "issue_category": category,
                                    "rating": score,
                                    "session_duration": int(item.get("session_duration") or 300),
                                    "retention": 1 if score >= 4 else 0,
                                    "is_new_user": int(item.get("is_new_user") or 0),
                                }
                            )
                        if not rows:
                            st.warning("没有可导入的有效数据。")
                        else:
                            added, duplicated = append_feedback(rows)
                            st.success(f"已导入 {added} 条反馈，跳过重复 {duplicated} 条。")
                            st.rerun()

        template = pd.DataFrame(
            [
                {
                    "feedback": "回答太长了，我只想要一个结论",
                    "rating": 3,
                    "user_type": "职场用户",
                    "scene": "办公",
                    "feature": "对话问答",
                    "issue_category": "",
                    "date": "",
                },
                {
                    "feedback": "生成速度有点慢，等了半分钟",
                    "rating": 2,
                    "user_type": "学生",
                    "scene": "学习",
                    "feature": "内容生成",
                    "issue_category": "",
                    "date": "",
                },
            ]
        )
        st.download_button(
            "下载 CSV 模板",
            template.to_csv(index=False).encode("utf-8-sig"),
            file_name="feedback_template.csv",
            mime="text/csv",
        )

    ui.note(
        "录入的反馈会直接写入 data/feedback.csv，与本页的统计、图表和 AI 洞察用的是同一份数据；"
        "完全相同的反馈内容会自动去重。如果需要恢复初始数据，使用侧边栏「数据与设置 → 重新生成模拟数据」。"
    )


def render() -> None:
    feedback = load_feedback()
    ui.page_header("用户洞察", "把零散的用户反馈，转成可决策的产品洞察")

    filters = st.columns([1.2, 1.2, 1])
    with filters[0]:
        user_types = st.multiselect(
            "用户类型", sorted(feedback["user_type"].unique()), placeholder="全部用户类型"
        )
    with filters[1]:
        scenes = st.multiselect("使用场景", sorted(feedback["scene"].unique()), placeholder="全部场景")
    with filters[2]:
        rating_range = st.selectbox("评分范围", ["全部", "仅负面（≤2 分）", "仅正面（≥4 分）"])

    view = feedback.copy()
    if user_types:
        view = view[view["user_type"].isin(user_types)]
    if scenes:
        view = view[view["scene"].isin(scenes)]
    if rating_range.startswith("仅负面"):
        view = view[view["rating"] <= 2]
    elif rating_range.startswith("仅正面"):
        view = view[view["rating"] >= 4]

    if view.empty:
        st.warning("当前筛选条件下没有反馈数据，请调整筛选条件。")
        return

    overview = analytics.feedback_overview(view)
    ui.kpi_row(
        [
            {
                "label": "反馈总量",
                "value": f"{overview['total']:,}",
                "delta": f"覆盖 {view['user_id'].nunique():,} 名用户",
                "direction": "flat",
                "hint": "近 30 天收集",
            },
            {
                "label": "用户满意度",
                "value": f"{overview['avg_rating']:.2f}/5",
                "delta": f"正面反馈占比 {overview['positive_rate']:.1f}%",
                "direction": "up" if overview["avg_rating"] >= 4 else "flat",
                "hint": "评分均值",
            },
            {
                "label": "负面反馈率",
                "value": f"{overview['negative_rate']:.1f}%",
                "delta": f"{overview['negative_count']} 条 ≤2 分反馈",
                "direction": "down" if overview["negative_rate"] < 20 else "flat",
                "hint": "行业参考：低于 20% 属于健康区间",
            },
            {
                "label": "平均会话时长",
                "value": f"{overview['avg_duration'] / 60:.1f} 分钟",
                "delta": "单次会话平均停留",
                "direction": "flat",
                "hint": "用于判断使用深度",
            },
        ]
    )

    ui.section("高频问题分布", "按反馈中的问题类型聚类")
    categories = analytics.category_stats(view)
    left, right = st.columns([1.15, 1])
    with left:
        st.plotly_chart(
            _bar_chart(categories["issue_category"], categories["count"].tolist(), "#2f5bff", " 条"),
            width="stretch",
            config=PLOT_CONFIG,
        )
    with right:
        st.markdown("**各类型负面反馈率**")
        st.plotly_chart(
            _bar_chart(
                categories["issue_category"],
                categories["negative_rate"].tolist(),
                "#f79009",
                "%",
            ),
            width="stretch",
            config=PLOT_CONFIG,
        )

    with st.expander("查看反馈明细数据"):
        st.dataframe(
            view[
                [
                    "date",
                    "user_id",
                    "user_type",
                    "scene",
                    "feature",
                    "feedback",
                    "issue_category",
                    "rating",
                ]
            ].sort_values("date", ascending=False),
            width="stretch",
            height=320,
        )

    ui.section("AI 用户洞察", "点击后由 AI 结合反馈统计数据生成洞察结论")
    left_btn, right_tag = st.columns([1, 4])
    with left_btn:
        run = st.button("开始分析", type="primary", width="stretch")
    status = llm_service.get_status()
    with right_tag:
        mode_text = (
            f"分析引擎：{status.provider} · {status.model}"
            if status.is_live
            else "分析引擎：本地 Mock（未配置 API Key 时同样可完整演示）"
        )
        ui.mode_tag(status.mode, mode_text)

    if run:
        with st.spinner("正在分析用户反馈..."):
            st.session_state["insight_result"] = llm_service.analyze_feedback(view)
            st.session_state["insight_scope"] = overview["total"]

    result = st.session_state.get("insight_result")
    if result:
        if result.get("error"):
            st.warning(result["error"])
        if st.session_state.get("insight_scope") != overview["total"]:
            st.info("筛选条件已变化，点击「开始分析」可重新生成当前范围的洞察。")

        row1 = st.columns(3)
        with row1[0]:
            ui.insight_card("高频用户痛点", result.get("pain_points", []))
        with row1[1]:
            ui.insight_card("用户核心需求", result.get("needs", []))
        with row1[2]:
            ui.insight_card("用户情绪", result.get("emotions", []))
        st.write("")
        row2 = st.columns(2)
        with row2[0]:
            ui.insight_card("使用场景", result.get("scenes", []))
        with row2[1]:
            ui.insight_card("潜在产品机会", result.get("opportunities", []))
    else:
        ui.note("提示：分析会读取当前筛选范围内的反馈数据。未配置 API Key 时会使用本地分析引擎，结论依然基于真实统计数据生成。")

    ui.section("录入反馈", "把新的用户反馈录入进来，立刻用同一套分析流程看结果")
    _feedback_intake(feedback)