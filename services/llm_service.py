"""LLM 服务层。

设计原则：
1. 没有配置 API Key 时，全部分析能力由本地 Mock 实现，Demo 依然完整可跑。
2. 配置了 API Key 时调用真实模型；调用失败自动降级到 Mock，并把错误信息返回给页面。
3. 所有能力对外返回统一结构：{"source": "mock" | "llm", "error": str | None, ...}

对外能力：
    analyze_feedback()      用户反馈洞察
    diagnose_problem()      产品问题诊断
    generate_product_plan() 产品方案生成
    analyze_ab_test()       A/B 实验结果分析
    evaluate_answer()       AI 回答体验评测
    run_agent()             Product Manager Agent 流程编排
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

PLACEHOLDER_MARKERS = (
    "your_api_key",
    "your-api-key",
    "sk-xxx",
    "xxxx",
    "填入",
    "在这里",
    "placeholder",
    "changeme",
)

CATEGORY_PAIN = {
    "回复质量": "陪伴回复与玩家当时的情绪不匹配，连败时还在讲道理，缺少情绪识别",
    "响应速度": "晚间高峰期回复变慢，玩家在局间的等待成本被放大",
    "功能缺失": "战绩同步、语音陪伴、一键组队等能力缺失，玩家要手动描述对局",
    "交互体验": "新玩家第一次打开不知道该说什么，四个人格的区别也看不懂",
    "回复长度": "陪伴回复默认偏长，玩家在局间碎片时间里读不完就退出",
    "稳定性": "对话中断与上下文丢失，陪伴感被打断",
}

CATEGORY_NEED = {
    "回复质量": "希望 AI 先接住情绪，再决定要不要给建议",
    "响应速度": "希望局间几秒钟就能收到回应，等待有明确预期",
    "功能缺失": "希望能自动读战绩，开黑的时候可以用语音说话",
    "交互体验": "希望打开就知道能聊什么，人格选择有清楚的说明",
    "回复长度": "希望默认两三句话，需要复盘的时候再展开",
    "稳定性": "希望长对话不中断，换设备后聊天记录还在",
}

CATEGORY_OPPORTUNITY = {
    "回复质量": "连败场景优先触发共情策略，把建议压缩到最多一条",
    "响应速度": "首字优先输出 + 高频情绪表达缓存",
    "功能缺失": "先做战绩截图识别，再验证语音陪伴在开黑场景的真实需求",
    "交互体验": "开场示例对话 + 人格差异说明 + 一键体验连败场景",
    "回复长度": "默认短回复，把复盘与攻略折叠为可展开内容",
    "稳定性": "长对话断点续传与上下文云端同步",
}

DIMENSION_ORDER = ["回答准确性", "意图匹配", "内容完整性", "简洁性", "可执行性"]
DIMENSION_WEIGHT = {
    "回答准确性": 0.25,
    "意图匹配": 0.20,
    "内容完整性": 0.20,
    "简洁性": 0.20,
    "可执行性": 0.15,
}

STOPWORDS = {
    "帮我", "一个", "一下", "怎么", "什么", "可以", "需要", "我的", "这个", "那个",
    "问题", "回答", "应该", "如果", "然后", "以及", "就是", "还是", "我们", "你们",
    "现在", "因为", "所以", "但是", "很多", "几个", "如何", "为什么", "最近",
}

HEDGING_WORDS = ["可能", "也许", "大概", "不一定", "建议你自己", "应该差不多"]

# 模板化安慰用语：看起来温柔，但没有回应玩家当下的诉求
CLICHE_PHRASES = [
    "抱抱你", "你已经很棒了", "你是最棒的", "加油", "相信自己", "别放弃",
    "每一次失败", "成长的机会", "下次一定", "保持好心态", "一定会好起来",
]

INTENT_KEYWORDS = {
    "retention": ["留存", "流失", "新用户", "新玩家", "新手", "激活", "首次使用", "注册", "次留"],
    "engagement": ["活跃", "dau", "日活", "在线", "使用时长", "打开率", "回访", "用得少了"],
    "quality": ["回复质量", "回答质量", "准确", "理解", "答非所问", "质量", "错误", "讲道理", "敷衍", "模板", "共情"],
    "length": ["太长", "过长", "长度", "啰嗦", "简洁", "简短", "阅读", "篇幅", "看不懂重点"],
    "speed": ["速度", "响应", "慢", "卡顿", "卡住", "等待", "延迟"],
    "stability": ["崩溃", "报错", "闪退", "失败", "丢失", "稳定", "掉线"],
    "feature": ["人格", "语音", "战绩", "组队", "导出", "同步", "功能", "入口", "切换"],
    "experiment": ["实验", "ab", "a/b", "灰度", "对照"],
    "requirement": ["需求", "优先级", "排期", "rice", "backlog", "先做哪个"],
    "monetization": ["付费", "转化", "充值", "收入", "营收", "买单", "订阅", "客单价", "商业化"],
}

INTENT_LABEL = {
    "retention": "新玩家留存与激活分析",
    "engagement": "活跃度与使用深度分析",
    "quality": "陪伴回复质量分析",
    "length": "回复长度与阅读体验分析",
    "speed": "响应速度与性能分析",
    "stability": "稳定性与故障分析",
    "feature": "功能使用与能力缺口分析",
    "experiment": "实验效果分析",
    "requirement": "需求优先级与排期分析",
    "monetization": "商业化与付费分析",
    "general": "综合产品分析",
}

DATA_COVERAGE = {
    "有": (
        "30 天产品指标（DAU、次日留存、新玩家次留、满意度、AI 回复有效率、首次会话完成率、"
        "平均响应时间、二次追问率、连败场景对话占比、负面反馈率）、"
        "640 条玩家反馈（问题类别 / 评分 / 场景 / 玩家类型）、2000 条 A/B 实验数据、8 条需求及 RICE 评分"
    ),
    "没有": "付费与收入数据、渠道投放数据、服务器性能数据、真实用户访谈记录",
}

# 配置与状态
# --------------------------------------------------------------------------


@dataclass
class LLMStatus:
    mode: str
    provider: str
    model: str
    detail: str
    base_url: str = ""

    @property
    def is_live(self) -> bool:
        return self.mode == "llm"


def _secret(name: str) -> str:
    """托管平台（Streamlit Community Cloud 等）把密钥放在 st.secrets 里。"""
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # noqa: BLE001 - 本地没有 secrets.toml 时忽略
        return ""
    return str(value).strip() if value else ""


def _setting(name: str) -> str:
    """先读环境变量（.env），再读托管平台的 secrets。"""
    return (os.getenv(name) or _secret(name) or "").strip()


def get_config() -> dict[str, str]:
    api_key = _setting("OPENAI_API_KEY") or _setting("DEEPSEEK_API_KEY") or _setting("LLM_API_KEY")
    base_url = _setting("OPENAI_BASE_URL") or _setting("LLM_BASE_URL") or DEFAULT_BASE_URL
    model = _setting("OPENAI_MODEL") or _setting("LLM_MODEL") or DEFAULT_MODEL
    return {"api_key": api_key, "base_url": base_url, "model": model}


def has_api_key() -> bool:
    key = get_config()["api_key"]
    if len(key) < 16:
        return False
    lowered = key.lower()
    return not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def get_status() -> LLMStatus:
    cfg = get_config()
    if has_api_key():
        provider = "DeepSeek" if "deepseek" in cfg["base_url"] else "OpenAI 兼容接口"
        return LLMStatus(
            mode="llm",
            provider=provider,
            model=cfg["model"],
            base_url=cfg["base_url"],
            detail=f"已连接 {provider} · {cfg['model']}",
        )
    return LLMStatus(
        mode="mock",
        provider="本地 Mock",
        model="rule-based",
        base_url="",
        detail="未配置 API Key，当前使用本地 Mock 分析引擎",
    )


def _client():
    from openai import OpenAI

    cfg = get_config()
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])


def _chat(system: str, user: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
    cfg = get_config()
    client = _client()
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _chat_json(system: str, user: str, temperature: float = 0.3, max_tokens: int = 1200) -> dict:
    raw = _chat(system, user, temperature=temperature, max_tokens=max_tokens)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型没有返回可解析的 JSON")
    return json.loads(raw[start : end + 1])


def _try_llm(system: str, user: str, fallback, **kwargs) -> dict:
    """调用真实模型，失败时降级到 Mock 结果并记录错误。"""
    if not has_api_key():
        result = fallback()
        result["source"] = "mock"
        return result
    try:
        data = _chat_json(system, user, **kwargs)
        data["source"] = "llm"
        data["error"] = None
        return data
    except Exception as exc:  # noqa: BLE001 - 需要把任何异常降级给页面展示
        result = fallback()
        result["source"] = "mock"
        result["error"] = f"模型调用失败，已自动使用本地分析：{exc}"
        return result


# --------------------------------------------------------------------------
# 通用数据处理
# --------------------------------------------------------------------------


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _feedback_stats(feedback: pd.DataFrame) -> dict:
    total = len(feedback)
    negative = feedback[feedback["rating"] <= 2]
    stats = {
        "total": int(total),
        "avg_rating": float(feedback["rating"].mean()),
        "negative_rate": float(len(negative) / total) if total else 0.0,
        "category_counts": feedback["issue_category"].value_counts().to_dict(),
        "category_negative": negative["issue_category"].value_counts().to_dict(),
        "scene_counts": feedback["scene"].value_counts().to_dict(),
        "scene_negative_rate": (
            negative["scene"].value_counts() / feedback["scene"].value_counts()
        ).fillna(0).to_dict(),
        "user_type_counts": feedback["user_type"].value_counts().to_dict(),
        "negative_samples": negative["feedback"].head(8).tolist(),
        "positive_samples": feedback[feedback["rating"] >= 4]["feedback"].head(5).tolist(),
    }
    return stats


def _mock_analyze_feedback(feedback: pd.DataFrame) -> dict:
    stats = _feedback_stats(feedback)
    total = stats["total"] or 1
    cat_counts = stats["category_counts"]
    cat_neg = stats["category_negative"]
    ranked = sorted(cat_counts.items(), key=lambda kv: kv[1], reverse=True)

    pain_points = []
    for name, count in ranked[:3]:
        neg_share = cat_neg.get(name, 0) / max(count, 1)
        pain_points.append(f"{CATEGORY_PAIN[name]}（{name}类反馈 {count} 条，占 {_pct(count / total)}，其中负面占 {_pct(neg_share)}）")

    needs = [CATEGORY_NEED[name] for name, _ in ranked[:3]]

    neg_rate = stats["negative_rate"]
    if neg_rate >= 0.18:
        mood = "整体情绪偏中性，负面情绪集中在连败后仍在被讲道理、以及局间等待回复这两个时刻"
    elif neg_rate >= 0.10:
        mood = "整体情绪偏正面，负面情绪主要集中在连败这一个高情绪场景"
    else:
        mood = "整体情绪正面，玩家更多是在期待战绩同步、语音陪伴这类新能力"

    emotions = [
        f"{mood}（负面反馈占比 {_pct(neg_rate)}，平均评分 {stats['avg_rating']:.2f}/5）",
        f"负面表达最集中的场景：{max(stats['scene_negative_rate'], key=stats['scene_negative_rate'].get)}",
        f"正面反馈主要集中在：{', '.join(list(stats['positive_samples'])[:2])}",
    ]

    scene_ranked = sorted(stats["scene_counts"].items(), key=lambda kv: kv[1], reverse=True)
    scenes = [f"{name}：{count} 条反馈（{_pct(count / total)}）" for name, count in scene_ranked[:4]]
    scenes.append(
        f"高价值场景：{scene_ranked[0][0]}，用户类型以 {max(stats['user_type_counts'], key=stats['user_type_counts'].get)} 为主"
    )

    opportunities = [CATEGORY_OPPORTUNITY[name] for name, _ in ranked[:3]]
    opportunities.append("把高频负面反馈接入需求池，形成“反馈-需求-实验-验证”的闭环")

    return {
        "pain_points": pain_points,
        "needs": needs,
        "emotions": emotions,
        "scenes": scenes,
        "opportunities": opportunities,
    }


def analyze_feedback(feedback: pd.DataFrame) -> dict:
    """用户洞察：从反馈数据中提炼痛点、需求、情绪、场景与机会。"""
    stats = _feedback_stats(feedback)
    summary = {
        "反馈总量": stats["total"],
        "平均评分": round(stats["avg_rating"], 2),
        "负面反馈率": _pct(stats["negative_rate"]),
        "问题分布": stats["category_counts"],
        "场景分布": stats["scene_counts"],
        "用户类型分布": stats["user_type_counts"],
        "典型负面反馈": stats["negative_samples"],
        "典型正面反馈": stats["positive_samples"],
    }
    system = (
        "你是一名资深 AI 产品经理，擅长从用户反馈中提炼产品洞察。"
        "你的输出必须是严格合法的 JSON，不要输出任何解释性文字或 Markdown 代码块。"
    )
    user = (
        "请基于以下真实的用户反馈数据统计，输出用户洞察。\n\n"
        f"数据统计：\n{json.dumps(summary, ensure_ascii=False, default=str)}\n\n"
        "要求：\n"
        "1. 结论必须引用上面的数据，不要编造新的数字。\n"
        "2. 每条结论控制在 45 字以内，具体、可执行，不要空话。\n"
        "3. 输出 JSON，字段为：pain_points（3 条高频痛点）、needs（3 条用户需求）、"
        "emotions（3 条用户情绪）、scenes（4 条使用场景）、opportunities（4 条产品机会）。\n"
        "4. 每个字段都是字符串数组。"
    )
    return _try_llm(system, user, lambda: _mock_analyze_feedback(feedback))


# --------------------------------------------------------------------------
# 直接回答（体验评测页：让 AI 回答用户问题）
# --------------------------------------------------------------------------


COMPANION_SYSTEM = (
    "你是「AI 游戏陪伴助手」里的陪伴 AI，服务对象是游戏玩家。"
    "硬性要求：回复控制在 2-5 句话；先接住玩家当下的情绪，再按需给最多一条可执行的建议；"
    "禁止使用“抱抱你”“加油”“你已经很棒了”这类模板化安慰；禁止讲大道理；"
    "禁止输出长篇攻略；禁止使用营销式语言。"
)


def _mock_answer(question: str) -> str:
    """本地示例回答：没有 API Key 时也能演示“AI 回答”这一步。"""
    text = question or ""
    if any(k in text for k in ["连败", "连跪", "连输", "一直输", "掉分", "输了"]):
        return (
            "连输的时候最难受的不是掉分，是明明想停又停不下来。"
            "先别复盘，这把打完给自己十分钟，回来只打一把，赢了再继续。"
            "想把过程说出来也行，我听着。"
        )
    if any(k in text for k in ["卡关", "卡住", "打不过", "过不去"]):
        return (
            "卡在这儿多半不是手速问题，是前面某一步的顺序不对。"
            "你把关卡和阵容发我，我看一眼再给具体建议。"
        )
    if any(k in text for k in ["赢了", "连胜", "上分", "翻盘"]):
        return (
            "这把赢在你能扛住那波节奏，不是运气。"
            "手感正热要不要再来一把，还是先记一下这局的思路？"
        )
    if any(k in text for k in ["无聊", "不知道玩什么", "没意思", "没目标"]):
        return (
            "不知道玩什么的时候硬开一局，通常也开心不起来。"
            "你是想要点挑战，还是单纯想放松？按这个选会快很多。"
        )
    if any(k in text for k in ["队友", "挂机", "送人头"]):
        return (
            "队友打成这样确实窝火，换谁都会烦。"
            "不过别带着这股劲开下一把，先起来走两圈再排更稳。"
        )
    return (
        "我在。你是想找人聊两句，还是想一起看看这局的问题出在哪？"
        "说清楚一点，我就按那个方向回你。"
    )


def answer_question(question: str) -> dict:
    """让陪伴 AI 直接回答玩家的问题，供体验评测页生成“AI 回答”。"""
    question = (question or "").strip()
    if not question:
        return {"answer": "", "source": "mock", "error": "请先在上方「用户问题」里写下玩家说的话。"}
    if not has_api_key():
        return {"answer": _mock_answer(question), "source": "mock", "error": None}
    try:
        reply = _chat(COMPANION_SYSTEM, question, temperature=0.75, max_tokens=320)
        reply = (reply or "").strip()
        if not reply:
            raise ValueError("模型返回了空内容")
        return {"answer": reply, "source": "llm", "error": None}
    except Exception as exc:  # noqa: BLE001 - 需要把失败原因交给页面展示
        return {
            "answer": _mock_answer(question),
            "source": "mock",
            "error": f"模型调用失败，已改用本地示例回答：{exc}",
        }


# --------------------------------------------------------------------------
# 问题诊断
# --------------------------------------------------------------------------


def detect_intent(question: str) -> str:
    text = (question or "").lower()
    scores = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        scores[intent] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def _mock_diagnose(question: str, evidence: dict) -> dict:
    """本地 Mock 诊断：按意图分支；用户描述与数据方向相反时，先纠正问题前提。"""
    intent = detect_intent(question)
    e = evidence
    t = e.get("trends", {}) or {}
    shares = e.get("category_shares", {}) or {}
    ratings = e.get("category_ratings", {}) or {}
    negatives = e.get("category_negative_rates", {}) or {}

    def g(key: str, default: str = "-") -> str:
        return e.get(key, default)

    def share(name: str) -> str:
        return shares.get(name, "-")

    def rating(name: str) -> str:
        return ratings.get(name, "-")

    def neg(name: str) -> str:
        return negatives.get(name, "-")

    def by_share() -> list:
        try:
            return sorted(shares, key=lambda k: float(str(shares[k]).rstrip("%")), reverse=True)
        except (TypeError, ValueError):
            return list(shares)

    order = by_share()
    rank = {name: i + 1 for i, name in enumerate(order)}

    dau_line = f"DAU {g('dau_start')} → {g('dau_end')}（{g('dau_relative')}）"
    completion_line = f"首次会话完成率 {g('completion_start')}% → {g('completion_end')}%（{g('completion_delta')}）"
    new_user_line = f"新玩家次日留存 {g('new_user_d1_start')}% → {g('new_user_d1_end')}%（{g('new_user_d1_delta')}）"
    response_line = f"平均响应时间 {g('response_time_start')}s → {g('response_time_end')}s（{g('response_time_delta')}）"
    streak_line = f"连败场景对话占比 {g('losing_streak_start')} → {g('losing_streak_end')}（{g('losing_streak_delta')}）"
    follow_line = f"二次追问率 {g('follow_up_start')}% → {g('follow_up_end')}%（{g('follow_up_delta')}）"
    csat_line = f"玩家满意度 CSAT {g('csat_start')} → {g('csat_end')}"
    effective_line = f"AI 回复有效率 {g('effective_start')}% → {g('effective_end')}%"
    negative_line = f"整体负面反馈率 {g('overall_negative_rate')}，反馈样本 {g('feedback_total')} 条"

    if intent == "retention":
        if t.get("first_session_completion") == "up" and t.get("new_user_d1_retention") == "up":
            location = (
                "数据不支持这个描述：" + completion_line + "、" + new_user_line
                + "，新玩家留存实际在回升，当前数据里看不到新玩家留存下滑。"
            )
            causes = [
                "如果体感上确实有流失，更可能来自老玩家，但当前数据没有做新老玩家拆分",
                "新玩家次留回升可能来自新增渠道质量变化，缺少分渠道数据验证",
                "连败场景对话占比仍在上升，情绪场景的回复质量需要继续跟踪",
            ]
            evidence_lines = [
                completion_line,
                new_user_line,
                streak_line,
                f"整体次日留存 {g('overall_d1')}%，新玩家负面反馈率 {g('new_user_negative_rate')}",
            ]
            impact = [
                "需要补充：新玩家 / 老玩家分层的留存数据",
                "需要补充：分渠道新增质量与来源",
                "连败场景会话完成率",
                "对话中断率",
            ]
        else:
            location = (
                "问题出现在新玩家的第一次会话：" + completion_line + "，" + new_user_line
                + "，两项下滑同步发生在首次使用环节。"
            )
            causes = [
                "新玩家第一次打开不知道该说什么，缺少开场引导与示例对话",
                "四个人格的差异没有解释，玩家只能靠名字猜，选不中就直接退出",
                "连败、卡关等情绪场景没有优先共情，回复偏向讲道理",
                "AI 回复默认偏长，玩家在局间碎片时间读不完就关掉",
            ]
            evidence_lines = [
                completion_line,
                new_user_line,
                streak_line,
                f"新玩家负面反馈率 {g('new_user_negative_rate')}，低于整体 "
                f"{g('overall_negative_rate')}，问题不在抱怨变多，而在会话没有走完",
            ]
            impact = ["首次会话完成率", "新玩家次日留存", "连败场景会话完成率", "对话中断率"]
    elif intent == "engagement":
        if t.get("dau") == "up":
            location = (
                "数据不支持这个描述：" + dau_line + "，近 30 天活跃度是上升的。"
                "真正走弱的是使用深度，" + completion_line + "。"
            )
            causes = [
                "活跃增长由新增拉动，但新玩家没走完第一次会话，留存没有接上",
                f"连败场景对话占比升到 {g('losing_streak_end')}，情绪最强的场景没有被接住",
                f"高峰期平均响应时间升到 {g('response_time_end')}s，等待放大了一部分流失",
                "缺少让玩家第二天主动回来的理由，例如战绩复盘与人格推荐",
            ]
            evidence_lines = [dau_line, completion_line, response_line, follow_line]
            impact = [
                "首次会话完成率",
                "新玩家次日留存",
                "DAU 的可持续性（当前增长主要来自新增）",
                "需要补充：使用时长与单次会话轮数（当前数据没有）",
            ]
        else:
            location = "活跃度确实在下滑：" + dau_line + "，需要结合留存与使用深度定位原因。"
            causes = [
                "新玩家没有走完第一次会话，新增没有沉淀成稳定活跃",
                "连败场景的情绪回复没有接住玩家，情绪最强的时刻流失最快",
                response_line + "，高峰期的等待劝退了一部分玩家",
            ]
            evidence_lines = [dau_line, completion_line, new_user_line, response_line]
            impact = ["DAU", "首次会话完成率", "新玩家次日留存", "对话中断率"]
    elif intent == "quality":
        location = (
            f"问题集中在回复质量：该类别反馈占全部反馈的 {share('回复质量')}，"
            f"平均评分 {rating('回复质量')} / 5，负面占比 {neg('回复质量')}，是第一大问题来源。"
        )
        causes = [
            "情绪场景没有被识别，把“想被接住”的对话当成了咨询场景",
            "回复习惯给完整建议，缺少先回情绪、再给一条建议的结构",
            "四个人格说话方式趋同，玩家感受不到差异",
            "负面反馈没有回流到 prompt 迭代，同类问题反复出现",
        ]
        evidence_lines = [
            f"回复质量类反馈占比 {share('回复质量')}，负面占比 {neg('回复质量')}，平均评分 {rating('回复质量')}/5",
            effective_line,
            csat_line,
            completion_line,
        ]
        impact = ["AI 回复有效率", "玩家满意度 CSAT", "首次会话完成率", "对话中断率"]
    elif intent == "length":
        location = (
            f"问题集中在回复长度：该类别反馈占 {share('回复长度')}，"
            f"平均评分 {rating('回复长度')}/5，玩家在局间读不完就直接退出。"
        )
        causes = [
            "回复缺少长度控制，一句吐槽也会触发长篇分析与复盘",
            "情绪回应与攻略内容没有分层，玩家要自己在大段文字里找重点",
            "没有把“局间碎片时间”当成默认使用场景来设计回复节奏",
        ]
        evidence_lines = [
            f"回复长度类反馈占比 {share('回复长度')}，负面占比 {neg('回复长度')}，平均评分 {rating('回复长度')}/5",
            completion_line,
            follow_line,
            csat_line,
        ]
        impact = ["对话中断率", "首次会话完成率", "二次追问率", "玩家满意度 CSAT"]
    elif intent == "speed":
        if t.get("avg_response_time") == "better":
            location = "数据不支持这个描述：" + response_line + "，响应时间实际在缩短。"
            causes = [
                "如果体感仍然慢，问题可能只集中在个别高峰时段，当前指标是全天平均",
                "缺少 P95 / P99 分位数数据，平均值会掩盖长尾等待",
            ]
            evidence_lines = [
                response_line,
                f"响应速度类反馈占比 {share('响应速度')}，负面占比 {neg('响应速度')}",
                csat_line,
                negative_line,
            ]
            impact = [
                "需要补充：分时段响应时间与 P95（当前数据没有）",
                "玩家满意度 CSAT",
                "首次会话完成率",
            ]
        else:
            location = "问题集中在响应速度：" + response_line + "，高峰期等待明显变长。"
            causes = [
                "晚间高峰并发上升，请求排队时间变长",
                "回复整体偏长且没有首字优先输出，玩家感知的等待被放大",
                "高频情绪表达没有做缓存，重复计算占用算力",
            ]
            evidence_lines = [
                response_line,
                f"响应速度类反馈占比 {share('响应速度')}，负面占比 {neg('响应速度')}，平均评分 {rating('响应速度')}/5",
                completion_line,
                csat_line,
            ]
            impact = [
                "玩家满意度 CSAT",
                "首次会话完成率",
                "高峰期流失率",
                "需要补充：分时段响应时间与 P95（当前数据没有）",
            ]
    elif intent == "stability":
        rank_note = "，是当前占比最低的一类反馈" if rank.get("稳定性") == len(order) and order else ""
        location = (
            f"稳定性相关反馈占 {share('稳定性')}，负面占比 {neg('稳定性')}，"
            f"平均评分 {rating('稳定性')}/5{rank_note}。"
        )
        causes = [
            "缺少崩溃与接口错误监控，玩家描述的“卡住 / 掉线”无法归因",
            "高峰期超时可能被玩家感知成崩溃，需要和响应时间一起看",
            "异常发生时没有降级提示，玩家分不清是网络还是产品的问题",
        ]
        evidence_lines = [
            f"稳定性类反馈占比 {share('稳定性')}，负面占比 {neg('稳定性')}，平均评分 {rating('稳定性')}/5",
            response_line,
            negative_line,
            csat_line,
        ]
        impact = [
            "需要补充：崩溃率 / 接口错误率 / 超时率（当前数据没有）",
            "玩家满意度 CSAT",
            "首次会话完成率",
            "对话中断率",
        ]
    elif intent == "feature":
        rank_text = f"，占比第 {rank.get('功能缺失')} 位" if rank.get("功能缺失") else ""
        location = (
            f"问题属于能力与说明缺口：功能缺失类反馈占 {share('功能缺失')}{rank_text}，"
            f"负面占比 {neg('功能缺失')}，平均评分 {rating('功能缺失')}/5。"
            "玩家要的是补齐能力，不是修一个坏掉的功能。"
        )
        causes = [
            "人格入口只有名字，没有说明适用场景，玩家不知道该选哪个",
            "缺少示例对话与开场引导，新玩家不知道第一句能说什么",
            "切换人格后的上下文继承规则没有说明，玩家担心记录丢失",
            "能力缺口（战绩同步、语音陪伴）没有公开的排期与验证计划",
        ]
        evidence_lines = [
            f"功能缺失类反馈占比 {share('功能缺失')}，负面占比 {neg('功能缺失')}，平均评分 {rating('功能缺失')}/5",
            f"回复质量类反馈占比 {share('回复质量')}（占比第一，说明体验问题与能力缺口同时存在）",
            negative_line,
            csat_line,
        ]
        impact = [
            "人格选择说明与示例对话（低成本、见效快）",
            "战绩同步（信号明确、成本可控）",
            "语音陪伴（建议先小范围验证）",
            "进入需求池后按 RICE 排序",
        ]
    elif intent == "monetization":
        location = (
            "数据不足，无法回答付费转化的问题：当前数据集不包含付费率、ARPU、订阅转化等商业化数据，"
            "我不会用陪伴体验指标去推断收入结论。"
        )
        causes = [
            "缺少付费转化埋点与账单数据，无法计算付费率与漏斗转化",
            "缺少用户分层标签（免费 / 试用 / 付费 / 流失），无法做分组对比",
            "商业化通常受留存影响，但当前只能用留存类信号做间接参考",
        ]
        evidence_lines = [
            f"当前可用的只有体验类数据：{dau_line}、{completion_line}",
            f"{csat_line}，{effective_line}",
            negative_line + "，全部是体验类反馈，不含付费行为",
            "待补充数据：付费率、ARPU、订阅转化漏斗、付费用户留存",
        ]
        impact = [
            "需要补充：付费率与 ARPU",
            "需要补充：订阅 / 内购转化漏斗",
            "需要补充：付费用户分层的留存对照",
            "数据补齐前不输出商业化结论",
        ]
    elif intent == "experiment":
        location = (
            "实验数据可用，可以判断方向是否有效：对照组与实验组存在明确差异，"
            "但样本只覆盖单次实验周期，长期留存还需继续观察。"
        )
        causes = [
            "实验组的陪伴回复策略变化带来了行为差异",
            "样本周期较短，还不能完全排除新鲜感效应",
            "实验分组与新增渠道是否交叉影响，当前未做交叉分析",
        ]
        evidence_lines = [
            f"A/B 实验样本：{g('experiment_sample')} 条",
            completion_line,
            new_user_line,
            csat_line,
        ]
        impact = [
            "首次会话完成率",
            "次日留存",
            "对话中断率",
            "需要补充：实验组与对照组的显著性检验明细",
        ]
    elif intent == "requirement":
        if order:
            location = (
                "按反馈占比排优先级："
                + " > ".join(f"{name} {share(name)}" for name in order[:4])
                + "。建议从占比最高、且与留存直接相关的回复质量切入。"
            )
            share_line = "各类反馈占比：" + "、".join(f"{n} {share(n)}" for n in order)
        else:
            location = "缺少反馈类别占比数据，无法给出优先级排序。"
            share_line = "反馈类别占比数据缺失"
        causes = [
            "回复质量占比最高，且与首次会话完成率下滑直接相关，应排在第一优先",
            "功能缺失属于能力补齐，周期长，可排在体验修复之后",
            "响应速度与稳定性占比相近且修复成本低，适合并行做小步优化",
        ]
        evidence_lines = [
            share_line,
            f"回复质量平均评分 {rating('回复质量')}/5，功能缺失平均评分 {rating('功能缺失')}/5",
            completion_line,
            response_line,
        ]
        impact = [
            "回复质量（第一优先级）",
            "响应速度与稳定性（低成本快修）",
            "功能缺失（进入需求池按 RICE 排序）",
            "首次会话完成率",
        ]
    else:
        quality_note = f"，其中回复质量类占比最高（{share('回复质量')}）" if order and order[0] == "回复质量" else ""
        location = (
            "问题没有指向具体方向，先给整体判断：" + dau_line + "，活跃度仍在增长；"
            "但使用深度在下滑，" + completion_line + "、" + new_user_line + quality_note + "。"
        )
        causes = [
            "新玩家没走完第一次会话，是当前最明确的异常指标",
            f"连败场景对话占比升到 {g('losing_streak_end')}，情绪场景的回复可能没接住玩家",
            f"平均响应时间升到 {g('response_time_end')}s，高峰期体验在变慢",
            f"回复质量类反馈占比最高（{share('回复质量')}），是体验问题的集中区",
        ]
        evidence_lines = [
            dau_line,
            completion_line,
            new_user_line,
            f"{streak_line}；{response_line}",
        ]
        impact = [
            "首次会话完成率",
            "新玩家次日留存",
            "回复质量与响应速度",
            "建议把问题聚焦到一个具体环节，结论会更明确",
        ]

    return {
        "intent": intent,
        "location": location,
        "causes": causes,
        "evidence": evidence_lines,
        "impact": impact,
    }


def diagnose_problem(question: str, evidence: dict) -> dict:
    """产品问题诊断：先验证问题前提，再给出原因假设、证据与影响面。"""
    system = (
        "你是一名资深 AI 产品经理，负责基于数据做产品问题诊断。"
        "输出必须是严格合法的 JSON，不要输出解释性文字或 Markdown 代码块。"
    )
    user = (
        f"用户提出的问题是：{question}\n\n"
        f"可用数据：\n{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
        f"数据覆盖范围：\n- 有：{DATA_COVERAGE['有']}\n- 没有：{DATA_COVERAGE['没有']}\n\n"
        "硬性要求：\n"
        "1. 只允许使用上面给出的数据，禁止编造任何数字、指标或结论。\n"
        "2. 先用 trends 核对用户描述的现象是否成立，分三种情况处理：\n"
        "   (a) 数据与描述明确相反（例如用户说活跃度下降，但 dau 是 up）："
        "location 必须以“数据不支持这个描述”开头，并写清实际趋势；\n"
        "   (b) 描述只部分成立（例如整体留存没降，但新玩家留存下降了）："
        "location 必须以“这个描述部分成立”开头，两边的数据都要给出，不要笼统说数据不支持；\n"
        "   (c) 描述成立：直接给结论，禁止为了显得严谨而强行使用“数据不支持”；\n"
        "   (d) 问题本身不是趋势描述，而是提问或求建议（例如问优先级、问怎么优化、问是否严重）："
        "直接给结论，禁止使用“数据不支持这个描述”或“这个描述部分成立”这类纠正句式。\n"
        "3. 如果问题涉及的数据不在覆盖范围内（例如付费、收入、渠道投放），"
        "location 必须以“数据不足，无法判断”开头，说明具体缺哪些数据，"
        "并在 impact 中列出需要补充的数据，不允许用现有数据推测。\n"
        "4. evidence 中每一条都必须带具体数字，并且方向要和结论一致；"
        "禁止用“指标在改善”的数字去证明“问题在恶化”。\n"
        "5. 如果现有信号不足以支撑明确结论，要直接说明，不要为了给出答案而编原因。\n"
        "6. trends 字段说明：up / down 表示指标相对期初上升或下降，worse / better 表示体验变差或变好；"
        "其中二次追问率（follow_up_rate）上升代表玩家更愿意继续对话，属于中性信号，不要直接当成负面。\n"
        "7. 字段说明：category_shares 是各问题类别的反馈条数占比，不是负面率，引用时必须写成“反馈占比”；"
        "category_negative_rates 是各类别中评分小于等于 2 的负面率；category_ratings 是各类别平均评分（满分 5）；"
        "scene_shares 是各游戏场景的对话占比；xxx_start / xxx_end / xxx_delta 分别是期初值、期末值与变化量。"
        "引用占比和负面率时不要混用两个字段。\n\n"
        "输出 JSON 字段：intent（问题类型，简短中文）、location（问题定位，80 字以内）、"
        "causes（可能原因，3-4 条，每条 35 字以内）、evidence（支撑证据，3-4 条，必须带数字）、"
        "impact（影响指标或需要补充的数据，3-4 条）。"
        "除 intent 为字符串外，其余字段均为字符串数组。"
    )

    def fallback() -> dict:
        return _mock_diagnose(question, evidence)

    return _try_llm(system, user, fallback)


# --------------------------------------------------------------------------
# 产品方案生成
# --------------------------------------------------------------------------


def _mock_product_plan(problem: str, evidence: dict) -> dict:
    """本地 Mock 方案：按问题意图给出不同方案，避免所有问题都套同一个留存故事。"""
    intent = detect_intent(problem)
    e = evidence
    shares = e.get("category_shares", {}) or {}
    completion = f"{e.get('completion_start', '-')}% → {e.get('completion_end', '-')}%"
    new_user = f"{e.get('new_user_d1_start', '-')}% → {e.get('new_user_d1_end', '-')}%"
    streak = f"{e.get('losing_streak_start', '-')} → {e.get('losing_streak_end', '-')}"
    response = f"{e.get('response_time_start', '-')}s → {e.get('response_time_end', '-')}s"
    quality_share = shares.get("回复质量", "-")
    length_share = shares.get("回复长度", "-")
    speed_share = shares.get("响应速度", "-")
    feature_share = shares.get("功能缺失", "-")

    if intent == "quality":
        return {
            "background": (
                f"围绕「{problem}」，回复质量类反馈占比 {quality_share}，是第一大问题来源；"
                f"同期首次会话完成率 {completion}，玩家在情绪最强的时刻没有被接住。"
            ),
            "target_users": [
                "连败、卡关后情绪波动明显的新手玩家",
                "把 AI 当搭子、以情绪表达为主的休闲玩家",
                "在局间碎片时间使用、需要快速回应的竞技玩家",
            ],
            "core_problem": (
                "玩家想被接住情绪，AI 却按咨询场景输出讲道理式建议，"
                "四个人格说话方式趋同，对话在几轮内就结束。"
            ),
            "solutions": [
                "识别到连败 / 卡关 / 被队友影响时优先共情，建议最多给一条",
                "回复结构固定为「先回应情绪 → 再给一条可选项 → 留一个话头」",
                "四个人格分别建立说话方式约束，禁止复用同一套句式",
                "把 👍 / 👎 反馈按人格与场景聚合，回流到 prompt 迭代",
                "对高频负面表达建立回归用例，每次改 prompt 都跑一遍",
            ],
            "metrics": ["AI 回复有效率", "回复质量类平均评分", "首次会话完成率", "玩家满意度 CSAT"],
            "expected": (
                "目标：回复质量类平均评分提升 0.3-0.5 分，负面反馈占比下降 3-5 个百分点，"
                "并用 A/B 实验验证“情绪优先”策略对会话完成率的影响。"
            ),
        }

    if intent == "length":
        return {
            "background": (
                f"围绕「{problem}」，回复长度类反馈占比 {length_share}，"
                f"同期首次会话完成率 {completion}，玩家在局间读不完就直接退出。"
            ),
            "target_users": [
                "在匹配、等队友的碎片时间使用的竞技玩家",
                "移动端、单手操作的玩家",
                "连败后只想快速吐槽、不想看长篇分析的玩家",
            ],
            "core_problem": (
                "默认回复偏长，情绪回应与攻略复盘混在一起，"
                "玩家要自己在大段文字里找重点，找不到就退出对话。"
            ),
            "solutions": [
                "陪伴回复默认 2-3 句，超出部分折叠为“展开看复盘”",
                "情绪回应与战术建议分层输出，先给短句接住情绪",
                "把“想聊天”与“想获得游戏建议”分开处理，分别控制篇幅",
                "为不同人格设置回复长度上限，温柔与损友人格默认更短",
            ],
            "metrics": ["对话中断率", "首次会话完成率", "二次追问率", "玩家满意度 CSAT"],
            "expected": (
                "目标：首次会话完成率回升 4-6 个百分点，回复长度类反馈占比下降 30%，"
                "用 A/B 实验对比“短回复默认 + 展开”与当前的长回复策略。"
            ),
        }

    if intent == "speed":
        return {
            "background": (
                f"围绕「{problem}」，平均响应时间 {response}，"
                f"响应速度类反馈占比 {speed_share}，等待容易被玩家理解成“它不想理我”。"
            ),
            "target_users": [
                "晚间高峰期使用的活跃玩家",
                "打团、等匹配间隙使用的竞技玩家",
                "对即时反馈敏感的移动端玩家",
            ],
            "core_problem": (
                "高峰期请求排队时间变长，叠加回复本身偏长，"
                "玩家在局间的几十秒里，感知到的等待被明显放大。"
            ),
            "solutions": [
                "首字优先流式输出，先把第一句情绪回应推给玩家",
                "对高频情绪表达与常见场景做缓存，减少重复计算",
                "高峰期前置排队提示，明确告知预计等待时间",
                "长回复分段推送，避免整段生成完才展示",
            ],
            "metrics": ["平均响应时间（含 P95）", "玩家满意度 CSAT", "首次会话完成率", "高峰期流失率"],
            "expected": (
                "目标：平均响应时间回到 5s 以内，高峰期 P95 不超过 8s，"
                "并用 A/B 实验验证首字优先输出对会话完成率的影响。"
            ),
        }

    if intent == "feature":
        return {
            "background": (
                f"围绕「{problem}」，功能缺失类反馈占比 {feature_share}，是占比靠前的问题类别；"
                "玩家提出的多是能力补齐诉求，而不是现有功能出错。"
            ),
            "target_users": [
                "第一次使用、不清楚四个人格差别的玩家",
                "希望把对局结果带进对话的竞技玩家",
                "习惯开黑、希望有语音陪伴的组队玩家",
            ],
            "core_problem": (
                "人格入口只有名字，没有适用场景说明与示例对话，玩家选不准就直接退出；"
                "战绩同步、语音陪伴等能力缺口也缺少明确的验证计划。"
            ),
            "solutions": [
                "人格选择页补一句说明与示例对话，标注适用场景",
                "新玩家首次进入时推荐人格，支持试用后一键切换",
                "说明切换人格后上下文会继承，消除丢记录的担心",
                "先做战绩截图识别与对局总结，验证后再接语音陪伴",
                "把能力缺口放进需求池，按 RICE 排序并公开排期",
            ],
            "metrics": ["首次会话完成率", "人格选择页跳出率", "战绩同步使用率", "新玩家次日留存"],
            "expected": (
                "目标：人格相关的重复追问减少，首次会话完成率回升 3-5 个百分点；"
                "战绩同步先小范围验证使用意愿，再决定语音陪伴的投入。"
            ),
        }

    if intent == "monetization":
        return {
            "background": (
                f"围绕「{problem}」，当前数据不足以支撑商业化结论："
                "数据集不包含付费率、ARPU 与订阅转化漏斗，只有体验类指标与反馈。"
            ),
            "target_users": [
                "当前无法拆分：缺少免费 / 试用 / 付费 / 流失的分层标签",
                "能间接参考的只有留存与满意度这类体验指标",
                "需要补齐数据后重新定义付费意愿较高的玩家画像",
            ],
            "core_problem": (
                "商业化判断缺少数据：没有付费转化埋点、账单数据与用户分层标签，"
                "任何收入结论都会是猜测。"
            ),
            "solutions": [
                "补齐付费事件埋点：曝光、点击、下单、支付成功四段漏斗",
                "对接账单数据，建立付费率、ARPU、LTV 的基础口径",
                "给用户打免费 / 试用 / 付费 / 流失分层标签",
                "先验证留存与付费的相关性，再讨论具体商业化方案",
            ],
            "metrics": ["付费率", "ARPU", "订阅转化漏斗", "付费用户留存"],
            "expected": (
                "目标：先把数据口径补齐，让商业化分析从“无数据”推进到“可计算”，"
                "本阶段不输出收入预测。"
            ),
        }

    return {
        "background": (
            f"围绕「{problem}」，数据已经给出明确信号：连败场景对话占比 {streak}，"
            f"但同期首次会话完成率 {completion}，新玩家次日留存 {new_user}。"
            "玩家在情绪最强的时刻打开了产品，却没有被接住。"
        ),
        "target_users": [
            "刚入坑、连败后情绪波动明显的新手玩家",
            "习惯在局间碎片时间使用的竞技玩家",
            "把 AI 当搭子、以情绪表达为主的休闲玩家",
        ],
        "core_problem": (
            "玩家在连败或卡关时打开产品，想被接住情绪，"
            "但 AI 要么讲道理、要么给一长串建议，导致对话在几轮内结束，没有形成陪伴关系。"
        ),
        "solutions": [
            "识别到连败 / 卡关时优先共情，建议最多给一条",
            "新增开场引导：用示例对话告诉玩家可以说什么",
            "讲清温柔 / 损友 / 教练 / 冒险四个人格的差异与适用场景",
            "陪伴回复默认控制在 2-3 句，复盘与攻略折叠为可展开",
            "对高频情绪表达做缓存，压缩高峰期首字等待时间",
        ],
        "metrics": [
            "连败场景会话完成率（核心）",
            "新玩家次日留存",
            "对话中断率",
            "玩家满意度评分",
        ],
        "expected": (
            "目标：连败场景会话完成率回升 5-8 个百分点，新玩家次日留存回升 3-5 个百分点，"
            "并通过 A/B 实验验证人格化陪伴对留存的长期影响。"
        ),
    }


def generate_product_plan(problem: str, evidence: dict) -> dict:
    """产品方案生成：背景、目标用户、核心问题、方案、指标与预期效果。"""
    system = (
        "你是一名资深 AI 产品经理，负责输出可落地的产品方案。"
        "要求方案具体、可执行，避免空话和营销语言。"
        "输出必须是严格合法的 JSON，不要输出解释性文字或 Markdown 代码块。"
    )
    user = (
        f"需要解决的问题：{problem}\n\n"
        f"相关数据：\n{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
        "请输出产品方案，JSON 字段：\n"
        "background（需求背景，80 字以内，引用上面数据）、"
        "target_users（目标用户，3 条）、core_problem（核心问题，60 字以内）、"
        "solutions（产品方案，4-5 条，每条 30 字以内）、"
        "metrics（核心指标，4 条）、expected（预期效果，60 字以内）。\n"
        "除 background、core_problem、expected 为字符串外，其余为字符串数组。"
    )
    return _try_llm(system, user, lambda: _mock_product_plan(problem, evidence))


# --------------------------------------------------------------------------
# A/B 实验分析
# --------------------------------------------------------------------------


def _mock_ab_analysis(summary: dict) -> dict:
    rows = summary.get("rows", [])
    improved = [r for r in rows if r.get("relative", 0) > 0]
    names = "、".join(r["metric"] for r in improved) or "核心指标"
    significant = [r for r in improved if r.get("p_value", 1) < 0.05]
    return {
        "observation": (
            f"B 组在{names}上均优于 A 组，其中 "
            + "、".join(
                f"{r['metric']} {r['a']}→{r['b']}（{r['relative']:+.1f}%）" for r in significant[:3]
            )
            + "。改善主要集中在连败场景的首次使用链路上，说明情绪优先的陪伴回复对激活环节有效。"
        ),
        "risk": (
            f"本次实验样本量为 {summary.get('sample', '-')} 名新用户、周期 {summary.get('days', '-')} 天，"
            "属于短周期实验。次日留存与满意度仍需要更长周期验证，"
            "同时要判断 B 组玩家是真的被接住了情绪，还是只因为回复更讨喜而多聊了几句。"
        ),
        "suggestion": [
            "延长实验到 14 天，重点观察 D7 留存与人均会话次数",
            "对 B 组做一次用户访谈，确认引导是否真正降低了理解成本",
            "按入口来源拆分数据，判断不同渠道的用户对引导的敏感度",
            "如果指标持续为正，按 20% → 50% → 全量灰度推进上线",
        ],
    }


def analyze_ab_test(summary: dict) -> dict:
    """A/B 实验分析：结论、风险与下一步建议。"""
    system = (
        "你是一名资深 AI 产品经理，负责解读 A/B 实验结果。"
        "必须基于给定数据，不允许夸大结论，要明确说明数据是模拟数据。"
        "输出必须是严格合法的 JSON，不要输出解释性文字或 Markdown 代码块。"
    )
    user = (
        f"实验名称：{summary.get('name', '-')}\n"
        f"样本量：{summary.get('sample', '-')}，周期：{summary.get('days', '-')} 天\n"
        f"实验数据：\n{json.dumps(summary.get('rows', []), ensure_ascii=False, default=str)}\n\n"
        "请输出 JSON，字段：observation（实验观察，引用具体数字，80 字以内）、"
        "risk（需要注意的风险与不确定性，80 字以内）、"
        "suggestion（下一步建议，4 条，每条 30 字以内，字符串数组）。"
    )
    return _try_llm(system, user, lambda: _mock_ab_analysis(summary))


# --------------------------------------------------------------------------
# AI 回答体验评测
# --------------------------------------------------------------------------


FUNCTION_CHARS = set(
    "我你他她它的了着是个在有为和与就都也很不要吗呢呀啊吧把被给跟而但所以对从到于之其此该等"
    "什么怎如何请帮可以能否没会想让你一下吗"
)

COMPLEX_HINTS = [
    "攻略", "出装", "配装", "阵容", "练枪", "枪法", "复盘", "上分", "打法", "意识",
    "代码", "爬虫", "python", "java", "sql", "脚本", "程序", "算法", "报错", "调试",
    "架构", "部署", "搭建", "实现", "方案", "分析", "设计", "重构", "接口",
]

DOC_HINTS = ["官方文档", "文档", "条例", "规定", "法律", "政策", "来源", "依据", "版本", "参数"]


def _extract_terms(text: str) -> set[str]:
    """提取问题中的关键词：英文单词 + 过滤掉虚词的中文二元组。"""
    text = (text or "").lower()
    terms = set(re.findall(r"[a-z]{2,}", text))
    for run in re.findall(r"[\u4e00-\u9fa5]+", text):
        for i in range(len(run) - 1):
            bigram = run[i : i + 2]
            if any(ch in FUNCTION_CHARS for ch in bigram):
                continue
            terms.add(bigram)
    return terms


def _content_chars(text: str) -> set[str]:
    """提取去掉虚词后的中文实义字符。"""
    return {ch for ch in re.findall(r"[\u4e00-\u9fa5]", text or "") if ch not in FUNCTION_CHARS}


EMOTION_HINTS = ["烦", "崩", "气死", "难受", "好累", "不想玩", "emo", "破防", "心态炸", "哭了", "郁闷"]
ADVICE_HINTS = ["怎么", "如何", "攻略", "出装", "配装", "阵容", "练", "推荐", "为什么"]


def _expected_length(question: str) -> int:
    """根据问题类型估计“合适的回复长度”。

    玩家在情绪表达时想要的是被接住，而不是一份长建议，所以这类问题的合适长度更短。
    """
    text = (question or "").lower()
    if any(hint in text for hint in COMPLEX_HINTS):
        return 550
    if any(hint in text for hint in EMOTION_HINTS) and not any(h in text for h in ADVICE_HINTS):
        return 280
    if len(text) <= 14:
        return 220
    return 400


def _heuristic_scores(question: str, answer: str) -> tuple[dict, list[str]]:
    answer = answer or ""
    length = len(answer)
    aspects = []

    if re.search(r"^\s*\d+[\.、)]", answer, flags=re.M) or any(
        kw in answer for kw in ["首先", "其次", "然后", "最后", "第一步", "第二步", "第三步"]
    ):
        aspects.append("步骤")
    if "```" in answer or any(kw in answer for kw in ["例如", "示例", "比如"]):
        aspects.append("示例")
    if any(kw in answer for kw in ["可以试试", "建议", "推荐", "方向", "试试", "几个"]):
        aspects.append("具体建议")
    if any(kw in answer for kw in ["注意", "风险", "避免", "坑", "容易出错"]):
        aspects.append("注意事项")
    if any(kw in answer for kw in ["复盘", "战绩", "输出", "保存", "导出", "结果", "返回"]):
        aspects.append("结果说明")
    if "？" in answer or "?" in answer:
        aspects.append("互动追问")

    # 简洁性：与“这个问题合适的回答长度”对比，而不是绝对长度
    expected = _expected_length(question)
    ratio = length / expected
    conciseness = 100 - max(0.0, ratio - 0.8) * 40
    if length < 80:
        conciseness = min(conciseness, 90)
    conciseness = int(max(30, min(96, conciseness)))

    # 可执行性：是否给出可直接使用的步骤、代码或命令
    executability = 70
    if "```" in answer:
        executability += 10
    if "步骤" in aspects:
        executability += 5
    if "示例" in aspects:
        executability += 4
    if re.search(r"[a-zA-Z_]+\(", answer):
        executability += 3
    if length < 420 and ("步骤" in aspects or "具体建议" in aspects):
        executability += 6
    executability = int(max(40, min(96, executability)))

    # 内容完整性：关键环节覆盖度
    completeness = 62 + 7 * len(aspects)
    if length > 500:
        completeness += 3
    completeness = int(max(45, min(96, completeness)))

    # 意图匹配：关键词覆盖率 + 实义字符覆盖率
    q_terms = _extract_terms(question)
    term_hit = len([t for t in q_terms if t in answer.lower()]) / len(q_terms) if q_terms else 0.0
    q_chars = _content_chars(question)
    char_hit = len([c for c in q_chars if c in answer]) / len(q_chars) if q_chars else 0.0
    cliche_count = sum(1 for phrase in CLICHE_PHRASES if phrase in answer)
    intent_match = int(max(35, min(95, 58 + 20 * term_hit + 20 * char_hit - 4 * cliche_count)))

    accuracy = 78
    if not any(w in answer for w in HEDGING_WORDS):
        accuracy += 6
    if "```" in answer or re.search(r"\d", answer):
        accuracy += 5
    if length > 300:
        accuracy += 3
    if any(kw in answer for kw in DOC_HINTS):
        accuracy += 3
    accuracy -= min(20, 5 * cliche_count)
    accuracy = int(max(40, min(96, accuracy)))

    scores = {
        "回答准确性": accuracy,
        "意图匹配": intent_match,
        "内容完整性": completeness,
        "简洁性": conciseness,
        "可执行性": executability,
    }
    return scores, aspects


ISSUE_BY_DIMENSION = {
    "简洁性": "陪伴回复偏长，玩家在局间读不完，容易直接退出对话。",
    "可执行性": "回答缺少可直接执行的步骤或示例，用户拿到后还需要二次加工。",
    "意图匹配": "回复没有回应当下真正的诉求——玩家在连败时往往想被接住情绪，而不是要一份建议清单。",
    "回答准确性": "回答中存在不确定表述，关键结论缺少明确依据。",
    "内容完整性": "回答缺少关键环节，用户需要再次追问才能补齐信息。",
}

ADVICE_BY_DIMENSION = {
    "简洁性": [
        "陪伴回复默认控制在 2-3 句，先回应情绪再补充信息",
        "根据场景动态调整长度：吐槽场景短，复盘场景再展开",
        "把复盘、攻略类长内容折叠为可展开卡片",
        "对情绪表达类输入优先给一句直接回应",
    ],
    "可执行性": [
        "回答中默认给出可运行的代码或操作步骤",
        "补充输入输出示例，降低用户二次加工成本",
        "把长流程拆成编号步骤，方便用户逐条执行",
        "对容易出错的地方给出明确提示",
    ],
    "意图匹配": [
        "在回答前先做一次意图澄清，确认用户目标",
        "对模糊问题主动给出 2-3 个可能方向",
        "结合上下文理解指代，减少答非所问",
        "增加意图识别评测集，持续监控匹配度",
    ],
    "回答准确性": [
        "关键结论补充依据或来源标注",
        "减少“可能、大概”等不确定表述",
        "对事实类问题优先检索后回答",
        "建立高频问题的准确率抽检机制",
    ],
    "内容完整性": [
        "补充边界条件与异常情况的处理说明",
        "对复杂问题给出完整流程而不是片段",
        "在回答末尾提示可能遗漏的相关问题",
        "结合模板保证关键环节不缺失",
    ],
}


def _mock_evaluate(question: str, answer: str) -> dict:
    scores, _ = _heuristic_scores(question, answer)
    overall = int(round(sum(scores[d] * DIMENSION_WEIGHT[d] for d in DIMENSION_ORDER)))
    weakest = min(scores, key=scores.get)
    issues = [
        ISSUE_BY_DIMENSION[weakest],
        f"综合评分 {overall} 分，其中{weakest}得分最低（{scores[weakest]} 分），是最主要的体验短板。",
    ]
    return {
        "scores": scores,
        "overall": overall,
        "weakest": weakest,
        "issues": issues,
        "suggestions": ADVICE_BY_DIMENSION[weakest],
    }


def evaluate_answer(question: str, answer: str) -> dict:
    """AI 回答体验评测：五个维度打分 + 体验问题 + 优化建议。"""
    heuristic_scores, _ = _heuristic_scores(question, answer)

    def fallback() -> dict:
        return _mock_evaluate(question, answer)

    system = (
        "你是一名 AI 产品的回答质量评测专家。"
        "你需要对 AI 回答做客观评测，评分要有区分度，不能全部给高分。"
        "输出必须是严格合法的 JSON，不要输出解释性文字或 Markdown 代码块。"
    )
    user = (
        f"用户问题：{question}\n\nAI 回答：\n{answer[:1800]}\n\n"
        "请从五个维度评分（0-100 的整数，越高越好）：回答准确性、意图匹配、内容完整性、简洁性、可执行性。\n"
        "注意：回答越长，简洁性得分应当越低；回答缺少步骤或代码时，可执行性得分应当降低。\n"
        "输出 JSON 字段：scores（包含上述五个维度）、overall（综合评分 0-100 整数）、"
        "weakest（得分最低的维度名称）、issues（2 条体验问题）、suggestions（4 条优化建议）。"
    )

    result = _try_llm(system, user, fallback)
    scores = result.get("scores")
    if not isinstance(scores, dict) or not all(d in scores for d in DIMENSION_ORDER):
        result = fallback()
        result["source"] = "mock"
        result["error"] = "模型返回的评分结构不完整，已使用本地评测"
        return result
    try:
        result["scores"] = {d: int(max(0, min(100, float(scores[d])))) for d in DIMENSION_ORDER}
        result["overall"] = int(result.get("overall") or round(
            sum(result["scores"][d] * DIMENSION_WEIGHT[d] for d in DIMENSION_ORDER)
        ))
        result["weakest"] = result.get("weakest") or min(result["scores"], key=result["scores"].get)
        result["issues"] = result.get("issues") or _mock_evaluate(question, answer)["issues"]
        result["suggestions"] = result.get("suggestions") or ADVICE_BY_DIMENSION[result["weakest"]]
    except (TypeError, ValueError):
        result = fallback()
        result["source"] = "mock"
        result["error"] = "模型返回的评分无法解析，已使用本地评测"
    return result


# --------------------------------------------------------------------------
# Product Manager Agent
# --------------------------------------------------------------------------

PIPELINE = [
    ("intent", "Intent Analyzer", "识别用户问题意图，决定后续调用哪些分析模块"),
    ("data", "Data Analyst", "读取指标与反馈数据，定位异常指标"),
    ("insight", "User Insight Agent", "从用户反馈中提炼痛点、需求与情绪"),
    ("strategy", "Product Strategy Agent", "生成问题诊断与产品方案"),
    ("experiment", "Experiment Agent", "结合 A/B 实验结果给出验证建议"),
]

PIPELINE_NAMES = {key: name for key, name, _ in PIPELINE}

ROUTE_BY_INTENT = {
    "retention": ["intent", "data", "insight", "strategy", "experiment"],
    "engagement": ["intent", "data", "insight", "strategy"],
    "quality": ["intent", "data", "insight", "strategy"],
    "length": ["intent", "data", "insight", "strategy"],
    "speed": ["intent", "data", "insight", "strategy"],
    "stability": ["intent", "data", "insight", "strategy"],
    "feature": ["intent", "data", "insight", "strategy"],
    "experiment": ["intent", "data", "strategy", "experiment"],
    "requirement": ["intent", "data", "insight", "strategy"],
    "monetization": ["intent", "data", "strategy"],
    "general": ["intent", "data", "insight", "strategy", "experiment"],
}

def _data_step_line(intent: str, evidence: dict) -> str:
    """Data Analyst 步骤的摘要：按问题意图展示相关指标，而不是固定三件套。"""
    e = evidence
    shares = e.get("category_shares", {}) or {}

    def g(key: str, default: str = "-") -> str:
        return e.get(key, default)

    if intent == "engagement":
        return (
            f"关键指标：DAU {g('dau_start')} → {g('dau_end')}（{g('dau_relative')}），"
            f"首次会话完成率 {g('completion_start')}% → {g('completion_end')}%，"
            f"二次追问率 {g('follow_up_start')}% → {g('follow_up_end')}%"
        )
    if intent == "quality":
        return (
            f"关键指标：回复质量类反馈占比 {shares.get('回复质量', '-')}，"
            f"AI 回复有效率 {g('effective_start')}% → {g('effective_end')}%，"
            f"满意度 {g('csat_start')} → {g('csat_end')}"
        )
    if intent == "length":
        return (
            f"关键指标：回复长度类反馈占比 {shares.get('回复长度', '-')}，"
            f"首次会话完成率 {g('completion_start')}% → {g('completion_end')}%，"
            f"二次追问率 {g('follow_up_start')}% → {g('follow_up_end')}%"
        )
    if intent == "speed":
        return (
            f"关键指标：平均响应时间 {g('response_time_start')}s → {g('response_time_end')}s"
            f"（{g('response_time_delta')}），满意度 {g('csat_start')} → {g('csat_end')}"
        )
    if intent == "stability":
        return (
            f"关键指标：稳定性类反馈占比 {shares.get('稳定性', '-')}，"
            f"整体负面反馈率 {g('overall_negative_rate')}；"
            "崩溃率与接口错误率不在当前数据范围内"
        )
    if intent == "feature":
        return (
            f"关键指标：功能缺失类反馈占比 {shares.get('功能缺失', '-')}，"
            f"回复质量类反馈占比 {shares.get('回复质量', '-')}，"
            f"整体负面反馈率 {g('overall_negative_rate')}"
        )
    if intent == "monetization":
        return "数据检查：当前数据集没有付费率、ARPU 与订阅转化数据，本问题只能给出数据缺口清单"
    if intent == "experiment":
        return (
            f"关键指标：实验样本 {g('experiment_sample')} 条，"
            f"首次会话完成率 {g('completion_start')}% → {g('completion_end')}%"
        )
    if intent == "requirement":
        if not shares:
            return "数据检查：反馈类别占比数据缺失"
        order = sorted(shares, key=lambda k: float(str(shares[k]).rstrip("%")), reverse=True)
        return "反馈占比排序：" + " > ".join(f"{n} {shares[n]}" for n in order[:4])
    return (
        f"关键指标：DAU {g('dau_start')} → {g('dau_end')}（{g('dau_relative')}），"
        f"首次会话完成率 {g('completion_start')}% → {g('completion_end')}%，"
        f"新玩家次日留存 {g('new_user_d1_start')}% → {g('new_user_d1_end')}%"
    )


@dataclass
class AgentResult:
    question: str
    intent: str
    intent_label: str
    steps: list[dict] = field(default_factory=list)
    diagnosis: dict = field(default_factory=dict)
    insights: dict = field(default_factory=dict)
    plan: dict = field(default_factory=dict)
    experiment: dict = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)


def run_agent(
    question: str,
    feedback: pd.DataFrame,
    evidence: dict,
    ab_summary: dict | None = None,
    progress=None,
) -> AgentResult:
    """Product Manager Agent：按意图路由到不同分析模块，并记录每一步的执行结果。"""
    intent = detect_intent(question)
    route = ROUTE_BY_INTENT.get(intent, ROUTE_BY_INTENT["general"])
    result = AgentResult(question=question, intent=intent, intent_label=INTENT_LABEL[intent])

    triggered = []

    # Step 1：意图识别（本地规则，不消耗模型调用）
    result.steps.append(
        {
            "key": "intent",
            "name": "Intent Analyzer",
            "output": f"识别为「{INTENT_LABEL[intent]}」，将调用："
            + "、".join(PIPELINE_NAMES[k] for k in route if k != "intent"),
            "done": True,
            "triggered": True,
        }
    )

    if "data" in route:
        triggered.append("data")
        line = _data_step_line(intent, evidence)
        result.steps.append(
            {"key": "data", "name": "Data Analyst", "output": line, "done": True, "triggered": True}
        )
    else:
        result.steps.append(
            {
                "key": "data",
                "name": "Data Analyst",
                "output": "本次问题未触发指标分析模块",
                "done": False,
                "triggered": False,
            }
        )

    if progress:
        progress()

    if "insight" in route:
        triggered.append("insight")
        result.insights = analyze_feedback(feedback)
        result.sources.append(result.insights.get("source", "mock"))
        result.steps.append(
            {
                "key": "insight",
                "name": "User Insight Agent",
                "output": result.insights.get("pain_points", ["-"])[0],
                "done": True,
                "triggered": True,
            }
        )
    else:
        result.steps.append(
            {
                "key": "insight",
                "name": "User Insight Agent",
                "output": "本次问题未触发用户洞察模块",
                "done": False,
                "triggered": False,
            }
        )

    if progress:
        progress()

    if "strategy" in route:
        triggered.append("strategy")
        result.diagnosis = diagnose_problem(question, evidence)
        result.sources.append(result.diagnosis.get("source", "mock"))
        result.plan = generate_product_plan(question, evidence)
        result.sources.append(result.plan.get("source", "mock"))
        causes = result.diagnosis.get("causes") or ["-"]
        result.steps.append(
            {
                "key": "strategy",
                "name": "Product Strategy Agent",
                "output": f"定位：{result.diagnosis.get('location', '-')}",
                "done": True,
                "triggered": True,
            }
        )
        result.steps.append(
            {
                "key": "strategy-2",
                "name": "Product Strategy Agent · 方案",
                "output": f"生成 {len(result.plan.get('solutions', []))} 条产品方案，首要原因假设：{causes[0]}",
                "done": True,
                "triggered": True,
            }
        )
    else:
        result.steps.append(
            {
                "key": "strategy",
                "name": "Product Strategy Agent",
                "output": "本次问题未触发产品策略模块",
                "done": False,
                "triggered": False,
            }
        )

    if progress:
        progress()

    if "experiment" in route and ab_summary:
        triggered.append("experiment")
        result.experiment = analyze_ab_test(ab_summary)
        result.sources.append(result.experiment.get("source", "mock"))
        result.steps.append(
            {
                "key": "experiment",
                "name": "Experiment Agent",
                "output": result.experiment.get("observation", "-"),
                "done": True,
                "triggered": True,
            }
        )
    else:
        result.steps.append(
            {
                "key": "experiment",
                "name": "Experiment Agent",
                "output": "本次问题未触发实验分析模块",
                "done": False,
                "triggered": False,
            }
        )

    result.steps.insert(
        0,
        {
            "key": "question",
            "name": "用户问题",
            "output": question,
            "done": True,
            "triggered": True,
        },
    )
    return result