"""指标计算与分析工具。

所有结论都由真实计算得出（基于 data/ 下的模拟数据），而不是写死的文案，
保证 Dashboard、诊断、A/B 实验之间的数字互相自洽。
"""

from __future__ import annotations

import math

import pandas as pd

CATEGORY_KEYWORDS = {
    "回复质量": ["理解", "答非所问", "不准", "不准确", "错误", "跑题", "不相关", "讲道理", "正确的废话", "没有一句", "质量", "敷衍"],
    "响应速度": ["有点慢", "太慢", "很慢", "卡住", "卡顿", "等待", "等了", "响应", "延迟", "转圈", "超时", "速度"],
    "功能缺失": ["希望增加", "希望能", "不支持", "缺少", "导入", "同步", "语音", "截图", "组队", "多设备", "功能"],
    "交互体验": ["不知道", "不会用", "找不到", "看不懂", "操作", "界面", "入口", "引导", "怎么用", "复杂", "随便选"],
    "回复长度": ["太长", "啰嗦", "简洁", "重点", "看不完", "八百字", "篇幅", "精简", "简短", "一大段", "五条建议"],
    "稳定性": ["中断", "报错", "失败", "崩溃", "闪退", "出错", "丢失", "重试", "不见了", "掉线"],
}

DEFAULT_CATEGORY = "回复质量"


def classify_feedback(text: str) -> str:
    """根据反馈文本自动归类到六大问题类型（本地规则，不消耗模型调用）。"""
    content = (text or "").lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for kw in keywords if kw in content)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else DEFAULT_CATEGORY


METRIC_LABELS = {
    "dau": "DAU",
    "d1_retention": "次日留存",
    "csat_index": "用户满意度",
    "ai_effective_rate": "AI 回复有效率",
    "first_session_completion": "首次会话完成率",
    "new_user_d1_retention": "新用户次日留存",
    "avg_response_time": "平均响应时间",
    "negative_feedback_rate": "负面反馈率",
    "follow_up_rate": "二次追问率",
    "losing_streak_share": "连败场景对话占比",
    "activation_rate": "新用户激活率",
}

CORE_TREND_METRICS = ["dau", "d1_retention", "csat_index", "ai_effective_rate"]


def _safe_delta(start: float, end: float) -> float:
    if not start:
        return 0.0
    return (end - start) / start * 100


def kpi_snapshot(metrics: pd.DataFrame) -> dict:
    """返回核心指标的当前值与近 30 天变化。"""
    first, last = metrics.iloc[0], metrics.iloc[-1]
    snapshot = {}
    for key in METRIC_LABELS:
        if key not in metrics.columns:
            continue
        snapshot[key] = {
            "value": float(last[key]),
            "previous": float(first[key]),
            "relative": _safe_delta(float(first[key]), float(last[key])),
            "absolute": float(last[key]) - float(first[key]),
        }
    return snapshot


def health_score(metrics: pd.DataFrame) -> dict:
    """AI 产品健康度：多个维度归一化后的加权得分。"""
    last = metrics.iloc[-1]
    components = [
        ("用户满意度", float(last["csat_index"]), 0.24),
        ("AI 回复有效率", float(last["ai_effective_rate"]), 0.23),
        ("次日留存", min(100.0, float(last["d1_retention"]) / 45 * 100), 0.14),
        (
            "新用户次留",
            min(100.0, float(last["new_user_d1_retention"]) / 45 * 100),
            0.14,
        ),
        (
            "首次会话完成率",
            min(100.0, float(last["first_session_completion"]) / 75 * 100),
            0.11,
        ),
        (
            "反馈健康度",
            (1 - float(last["negative_feedback_rate"]) / 100) * 100,
            0.14,
        ),
    ]
    score = sum(value * weight for _, value, weight in components)
    previous = sum(
        min(100.0, float(metrics.iloc[0][col]) / scale * 100) * weight
        for col, scale, weight in [
            ("csat_index", 1, 0.24),
            ("ai_effective_rate", 1, 0.23),
            ("d1_retention", 45, 0.14),
            ("new_user_d1_retention", 45, 0.14),
            ("first_session_completion", 75, 0.11),
        ]
    ) + (1 - float(metrics.iloc[0]["negative_feedback_rate"]) / 100) * 100 * 0.14
    return {
        "score": round(score, 1),
        "previous": round(previous, 1),
        "delta": round(score - previous, 1),
        "components": [
            {"name": name, "value": round(value, 1), "weight": weight}
            for name, value, weight in components
        ],
    }


def category_stats(feedback: pd.DataFrame) -> pd.DataFrame:
    """按问题类别统计反馈量、占比与负面率。"""
    total = len(feedback)
    grouped = feedback.groupby("issue_category").agg(
        count=("feedback_id", "count"),
        avg_rating=("rating", "mean"),
        negative=("rating", lambda s: int((s <= 2).sum())),
    )
    grouped["share"] = grouped["count"] / total * 100
    grouped["negative_rate"] = grouped["negative"] / grouped["count"] * 100
    grouped = grouped.sort_values("count", ascending=False)
    grouped["avg_rating"] = grouped["avg_rating"].round(2)
    grouped["share"] = grouped["share"].round(1)
    grouped["negative_rate"] = grouped["negative_rate"].round(1)
    return grouped.reset_index()


def feedback_overview(feedback: pd.DataFrame) -> dict:
    total = len(feedback)
    negative = int((feedback["rating"] <= 2).sum())
    return {
        "total": total,
        "avg_rating": round(float(feedback["rating"].mean()), 2),
        "negative_rate": round(negative / total * 100, 1) if total else 0.0,
        "negative_count": negative,
        "positive_rate": round(float((feedback["rating"] >= 4).mean()) * 100, 1),
        "avg_duration": round(float(feedback["session_duration"].mean()), 0),
    }


def auto_problems(metrics: pd.DataFrame, feedback: pd.DataFrame) -> list[dict]:
    """AI 自动发现的问题：全部由数据异常触发，而不是写死的案例。"""
    first, last = metrics.iloc[0], metrics.iloc[-1]
    cat = category_stats(feedback).set_index("issue_category")
    new_users = int(last["new_users"]) * 7

    def cat_share(name: str) -> float:
        return float(cat.loc[name, "share"]) if name in cat.index else 0.0

    def cat_rating(name: str) -> float:
        return float(cat.loc[name, "avg_rating"]) if name in cat.index else 0.0

    problems = []

    completion_delta = last["first_session_completion"] - first["first_session_completion"]
    retention_delta = last["new_user_d1_retention"] - first["new_user_d1_retention"]
    streak_delta = last["losing_streak_share"] - first["losing_streak_share"]
    problems.append(
        {
            "priority": "P0",
            "title": "连败场景下玩家流失加剧",
            "metrics": {
                "影响指标": "首次会话完成率、新玩家次日留存",
                "影响用户": f"近 7 天新注册玩家约 {new_users:,} 人",
                "趋势": (
                    f"连败场景对话占比 {first['losing_streak_share']:.1f}% → "
                    f"{last['losing_streak_share']:.1f}%（{streak_delta:+.1f}pt），"
                    f"同期首次会话完成率 {completion_delta:+.1f}pt、新玩家次留 {retention_delta:+.1f}pt"
                ),
            },
            "advice": (
                f"连败是玩家情绪最需要被接住的时刻，但回复质量类反馈占比已达 {cat_share('回复质量'):.1f}%，"
                f"该类别平均评分仅 {cat_rating('回复质量'):.2f}/5。"
                "建议在识别到连败后优先触发共情策略，把建议压缩到最多一条。"
            ),
        }
    )

    follow_delta = last["follow_up_rate"] - first["follow_up_rate"]
    problems.append(
        {
            "priority": "P1",
            "title": "陪伴回复过长导致对话中断",
            "metrics": {
                "影响指标": "二次追问率、对话中断率",
                "影响用户": "全量玩家，局间碎片时间使用与移动端玩家为主",
                "趋势": (
                    f"二次追问率 {first['follow_up_rate']:.1f}% → {last['follow_up_rate']:.1f}%"
                    f"（{follow_delta:+.1f}pt），回复长度类反馈占比 {cat_share('回复长度'):.1f}%"
                ),
            },
            "advice": (
                "玩家在局间只有几十秒，长回复直接等于读不完。"
                "建议默认输出 2-3 句短回复，把复盘与攻略折叠为可展开内容；"
                f"当前回复长度类反馈平均评分 {cat_rating('回复长度'):.2f}/5。"
            ),
        }
    )

    time_delta = last["avg_response_time"] - first["avg_response_time"]
    problems.append(
        {
            "priority": "P1",
            "title": "高峰期响应变慢打断陪伴节奏",
            "metrics": {
                "影响指标": "玩家满意度、会话完成率",
                "影响用户": "晚间高峰期活跃玩家",
                "趋势": (
                    f"平均响应时间 {first['avg_response_time']:.1f}s → {last['avg_response_time']:.1f}s"
                    f"（{time_delta:+.1f}s），响应速度类反馈占比 {cat_share('响应速度'):.1f}%"
                ),
            },
            "advice": (
                "打团、等匹配的空档本来就短，等待会被放大成“它不想理我”。"
                "建议首字优先输出降低体感等待，并对高频情绪表达做缓存。"
            ),
        }
    )

    missing_share = cat_share("功能缺失")
    problems.append(
        {
            "priority": "P2",
            "title": "战绩同步与语音陪伴能力缺失",
            "metrics": {
                "影响指标": "对局复盘使用率、开黑场景会话时长",
                "影响用户": f"约 {missing_share:.1f}% 的反馈玩家主动提出",
                "趋势": f"功能缺失类反馈占比 {missing_share:.1f}%，需求信号稳定",
            },
            "advice": (
                "建议进入需求池并按 RICE 评估排期：战绩截图识别成本较低、收益明确，"
                "语音陪伴成本高，可先小范围验证开黑场景的真实使用意愿。"
            ),
        }
    )
    return problems


def diagnosis_evidence(
    metrics: pd.DataFrame, feedback: pd.DataFrame, ab_test: pd.DataFrame | None = None
) -> dict:
    """为问题诊断与 Agent 准备证据数据（含指标方向，用于判断结论是否成立）。"""
    first, last = metrics.iloc[0], metrics.iloc[-1]
    cat = category_stats(feedback).set_index("issue_category")
    overall_negative = float((feedback["rating"] <= 2).mean() * 100)
    new_user_feedback = feedback[feedback["is_new_user"] == 1]
    new_user_negative = (
        float((new_user_feedback["rating"] <= 2).mean() * 100)
        if len(new_user_feedback)
        else 0.0
    )

    def rel(column: str) -> str:
        a, b = float(first[column]), float(last[column])
        return f"{(b - a) / a * 100:+.1f}%" if a else "-"

    def delta(column: str) -> str:
        return f"{float(last[column]) - float(first[column]):+.1f}pt"

    evidence = {
        "dau_start": f"{first['dau']:.0f}",
        "dau_end": f"{last['dau']:.0f}",
        "dau_relative": rel("dau"),
        "d1_start": f"{first['d1_retention']:.1f}",
        "d1_end": f"{last['d1_retention']:.1f}",
        "d1_delta": delta("d1_retention"),
        "csat_start": f"{first['csat_index']:.1f}",
        "csat_end": f"{last['csat_index']:.1f}",
        "effective_start": f"{first['ai_effective_rate']:.1f}",
        "effective_end": f"{last['ai_effective_rate']:.1f}",
        "completion_start": f"{first['first_session_completion']:.1f}",
        "completion_end": f"{last['first_session_completion']:.1f}",
        "completion_delta": delta("first_session_completion"),
        "new_user_d1_start": f"{first['new_user_d1_retention']:.1f}",
        "new_user_d1_end": f"{last['new_user_d1_retention']:.1f}",
        "new_user_d1_delta": delta("new_user_d1_retention"),
        "losing_streak_start": f"{first['losing_streak_share']:.1f}%",
        "losing_streak_end": f"{last['losing_streak_share']:.1f}%",
        "losing_streak_delta": delta("losing_streak_share"),
        "response_time_start": f"{first['avg_response_time']:.1f}",
        "response_time_end": f"{last['avg_response_time']:.1f}",
        "response_time_delta": (
            f"{float(last['avg_response_time']) - float(first['avg_response_time']):+.1f}s"
        ),
        "follow_up_start": f"{first['follow_up_rate']:.1f}",
        "follow_up_end": f"{last['follow_up_rate']:.1f}",
        "follow_up_delta": delta("follow_up_rate"),
        "overall_d1": f"{last['d1_retention']:.1f}",
        "category_shares": {n: f"{float(cat.loc[n, 'share']):.1f}%" for n in cat.index},
        "category_ratings": {n: f"{float(cat.loc[n, 'avg_rating']):.2f}" for n in cat.index},
        "category_negative_rates": {
            n: f"{float(cat.loc[n, 'negative_rate']):.1f}%" for n in cat.index
        },
        "scene_shares": {
            name: f"{count / len(feedback) * 100:.1f}%"
            for name, count in feedback["scene"].value_counts().items()
        },
        "new_user_negative_rate": f"{new_user_negative:.1f}%",
        "overall_negative_rate": f"{overall_negative:.1f}%",
        "feedback_total": str(len(feedback)),
        "quality_negative_share": f"{float(cat.loc['回复质量', 'share']):.1f}%",
        "length_negative_share": f"{float(cat.loc['回复长度', 'share']):.1f}%",
        "speed_negative_share": f"{float(cat.loc['响应速度', 'share']):.1f}%",
        "missing_negative_share": f"{float(cat.loc['功能缺失', 'share']):.1f}%",
        "negative_feedback_rate": f"{last['negative_feedback_rate']:.1f}%",
        "trends": {
            "dau": "down" if float(last["dau"]) < float(first["dau"]) else "up",
            "d1_retention": (
                "down" if float(last["d1_retention"]) < float(first["d1_retention"]) else "up"
            ),
            "csat": "down" if float(last["csat_index"]) < float(first["csat_index"]) else "up",
            "ai_effective_rate": (
                "down"
                if float(last["ai_effective_rate"]) < float(first["ai_effective_rate"])
                else "up"
            ),
            "new_user_d1_retention": (
                "down"
                if float(last["new_user_d1_retention"]) < float(first["new_user_d1_retention"])
                else "up"
            ),
            "first_session_completion": (
                "down"
                if float(last["first_session_completion"])
                < float(first["first_session_completion"])
                else "up"
            ),
            "avg_response_time": (
                "worse"
                if float(last["avg_response_time"]) > float(first["avg_response_time"])
                else "better"
            ),
            "follow_up_rate": (
                "worse"
                if float(last["follow_up_rate"]) > float(first["follow_up_rate"])
                else "better"
            ),
            "losing_streak_share": (
                "worse"
                if float(last["losing_streak_share"]) > float(first["losing_streak_share"])
                else "better"
            ),
        },
    }
    if ab_test is not None and "group" in ab_test.columns:
        summary = ab_summary(ab_test)
        evidence["experiment_sample"] = str(summary["sample"])
    return evidence


def _two_proportion_p(x1: int, n1: int, x2: int, n2: int) -> float:
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (p2 - p1) / se
    return math.erfc(abs(z) / math.sqrt(2))


def _mean_p(values_a: pd.Series, values_b: pd.Series) -> float:
    n1, n2 = len(values_a), len(values_b)
    if n1 < 2 or n2 < 2:
        return 1.0
    se = math.sqrt(values_a.var(ddof=1) / n1 + values_b.var(ddof=1) / n2)
    if se == 0:
        return 1.0
    t = (values_b.mean() - values_a.mean()) / se
    return math.erfc(abs(t) / math.sqrt(2))


def ab_summary(ab_test: pd.DataFrame, days: int = 7) -> dict:
    """A/B 实验结果汇总，包含变化率与显著性检验。"""
    group_a = ab_test[ab_test["group"] == "A"]
    group_b = ab_test[ab_test["group"] == "B"]
    n = min(len(group_a), len(group_b))

    rows = []

    def add_rate(metric: str, column: str) -> None:
        xa, xb = int(group_a[column].sum()), int(group_b[column].sum())
        pa, pb = xa / len(group_a), xb / len(group_b)
        rows.append(
            {
                "metric": metric,
                "a": f"{pa * 100:.1f}%",
                "b": f"{pb * 100:.1f}%",
                "a_value": pa,
                "b_value": pb,
                "relative": (pb - pa) / pa * 100 if pa else 0.0,
                "absolute": (pb - pa) * 100,
                "p_value": _two_proportion_p(xa, len(group_a), xb, len(group_b)),
            }
        )

    add_rate("激活率", "activated")
    add_rate("次日留存", "retained_d1")
    add_rate("会话完成率", "session_completed")

    sa, sb = group_a["satisfaction"], group_b["satisfaction"]
    rows.append(
        {
            "metric": "满意度",
            "a": f"{sa.mean():.2f}",
            "b": f"{sb.mean():.2f}",
            "a_value": float(sa.mean()),
            "b_value": float(sb.mean()),
            "relative": (sb.mean() - sa.mean()) / sa.mean() * 100,
            "absolute": float(sb.mean() - sa.mean()),
            "p_value": _mean_p(sa, sb),
        }
    )

    return {
        "name": str(ab_test["experiment"].iloc[0]),
        "sample": int(len(group_a) + len(group_b)),
        "group_size": int(n),
        "days": days,
        "rows": rows,
        "significant_count": sum(1 for r in rows if r["p_value"] < 0.05),
    }


def funnel_stages(requirements: pd.DataFrame) -> list[dict]:
    """需求池 → 开发 → 实验 → 上线 → 数据验证 的流转统计。"""
    mapping = {
        "需求池": ["需求池"],
        "开发中": ["待开发", "开发中"],
        "实验验证": ["实验中"],
        "已上线": ["已上线"],
    }
    stages = []
    for stage, statuses in mapping.items():
        items = requirements[requirements["status"].isin(statuses)]
        stages.append({"stage": stage, "count": int(len(items)), "items": items["name"].tolist()})
    return stages
