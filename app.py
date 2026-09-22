"""AI Product Intelligence —— AI 产品智能增长与体验优化平台。

运行方式：
    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="AI Product Intelligence",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

from modules import (  # noqa: E402
    ab_test,
    ai_evaluation,
    dashboard,
    diagnosis,
    iteration,
    product_plan,
    user_insight,
)
from services import llm_service  # noqa: E402
from utils import product  # noqa: E402
from utils import ui  # noqa: E402
from utils.data_loader import ensure_data  # noqa: E402

PAGES = {
    "产品总览": dashboard.render,
    "用户洞察": user_insight.render,
    "AI 体验评测": ai_evaluation.render,
    "问题诊断": diagnosis.render,
    "产品方案": product_plan.render,
    "A/B 实验": ab_test.render,
    "迭代中心": iteration.render,
}


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            '<div class="ap-brand"><div class="name">AI Product Intelligence</div>'
            '<div class="sub">AI 产品智能增长与体验优化平台</div></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"分析对象：{product.name()}")
        page = st.radio("导航", list(PAGES.keys()), label_visibility="collapsed")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        status = llm_service.get_status()
        if status.is_live:
            ui.mode_tag("llm", f"已连接 {status.provider}")
            st.caption(f"模型：{status.model}")
        else:
            ui.mode_tag("mock", "Mock 模式")
            st.caption("未配置 API Key，使用本地分析引擎，全部功能可正常演示")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        with st.expander("数据与设置"):
            st.caption(f"分析对象：{product.name()}")
            st.caption(f"产品定位：{product.positioning()}")
            st.caption("当前所有指标与反馈均为模拟数据，由 generate_data.py 生成，不涉及任何真实企业数据。")
            if st.button("重新生成模拟数据", width="stretch"):
                ensure_data(force=True)
                st.success("模拟数据已重新生成。")
                st.rerun()
            st.caption("分析方法：指标异常检测 + 反馈聚类 + RICE 评分 + A/B 显著性检验")
    return page


def main() -> None:
    ui.inject_css()
    ensure_data()
    page = render_sidebar()
    PAGES[page]()


if __name__ == "__main__":
    main()