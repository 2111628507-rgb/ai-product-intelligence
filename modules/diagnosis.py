"""问题诊断模块：AI Product Diagnosis Agent。

体现 Agent 的工作方式：先识别意图，再按需调用指标分析、用户洞察、
产品策略与实验分析模块，最后输出可解释的诊断结论。
"""

from __future__ import annotations

import streamlit as st

from services import llm_service
from utils import analytics, ui
from utils.data_loader import (
    load_ab_test,
    load_feedback,
    load_metrics,
)

EXAMPLES = [
    "最近连败场景的玩家留存下降了，帮我分析原因。",
    "玩家反馈 AI 总在讲道理，连败的时候更明显，应该怎么优化？",
    "晚间高峰期回复越来越慢，对陪伴体验有什么影响？",
]

STEPS_SCHEMA = [
    ("Intent Analyzer", "识别问题意图并决定调用哪些分析模块"),
    ("Data Analyst", "读取指标与反馈数据，定位异常"),
    ("User Insight Agent", "从反馈中提炼痛点与情绪"),
    ("Product Strategy Agent", "生成诊断结论与产品方案"),
    ("Experiment Agent", "结合 A/B 实验给出验证建议"),
]


def render() -> None:
    ui.page_header(
        "问题诊断",
        "输入一个业务问题，Agent 会自动路由到相应分析模块并给出可解释的诊断结论",
    )

    metrics = load_metrics()
    feedback = load_feedback()
    ab_test = load_ab_test()
    evidence = analytics.diagnosis_evidence(metrics, feedback, ab_test)
    ab_data = analytics.ab_summary(ab_test)

    ui.section("输入问题")
    preset = st.radio("常见问题", EXAMPLES, horizontal=False, label_visibility="collapsed")
    question = st.text_area("或者输入你自己的问题", value=preset, height=90)
    run = st.button("开始诊断", type="primary")

    if run:
        progress = st.progress(0, text="Agent 正在运行...")
        step_state = {"done": 0}

        def step_callback() -> None:
            step_state["done"] += 1
            progress.progress(
                min(1.0, step_state["done"] * 0.25), text="Agent 正在运行..."
            )

        with st.spinner("正在分析指标、用户反馈与实验数据..."):
            result = llm_service.run_agent(
                question,
                feedback,
                evidence,
                ab_summary=ab_data,
                progress=step_callback,
            )
        progress.empty()
        st.session_state["agent_result"] = result

    result = st.session_state.get("agent_result")

    ui.section("Agent 工作流程", "只有被意图命中的模块才会真正执行，未命中的模块会跳过")
    if result:
        ui.agent_steps(result.steps)
    else:
        ui.agent_steps(
            [
                {"name": name, "output": desc, "done": False, "triggered": False}
                for name, desc in STEPS_SCHEMA
            ]
        )
        ui.note("点击「开始诊断」后，Agent 会按顺序调用命中的分析模块，并在每一步展示中间结论。")
        return

    diagnosis = result.diagnosis
    if not diagnosis:
        ui.note(
            "本次问题没有触发产品策略模块，因此没有生成诊断结论卡片，"
            "可以先看上面的 Agent 工作流程了解各模块的中间结论。"
        )
        if result.experiment.get("observation"):
            ui.insight_card("实验观察", [result.experiment["observation"]])
        return
    if diagnosis.get("error"):
        st.warning(diagnosis["error"])

    ui.section("诊断结论", f"问题类型：{result.intent_label}")

    st.markdown(
        f'<div class="ap-card" style="margin-bottom:16px">'
        f'<h4>问题定位</h4><p>{diagnosis.get("location", "-")}</p></div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        ui.insight_card(
            "可能原因",
            [f"{i}. {c}" for i, c in enumerate(diagnosis.get("causes", []), start=1)],
        )
    with col2:
        ui.insight_card("支撑证据", diagnosis.get("evidence", []))

    st.write("")
    impact = diagnosis.get("impact", [])
    st.markdown(
        '<div class="ap-card"><h4>影响范围</h4><p>'
        + " ".join(ui.badge(i, "p2") for i in impact)
        + "</p></div>",
        unsafe_allow_html=True,
    )

    if result.insights and result.insights.get("opportunities"):
        st.write("")
        ui.insight_card("Agent 识别的产品机会", result.insights["opportunities"])

    if result.plan:
        st.write("")
        with st.expander("查看 Agent 自动生成的产品方案（完整版可在「产品方案」页查看）"):
            st.markdown(f"**需求背景**：{result.plan.get('background', '-')}")
            st.markdown("**产品方案**")
            for i, item in enumerate(result.plan.get("solutions", []), start=1):
                st.markdown(f"{i}. {item}")
            st.markdown(f"**预期效果**：{result.plan.get('expected', '-')}")

    sources = {s for s in result.sources if s}
    engine = "真实模型" if "llm" in sources else "本地 Mock 分析引擎"
    ui.note(
        f"本次分析由 {engine} 完成，结论均基于 data/ 目录中的模拟数据计算得出。"
        "如需把诊断结论转成排期方案，可前往「产品方案」页使用 RICE 评估需求优先级。"
    )