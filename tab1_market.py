import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# [V237 Update] KPI Card 支持传入主色调
def kpi_card(label, value, secondary="", color_hex="#111827"):
    sub_html = f'<div style="font-size: 11px; color: #9ca3af; margin-top: 4px;">{secondary}</div>' if secondary else ''
    
    return f"""
    <div style="background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <div style="font-size: 13px; color: #6b7280; margin-bottom: 4px; font-weight: 500;">{label}</div>
        <div style="font-size: 18px; font-weight: 700; color: {color_hex}; line-height: 1.2;">{value}</div>
        {sub_html}
    </div>
    """

def render(df, chart_color="#2563eb", chart_font_size=12, inventory_map=None):
    st.subheader("📊 市场概览 (Market Overview)")

    # 0. 基础校验
    required_cols = ['Sale Date', 'Unit Price ($ psf)', 'Sale Price']
    for col in required_cols:
        if col not in df.columns:
            st.error(f"数据缺少必要列: {col}，无法生成报告。")
            return

    # 1. 初始化 Session State
    min_db_date = df['Sale Date'].min().date()
    max_db_date = df['Sale Date'].max().date()

    if "mkt_start_v237" not in st.session_state: st.session_state.mkt_start_v237 = min_db_date
    if "mkt_end_v237" not in st.session_state: st.session_state.mkt_end_v237 = max_db_date

    # 2. 宏观 KPI
    total_units = df['Unit_ID'].nunique() if 'Unit_ID' in df.columns else len(df)
    cat_col = 'Type' if 'Type' in df.columns else ('Category' if 'Category' in df.columns else None)
    total_types = df[cat_col].nunique() if cat_col else 0
    
    st.markdown("##### 🏗️ 基础数据 (Project Stats)")
    c1, c2, c3, c4 = st.columns(4)
    # [修改] 传入 chart_color 让数字变色
    with c1: st.markdown(kpi_card("已成交单位", f"{total_units:,}", color_hex=chart_color), unsafe_allow_html=True)
    with c2: st.markdown(kpi_card("户型总数", total_types, color_hex=chart_color), unsafe_allow_html=True)
    with c3: st.markdown(kpi_card("最早成交", min_db_date.strftime('%Y-%m-%d'), color_hex=chart_color), unsafe_allow_html=True)
    with c4: st.markdown(kpi_card("最近成交", max_db_date.strftime('%Y-%m-%d'), color_hex=chart_color), unsafe_allow_html=True)
    st.divider()

    # 3. 筛选与设置
    with st.expander("🛠️ 筛选与设置 (Filters & Settings)", expanded=True):
        def apply_preset():
            preset = st.session_state.get("mkt_preset_selector_v237")
            target_end = max_db_date
            if preset == "全部 (All)": target_start = min_db_date
            elif preset == "近6个月": target_start = target_end - relativedelta(months=6)
            elif preset == "近1年": target_start = target_end - relativedelta(years=1)
            elif preset == "近2年": target_start = target_end - relativedelta(years=2)
            elif preset == "近3年": target_start = target_end - relativedelta(years=3)
            elif preset == "近5年": target_start = target_end - relativedelta(years=5)
            elif preset == "近10年": target_start = target_end - relativedelta(years=10)
            else: target_start = min_db_date
            st.session_state.mkt_start_v237 = max(target_start, min_db_date)
            st.session_state.mkt_end_v237 = target_end

        c_top1, c_top2 = st.columns([1, 2])
        with c_top1:
            freq_mode = st.radio("时间维度:", ["Yearly (年)", "Quarterly (季)", "Monthly (月)"], index=0, horizontal=True, key="tab1_freq_mode_v237")
        with c_top2:
            preset_options = ["全部 (All)", "近6个月", "近1年", "近2年", "近3年", "近5年", "近10年"]
            try: st.pills("📅 快速选择:", preset_options, selection_mode="single", key="mkt_preset_selector_v237", on_change=apply_preset)
            except AttributeError: st.selectbox("📅 快速选择:", preset_options, index=0, key="mkt_preset_selector_v237", on_change=apply_preset)

        c_d1, c_d2 = st.columns(2)
        with c_d1: st.date_input("开始日期:", min_value=min_db_date, max_value=max_db_date, key="mkt_start_v237")
        with c_d2: st.date_input("结束日期:", min_value=min_db_date, max_value=max_db_date, key="mkt_end_v237")

    start_date = st.session_state.mkt_start_v237
    end_date = st.session_state.mkt_end_v237
    if start_date > end_date: st.error("开始日期不能晚于结束日期"); return
    
    mask = (df['Sale Date'].dt.date >= start_date) & (df['Sale Date'].dt.date <= end_date)
    filtered_df = df.loc[mask].copy()
    if filtered_df.empty: st.warning("该时间段内无交易数据。"); return

    # 4. 图表逻辑
    if "Yearly" in freq_mode: group_col, x_label = filtered_df['Sale Date'].dt.to_period("Y").astype(str), "Year"
    elif "Quarterly" in freq_mode: group_col, x_label = filtered_df['Sale Date'].dt.to_period("Q").astype(str), "Quarter"
    else: group_col, x_label = filtered_df['Sale Date'].dt.to_period("M").astype(str), "Month"

    trend_data = filtered_df.groupby(group_col).agg(Avg_PSF=('Unit Price ($ psf)', 'mean'), Volume=('Unit Price ($ psf)', 'count')).reset_index()
    trend_data.columns = ['Period', 'Avg PSF', 'Volume']
    trend_data['Period'] = trend_data['Period'].astype(str)

    fig = go.Figure()
    # [修改] 柱状图使用主色调，但降低透明度
    fig.add_trace(go.Bar(x=trend_data['Period'], y=trend_data['Volume'], name="Volume", marker_color=chart_color, opacity=0.3, yaxis='y2'))
    fig.add_trace(go.Scatter(x=trend_data['Period'], y=trend_data['Avg PSF'], name="Avg PSF", mode='lines+markers', line=dict(color=chart_color, width=3), marker=dict(size=8, color=chart_color)))
    
    fig.update_layout(
        title_text=f"Price & Volume Trend ({x_label})", hovermode="x unified", legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.8)"),
        margin=dict(l=20, r=20, t=50, b=20), height=400, font=dict(size=chart_font_size),
        yaxis=dict(title="Avg Price ($ psf)", title_font=dict(color=chart_color), tickfont=dict(color=chart_color), side="left"),
        yaxis2=dict(title="Volume", title_font=dict(color=chart_color), tickfont=dict(color=chart_color), anchor="x", overlaying="y", side="right", showgrid=False), # [修改] 右轴颜色也统一
        xaxis=dict(title=x_label, tickangle=-45)
    )
    st.plotly_chart(fig, use_container_width=True)
    st.divider()

    # 5. 活跃度分析
    st.markdown("##### 🔥 活跃度分析 (Top Performers)")
    def get_top(col):
        if col not in filtered_df.columns: return "N/A", 0, 0
        stats = filtered_df.groupby(col).agg({'Sale Price':'count', 'Unit Price ($ psf)':'mean'}).reset_index()
        if stats.empty: return "N/A", 0, 0
        top = stats.sort_values('Sale Price', ascending=False).iloc[0]
        return top[col], top['Sale Price'], top['Unit Price ($ psf)']

    a1, a2, a3, a4 = st.columns(4)
    b_n, b_c, b_p = get_top('BLK')
    a1.info(f"**Top 楼栋: {b_n}**\n\n{b_c}笔 | ${b_p:,.0f}psf")
    s_n, s_c, s_p = get_top('Stack')
    a2.info(f"**Top Stack: {s_n}**\n\n{s_c}笔 | ${s_p:,.0f}psf")
    
    if 'Floor_Num' in filtered_df.columns:
        filtered_df['Floor_Zone'] = filtered_df['Floor_Num'].apply(lambda x: 'Low' if x<=5 else ('Mid' if x<=15 else 'High'))
        f_n, f_c, f_p = get_top('Floor_Zone')
        a3.info(f"**Top 层段: {f_n}**\n\n{f_c}笔 | ${f_p:,.0f}psf")
    else: a3.info("无楼层数据")
    
    if cat_col in filtered_df.columns:
        c_n, c_c, c_p = get_top(cat_col)
        a4.info(f"**Top 户型: {c_n}**\n\n{c_c}笔 | ${c_p:,.0f}psf")
    else: a4.info("无户型数据")
    st.markdown("---")

    # 6. 转售与回报
    st.subheader("💰 转售与回报 (Resale & Returns)")
    full_df_sorted = df.sort_values(['Unit_ID', 'Sale Date']).copy()
    full_df_sorted['Prev_Price'] = full_df_sorted.groupby('Unit_ID')['Sale Price'].shift(1)
    full_df_sorted['Prev_Date'] = full_df_sorted.groupby('Unit_ID')['Sale Date'].shift(1)
    full_df_sorted['Gain'] = full_df_sorted['Sale Price'] - full_df_sorted['Prev_Price']
    full_df_sorted['Hold_Days'] = (full_df_sorted['Sale Date'] - full_df_sorted['Prev_Date']).dt.days
    full_df_sorted['Hold_Years'] = full_df_sorted['Hold_Days'] / 365.0
    full_df_sorted['Annualized'] = np.where(full_df_sorted['Hold_Days'] >= 180, ((full_df_sorted['Sale Price'] / full_df_sorted['Prev_Price']) ** (365 / full_df_sorted['Hold_Days']) - 1) * 100, np.nan)
    
    resale_df = full_df_sorted[(full_df_sorted['Sale Date'].dt.date >= start_date) & (full_df_sorted['Sale Date'].dt.date <= end_date) & (full_df_sorted['Prev_Price'].notnull()) & (full_df_sorted['Hold_Days'] >= 30)].copy()

    if resale_df.empty:
        st.warning("选定时间段内无有效的转售数据。")
    else:
        st.markdown("###### 1. 持有表现")
        uid_counts = df.groupby('Unit_ID').size()
        max_turnover = uid_counts.max() - 1 if not uid_counts.empty else 0
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(kpi_card("平均持有时间", f"{resale_df['Hold_Years'].mean():.1f} 年"), unsafe_allow_html=True)
        with c2: st.markdown(kpi_card("最长 / 最短持有", f"{resale_df['Hold_Years'].max():.1f} / {resale_df['Hold_Years'].min():.1f} 年"), unsafe_allow_html=True)
        with c3: st.markdown(kpi_card("单位最大转售", f"{max_turnover} 次"), unsafe_allow_html=True)

        profits = resale_df[resale_df['Gain'] > 0]
        losses = resale_df[resale_df['Gain'] <= 0]

        st.markdown("###### 2. 盈利表现 (Profitable Deals)")
        if not profits.empty:
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(kpi_card("盈利笔数", f"{len(profits)} 笔", color_hex="#16a34a"), unsafe_allow_html=True)
            with c2: st.markdown(kpi_card("平均获利", f"${profits['Gain'].mean()/1e6:,.2f}M", color_hex="#16a34a"), unsafe_allow_html=True)
            with c3: st.markdown(kpi_card("最大获利", f"${profits['Gain'].max()/1e6:,.2f}M", color_hex="#16a34a"), unsafe_allow_html=True)
            with c4: st.markdown(kpi_card("平均年化回报", f"{profits['Annualized'].mean():.1f}%", color_hex="#16a34a"), unsafe_allow_html=True)
        else: st.info("暂无盈利交易")

        st.markdown("###### 3. 风险与亏损 (Unprofitable Deals)")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(kpi_card("亏损笔数", f"{len(losses)} 笔", color_hex="#dc2626"), unsafe_allow_html=True)
        with c2: st.markdown(kpi_card("亏损占比", f"{(len(losses)/len(resale_df))*100:.1f}%", color_hex="#dc2626"), unsafe_allow_html=True)
        if not losses.empty:
            with c3: st.markdown(kpi_card("平均亏损", f"-${abs(losses['Gain'].mean())/1e6:,.2f}M", color_hex="#dc2626"), unsafe_allow_html=True)
            with c4: st.markdown(kpi_card("最大亏损", f"-${abs(losses['Gain'].min())/1e6:,.2f}M", color_hex="#dc2626"), unsafe_allow_html=True)
        else:
            with c3: st.markdown(kpi_card("平均亏损", "-", color_hex="#dc2626"), unsafe_allow_html=True)
            with c4: st.markdown(kpi_card("最大亏损", "-", color_hex="#dc2626"), unsafe_allow_html=True)
    st.markdown("---")
    st.caption("ℹ️ **说明**: 持有<30天数据已剔除；持有<6个月不计年化回报。")