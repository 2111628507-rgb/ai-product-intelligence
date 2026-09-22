"""统一的界面组件与视觉规范。

目标：让页面看起来像现代 AI SaaS 后台，而不是开发者调试页面。
所有页面共用这里的卡片、指标、标签与标题样式，保证信息层级一致。
"""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
:root {
  --ap-ink: #0f172a;
  --ap-muted: #64748b;
  --ap-line: #e6e9f2;
  --ap-brand: #2f5bff;
  --ap-soft: #f7f8fc;
}
html, body, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei",
    "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", sans-serif;
}
.stApp { background: #ffffff; }
.block-container { max-width: 1180px; padding-top: 2.4rem; padding-bottom: 4rem; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

/* 顶部标题 */
.ap-header h1 {
  font-size: 25px; font-weight: 700; color: var(--ap-ink);
  margin: 0; letter-spacing: .2px;
}
.ap-header p { color: var(--ap-muted); font-size: 13.5px; margin: 7px 0 0; }
.ap-header { padding-bottom: 18px; border-bottom: 1px solid var(--ap-line); margin-bottom: 4px; }

/* 分区标题 */
.ap-section { margin: 30px 0 14px; }
.ap-section h3 {
  font-size: 16px; font-weight: 650; color: var(--ap-ink); margin: 0;
  display: flex; align-items: center; gap: 8px;
}
.ap-section h3::before {
  content: ""; width: 3px; height: 15px; border-radius: 2px; background: var(--ap-brand);
}
.ap-section span { display: block; color: var(--ap-muted); font-size: 12.5px; margin-top: 6px; }

/* 健康度主卡片 */
.ap-hero {
  background: linear-gradient(120deg, #101a33 0%, #1d2a4d 65%, #24345f 100%);
  border-radius: 16px; padding: 24px 28px; color: #fff;
  display: flex; align-items: center; gap: 30px; flex-wrap: wrap;
  box-shadow: 0 8px 24px rgba(16, 24, 40, .12);
}
.ap-hero .score { font-size: 54px; font-weight: 700; line-height: 1; letter-spacing: -1px; }
.ap-hero .score small { font-size: 17px; font-weight: 500; opacity: .6; margin-left: 4px; }
.ap-hero .label { font-size: 12.5px; opacity: .68; letter-spacing: .4px; margin-bottom: 10px; }
.ap-hero .desc { font-size: 13px; opacity: .82; max-width: 520px; line-height: 1.7; }
.ap-hero .divider { width: 1px; align-self: stretch; background: rgba(255, 255, 255, .14); }

/* KPI 卡片 */
.ap-kpi {
  background: #fff; border: 1px solid var(--ap-line); border-radius: 14px;
  padding: 16px 18px; height: 100%;
  box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
}
.ap-kpi-label { font-size: 12.5px; color: var(--ap-muted); }
.ap-kpi-value { font-size: 27px; font-weight: 680; color: var(--ap-ink); line-height: 1.2; margin: 9px 0 8px; }
.ap-delta { display: inline-block; font-size: 11.5px; font-weight: 650; padding: 2px 8px; border-radius: 999px; }
.ap-delta.up { background: #e9f9f0; color: #12805c; }
.ap-delta.down { background: #fdecec; color: #c0392b; }
.ap-delta.flat { background: #eef1f6; color: #475569; }
.ap-kpi-hint { font-size: 11.5px; color: #94a3b8; margin-top: 8px; }

/* 通用卡片 */
.ap-card {
  background: #fff; border: 1px solid var(--ap-line); border-radius: 14px;
  padding: 18px 20px; box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
}
.ap-card h4 { margin: 0 0 10px; font-size: 13.5px; color: var(--ap-ink); font-weight: 650; }
.ap-card p { margin: 0; font-size: 13px; color: #334155; line-height: 1.75; }

/* 问题卡片 */
.ap-problem {
  background: #fff; border: 1px solid var(--ap-line); border-left: 3px solid #cbd5e1;
  border-radius: 12px; padding: 16px 18px; margin-bottom: 12px;
}
.ap-problem.p0 { border-left-color: #d92d20; }
.ap-problem.p1 { border-left-color: #f79009; }
.ap-problem.p2 { border-left-color: #2f5bff; }
.ap-problem .top { display: flex; align-items: center; gap: 10px; }
.ap-problem .title { font-size: 14.5px; font-weight: 650; color: var(--ap-ink); }
.ap-meta { display: flex; gap: 26px; flex-wrap: wrap; margin-top: 12px; }
.ap-meta .item { font-size: 12.5px; color: var(--ap-muted); }
.ap-meta .item b { display: block; color: var(--ap-ink); font-size: 13px; font-weight: 620; margin-top: 3px; }
.ap-advice {
  margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--ap-line);
  font-size: 12.8px; color: #334155; line-height: 1.7;
}

/* 标签 */
.ap-badge {
  display: inline-block; font-size: 11.5px; font-weight: 650;
  padding: 2px 9px; border-radius: 6px; letter-spacing: .2px;
}
.ap-badge.p0 { background: #fdecec; color: #b42318; }
.ap-badge.p1 { background: #fff4e5; color: #b25e09; }
.ap-badge.p2 { background: #eef4ff; color: #2f5bff; }
.ap-badge.p3 { background: #eef1f6; color: #475569; }
.ap-badge.gray { background: #eef1f6; color: #475569; }
.ap-badge.green { background: #e9f9f0; color: #12805c; }

/* 洞察卡片 */
.ap-insight {
  background: #fcfdff; border: 1px solid var(--ap-line); border-radius: 12px;
  padding: 16px 18px; height: 100%;
}
.ap-insight h4 { margin: 0 0 10px; font-size: 13.5px; color: var(--ap-brand); font-weight: 650; }
.ap-insight ul { margin: 0; padding-left: 17px; }
.ap-insight li { font-size: 12.9px; color: #334155; margin-bottom: 7px; line-height: 1.65; }
.ap-insight li:last-child { margin-bottom: 0; }

/* Agent 步骤 */
.ap-step { display: flex; gap: 14px; padding: 13px 0; border-bottom: 1px dashed var(--ap-line); }
.ap-step:last-child { border-bottom: none; }
.ap-step-idx {
  flex: 0 0 24px; width: 24px; height: 24px; border-radius: 50%;
  background: #eef4ff; color: var(--ap-brand); font-size: 12px; font-weight: 650;
  display: flex; align-items: center; justify-content: center; margin-top: 1px;
}
.ap-step.done .ap-step-idx { background: #e9f9f0; color: #12805c; }
.ap-step-body h5 { margin: 0 0 4px; font-size: 13.3px; color: var(--ap-ink); font-weight: 620; }
.ap-step-body p { margin: 0; font-size: 12.6px; color: var(--ap-muted); line-height: 1.65; }

/* 说明文字 */
.ap-note {
  font-size: 12px; color: #94a3b8; line-height: 1.7;
  background: var(--ap-soft); border: 1px solid var(--ap-line);
  border-radius: 10px; padding: 11px 14px; margin-top: 10px;
}
.ap-mode {
  display: inline-block; font-size: 11.5px; font-weight: 600;
  padding: 3px 9px; border-radius: 999px;
  background: #eef4ff; color: #2f5bff;
}
.ap-mode.mock { background: #eef1f6; color: #475569; }

/* 控件微调 */
.stButton > button { border-radius: 9px; font-weight: 600; }
div[data-testid="stMetricValue"] { font-size: 24px; }
[data-testid="stSidebar"] { border-right: 1px solid var(--ap-line); }
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
.ap-brand { padding: 4px 0 14px; border-bottom: 1px solid var(--ap-line); margin-bottom: 14px; }
.ap-brand .name { font-size: 15px; font-weight: 700; color: var(--ap-ink); letter-spacing: .2px; }
.ap-brand .sub { font-size: 11.5px; color: var(--ap-muted); margin-top: 5px; line-height: 1.5; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="ap-header"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def section(title: str, desc: str = "") -> None:
    desc_html = f"<span>{desc}</span>" if desc else ""
    st.markdown(
        f'<div class="ap-section"><h3>{title}</h3>{desc_html}</div>',
        unsafe_allow_html=True,
    )


def compact_section(title: str, desc: str = "") -> None:
    desc_html = f"<span>{desc}</span>" if desc else ""
    st.markdown(
        f'<div class="ap-section" style="margin-top:16px"><h3>{title}</h3>{desc_html}</div>',
        unsafe_allow_html=True,
    )


def _delta_html(delta: str | None, direction: str) -> str:
    if not delta:
        return ""
    cls = {"up": "up", "down": "down"}.get(direction, "flat")
    return f'<div><span class="ap-delta {cls}">{delta}</span></div>'


def kpi_card(label: str, value: str, delta: str | None = None, direction: str = "flat", hint: str = "") -> str:
    hint_html = f'<div class="ap-kpi-hint">{hint}</div>' if hint else ""
    return (
        f'<div class="ap-kpi"><div class="ap-kpi-label">{label}</div>'
        f'<div class="ap-kpi-value">{value}</div>'
        f'{_delta_html(delta, direction)}{hint_html}</div>'
    )


def kpi_row(items: list[dict]) -> None:
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col:
            st.markdown(kpi_card(**item), unsafe_allow_html=True)


def hero(score: str, unit: str, label: str, desc: str) -> None:
    st.markdown(
        f'<div class="ap-hero"><div><div class="label">{label}</div>'
        f'<div class="score">{score}<small>{unit}</small></div></div>'
        f'<div class="divider"></div><div class="desc">{desc}</div></div>',
        unsafe_allow_html=True,
    )


def badge(text: str, kind: str = "gray") -> str:
    return f'<span class="ap-badge {kind}">{text}</span>'


def priority_badge(priority: str) -> str:
    return badge(priority, priority.lower() if priority in {"P0", "P1", "P2", "P3"} else "gray")


def status_badge(status: str) -> str:
    kind = {"已上线": "green", "实验中": "p2"}.get(status, "gray")
    return badge(status, kind)


def problem_card(
    priority: str,
    title: str,
    metrics: dict[str, str],
    advice: str,
) -> None:
    meta = "".join(
        f'<div class="item">{key}<b>{value}</b></div>' for key, value in metrics.items()
    )
    st.markdown(
        f'<div class="ap-problem {priority.lower()}">'
        f'<div class="top">{priority_badge(priority)}<span class="title">{title}</span></div>'
        f'<div class="ap-meta">{meta}</div>'
        f'<div class="ap-advice"><b>AI 建议：</b>{advice}</div></div>',
        unsafe_allow_html=True,
    )


def insight_card(title: str, bullets: list[str]) -> None:
    items = "".join(f"<li>{b}</li>" for b in bullets)
    st.markdown(
        f'<div class="ap-insight"><h4>{title}</h4><ul>{items}</ul></div>',
        unsafe_allow_html=True,
    )


def plain_card(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ap-card"><h4>{title}</h4><p>{body}</p></div>',
        unsafe_allow_html=True,
    )


def agent_steps(steps: list[dict]) -> None:
    html = []
    for i, step in enumerate(steps, start=1):
        state = "done" if step.get("done", True) else ""
        html.append(
            f'<div class="ap-step {state}"><div class="ap-step-idx">{i}</div>'
            f'<div class="ap-step-body"><h5>{step["name"]}</h5>'
            f'<p>{step["output"]}</p></div></div>'
        )
    st.markdown("".join(html), unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="ap-note">{text}</div>', unsafe_allow_html=True)


def mode_tag(mode: str, text: str) -> None:
    cls = "ap-mode mock" if mode == "mock" else "ap-mode"
    st.markdown(f'<span class="{cls}">{text}</span>', unsafe_allow_html=True)