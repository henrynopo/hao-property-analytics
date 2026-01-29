# 文件名: tab4_history.py
import streamlit as st
import pandas as pd

# 🟢 纯净版：只显示表格，不重复显示趋势图
def render(df, chart_font_size=12):
    st.subheader("📋 历年交易详情 (Transaction Details)")
    
    if 'Sale Date' not in df.columns:
        st.warning("数据缺失，无法显示详情")
        return

    # 简单清洗
    display_df = df.copy()
    if 'Sale Date' in display_df.columns:
        display_df['Sale Date'] = pd.to_datetime(display_df['Sale Date']).dt.date
    
    # 按照日期倒序排列
    display_df = display_df.sort_values('Sale Date', ascending=False)

    # 🟢 核心修正：
    # 1. 直接展示 dataframe，不使用 expander 折叠
    # 2. hide_index=True 去除第一列无意义的索引号
    st.dataframe(
        display_df, 
        use_container_width=True, 
        hide_index=True
    )
    
    st.caption(f"共显示 {len(display_df)} 条交易记录。")
