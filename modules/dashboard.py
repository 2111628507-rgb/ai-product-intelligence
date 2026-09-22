"""产品总览 Dashboard。"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from utils import analytics, product, ui
from utils.data_loader import load_feedback, load_metrics

TREND_CHOICES = {
    "DAU": "dau",
    "次日留存": "d1_retention",
    "用户满意度": "csat_index",
    "AI 回复有效率": "ai_effective_rate",
}

PLOT_CONFIG = {"displayModeBar": False}


def _base_layout(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='-apple-system, "Microsoft YaHei", sans-serif', size=12, color="#475569"),
        hovermode="x unified",
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, linecolor="#e6e9f2", tickcolor="#e6e9f2")
    fig.update_yaxes(showgrid=True, gridcolor="#eef1f6", zeroline=False, linecolor="rgba(0,0,0,0)")
    return fig


def _trend_chart(metrics, column: str, label: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=metrics["date"],
            y=metrics[column],
            mode="lines",
            name=label,
            line=dict(color="#2f5bff", width=2.4, shape="spline"),
            fill="tozeroy",
            fillcolor="rgba(47,91,255,0.07)",
        )
    )
    fig.update_yaxes(rangemode="tozero" if column == "dau" else "normal")
    return _base_layout(fig)


def _delta_dir(value: float, higher_is_better: bool = True) -> str:
    if abs(value) < 0.05:
        return "flat"
    positive = value > 0
    return "up" if positive == higher_is_better else "down"


def render() -> None:
    metrics = load_metrics()
    feedback = load_feedback()
    snapshot = analytics.kpi_snapshot(metrics)
    health = analytics.health_score(metrics)

    ui.page_header(
        "产品总览",
        f"{product.subtitle()}",
    )

    desc = (
        f"健康度由满意度、回答有效率、留存与反馈健康度加权计算得出，"
        f"较 30 天前 {health['delta']:+.1f} 分。"
        f"当前最需要关注的是连败场景与新玩家首次体验：以下问题由指标异常自动触发，而非人工挑选。"
    )
    ui.hero(f"{health['score']:.1f}", "分", "AI 产品健康度", desc)

    dau = snapshot["dau"]
    d1 = snapshot["d1_retention"]
    csat = snapshot["csat_index"]
    eff = snapshot["ai_effective_rate"]
    ui.kpi_row(
        [
            {
                "label": "DAU",
                "value": f"{int(dau['value']):,}",
                "delta": f"{dau['relative']:+.1f}%",
                "direction": _delta_dir(dau["relative"]),
                "hint": "较 30 天前",
            },
            {
                "label": "次日留存",
                "value": f"{d1['value']:.1f}%",
                "delta": f"{d1['relative']:+.1f}%",
                "direction": _delta_dir(d1["relative"]),
                "hint": "较 30 天前",
            },
            {
                "label": "用户满意度",
                "value": f"{csat['value']:.1f}",
                "delta": f"{csat['relative']:+.1f}%",
                "direction": _delta_dir(csat["relative"]),
                "hint": "CSAT 指数（百分制）",
            },
            {
                "label": "AI 回复有效率",
                "value": f"{eff['value']:.1f}%",
                "delta": f"{eff['relative']:+.1f}%",
                "direction": _delta_dir(eff["relative"]),
                "hint": "较 30 天前",
            },
        ]
    )

    ui.section("核心指标趋势", "近 30 天，可切换指标查看变化")
    choice = st.radio(
        "选择指标",
        list(TREND_CHOICES.keys()),
        horizontal=True,
        label_visibility="collapsed",
    )
    column = TREND_CHOICES[choice]
    st.plotly_chart(_trend_chart(metrics, column, choice), width="stretch", config=PLOT_CONFIG)

    low_col, high_col = st.columns(2)
    with low_col:
        ui.compact_section("值得关注的下滑指标")
        st.plotly_chart(
            _trend_chart(metrics, "new_user_d1_retention", "新用户次日留存"),
            width="stretch",
            config=PLOT_CONFIG,
        )
    with high_col:
        ui.compact_section("持续走高的体验成本")
        st.plotly_chart(
            _trend_chart(metrics, "avg_response_time", "平均响应时间"),
            width="stretch",
            config=PLOT_CONFIG,
        )

    ui.section("AI 自动发现的问题", "由指标异常与反馈聚类的交叉结果生成，按影响程度排序")
    for problem in analytics.auto_problems(metrics, feedback):
        ui.problem_card(
            problem["priority"],
            problem["title"],
            problem["metrics"],
            problem["advice"],
        )

    ui.note(
        f"数据说明：本页分析对象为「{product.name()}」，"
        "指标与用户反馈均为 generate_data.py 生成的模拟数据，"
        "用于演示 AI 产品经理的分析与决策流程，不代表任何真实企业数据。"
    )