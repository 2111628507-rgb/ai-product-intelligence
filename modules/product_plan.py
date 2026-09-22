"""产品方案模块：需求优先级（RICE）与产品方案生成。"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from services import llm_service
from utils import analytics, ui
from utils.data_loader import load_feedback, load_metrics, load_requirements

PLOT_CONFIG = {"displayModeBar": False}

RICE_DEFINITION = {
    "Reach": "影响多少用户（1-10，越高影响面越大）",
    "Impact": "对目标指标的影响程度（1-10）",
    "Confidence": "对判断的把握程度（0-1）",
    "Effort": "研发成本（人日或相对工作量）",
}


def _rice_chart(df) -> go.Figure:
    ordered = df.sort_values("rice_score")
    colors = {"P0": "#d92d20", "P1": "#f79009", "P2": "#2f5bff", "P3": "#94a3b8"}
    fig = go.Figure(
        go.Bar(
            x=ordered["rice_score"],
            y=ordered["name"],
            orientation="h",
            marker=dict(color=[colors.get(p, "#94a3b8") for p in ordered["priority"]], cornerradius=4),
            text=[f"{s:.1f}（{p}）" for s, p in zip(ordered["rice_score"], ordered["priority"])],
            textposition="outside",
            textfont=dict(size=11, color="#475569"),
            hovertemplate="%{y}：RICE %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=70, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='-apple-system, "Microsoft YaHei", sans-serif', size=12, color="#475569"),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef1f6", zeroline=False, title="RICE 得分")
    fig.update_yaxes(showgrid=False)
    return fig


def _priority_table(df):
    view = df[
        ["priority", "name", "reach", "impact", "confidence", "effort", "rice_score", "status"]
    ].copy()
    view.columns = ["优先级", "需求名称", "Reach", "Impact", "Confidence", "Effort", "RICE", "状态"]
    return view.sort_values("RICE", ascending=False)


def _render_rice_tab() -> None:
    df = load_requirements()

    ui.section("需求优先级（RICE）", "用统一的评分口径替代“我觉得这个更重要”")
    left, right = st.columns([1.15, 1])
    with left:
        st.plotly_chart(_rice_chart(df), width="stretch", config=PLOT_CONFIG)
    with right:
        st.markdown("**评分口径**")
        for key, desc in RICE_DEFINITION.items():
            st.markdown(f"- **{key}**：{desc}")
        st.markdown(
            "**计算公式**：RICE = (Reach × Impact × Confidence) ÷ Effort\n\n"
            "**优先级阈值**：RICE ≥ 14 → P0；≥ 8 → P1；≥ 4 → P2；其余为 P3"
        )

    ui.compact_section("需求评分明细")
    st.dataframe(_priority_table(df), width="stretch", hide_index=True)

    ui.compact_section("查看计算过程")
    name = st.selectbox("选择需求", df.sort_values("rice_score", ascending=False)["name"].tolist())
    row = df[df["name"] == name].iloc[0]
    st.markdown(
        f'<div class="ap-card">'
        f'<h4>{row["name"]} · RICE = {row["rice_score"]:.2f}</h4>'
        f'<p style="font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.9">'
        f'RICE = (Reach × Impact × Confidence) ÷ Effort<br>'
        f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= ({row["reach"]} × {row["impact"]} × {row["confidence"]:.2f}) ÷ {row["effort"]}<br>'
        f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= {row["rice_score"]:.2f} → 优先级 {row["priority"]}</p>'
        f'<p style="margin-top:10px;color:#64748b">需求描述：{row["problem"]}</p>'
        f'<p style="color:#64748b">对应方案：{row["solution"]}</p>'
        f'<p style="color:#64748b">目标指标：{row["expected_metric"]}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _problem_options(feedback, metrics) -> list[str]:
    options = [p["title"] for p in analytics.auto_problems(metrics, feedback)]
    extra = "AI 回答质量不稳定，用户需要反复追问"
    if extra not in options:
        options.append(extra)
    return options


def _render_plan_tab() -> None:
    feedback = load_feedback()
    metrics = load_metrics()
    evidence = analytics.diagnosis_evidence(metrics, feedback)

    ui.section("产品方案生成", "选择问题后，生成从背景到指标口径的完整方案")
    options = _problem_options(feedback, metrics)
    problem = st.selectbox("选择要解决的问题", options)
    run = st.button("生成产品方案", type="primary")

    if run:
        with st.spinner("正在生成产品方案..."):
            st.session_state["plan_result"] = llm_service.generate_product_plan(problem, evidence)
            st.session_state["plan_problem"] = problem

    result = st.session_state.get("plan_result")
    if not result:
        ui.note("生成的方案包含需求背景、目标用户、核心问题、产品方案、核心指标与预期效果六个部分。")
        return

    if result.get("error"):
        st.warning(result["error"])

    ui.compact_section(f"方案：{st.session_state.get('plan_problem', problem)}")

    st.markdown(
        f'<div class="ap-card" style="margin-bottom:14px"><h4>需求背景</h4>'
        f'<p>{result.get("background", "-")}</p></div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        ui.insight_card("目标用户", result.get("target_users", []))
    with col2:
        ui.insight_card("核心指标", result.get("metrics", []))

    st.write("")
    st.markdown(
        f'<div class="ap-card" style="margin-bottom:14px"><h4>核心问题</h4>'
        f'<p>{result.get("core_problem", "-")}</p></div>',
        unsafe_allow_html=True,
    )

    ui.insight_card("产品方案", result.get("solutions", []))
    st.write("")
    ui.insight_card("预期效果", [result.get("expected", "-")])

    status = llm_service.get_status()
    engine = f"{status.provider} · {status.model}" if status.is_live else "本地方案引擎"
    ui.note(f"方案生成引擎：{engine}。方案内容基于模拟数据与产品方法论生成，用于演示产品设计思路。")


def render() -> None:
    ui.page_header("产品方案", "从需求优先级判断，到可落地的产品方案输出")
    tab1, tab2 = st.tabs(["需求优先级（RICE）", "产品方案生成"])
    with tab1:
        _render_rice_tab()
    with tab2:
        _render_plan_tab()