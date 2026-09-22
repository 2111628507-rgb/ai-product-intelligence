"""A/B 实验模块：实验数据对比、显著性检验与 AI 实验分析。"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from services import llm_service
from utils import analytics, ui
from utils.data_loader import load_ab_test

PLOT_CONFIG = {"displayModeBar": False}

RATE_METRICS = ["激活率", "次日留存", "会话完成率"]


def _grouped_bar(rows) -> go.Figure:
    rate_rows = [r for r in rows if r["metric"] in RATE_METRICS]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="A 组 · 原有首页",
            x=[r["metric"] for r in rate_rows],
            y=[r["a_value"] * 100 for r in rate_rows],
            marker=dict(color="#94a3b8", cornerradius=4),
            text=[r["a"] for r in rate_rows],
            textposition="outside",
            textfont=dict(size=11),
        )
    )
    fig.add_trace(
        go.Bar(
            name="B 组 · AI 引导优化",
            x=[r["metric"] for r in rate_rows],
            y=[r["b_value"] * 100 for r in rate_rows],
            marker=dict(color="#2f5bff", cornerradius=4),
            text=[r["b"] for r in rate_rows],
            textposition="outside",
            textfont=dict(size=11),
        )
    )
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        barmode="group",
        bargap=0.32,
        font=dict(family='-apple-system, "Microsoft YaHei", sans-serif', size=12, color="#475569"),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#eef1f6", zeroline=False, ticksuffix="%")
    return fig


def _relative_chart(rows) -> go.Figure:
    ordered = sorted(rows, key=lambda r: r["relative"])
    colors = ["#12805c" if r["relative"] > 0 else "#d92d20" for r in ordered]
    fig = go.Figure(
        go.Bar(
            x=[r["relative"] for r in ordered],
            y=[r["metric"] for r in ordered],
            orientation="h",
            marker=dict(color=colors, cornerradius=4),
            text=[f"{r['relative']:+.1f}%" for r in ordered],
            textposition="outside",
            textfont=dict(size=11, color="#475569"),
            hovertemplate="%{y}：%{x:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=60, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='-apple-system, "Microsoft YaHei", sans-serif', size=12, color="#475569"),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef1f6", zeroline=True, zerolinecolor="#cbd5e1", ticksuffix="%")
    fig.update_yaxes(showgrid=False)
    return fig


def render() -> None:
    ab_test = load_ab_test()
    summary = analytics.ab_summary(ab_test)
    ui.page_header("A/B 实验", "新用户 AI 引导优化的实验结果与决策建议")

    sig_count = summary["significant_count"]
    ui.kpi_row(
        [
            {"label": "实验名称", "value": summary["name"], "hint": "实验周期 7 天", "direction": "flat"},
            {
                "label": "样本量",
                "value": f"{summary['sample']:,}",
                "delta": f"A / B 各 {summary['group_size']:,} 人",
                "direction": "flat",
                "hint": "新注册玩家",
            },
            {
                "label": "显著提升指标",
                "value": f"{sig_count} / 4",
                "delta": "p < 0.05",
                "direction": "up" if sig_count >= 3 else "flat",
                "hint": "双侧检验",
            },
            {
                "label": "实验结论",
                "value": "继续验证" if sig_count >= 3 else "待观察",
                "delta": f"{sig_count} 项指标优于对照组",
                "direction": "up" if sig_count >= 3 else "flat",
                "hint": "建议延长至 14 天",
            },
        ]
    )

    ui.section("实验分组", "A 组：通用回复策略　|　B 组：连败场景情绪识别 + 人格化陪伴回复")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(_grouped_bar(summary["rows"]), width="stretch", config=PLOT_CONFIG)
    with right:
        st.plotly_chart(_relative_chart(summary["rows"]), width="stretch", config=PLOT_CONFIG)

    ui.compact_section("实验数据明细")
    table = [
        {
            "指标": r["metric"],
            "A 组": r["a"],
            "B 组": r["b"],
            "相对变化": f"{r['relative']:+.1f}%",
            "绝对变化": f"{r['absolute']:+.2f}",
            "p 值": f"{r['p_value']:.4f}",
            "是否显著": "显著" if r["p_value"] < 0.05 else "不显著",
        }
        for r in summary["rows"]
    ]
    st.dataframe(table, width="stretch", hide_index=True)

    ui.section("AI 实验分析", "由实验数据自动生成，包含结论、风险与下一步建议")
    status = llm_service.get_status()
    if st.button("生成实验分析", type="primary"):
        with st.spinner("正在分析实验结果..."):
            st.session_state["ab_result"] = llm_service.analyze_ab_test(summary)

    result = st.session_state.get("ab_result")
    if result:
        if result.get("error"):
            st.warning(result["error"])
        col1, col2 = st.columns([1, 1])
        with col1:
            ui.insight_card("实验观察", [result.get("observation", "-")])
        with col2:
            ui.insight_card("需要注意", [result.get("risk", "-")])
        st.write("")
        ui.insight_card("下一步建议", result.get("suggestion", []))
        engine = f"{status.provider} · {status.model}" if status.is_live else "本地实验分析引擎"
        st.caption(f"分析引擎：{engine}")
    else:
        ui.note("点击「生成实验分析」，AI 会基于上方真实计算出的实验数据给出结论、风险与上线建议。")

    ui.note(
        "数据说明：本页实验数据为模拟数据，用于演示 A/B 实验的设计、指标口径与结果解读方法，"
        "不代表真实线上实验结论。p 值采用双比例 z 检验与均值近似检验计算。"
    )