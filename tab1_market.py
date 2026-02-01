import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# [V228 Fix] 
# 1. 将日期选择从 Slider 升级为 Date Input (支持日历选择/手动输入)
# 2. 保持 Plotly 修复 (扁平化参数，防止 ValueError)
def render(df, chart_color="#2563eb", chart_font_size=12, inventory_map=None):
    st.subheader("📊 市场概览 (Market Overview)")

    # 1. 筛选逻辑
    with st.expander("🛠️ 筛选与设置 (Settings)", expanded=True):
        col1, col2 = st.columns(2)
        
        # A. 时间频率
        with col1:
            freq_mode = st.radio(
                "时间维度 (Time Frequency):",
                ["Yearly (按年)", "Quarterly (按季)", "Monthly (按月)"],
                index=0,
                horizontal=True,
                key="tab1_freq_mode_v228"
            )
            
        # B. 日期选择器 (Date Picker)
        with col2:
            if 'Sale Date' not in df.columns:
                st.error("数据缺少 'Sale Date' 列，无法生成图表。")
                return

            min_date = df['Sale Date'].min().date()
            max_date = df['Sale Date'].max().date()
            
            # 默认显示最近 5 年
            try:
                default_start = max(min_date, max_date.replace(year=max_date.year - 5))
            except:
                default_start = min_date
            
            # 使用 date_input 替代 slider
            date_range_input = st.date_input(
                "日期范围 (Date Range):",
                value=(default_start, max_date),
                min_value=min_date,
                max_value=max_date,
                format="YYYY-MM-DD",
                key="tab1_date_picker_v228",
                help="点击日历选择，或直接输入日期 (格式 YYYY-MM-DD)"
            )
            
            # 校验日期选择 (确保选了开始和结束)
            if len(date_range_input) == 2:
                start_date, end_date = date_range_input
            else:
                st.warning("请选择完整的起止日期 (Start & End Date)")
                return

    # 2. 数据聚合
    mask = (df['Sale Date'].dt.date >= start_date) & (df['Sale Date'].dt.date <= end_date)
    filtered_df = df.loc[mask].copy()

    if filtered_df.empty:
        st.warning("⚠️ 该时间段内无交易数据。")
        return

    # 频率转换
    if "Yearly" in freq_mode:
        group_col = filtered_df['Sale Date'].dt.to_period("Y").astype(str)
        x_label = "Year"
    elif "Quarterly" in freq_mode:
        group_col = filtered_df['Sale Date'].dt.to_period("Q").astype(str)
        x_label = "Quarter"
    else:
        group_col = filtered_df['Sale Date'].dt.to_period("M").astype(str)
        x_label = "Month"

    # 统计计算
    trend_data = filtered_df.groupby(group_col).agg(
        Avg_PSF=('Unit Price ($ psf)', 'mean'),
        Volume=('Unit Price ($ psf)', 'count')
    ).reset_index()
    trend_data.columns = ['Period', 'Avg PSF', 'Volume']
    trend_data['Period'] = trend_data['Period'].astype(str)

    # 3. KPI 指标
    kpi1, kpi2, kpi3 = st.columns(3)
    avg_psf_now = trend_data['Avg PSF'].iloc[-1] if not trend_data.empty else 0
    total_vol = trend_data['Volume'].sum()
    highest_psf = filtered_df['Unit Price ($ psf)'].max() if not filtered_df.empty else 0

    kpi1.metric("当前平均尺价 (Avg PSF)", f"${avg_psf_now:,.0f}")
    kpi2.metric("期间总交易量 (Total Vol)", f"{total_vol} Units")
    kpi3.metric("最高成交尺价 (Highest)", f"${highest_psf:,.0f} psf")

    # 4. 图表绘制 (Safe Mode - V227 Flat API)
    fig = go.Figure()

    # Trace 1: 交易量 (柱状图) - 对应右轴 y2
    fig.add_trace(go.Bar(
        x=trend_data['Period'],
        y=trend_data['Volume'],
        name="Volume (交易量)",
        marker_color='#94a3b8', # 浅灰色
        opacity=0.5,
        yaxis='y2' # 绑定到第二个Y轴
    ))

    # Trace 2: 平均尺价 (折线图) - 对应左轴 y
    fig.add_trace(go.Scatter(
        x=trend_data['Period'],
        y=trend_data['Avg PSF'],
        name="Avg PSF (平均尺价)",
        mode='lines+markers',
        line=dict(color=chart_color, width=3),
        marker=dict(size=8, color=chart_color)
    ))

    # Layout: 使用扁平参数，避免嵌套字典错误
    fig.update_layout(
        title_text=f"Price & Volume Trend ({x_label})",
        hovermode="x unified",
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.8)"),
        margin=dict(l=20, r=20, t=50, b=20),
        height=450,
        font=dict(size=chart_font_size),
        
        # 定义双轴
        yaxis=dict(
            title="Avg Price ($ psf)",
            title_font=dict(color=chart_color),
            tickfont=dict(color=chart_color),
            side="left"
        ),
        yaxis2=dict(
            title="Volume (Units)",
            title_font=dict(color="#64748b"),
            tickfont=dict(color="#64748b"),
            anchor="x",
            overlaying="y", # 关键：覆盖在第一个Y轴上
            side="right",
            showgrid=False
        ),
        xaxis=dict(
            title=x_label,
            tickangle=-45
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    # 5. 数据表
    with st.expander("📋 查看详细统计数据 (View Data Table)"):
        st.dataframe(
            trend_data.style.format({"Avg PSF": "${:,.0f}", "Volume": "{:.0f}"}), 
            use_container_width=True
        )