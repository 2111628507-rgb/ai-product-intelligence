"""迭代中心：需求池、状态流转与迭代节奏管理。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils import analytics, ui
from utils.data_loader import load_requirements, save_requirements

STATUSES = ["需求池", "待开发", "开发中", "实验中", "已上线"]
PRIORITIES = ["P0", "P1", "P2", "P3"]

PRIORITY_TAG = {"P0": "p0", "P1": "p1", "P2": "p2", "P3": "p3"}


def _funnel(stages: list[dict]) -> None:
    cards = []
    for i, stage in enumerate(stages):
        items = "".join(
            f'<div style="font-size:11.5px;color:#64748b;margin-top:6px">{name}</div>'
            for name in stage["items"][:4]
        )
        cards.append(
            f'<div class="ap-kpi" style="flex:1">'
            f'<div class="ap-kpi-label">{stage["stage"]}</div>'
            f'<div class="ap-kpi-value" style="font-size:26px">{stage["count"]}</div>'
            f"{items}</div>"
        )
        if i < len(stages) - 1:
            cards.append('<div style="align-self:center;color:#cbd5e1;font-size:16px">→</div>')
    st.markdown(
        f'<div style="display:flex;gap:12px;align-items:stretch">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def _board(df: pd.DataFrame) -> None:
    cols = st.columns(len(STATUSES))
    for col, status in zip(cols, STATUSES):
        items = df[df["status"] == status]
        with col:
            st.markdown(
                f'<div style="font-size:12.5px;font-weight:650;color:#0f172a;margin-bottom:8px">'
                f'{status} · {len(items)}</div>',
                unsafe_allow_html=True,
            )
            if items.empty:
                st.markdown(
                    '<div class="ap-card" style="padding:12px;color:#94a3b8;font-size:12px">暂无需求</div>',
                    unsafe_allow_html=True,
                )
                continue
            for _, row in items.iterrows():
                st.markdown(
                    f'<div class="ap-card" style="padding:12px;margin-bottom:10px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;gap:6px">'
                    f'{ui.priority_badge(row["priority"])}'
                    f'<span style="font-size:11px;color:#94a3b8">RICE {row["rice_score"]:.1f}</span></div>'
                    f'<div style="font-size:12.8px;color:#0f172a;font-weight:600;margin-top:8px">{row["name"]}</div>'
                    f'<div style="font-size:11.5px;color:#64748b;margin-top:6px;line-height:1.6">'
                    f'{str(row["expected_metric"])}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def _new_requirement_form(df: pd.DataFrame) -> None:
    with st.form("new_requirement", clear_on_submit=True):
        name = st.text_input("需求名称", placeholder="例如：回答质量反馈闭环")
        problem = st.text_area("要解决的问题", height=70, placeholder="用户反馈回答质量不稳定，缺少反馈回流机制")
        solution = st.text_area("初步方案", height=70, placeholder="增加回答评分与原因标签，回流到模型优化")
        col1, col2, col3, col4 = st.columns(4)
        reach = col1.slider("Reach", 1, 10, 7)
        impact = col2.slider("Impact", 1, 10, 6)
        confidence = col3.slider("Confidence", 0.1, 1.0, 0.7, 0.05)
        effort = col4.slider("Effort", 1, 10, 4)
        expected = st.text_input("目标指标", value="首次会话完成率")
        submitted = st.form_submit_button("新增到需求池", type="primary")

    if not submitted:
        return
    if not name.strip():
        st.error("需求名称不能为空。")
        return

    rice = round(reach * impact * confidence / effort, 2)
    priority = "P0" if rice >= 14 else "P1" if rice >= 8 else "P2" if rice >= 4 else "P3"
    next_id = f"R-{len(df) + 1:03d}"
    new_row = {
        "req_id": next_id,
        "name": name.strip(),
        "problem": problem.strip(),
        "solution": solution.strip(),
        "reach": reach,
        "impact": impact,
        "confidence": confidence,
        "effort": effort,
        "rice_score": rice,
        "priority": priority,
        "status": "需求池",
        "owner": "待分配",
        "expected_metric": expected.strip(),
        "created_at": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "updated_at": pd.Timestamp.now().strftime("%Y-%m-%d"),
    }
    updated = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_requirements(updated)
    st.success(f"已新增需求「{name}」，RICE {rice}，优先级 {priority}。")
    st.rerun()


def _update_form(df: pd.DataFrame) -> None:
    names = df["name"].tolist()
    selected = st.selectbox("选择需求", names)
    row = df[df["name"] == selected].iloc[0]
    col1, col2, col3 = st.columns(3)
    new_status = col1.selectbox("状态", STATUSES, index=STATUSES.index(row["status"]))
    new_priority = col2.selectbox("优先级", PRIORITIES, index=PRIORITIES.index(row["priority"]))
    new_owner = col3.text_input("负责人", value=str(row["owner"]))
    if st.button("保存修改", type="primary"):
        mask = df["name"] == selected
        df.loc[mask, "status"] = new_status
        df.loc[mask, "priority"] = new_priority
        df.loc[mask, "owner"] = new_owner
        df.loc[mask, "updated_at"] = pd.Timestamp.now().strftime("%Y-%m-%d")
        save_requirements(df)
        st.success(f"「{selected}」已更新为 {new_status} / {new_priority}。")
        st.rerun()


def render() -> None:
    df = load_requirements()
    ui.page_header("迭代中心", "需求池、开发、实验、上线的完整流转，形成产品迭代闭环")

    stages = analytics.funnel_stages(df)
    in_progress = int(df[df["status"].isin(["待开发", "开发中"])].shape[0])
    released = int((df["status"] == "已上线").sum())
    ui.kpi_row(
        [
            {"label": "需求总数", "value": str(len(df)), "hint": "当前 Backlog", "direction": "flat"},
            {
                "label": "推进中",
                "value": str(in_progress),
                "delta": "待开发 / 开发中",
                "direction": "flat",
                "hint": "研发阶段",
            },
            {
                "label": "已上线",
                "value": str(released),
                "delta": f"{released / len(df) * 100:.0f}% 已交付",
                "direction": "up",
                "hint": "完成数据验证",
            },
            {
                "label": "平均 RICE",
                "value": f"{df['rice_score'].mean():.1f}",
                "hint": "全部需求均值",
                "direction": "flat",
            },
        ]
    )

    ui.section("迭代流程", "需求池 → 开发 → 实验 → 上线 → 数据验证")
    _funnel(stages)

    ui.section("需求看板", "按状态查看当前 Backlog")
    _board(df)

    ui.section("需求管理", "支持新增需求，以及调整状态、优先级与负责人")
    tab1, tab2, tab3 = st.tabs(["新增需求", "修改需求", "全部需求"])
    with tab1:
        _new_requirement_form(df)
    with tab2:
        _update_form(df)
    with tab3:
        view = df[
            [
                "priority",
                "name",
                "problem",
                "rice_score",
                "status",
                "owner",
                "expected_metric",
                "updated_at",
            ]
        ].copy()
        view.columns = ["优先级", "需求名称", "问题", "RICE", "状态", "负责人", "目标指标", "更新时间"]
        st.dataframe(view.sort_values("RICE", ascending=False), width="stretch", hide_index=True)

    ui.note(
        "迭代中心的修改会写回 data/requirements.csv。"
        "建议在面试演示中展示一次“新增需求 → 自动计算 RICE → 分配优先级”的完整过程。"
    )