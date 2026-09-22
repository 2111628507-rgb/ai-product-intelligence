"""生成 AI Product Intelligence Demo 所需的全部模拟数据。

运行方式：
    python generate_data.py

说明：
    本文件生成的全部数据均为模拟数据，用于产品 Demo 与求职展示，
    不代表任何真实企业、真实用户或真实业务数据。
"""

from __future__ import annotations

import sys as _sys

# 兼容部分 Windows 控制台的默认编码（cp1252/gbk），避免打印中文时抛错
if hasattr(_sys.stdout, "reconfigure"):
    try:
        _sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import math
import random
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ENCODING = "utf-8-sig"

SEED = 20260922
METRIC_DAYS = 30
N_USERS = 900
N_FEEDBACK = 640
AB_GROUP_SIZE = 1000

USER_TYPES = ["竞技玩家", "休闲玩家", "回归玩家", "新手玩家"]
USER_TYPE_W = [0.34, 0.30, 0.18, 0.18]

SCENES = ["连败", "卡关", "上分冲分", "开黑组队", "日常闲聊", "攻略查询"]
SCENE_W = [0.21, 0.16, 0.20, 0.15, 0.16, 0.12]

CHANNELS = ["应用商店", "社交媒体", "朋友推荐", "内容平台", "搜索引擎"]
CHANNEL_W = [0.31, 0.24, 0.15, 0.18, 0.12]

FEATURES = ["情绪陪伴", "对局复盘", "攻略问答", "人格切换", "上下文记忆"]
FEATURE_W = [0.34, 0.22, 0.20, 0.13, 0.11]

ISSUE_CATEGORIES = ["回复质量", "响应速度", "功能缺失", "交互体验", "回复长度", "稳定性"]

RATING_VALUES = [5, 4, 3, 2, 1]
RATING_WEIGHTS = [0.560, 0.200, 0.056, 0.149, 0.035]

# 不同评分区间下，问题类别的分布（让数据具备业务解释性，而不是纯随机）
CATEGORY_W_BY_BAND = {
    "pos": [0.30, 0.12, 0.20, 0.14, 0.12, 0.12],
    "neu": [0.26, 0.14, 0.14, 0.16, 0.18, 0.12],
    "neg": [0.28, 0.18, 0.14, 0.12, 0.16, 0.12],
}

FEEDBACK_TEXTS = {
    ("回复质量", "pos"): [
        "连跪的时候它没有讲大道理，先顺着我说了两句，舒服多了",
        "复盘讲得挺具体，知道下一把该改什么了",
        "选损友模式吐槽得刚好，不难受也不敷衍",
        "它记得我上一把玩的是什么，接得上话",
    ],
    ("回复质量", "neu"): [
        "有时候能接住我的情绪，有时候又变成讲道理",
        "内容不错，但要我先解释半天背景",
        "共情是有的，但最后总想塞给我三条建议",
    ],
    ("回复质量", "neg"): [
        "我都说了烦死了，它还在教我调整心态",
        "回复经常没有理解我的意思，答非所问",
        "同一个问题问两次，说话方式差别很大",
        "说了一堆正确的废话，没有一句是我当时想听的",
    ],
    ("响应速度", "pos"): [
        "回复挺快，局间那点时间也够用",
        "速度可以，不打断我和朋友语音",
    ],
    ("响应速度", "neu"): [
        "一句吐槽回得很快，长一点的复盘就要等",
        "速度一般，打团的时候不太方便等",
    ],
    ("响应速度", "neg"): [
        "回复有点慢，等它加载完我下一把都开了",
        "高峰期等了一分多钟才出回复",
        "打完一把想马上吐槽，结果卡在那儿不动",
        "生成到一半停住了，还要重新问一次",
    ],
    ("功能缺失", "pos"): [
        "人格切换很好玩，换一个像换了个搭子",
        "上下文记得住，不用每次都从头说",
    ],
    ("功能缺失", "neu"): [
        "希望能自动读我的战绩，不用每次自己说",
        "如果有语音陪伴就更好了",
    ],
    ("功能缺失", "neg"): [
        "希望能直接导入战绩截图，现在只能手动打字",
        "没有语音输入，开黑的时候根本腾不出手",
        "希望能一键组队，现在只能自己找人",
        "不支持多设备同步，手机上聊的电脑上看不到",
    ],
    ("交互体验", "pos"): [
        "页面挺清爽，选完人格直接开聊",
        "第一次打开就有示例，不用想说什么",
    ],
    ("交互体验", "neu"): [
        "人格挺多的，要试几次才知道哪个适合自己",
        "手机上排版可以再宽松一点",
    ],
    ("交互体验", "neg"): [
        "第一次使用不知道该输入什么，愣了半天",
        "看不懂四个人格的区别，随便选了一个",
        "不知道在哪儿切换游戏，找了很久",
        "不知道怎么删掉刚才说的那句话",
    ],
    ("回复长度", "pos"): [
        "回复不长不短，正好是打游戏间隙能看完的量",
        "只回了两三句，很贴心",
    ],
    ("回复长度", "neu"): [
        "有时候回复会稍微长一点，需要划两下",
        "希望能先给一句结论，再展开",
    ],
    ("回复长度", "neg"): [
        "我就想吐槽一句，它给我写了八百字",
        "回复太长了，打游戏的时候根本看不完",
        "每次都一大段，重点还得我自己找",
        "我只要一句安慰，它给我列了五条建议",
    ],
    ("稳定性", "pos"): [
        "用了两周没掉过线，聊天记录都在",
    ],
    ("稳定性", "neu"): [
        "偶尔会转圈，刷新一下就好了",
    ],
    ("稳定性", "neg"): [
        "聊到一半断了，之前的上下文也没了",
        "偶尔会报错，需要重新开一个对话",
        "换了设备之后，之前的聊天记录不见了",
    ],
}

RETENTION_BY_RATING = {5: 0.46, 4: 0.38, 3: 0.28, 2: 0.18, 1: 0.12}

SCENE_DURATION = {
    "连败": (240, 900),
    "卡关": (180, 720),
    "上分冲分": (120, 480),
    "开黑组队": (300, 1200),
    "日常闲聊": (180, 900),
    "攻略查询": (90, 360),
}


def _band(rating: int) -> str:
    if rating >= 4:
        return "pos"
    if rating == 3:
        return "neu"
    return "neg"


def build_users(rng: np.random.Generator, today: pd.Timestamp) -> pd.DataFrame:
    user_ids = [f"U{100000 + i}" for i in range(N_USERS)]
    register_offsets = rng.integers(0, 120, N_USERS)
    register_dates = [today - timedelta(days=int(o)) for o in register_offsets]
    return pd.DataFrame(
        {
            "user_id": user_ids,
            "user_type": rng.choice(USER_TYPES, N_USERS, p=USER_TYPE_W),
            "core_scene": rng.choice(SCENES, N_USERS, p=SCENE_W),
            "channel": rng.choice(CHANNELS, N_USERS, p=CHANNEL_W),
            "register_date": [d.date() for d in register_dates],
            "is_new_user": [int((today - d).days <= 14) for d in register_dates],
        }
    )


def build_feedback(
    rng: np.random.Generator, users: pd.DataFrame, today: pd.Timestamp
) -> pd.DataFrame:
    rows = []
    user_records = users.to_dict("records")
    for i in range(N_FEEDBACK):
        user = random.choice(user_records)
        rating = int(rng.choice(RATING_VALUES, p=RATING_WEIGHTS))
        band = _band(rating)
        category = str(rng.choice(ISSUE_CATEGORIES, p=CATEGORY_W_BY_BAND[band]))
        text = random.choice(FEEDBACK_TEXTS[(category, band)])
        scene = user["core_scene"] if rng.random() < 0.7 else str(rng.choice(SCENES, p=SCENE_W))
        feature = str(rng.choice(FEATURES, p=FEATURE_W))
        low, high = SCENE_DURATION[scene]
        duration = int(rng.integers(low, high))
        retention = int(rng.random() < RETENTION_BY_RATING[rating])
        day_offset = int(rng.integers(0, METRIC_DAYS))
        rows.append(
            {
                "feedback_id": f"F{200000 + i}",
                "user_id": user["user_id"],
                "date": (today - timedelta(days=day_offset)).date(),
                "user_type": user["user_type"],
                "scene": scene,
                "feature": feature,
                "feedback": text,
                "issue_category": category,
                "rating": rating,
                "session_duration": duration,
                "retention": retention,
                "is_new_user": user["is_new_user"],
            }
        )
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return df


def _trend_series(
    rng: np.random.Generator, start: float, end: float, days: int, noise: float
) -> np.ndarray:
    base = np.linspace(start, end, days)
    vals = base * (1 + rng.normal(0, noise, days))
    vals[-1] = end
    return vals


def build_metrics(rng: np.random.Generator, today: pd.Timestamp) -> pd.DataFrame:
    days = METRIC_DAYS
    dates = [today - timedelta(days=days - 1 - i) for i in range(days)]

    dau = _trend_series(rng, 11526, 12483, days, 0.012)
    d1 = _trend_series(rng, 36.9, 38.2, days, 0.012)
    csat = _trend_series(rng, 80.4, 84.6, days, 0.008)
    effective = _trend_series(rng, 83.9, 87.3, days, 0.010)

    # 值得关注的下滑信号：新用户首次使用体验
    new_user_d1 = _trend_series(rng, 31.4, 27.6, days, 0.015)
    first_completion = _trend_series(rng, 64.5, 58.2, days, 0.012)
    activation = _trend_series(rng, 62.8, 66.1, days, 0.010)
    response_time = _trend_series(rng, 4.6, 6.2, days, 0.030)
    negative_rate = _trend_series(rng, 21.5, 18.4, days, 0.020)
    follow_up = _trend_series(rng, 22.4, 29.6, days, 0.020)
    losing_streak = _trend_series(rng, 18.6, 24.3, days, 0.020)

    df = pd.DataFrame(
        {
            "date": [d.date() for d in dates],
            "dau": dau.round(0).astype(int),
            "new_users": (dau * rng.uniform(0.055, 0.075, days)).round(0).astype(int),
            "d1_retention": d1.round(1),
            "new_user_d1_retention": new_user_d1.round(1),
            "csat_index": csat.round(1),
            "ai_effective_rate": effective.round(1),
            "activation_rate": activation.round(1),
            "first_session_completion": first_completion.round(1),
            "avg_response_time": response_time.round(2),
            "negative_feedback_rate": negative_rate.round(1),
            "follow_up_rate": follow_up.round(1),
            "losing_streak_share": losing_streak.round(1),
        }
    )
    return df


def build_ab_test(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    config = {
        "A": {"activation": 0.612, "retention": 0.325, "completion": 0.580, "sat": 3.92},
        "B": {"activation": 0.687, "retention": 0.378, "completion": 0.651, "sat": 4.28},
    }
    devices = ["iOS", "Android", "Web"]
    device_w = [0.36, 0.44, 0.20]
    for group, cfg in config.items():
        latent = rng.normal(0, 1, AB_GROUP_SIZE)
        activation_cut = -_z(cfg["activation"])
        activated = (latent > activation_cut).astype(int)
        for i in range(AB_GROUP_SIZE):
            act = int(activated[i])
            p_ret = cfg["retention"] * (1.25 if act else 0.72)
            p_com = cfg["completion"] * (1.18 if act else 0.75)
            sat = float(np.clip(rng.normal(cfg["sat"] + (0.25 if act else -0.3), 0.85), 1, 5))
            rows.append(
                {
                    "user_id": f"{group}{300000 + i}",
                    "group": group,
                    "device": str(rng.choice(devices, p=device_w)),
                    "activated": act,
                    "retained_d1": int(rng.random() < p_ret),
                    "session_completed": int(rng.random() < p_com),
                    "satisfaction": round(sat, 2),
                    "session_duration": int(rng.integers(120, 900)),
                    "experiment": "连败场景 AI 陪伴回复优化",
                }
            )
    return pd.DataFrame(rows)


def _z(p: float) -> float:
    """标准正态分位数（避免引入 scipy 依赖）。"""
    return math.sqrt(2) * _erfinv(2 * p - 1)


def _erfinv(x: float) -> float:
    a = 0.147
    ln = math.log(1 - x * x)
    t = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), x)


def build_requirements(today: pd.Timestamp) -> pd.DataFrame:
    items = [
        {
            "req_id": "R-001",
            "name": "新玩家首次体验引导",
            "problem": "新玩家第一次打开不知道该说什么，也不知道四个人格的区别",
            "solution": "开场示例对话 + 人格差异说明 + 一键体验连败场景",
            "reach": 8,
            "impact": 8,
            "confidence": 0.9,
            "effort": 3,
            "status": "实验中",
            "owner": "产品组",
            "expected_metric": "首次会话完成率",
        },
        {
            "req_id": "R-002",
            "name": "陪伴回复长度控制",
            "problem": "回复默认偏长，玩家在局间只有碎片时间，看不完就退出",
            "solution": "默认 2-3 句短回复 + 长内容折叠为可展开",
            "reach": 9,
            "impact": 6,
            "confidence": 0.8,
            "effort": 4,
            "status": "待开发",
            "owner": "算法组",
            "expected_metric": "对话中断率",
        },
        {
            "req_id": "R-003",
            "name": "回复质量反馈闭环",
            "problem": "连败场景回复偏向讲道理，缺少情绪识别与反馈回流机制",
            "solution": "增加回复评分与原因标签，把连败场景的负面反馈回流到策略优化",
            "reach": 8,
            "impact": 8,
            "confidence": 0.7,
            "effort": 5,
            "status": "开发中",
            "owner": "算法组",
            "expected_metric": "回复有效率",
        },
        {
            "req_id": "R-004",
            "name": "战绩自动同步",
            "problem": "玩家需要手动描述自己的对局情况，表达成本高",
            "solution": "支持战绩截图识别与游戏账号数据同步",
            "reach": 7,
            "impact": 8,
            "confidence": 0.7,
            "effort": 6,
            "status": "需求池",
            "owner": "研发组",
            "expected_metric": "对局复盘使用率",
        },
        {
            "req_id": "R-005",
            "name": "语音陪伴（开黑免手打）",
            "problem": "开黑时腾不出手打字，语音陪伴需求明确但成本较高",
            "solution": "接入语音转文字与语音回复，适配开黑场景",
            "reach": 4,
            "impact": 6,
            "confidence": 0.4,
            "effort": 8,
            "status": "需求池",
            "owner": "研发组",
            "expected_metric": "开黑场景会话时长",
        },
        {
            "req_id": "R-006",
            "name": "一键组队找搭子",
            "problem": "玩家想找人开黑，但缺少匹配入口",
            "solution": "按游戏与段位匹配同水平玩家",
            "reach": 5,
            "impact": 6,
            "confidence": 0.5,
            "effort": 6,
            "status": "需求池",
            "owner": "运营组",
            "expected_metric": "组队成功率",
        },
        {
            "req_id": "R-007",
            "name": "高峰期响应速度优化",
            "problem": "晚间高峰期平均响应时间从 4.6s 上升到 6.2s，打断陪伴节奏",
            "solution": "首字优先输出 + 高频情绪回复缓存",
            "reach": 9,
            "impact": 7,
            "confidence": 0.8,
            "effort": 6,
            "status": "开发中",
            "owner": "研发组",
            "expected_metric": "平均响应时间",
        },
        {
            "req_id": "R-008",
            "name": "移动端对话排版优化",
            "problem": "移动端长对话排版拥挤，局间阅读体验差",
            "solution": "移动端卡片化排版与折叠长内容",
            "reach": 6,
            "impact": 4,
            "confidence": 0.6,
            "effort": 3,
            "status": "已上线",
            "owner": "设计组",
            "expected_metric": "移动端满意度",
        },
    ]
    df = pd.DataFrame(items)
    df["rice_score"] = (
        df["reach"] * df["impact"] * df["confidence"] / df["effort"]
    ).round(2)
    df = df.sort_values("rice_score", ascending=False).reset_index(drop=True)
    df["priority"] = df["rice_score"].apply(_priority)
    df["created_at"] = (today - timedelta(days=21)).date()
    df["updated_at"] = today.date()
    return df[
        [
            "req_id",
            "name",
            "problem",
            "solution",
            "reach",
            "impact",
            "confidence",
            "effort",
            "rice_score",
            "priority",
            "status",
            "owner",
            "expected_metric",
            "created_at",
            "updated_at",
        ]
    ]


def _priority(score: float) -> str:
    if score >= 14:
        return "P0"
    if score >= 8:
        return "P1"
    if score >= 4:
        return "P2"
    return "P3"


def main() -> None:
    random.seed(SEED)
    rng = np.random.default_rng(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now().normalize()

    users = build_users(rng, today)
    feedback = build_feedback(rng, users, today)
    metrics = build_metrics(rng, today)
    ab_test = build_ab_test(rng)
    requirements = build_requirements(today)

    users.to_csv(DATA_DIR / "users.csv", index=False, encoding=ENCODING)
    feedback.to_csv(DATA_DIR / "feedback.csv", index=False, encoding=ENCODING)
    metrics.to_csv(DATA_DIR / "metrics.csv", index=False, encoding=ENCODING)
    ab_test.to_csv(DATA_DIR / "ab_test.csv", index=False, encoding=ENCODING)
    requirements.to_csv(DATA_DIR / "requirements.csv", index=False, encoding=ENCODING)

    avg_rating = feedback["rating"].mean()
    negative_rate = (feedback["rating"] <= 2).mean() * 100
    print("模拟数据生成完成")
    print(f"  用户数        : {len(users)}")
    print(f"  反馈条数      : {len(feedback)}")
    print(f"  反馈平均评分  : {avg_rating:.2f} / 5")
    print(f"  负面反馈率    : {negative_rate:.1f}%")
    print(f"  指标天数      : {len(metrics)}")
    print(f"  A/B 实验样本  : {len(ab_test)}")
    print(f"  需求条数      : {len(requirements)}")
    print(f"  输出目录      : {DATA_DIR}")


if __name__ == "__main__":
    main()