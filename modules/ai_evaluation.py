"""AI 体验评测模块：对 AI 的回答做多维评测并给出优化建议。"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from services import llm_service
from utils import ui

PLOT_CONFIG = {"displayModeBar": False}

EXAMPLES = {
    "示例一 · 连败吐槽（回复偏长）": {
        "question": "王者荣耀连跪五把了，队友一直送，我真的烦死了",
        "answer": (
            "连败确实很影响心情，不过先别急着怪队友，我们来系统看一下这五把的问题。首先，你要区分是操作问题还是节奏问题："
            "如果是前期被抓，说明视野和站位需要调整；如果是后期打团输，说明阵容理解有偏差。第二，建议你在连败之后先停一把，"
            "做三分钟的复盘，看看自己每把的死亡次数和参团率，这两项数据最能反映你的问题。第三，关于队友，匹配机制决定了你"
            "无法控制队友的水平，你能控制的只有自己的经济和节奏，所以不要因为队友的失误影响自己的判断。第四，选英雄的时候尽量"
            "选择你能稳定发挥的位置，避免在情绪不好的时候玩高难度英雄。第五，如果真的连跪到心态崩了，建议先去做点别的事情，"
            "等情绪平复了再回来打，胜率会明显提升。另外补充一点，连败往往不是技术问题，而是心态问题，人在烦躁的时候判断力会下降，"
            "操作也会变形，所以及时止损非常重要。例如你可以在连输两把之后就固定休息十分钟，让手感和情绪都回到正常状态。"
            "第六，关于出装和铭文，建议你把最近五把的装备截图发我，我帮你看一下是不是在逆风局还在堆输出装。"
            "最后，如果方便的话，把这五把的对局结果发给我，我帮你具体分析问题出在哪里，是节奏问题还是操作问题。"
            "希望你能尽快调整过来，下一把一定能赢。"
        ),
    },
    "示例二 · 星露谷没目标（简洁共情）": {
        "question": "星露谷玩到第三年了，突然不知道要干嘛",
        "answer": (
            "星露谷到第三年确实容易卡住，该建的都建完了，新鲜感自然就下来了。\n\n"
            "可以试试这几个方向：把博物馆捐赠补全、做一次完美农场布局，或者开个新档换个流派玩。\n\n"
            "你是觉得没事做，还是觉得少了点目标感？"
        ),
    },
    "示例三 · 模板化安慰（看似温柔但没用）": {
        "question": "CSGO 一直输，好烦",
        "answer": (
            "抱抱你，你已经很棒了，每一场失败都是成长的机会，加油！"
            "相信自己，保持好心态，下一次一定能赢～"
        ),
    },
}

DIMENSION_HINT = {
    "回答准确性": "回答内容是否正确、是否有事实性错误",
    "意图匹配": "是否真正回答了用户想问的问题",
    "内容完整性": "关键环节是否完整、是否需要再次追问",
    "简洁性": "信息密度与阅读成本",
    "可执行性": "用户拿到回答后能否直接执行",
}


def _score_card(name: str, value: int) -> str:
    if value >= 85:
        color = "#12805c"
    elif value >= 70:
        color = "#f79009"
    else:
        color = "#d92d20"
    return (
        f'<div class="ap-kpi"><div class="ap-kpi-label">{name}</div>'
        f'<div class="ap-kpi-value" style="font-size:24px">{value}</div>'
        f'<div style="height:6px;background:#eef1f6;border-radius:3px;overflow:hidden">'
        f'<div style="height:100%;width:{value}%;background:{color};border-radius:3px"></div></div></div>'
    )


def _radar(scores: dict) -> go.Figure:
    labels = list(scores.keys())
    values = [scores[label] for label in labels]
    fig = go.Figure(
        go.Scatterpolar(
            r=values + values[:1],
            theta=labels + labels[:1],
            fill="toself",
            fillcolor="rgba(47,91,255,0.14)",
            line=dict(color="#2f5bff", width=2),
            hovertemplate="%{theta}：%{r} 分<extra></extra>",
        )
    )
    fig.update_layout(
        height=340,
        margin=dict(l=40, r=40, t=30, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(range=[0, 100], showline=False, gridcolor="#eef1f6", tickfont=dict(size=10)),
            angularaxis=dict(gridcolor="#eef1f6", tickfont=dict(size=12)),
        ),
        showlegend=False,
        font=dict(family='-apple-system, "Microsoft YaHei", sans-serif', size=12, color="#475569"),
    )
    return fig


def render() -> None:
    ui.page_header("AI 体验评测", "像评测一个 AI 回答一样，量化体验问题并给出优化方向")

    ui.note(
        "左边填玩家说的话，点「让 AI 回答」让模型生成一条陪伴回复；"
        "右边也可以直接粘贴任意一段 AI 回答，点「开始评测」给它打分。"
    )

    preset = st.radio("选择评测示例", list(EXAMPLES.keys()), horizontal=True)
    example = EXAMPLES[preset]

    if st.session_state.get("eval_preset") != preset:
        st.session_state["eval_preset"] = preset
        st.session_state["eval_question"] = example["question"]
        st.session_state["eval_answer"] = example["answer"]

    col_left, col_right = st.columns(2)
    with col_left:
        question = st.text_area("用户问题", key="eval_question", height=120)
        gen = st.button("让 AI 回答这个问题", width="stretch")
        # 必须在右侧「AI 回答」输入框创建之前写入，否则会触发 Streamlit 状态冲突
        if gen:
            if not (question or "").strip():
                st.warning("请先在上方「用户问题」里写下玩家说的话。")
            else:
                with st.spinner("正在生成陪伴回复..."):
                    reply = llm_service.answer_question(question)
                if reply.get("answer"):
                    st.session_state["eval_answer"] = reply["answer"]
                if reply.get("error"):
                    st.warning(reply["error"])
    with col_right:
        answer = st.text_area("AI 回答", key="eval_answer", height=120)

    run = st.button("开始评测", type="primary")

    if run:
        with st.spinner("正在评测回答质量..."):
            st.session_state["eval_result"] = llm_service.evaluate_answer(question, answer)
            st.session_state["eval_input"] = (question, answer)

    result = st.session_state.get("eval_result")
    if not result:
        ui.note("评测维度：回答准确性、意图匹配、内容完整性、简洁性、可执行性。未配置 API Key 时使用本地评测引擎，评分会随回答内容变化。")
        return

    if result.get("error"):
        st.warning(result["error"])

    scores = result["scores"]
    overall = result["overall"]
    ui.section("评测结果", f"综合评分 {overall} 分")
    chart_col, score_col = st.columns([1, 1.1])
    with chart_col:
        st.plotly_chart(_radar(scores), width="stretch", config=PLOT_CONFIG)
    with score_col:
        st.markdown(
            f'<div class="ap-kpi" style="margin-bottom:14px">'
            f'<div class="ap-kpi-label">综合评分</div>'
            f'<div class="ap-kpi-value" style="font-size:34px">{overall}'
            f'<span style="font-size:14px;color:#94a3b8"> / 100</span></div>'
            f'<div class="ap-kpi-hint">最低维度：{result.get("weakest", "-")}，是当前最主要的体验短板</div></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(3)
        for i, (name, value) in enumerate(scores.items()):
            with cols[i % 3]:
                st.markdown(_score_card(name, value), unsafe_allow_html=True)
                st.caption(DIMENSION_HINT.get(name, ""))

    ui.section("体验问题", "由评测结果中得分最低的维度推导")
    issue_col, advice_col = st.columns(2)
    with issue_col:
        ui.insight_card("当前主要问题", result.get("issues", []))
    with advice_col:
        ui.insight_card("优化建议", result.get("suggestions", []))

    status = llm_service.get_status()
    engine = f"{status.provider} · {status.model}" if status.is_live else "本地评测引擎"
    ui.note(f"评测引擎：{engine}。评分由模型输出与本地规则共同校验，用于产品 Demo 演示，不构成线上质量结论。")