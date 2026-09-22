"""数据读取工具。

统一负责加载与保存 data/ 目录下的模拟数据，并提供 Streamlit 缓存。
如果数据文件缺失，会自动调用 generate_data.py 重新生成。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ENCODING = "utf-8-sig"

DATA_FILES = {
    "users": "users.csv",
    "feedback": "feedback.csv",
    "metrics": "metrics.csv",
    "ab_test": "ab_test.csv",
    "requirements": "requirements.csv",
}


def ensure_data(force: bool = False) -> list[str]:
    """确保数据文件存在，缺失时自动重新生成一份。"""
    if force:
        missing = list(DATA_FILES.values())
    else:
        missing = [name for name in DATA_FILES.values() if not (DATA_DIR / name).exists()]

    if missing:
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        import generate_data

        generate_data.main()
        clear_cache()
    return missing


@st.cache_data(show_spinner=False)
def _read(name: str) -> pd.DataFrame:
    path = DATA_DIR / DATA_FILES[name]
    df = pd.read_csv(path, encoding=ENCODING)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def clear_cache() -> None:
    _read.clear()


def load_users() -> pd.DataFrame:
    return _read("users")


def load_feedback() -> pd.DataFrame:
    return _read("feedback")


def load_metrics() -> pd.DataFrame:
    return _read("metrics")


def load_ab_test() -> pd.DataFrame:
    return _read("ab_test")


def load_requirements() -> pd.DataFrame:
    return _read("requirements")


def next_feedback_id() -> str:
    """生成下一个反馈编号，避免与已有数据冲突。"""
    try:
        existing = pd.read_csv(DATA_DIR / DATA_FILES["feedback"], encoding=ENCODING)
        numbers = existing["feedback_id"].astype(str).str.extract(r"(\d+)$")[0].dropna()
        start = int(numbers.astype(int).max()) + 1 if len(numbers) else 300001
    except Exception:  # noqa: BLE001
        start = 300001
    return str(start)


def append_feedback(rows: list[dict]) -> tuple[int, int]:
    """把新反馈追加到 feedback.csv，返回 (写入条数, 跳过的重复条数)。"""
    path = DATA_DIR / DATA_FILES["feedback"]
    current = pd.read_csv(path, encoding=ENCODING)
    incoming = pd.DataFrame(rows)
    if incoming.empty:
        return 0, 0

    existing_texts = set(current["feedback"].astype(str).str.strip())
    incoming["_key"] = incoming["feedback"].astype(str).str.strip()
    duplicated = int(incoming["_key"].isin(existing_texts).sum())
    incoming = incoming[~incoming["_key"].isin(existing_texts)].drop(columns=["_key"])

    for column in current.columns:
        if column not in incoming.columns:
            incoming[column] = None
    incoming = incoming[current.columns]
    merged = pd.concat([current, incoming], ignore_index=True)
    merged.to_csv(path, index=False, encoding=ENCODING)
    clear_cache()
    return len(incoming), duplicated


def save_requirements(df: pd.DataFrame) -> None:
    """保存需求池（迭代中心支持新增与状态流转）。"""
    df.to_csv(DATA_DIR / DATA_FILES["requirements"], index=False, encoding=ENCODING)
    clear_cache()