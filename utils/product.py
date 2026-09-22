"""被分析的 AI 产品档案。

本 Demo 分析的是「AI 游戏陪伴助手」这一虚构产品（原型来自个人项目 GameBuddy），
所有指标与用户反馈均为模拟数据，不涉及任何真实企业、真实用户或真实业务数据。

如果你想调整分析对象，只需要修改下面 PRODUCT 里的名称与定位即可，其余分析逻辑无需改动。
"""

from __future__ import annotations

PRODUCT = {
    "name": "AI 游戏陪伴助手（虚构演示产品）",
    "positioning": "面向游戏玩家的 AI 陪伴产品，覆盖连败情绪陪伴、对局复盘、攻略问答与开黑组队场景",
    "features": ["情绪陪伴", "对局复盘", "攻略问答", "人格切换", "上下文记忆"],
    "users": ["竞技玩家", "休闲玩家", "回归玩家", "新手玩家"],
    "scenes": ["连败", "卡关", "上分冲分", "开黑组队", "日常闲聊", "攻略查询"],
    "issues": ["回复质量", "响应速度", "功能缺失", "交互体验", "回复长度", "稳定性"],
    "data_note": "所有指标与用户反馈均为由 generate_data.py 生成的模拟数据，用于演示 AI 产品经理的分析与决策流程。",
}


def name() -> str:
    return PRODUCT["name"]


def positioning() -> str:
    return PRODUCT["positioning"]


def subtitle() -> str:
    return f"分析对象：{PRODUCT['name']} · {PRODUCT['positioning']}"