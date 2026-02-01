import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# [V225 Fix] 更新函数签名以匹配 app.py 的调用 (接收4个参数)
def render(df, chart_color="#2563eb", chart_font_size=12, inventory_map=None):
    st.subheader("📊 市场概览 (Market Overview)")

    # 1. 侧边栏/顶部筛选器
    with st.expander("🛠️ 筛选与设置 (Settings)", expanded=True):
        col1, col2 = st.columns(2)
        
        # A. 时间频率选择
        with col1:
            freq_mode = st.radio(
                "时间维度 (Time Frequency):",
                ["Yearly (按年)", "Quarterly (按季)", "Monthly (按月)"],
                index=0,
                horizontal=True,
                key="tab1_freq_mode" # 增加key防止状态丢失
            )
            
        # B. 日期范围滑块
        with col2:
            if 'Sale Date' not in df.columns:
                st.error("数据缺少 'Sale Date' 列")
                return

            min_date = df['Sale Date'].min().date()
            max_date = df['Sale Date'].max().date()
            
            # 默认最近5年，如果数据不足5年则显示全部
            try:
                default_start = max(min_date, max_date.replace(year=max_date.year - 5))
            except:
                default_start = min_date
            
            date_range = st.slider(
                "日期范围 (Date Range):",
                min_value=min_date,
                max_value=max_date,
                value=(default_start, max_date),
                format="YYYY-MM-DD",
                key="tab1_date_slider"
            )

    # 2. 数据处理
    # 按日期筛选
    mask = (df['Sale Date'].dt.date >= date_range[0]) & (df['Sale Date'].dt.date <= date_range[1])
    filtered_df = df.loc[mask].copy()

    if filtered_df.empty:
        st.warning("⚠️ 该时间段内无交易数据。")
        return

    # 按频率聚合
    if "Yearly" in freq_mode:
        group_col = filtered_df['Sale Date'].dt.to_period("Y").astype(str)
        x_label = "Year"
    elif "Quarterly" in freq_mode:
        group_col = filtered_df['Sale Date'].dt.to_period("Q").astype(str)
        x_label = "Quarter"
    else:
        group_col = filtered_df['Sale Date'].dt.to_period("M").astype(str)
        x_label = "Month"

    # 聚合计算：平均尺价 & 交易量
    trend_data = filtered_df.groupby(group_col).agg(
        Avg_PSF=('Unit Price ($ psf)', 'mean'),
        Volume=('Unit Price ($ psf)', 'count')
    ).reset_index()
    trend_data.columns = ['Period', 'Avg PSF', 'Volume']
    trend_data['Period'] = trend_data['Period'].astype(str) 

    # 3. 关键指标卡片 (KPI Cards)
    kpi1, kpi2, kpi3 = st.columns(3)
    avg_psf_now = trend_data['Avg PSF'].iloc[-1] if not trend_data.empty else 0
    total_vol = trend_data['Volume'].sum()
    highest_psf = filtered_df['Unit Price ($ psf)'].max()

    kpi1.metric("当前平均尺价 (Avg PSF)", f"${avg_psf_now:,.0f}")
    kpi2.metric("期间总交易量 (Total Vol)", f"{total_vol} Units")
    kpi3.metric("最高成交尺价 (Highest)", f"${highest_psf:,.0f} psf")

    # 4. 混合图表 (Line + Bar)
    fig = go.Figure()

    # 柱状图：交易量
    fig.add_trace(go.Bar(
        x=trend_data['Period'],
        y=trend_data['Volume'],
        name="Volume (交易量)",
        marker_color='#cbd5e1',
        opacity=0.6,
        yaxis='y2'
    ))

    # 折线图：平均尺价 (使用传入的 chart_color)
    fig.add_trace(go.Scatter(
        x=trend_data['Period'],
        y=trend_data['Avg PSF'],
        name="Avg PSF (平均尺价)",
        mode='lines+markers',
        line=dict(color=chart_color, width=3),
        marker=dict(size=8)
    ))

    # 布局设置
    fig.update_layout(
        title=f"Price & Volume Trend ({x_label})",
        xaxis=dict(title=x_label, tickangle=-45),
        yaxis=dict(
            title="Avg Price ($ psf)",
            titlefont=dict(color=chart_color),
            tickfont=dict(color=chart_color)
        ),
        yaxis2=dict(
            title="Volume (Units)",
            titlefont=dict(color="#64748b"),
            tickfont=dict(color="#64748b"),
            overlaying='y',
            side='right',
            showgrid=False
        ),
        legend=dict(x=0.01, y=0.99),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20),
        height=450,
        font=dict(size=chart_font_size) # 使用传入的 font size
    )

    st.plotly_chart(fig, use_container_width=True)

    # 5. 详细数据表 (可选展开)
    with st.expander("📋 查看详细统计数据 (View Data Table)"):
        st.dataframe(trend_data.style.format({"Avg PSF": "${:,.0f}", "Volume": "{:.0f}"}), use_container_width=True)