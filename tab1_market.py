# 文件名: tab1_market.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 内部辅助函数 ---
def _process_resale_data(df):
    required_cols = ['BLK', 'Stack', 'Floor_Num', 'Sale Date', 'Sale Price']
    if not all(c in df.columns for c in required_cols):
        return pd.DataFrame()
    
    df_sorted = df.sort_values(['BLK', 'Stack', 'Floor_Num', 'Sale Date'])
    df_sorted['_uid'] = df_sorted['BLK'].astype(str) + "-" + df_sorted['Stack'].astype(str) + "-" + df_sorted['Floor_Num'].astype(str)
    
    df_sorted['Prev_Price'] = df_sorted.groupby('_uid')['Sale Price'].shift(1)
    df_sorted['Prev_Date'] = df_sorted.groupby('_uid')['Sale Date'].shift(1)
    
    resales = df_sorted.dropna(subset=['Prev_Price']).copy()
    if resales.empty: return pd.DataFrame()
    
    resales['Gain'] = resales['Sale Price'] - resales['Prev_Price']
    resales['Hold_Days'] = (resales['Sale Date'] - resales['Prev_Date']).dt.days
    
    # 剔除 < 30天
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

    # 1. 基础清洗
    if 'Sale Date' not in df.columns:
        st.error("数据缺失 Sale Date"); return
        
    df['Sale Date'] = pd.to_datetime(df['Sale Date'])
    df['Year'] = df['Sale Date'].dt.year

    resale_df = _process_resale_data(df)

    # ================= 2. 宏观 KPI (优化排版) =================
    # 🟢 修正：使用自定义 CSS/HTML 替代 st.metric，解决字体过大和日期显示不全的问题
    
    if 'Floor_Num' in df.columns:
        total_units = df[['BLK', 'Stack', 'Floor_Num']].drop_duplicates().shape[0]
    else:
        total_units = len(df)
    
    cat_col = next((c for c in ['Bedroom Type', 'Category', 'Type'] if c in df.columns), None)
    total_types = df[cat_col].nunique() if cat_col else 0
    
    # 日期格式化为 YYYY-MM-DD
    min_date_str = df['Sale Date'].min().strftime('%Y-%m-%d')
    max_date_str = df['Sale Date'].max().strftime('%Y-%m-%d')

    # 自定义样式卡片
    st.markdown("""
    <style>
    .kpi-box {
        background-color: #f9fafb;
        border-radius: 8px;
        padding: 10px;
        text-align: center;
        border: 1px solid #e5e7eb;
    }
    .kpi-label { font-size: 14px; color: #6b7280; margin-bottom: 4px; }
    .kpi-value { font-size: 18px; font-weight: 600; color: #111827; }
    </style>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="kpi-box"><div class="kpi-label">已成交单位</div><div class="kpi-value">{total_units:,}</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="kpi-box"><div class="kpi-label">户型总数</div><div class="kpi-value">{total_types}</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="kpi-box"><div class="kpi-label">最早成交</div><div class="kpi-value">{min_date_str}</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="kpi-box"><div class="kpi-label">最近成交</div><div class="kpi-value">{max_date_str}</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    # 3. 历年量价
    st.markdown("##### 📈 历年量价趋势")
    yearly = df.groupby('Year').agg({'Sale Price': 'count', 'Sale PSF': 'mean'}).reset_index()
    yearly.columns = ['Year', 'Volume', 'Avg_PSF']

    fig = go.Figure()
    fig.add_trace(go.Bar(x=yearly['Year'], y=yearly['Volume'], name='成交量', marker_color='#dbeafe', yaxis='y'))
    fig.add_trace(go.Scatter(x=yearly['Year'], y=yearly['Avg_PSF'], name='平均尺价', mode='lines+markers', line=dict(color=chart_color, width=3), yaxis='y2'))
    fig.update_layout(
        yaxis=dict(title='成交量 (笔)', side='left', showgrid=False),
        yaxis2=dict(title='尺价 ($PSF)', side='right', overlaying='y', showgrid=True),
        hovermode='x unified', height=350, margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    # 4. 活跃度分析
    st.markdown("##### 🔥 活跃度分析 (Most Active)")
    
    def get_top(col):
        if col not in df.columns: return "N/A", 0, 0
        stats = df.groupby(col).agg({'Sale Price':'count', 'Sale PSF':'mean'}).reset_index()
        top = stats.sort_values('Sale Price', ascending=False).iloc[0]
        return top[col], top['Sale Price'], top['Sale PSF']

    a1, a2, a3, a4 = st.columns(4)
    b_n, b_c, b_p = get_top('BLK')
    a1.info(f"**最热楼栋: {b_n}**\n\n成交: {b_c}笔 | ${b_p:,.0f} psf")
    s_n, s_c, s_p = get_top('Stack')
    a2.info(f"**最热 Stack: {s_n}**\n\n成交: {s_c}笔 | ${s_p:,.0f} psf")
    
    if 'Floor_Num' in df.columns:
        df['Floor_Zone'] = df['Floor_Num'].apply(lambda x: 'Low' if x<=5 else ('Mid' if x<=15 else 'High'))
        f_n, f_c, f_p = get_top('Floor_Zone')
        a3.info(f"**最热层段: {f_n}**\n\n成交: {f_c}笔 | ${f_p:,.0f} psf")
    else: a3.info("无楼层数据")
    
    if cat_col:
        c_n, c_c, c_p = get_top(cat_col)
        a4.info(f"**最热户型: {c_n}**\n\n成交: {c_c}笔 | ${c_p:,.0f} psf")
    else: a4.info("无户型数据")

    st.markdown("---")

    # 5. 转售与回报
    st.subheader("💰 转售与回报 (Resale & Returns)")
    
    if resale_df.empty:
        st.warning("无足够转售数据。")
    else:
        # 5.1 持有统计
        st.markdown("###### 1. 持有表现")
        uid_counts = df.groupby(['BLK','Stack','Floor_Num']).size()
        uid_counts = uid_counts[uid_counts > 1] 
        avg_turnover = uid_counts.mean() - 1 if not uid_counts.empty else 0
        
        r1, r2, r3 = st.columns(3)
        r1.metric("平均持有时间", f"{resale_df['Hold_Years'].mean():.1f} 年")
        r2.metric("最长 / 最短持有", f"{resale_df['Hold_Years'].max():.1f} / {resale_df['Hold_Years'].min():.1f} 年")
        r3.metric("单位最大转售次数", f"{uid_counts.max() - 1 if not uid_counts.empty else 0} 次", f"平均 {avg_turnover:.1f} 次")

        profits = resale_df[resale_df['Gain'] > 0]
        losses = resale_df[resale_df['Gain'] <= 0]

        # 5.2 盈利表现
        st.markdown("###### 2. 盈利表现 (获利交易)")
        if not profits.empty:
            avg_ann = profits['Annualized'].mean()
            max_ann = profits['Annualized'].max()
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("盈利交易笔数", f"{len(profits)} 笔")
            p2.metric("平均获利", f"${profits['Gain'].mean()/1e4:,.0f}k")
            p3.metric("最大获利", f"${profits['Gain'].max()/1e4:,.0f}k")
            p4.metric("平均年化回报", f"{avg_ann:.1f}% p.a.", f"Top: {max_ann:.1f}%")
        else:
            st.info("暂无盈利交易")

        # 5.3 风险与亏损
        st.markdown("###### 3. 风险与亏损 (亏损交易)")
        total_resale = len(resale_df)
        loss_count = len(losses)
        loss_rate = (loss_count / total_resale) * 100 if total_resale > 0 else 0
        
        recent = resale_df[resale_df['Sale Date'] > (datetime.now() - timedelta(days=365*5))]
        recent_total = len(recent)
        recent_losses = len(recent[recent['Gain'] <= 0]) if recent_total > 0 else 0
        recent_loss_rate = (recent_losses / recent_total) * 100 if recent_total > 0 else 0

        l1, l2, l3, l4 = st.columns(4)
        l1.metric("亏损交易笔数", f"{loss_count} 笔", f"占比 {loss_rate:.1f}%", delta_color="inverse")
        l2.metric("近5年亏损占比", f"{recent_loss_rate:.1f}%", delta=f"{recent_loss_rate - loss_rate:.1f}% vs Hist", delta_color="inverse")
        
        if not losses.empty:
            l3.metric("平均亏损", f"-${abs(losses['Gain'].mean())/1e4:,.0f}k", delta_color="inverse")
            l4.metric("最大亏损", f"-${abs(losses['Gain'].min())/1e4:,.0f}k", delta_color="inverse")
        else:
            l3.metric("平均亏损", "-")
            l4.metric("最大亏损", "-")

        # 5.4 详情 Breakdown
        st.markdown("###### 4. 详细表现 (Breakdown)")
        tab_type, tab_blk = st.tabs(["按户型 (By Type)", "按楼栋 (By Block)"])
        
        with tab_type:
            if cat_col:
                sum_type = resale_df.groupby(cat_col).agg({
                    'Gain': ['count', 'mean', 'max', 'min'],
                    'Annualized': 'mean',
                    'Hold_Years': 'mean'
                }).reset_index()
                sum_type.columns = ['Type', 'Count', 'Avg Gain', 'Max Gain', 'Min Gain', 'Avg Ann%', 'Avg Hold']
                # 🟢 修正：hide_index=True 去除序列号列
                st.dataframe(sum_type.style.format({'Avg Gain':"${:,.0f}", 'Max Gain':"${:,.0f}", 'Min Gain':"${:,.0f}", 'Avg Ann%':"{:.1f}%", 'Avg Hold':"{:.1f} Yrs"}), use_container_width=True, hide_index=True)
            else: st.info("无户型信息")

        with tab_blk:
            sum_blk = resale_df.groupby('BLK').agg({
                'Gain': ['count', 'mean', 'max', 'min'],
                'Annualized': 'mean',
                'Hold_Years': 'mean'
            }).reset_index()
            sum_blk.columns = ['Block', 'Count', 'Avg Gain', 'Max Gain', 'Min Gain', 'Avg Ann%', 'Avg Hold']
            # 🟢 修正：hide_index=True 去除序列号列
            st.dataframe(sum_blk.style.format({'Avg Gain':"${:,.0f}", 'Max Gain':"${:,.0f}", 'Min Gain':"${:,.0f}", 'Avg Ann%':"{:.1f}%", 'Avg Hold':"{:.1f} Yrs"}), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.caption("ℹ️ **说明**: 持有<30天数据已剔除；持有<6个月不计年化回报。")
