# 文件名: tab1_market.py (或 tab1_overview.py)
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
from datetime import datetime, timedelta

# --- 内部辅助函数 1: 自然排序 ---
def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# --- 内部辅助函数 2: 通用 KPI 卡片生成器 (核心UI组件) ---
def kpi_card(label, value, sub_value=None, color="default"):
    """
    生成统一风格的 HTML 卡片
    color: 'default' (黑), 'green' (绿-盈利), 'red' (红-亏损)
    """
    color_map = {
        "default": "#111827",
        "green": "#059669", # Emerald 600
        "red": "#dc2626"    # Red 600
    }
    text_color = color_map.get(color, "#111827")
    
    sub_html = f'<div style="font-size: 12px; color: #6b7280; margin-top: 2px;">{sub_value}</div>' if sub_value else ""
    
    return f"""
    <div style="
        background-color: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 12px 8px;
        text-align: center;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    ">
        <div style="font-size: 13px; color: #6b7280; margin-bottom: 4px; font-weight: 500;">{label}</div>
        <div style="font-size: 18px; font-weight: 700; color: {text_color}; line-height: 1.2;">{value}</div>
        {sub_html}
    </div>
    """

# --- 内部辅助函数 3: 数据处理 ---
def _process_resale_data(df):
    required_cols = ['BLK', 'Stack', 'Floor_Num', 'Sale Date', 'Sale Price']
    if not all(c in df.columns for c in required_cols): return pd.DataFrame()
    
    df_sorted = df.sort_values(['BLK', 'Stack', 'Floor_Num', 'Sale Date'])
    df_sorted['_uid'] = df_sorted['BLK'].astype(str) + "-" + df_sorted['Stack'].astype(str) + "-" + df_sorted['Floor_Num'].astype(str)
    
    df_sorted['Prev_Price'] = df_sorted.groupby('_uid')['Sale Price'].shift(1)
    df_sorted['Prev_Date'] = df_sorted.groupby('_uid')['Sale Date'].shift(1)
    
    resales = df_sorted.dropna(subset=['Prev_Price']).copy()
    if resales.empty: return pd.DataFrame()
    
    resales['Gain'] = resales['Sale Price'] - resales['Prev_Price']
    resales['Hold_Days'] = (resales['Sale Date'] - resales['Prev_Date']).dt.days
    
    # 过滤 < 30天
    resales = resales[resales['Hold_Days'] > 30].copy()
    if resales.empty: return pd.DataFrame()

    resales['Hold_Years'] = resales['Hold_Days'] / 365.25
    
    def calc_annualized(row):
        if row['Hold_Years'] < 0.5: return None 
        if row['Prev_Price'] == 0: return 0
        ratio = row['Sale Price'] / row['Prev_Price']
        return (ratio ** (1 / row['Hold_Years']) - 1) * 100

    resales['Annualized'] = resales.apply(calc_annualized, axis=1)
    return resales

# --- 主渲染函数 ---
def render(df, chart_color='#1f77b4', chart_font_size=12, inventory_map=None):
    st.subheader("📊 项目全景概览 (Project Overview)")

    if 'Sale Date' not in df.columns: st.error("数据缺失 Sale Date"); return
    df['Sale Date'] = pd.to_datetime(df['Sale Date'])
    df['Year'] = df['Sale Date'].dt.year

    resale_df = _process_resale_data(df)

    # ================= 2. 宏观 KPI (UI 统一) =================
    if 'Floor_Num' in df.columns:
        total_units = df[['BLK', 'Stack', 'Floor_Num']].drop_duplicates().shape[0]
    else:
        total_units = len(df)
    
    cat_col = next((c for c in ['Bedroom Type', 'Category', 'Type'] if c in df.columns), None)
    total_types = df[cat_col].nunique() if cat_col else 0
    
    min_date_str = df['Sale Date'].min().strftime('%Y-%m-%d')
    max_date_str = df['Sale Date'].max().strftime('%Y-%m-%d')

    st.markdown("##### 🏗️ 基础数据")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(kpi_card("已成交单位", f"{total_units:,}"), unsafe_allow_html=True)
    with c2: st.markdown(kpi_card("户型总数", total_types), unsafe_allow_html=True)
    with c3: st.markdown(kpi_card("最早成交", min_date_str), unsafe_allow_html=True)
    with c4: st.markdown(kpi_card("最近成交", max_date_str), unsafe_allow_html=True)

    st.markdown("---")

    # ================= 3. 历年量价 =================
    st.markdown("##### 📈 历年量价趋势")
    tab_trend_all, tab_trend_cat = st.tabs(["总体趋势", "分户型趋势"])
    
    with tab_trend_all:
        yearly = df.groupby('Year').agg({'Sale Price': 'count', 'Sale PSF': 'mean'}).reset_index()
        fig = go.Figure()
        fig.add_trace(go.Bar(x=yearly['Year'], y=yearly['Sale Price'], name='成交量', marker_color='#dbeafe', yaxis='y'))
        fig.add_trace(go.Scatter(x=yearly['Year'], y=yearly['Sale PSF'], name='平均尺价', mode='lines+markers', line=dict(color=chart_color, width=3), yaxis='y2'))
        fig.update_layout(yaxis=dict(title='成交量 (笔)', side='left', showgrid=False), yaxis2=dict(title='尺价 ($PSF)', side='right', overlaying='y'), hovermode='x unified', height=350, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with tab_trend_cat:
        if cat_col:
            cat_trend = df.groupby(['Year', cat_col]).agg({'Sale PSF': 'mean'}).reset_index()
            fig_cat = px.line(cat_trend, x='Year', y='Sale PSF', color=cat_col, markers=True, title="各户型平均尺价走势")
            fig_cat.update_layout(height=400, hovermode='x unified')
            st.plotly_chart(fig_cat, use_container_width=True)
        else: st.info("无户型信息")

    st.markdown("---")

    # ================= 4. 活跃度分析 (UI 统一) =================
    st.markdown("##### 🔥 活跃度分析")
    def get_top(col):
        if col not in df.columns: return "N/A", 0, 0
        stats = df.groupby(col).agg({'Sale Price':'count', 'Sale PSF':'mean'}).reset_index()
        top = stats.sort_values('Sale Price', ascending=False).iloc[0]
        return top[col], top['Sale Price'], top['Sale PSF']

    # 这里虽然是 st.info，但也可以考虑改用卡片，不过 st.info 适合展示多行文本，暂时保留，保持语义区别
    a1, a2, a3, a4 = st.columns(4)
    b_n, b_c, b_p = get_top('BLK')
    a1.info(f"**楼栋: {b_n}**\n\n{b_c}笔 | ${b_p:,.0f}psf")
    s_n, s_c, s_p = get_top('Stack')
    a2.info(f"**Stack: {s_n}**\n\n{s_c}笔 | ${s_p:,.0f}psf")
    if 'Floor_Num' in df.columns:
        df['Floor_Zone'] = df['Floor_Num'].apply(lambda x: 'Low' if x<=5 else ('Mid' if x<=15 else 'High'))
        f_n, f_c, f_p = get_top('Floor_Zone')
        a3.info(f"**层段: {f_n}**\n\n{f_c}笔 | ${f_p:,.0f}psf")
    else: a3.info("无数据")
    if cat_col:
        c_n, c_c, c_p = get_top(cat_col)
        a4.info(f"**户型: {c_n}**\n\n{c_c}笔 | ${c_p:,.0f}psf")
    else: a4.info("无数据")

    st.markdown("---")

    # ================= 5. 转售与回报 (核心区域 - UI 统一) =================
    st.subheader("💰 转售与回报 (Resale & Returns)")
    
    if resale_df.empty:
        st.warning("无足够转售数据。")
    else:
        # --- 5.1 持有统计 ---
        st.markdown("###### 1. 持有表现")
        uid_counts = df.groupby(['BLK','Stack','Floor_Num']).size()
        uid_counts = uid_counts[uid_counts > 1] 
        avg_turnover = uid_counts.mean() - 1 if not uid_counts.empty else 0
        
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(kpi_card("平均持有时间", f"{resale_df['Hold_Years'].mean():.1f} 年"), unsafe_allow_html=True)
        with c2: st.markdown(kpi_card("最长 / 最短持有", f"{resale_df['Hold_Years'].max():.1f} / {resale_df['Hold_Years'].min():.1f} 年"), unsafe_allow_html=True)
        with c3: st.markdown(kpi_card("单位最大转售", f"{uid_counts.max() - 1 if not uid_counts.empty else 0} 次", f"平均周转: {avg_turnover:.1f} 次"), unsafe_allow_html=True)

        profits = resale_df[resale_df['Gain'] > 0]
        losses = resale_df[resale_df['Gain'] <= 0]

        # --- 5.2 盈利表现 ---
        st.markdown("###### 2. 盈利表现 (仅统计获利交易)")
        if not profits.empty:
            avg_ann = profits['Annualized'].mean()
            max_ann = profits['Annualized'].max()
            
            c1, c2, c3, c4 = st.columns(4)
            # 使用 green 风格
            with c1: st.markdown(kpi_card("盈利笔数", f"{len(profits)} 笔", color="green"), unsafe_allow_html=True)
            with c2: st.markdown(kpi_card("平均获利", f"${profits['Gain'].mean()/1e4:,.0f}k", color="green"), unsafe_allow_html=True)
            with c3: st.markdown(kpi_card("最大获利", f"${profits['Gain'].max()/1e4:,.0f}k", color="green"), unsafe_allow_html=True)
            with c4: st.markdown(kpi_card("平均年化", f"{avg_ann:.1f}%", f"Top: {max_ann:.1f}%", color="green"), unsafe_allow_html=True)
        else:
            st.info("暂无盈利交易")

        # --- 5.3 风险与亏损 ---
        st.markdown("###### 3. 风险与亏损 (仅统计亏损交易)")
        loss_count = len(losses)
        loss_rate = (loss_count / len(resale_df)) * 100
        
        recent = resale_df[resale_df['Sale Date'] > (datetime.now() - timedelta(days=365*5))]
        recent_total = len(recent)
        recent_losses = len(recent[recent['Gain'] <= 0]) if recent_total > 0 else 0
        recent_loss_rate = (recent_losses / recent_total) * 100 if recent_total > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        # 使用 red 风格
        with c1: st.markdown(kpi_card("亏损笔数", f"{loss_count} 笔", f"占比 {loss_rate:.1f}%", color="red"), unsafe_allow_html=True)
        with c2: st.markdown(kpi_card("近5年亏损占比", f"{recent_loss_rate:.1f}%", f"vs Hist: {loss_rate:.1f}%", color="red"), unsafe_allow_html=True)
        
        if not losses.empty:
            with c3: st.markdown(kpi_card("平均亏损", f"-${abs(losses['Gain'].mean())/1e4:,.0f}k", color="red"), unsafe_allow_html=True)
            with c4: st.markdown(kpi_card("最大亏损", f"-${abs(losses['Gain'].min())/1e4:,.0f}k", color="red"), unsafe_allow_html=True)
        else:
            with c3: st.markdown(kpi_card("平均亏损", "-", color="red"), unsafe_allow_html=True)
            with c4: st.markdown(kpi_card("最大亏损", "-", color="red"), unsafe_allow_html=True)

        # --- 5.4 详情 ---
        st.markdown("###### 4. 详细表现")
        tab_type, tab_blk = st.tabs(["按户型", "按楼栋"])
        
        with tab_type:
            if cat_col:
                sum_type = resale_df.groupby(cat_col).agg({'Gain': ['count', 'mean', 'max', 'min'], 'Annualized': 'mean', 'Hold_Years': 'mean'}).reset_index()
                sum_type.columns = ['Type', 'Count', 'Avg Gain', 'Max Gain', 'Min Gain', 'Avg Ann%', 'Avg Hold']
                st.dataframe(sum_type.style.format({'Avg Gain':"${:,.0f}", 'Max Gain':"${:,.0f}", 'Min Gain':"${:,.0f}", 'Avg Ann%':"{:.1f}%", 'Avg Hold':"{:.1f} Yrs"}), use_container_width=True, hide_index=True)
            else: st.info("无数据")

        with tab_blk:
            sum_blk = resale_df.groupby('BLK').agg({'Gain': ['count', 'mean', 'max', 'min'], 'Annualized': 'mean', 'Hold_Years': 'mean'}).reset_index()
            # 🟢 严谨排序
            sorted_blks = sorted(sum_blk['BLK'].unique().tolist(), key=natural_key)
            sum_blk['BLK'] = pd.Categorical(sum_blk['BLK'], categories=sorted_blks, ordered=True)
            sum_blk = sum_blk.sort_values('BLK')
            
            sum_blk.columns = ['Block', 'Count', 'Avg Gain', 'Max Gain', 'Min Gain', 'Avg Ann%', 'Avg Hold']
            st.dataframe(sum_blk.style.format({'Avg Gain':"${:,.0f}", 'Max Gain':"${:,.0f}", 'Min Gain':"${:,.0f}", 'Avg Ann%':"{:.1f}%", 'Avg Hold':"{:.1f} Yrs"}), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.caption("ℹ️ **说明**: 持有<30天数据已剔除；持有<6个月不计年化回报。")
