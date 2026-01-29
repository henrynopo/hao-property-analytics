# 文件名: tab1_market.py (或 tab1_overview.py)
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 内部辅助函数：处理转售逻辑 ---
def _process_resale_data(df):
    required_cols = ['BLK', 'Stack', 'Floor_Num', 'Sale Date', 'Sale Price']
    # 检查列是否存在
    if not all(c in df.columns for c in required_cols):
        return pd.DataFrame()
    
    # 排序
    df_sorted = df.sort_values(['BLK', 'Stack', 'Floor_Num', 'Sale Date'])
    # 构建临时ID
    df_sorted['_uid'] = df_sorted['BLK'].astype(str) + "-" + df_sorted['Stack'].astype(str) + "-" + df_sorted['Floor_Num'].astype(str)
    
    # 计算差异
    df_sorted['Prev_Price'] = df_sorted.groupby('_uid')['Sale Price'].shift(1)
    df_sorted['Prev_Date'] = df_sorted.groupby('_uid')['Sale Date'].shift(1)
    
    # 提取转售记录
    resales = df_sorted.dropna(subset=['Prev_Price']).copy()
    if resales.empty: return pd.DataFrame()
    
    # 计算指标
    resales['Gain'] = resales['Sale Price'] - resales['Prev_Price']
    resales['Hold_Days'] = (resales['Sale Date'] - resales['Prev_Date']).dt.days
    resales['Hold_Years'] = resales['Hold_Days'] / 365.25
    # 年化 (防止除零)
    resales['Annualized'] = ((resales['Sale Price'] / resales['Prev_Price']) ** (1 / resales['Hold_Years'].apply(lambda x: max(x, 0.01))) - 1) * 100
    return resales

# --- 主渲染函数：参数必须匹配 app.py 的调用 ---
def render(df, chart_color='#1f77b4', chart_font_size=12, inventory_map=None):
    st.subheader("📊 项目全景概览 (Project Overview)")

    # 1. 基础清洗
    if 'Sale Date' not in df.columns:
        st.error("数据缺失 Sale Date"); return
    df['Sale Date'] = pd.to_datetime(df['Sale Date'])
    df['Year'] = df['Sale Date'].dt.year

    resale_df = _process_resale_data(df)

    # 2. 宏观 KPI
    st.markdown("##### 🏗️ 基础数据")
    k1, k2, k3, k4 = st.columns(4)
    
    # 计算逻辑
    total_units = df[['BLK', 'Stack', 'Floor_Num']].drop_duplicates().shape[0] if 'Floor_Num' in df.columns else len(df)
    
    # 动态寻找户型列
    cat_col = next((c for c in ['Bedroom Type', 'Category', 'Type'] if c in df.columns), None)
    total_types = df[cat_col].nunique() if cat_col else 0
    
    k1.metric("总单位数", f"{total_units:,}")
    k2.metric("户型总数", total_types)
    k3.metric("最早交易", df['Sale Date'].min().strftime('%Y-%m-%d'))
    k4.metric("最晚交易", df['Sale Date'].max().strftime('%Y-%m-%d'))

    st.markdown("---")

    # 3. 历年量价 (双轴图)
    st.markdown("##### 📈 历年量价趋势")
    yearly = df.groupby('Year').agg({'Sale Price': 'count', 'Sale PSF': 'mean'}).reset_index()
    yearly.columns = ['Year', 'Volume', 'Avg_PSF']

    fig = go.Figure()
    fig.add_trace(go.Bar(x=yearly['Year'], y=yearly['Volume'], name='成交量', marker_color='#dbeafe', yaxis='y'))
    fig.add_trace(go.Scatter(x=yearly['Year'], y=yearly['Avg_PSF'], name='平均尺价', mode='lines+markers', line=dict(color=chart_color, width=3), yaxis='y2'))
    fig.update_layout(
        yaxis=dict(title='成交量', side='left', showgrid=False),
        yaxis2=dict(title='尺价 ($PSF)', side='right', overlaying='y', showgrid=True),
        hovermode='x unified', height=350, margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    # 4. 活跃度矩阵
    st.markdown("##### 🔥 活跃度分析 (Most Active)")
    
    def get_top(col):
        if col not in df.columns: return "N/A", 0, 0
        stats = df.groupby(col).agg({'Sale Price':'count', 'Sale PSF':'mean'}).reset_index()
        top = stats.sort_values('Sale Price', ascending=False).iloc[0]
        return top[col], top['Sale Price'], top['Sale PSF']

    a1, a2, a3, a4 = st.columns(4)
    # 楼栋
    b_n, b_c, b_p = get_top('BLK')
    a1.info(f"**楼栋: {b_n}**\n\n{b_c}套 | ${b_p:,.0f} psf")
    # Stack
    s_n, s_c, s_p = get_top('Stack')
    a2.info(f"**Stack: {s_n}**\n\n{s_c}套 | ${s_p:,.0f} psf")
    # 楼层
    if 'Floor_Num' in df.columns:
        df['Floor_Zone'] = df['Floor_Num'].apply(lambda x: 'Low' if x<=5 else ('Mid' if x<=15 else 'High'))
        f_n, f_c, f_p = get_top('Floor_Zone')
        a3.info(f"**层段: {f_n}**\n\n{f_c}套 | ${f_p:,.0f} psf")
    else: a3.info("无楼层数据")
    # 户型
    if cat_col:
        c_n, c_c, c_p = get_top(cat_col)
        a4.info(f"**户型: {c_n}**\n\n{c_c}套 | ${c_p:,.0f} psf")
    else: a4.info("无户型数据")

    st.markdown("---")

    # 5. 转售深度分析
    st.subheader("💰 转售与回报 (Resale & Returns)")
    
    if resale_df.empty:
        st.warning("数据不足，无法计算转售增值信息（需要同一单位至少2次交易）。")
    else:
        # 5.1 持有统计
        st.markdown("###### 1. 持有表现")
        # 统计转售次数
        uid_counts = df.groupby(['BLK','Stack','Floor_Num']).size()
        uid_counts = uid_counts[uid_counts > 1] # 至少交易过2次才算有转售
        
        r1, r2, r3 = st.columns(3)
        r1.metric("平均持有时间", f"{resale_df['Hold_Years'].mean():.1f} 年")
        r2.metric("最长/最短持有", f"{resale_df['Hold_Years'].max():.1f} / {resale_df['Hold_Years'].min():.1f} 年")
        r3.metric("平均/最大转售次数", f"{uid_counts.mean():.1f} 次", f"Max: {uid_counts.max()} 次")

        # 5.2 盈亏统计
        st.markdown("###### 2. 盈亏概览")
        profits = resale_df[resale_df['Gain'] > 0]
        losses = resale_df[resale_df['Gain'] <= 0]
        
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("平均获利", f"${profits['Gain'].mean()/1e4:,.0f}k", f"{profits['Annualized'].mean():.1f}% p.a.")
        g2.metric("最大获利", f"${profits['Gain'].max()/1e4:,.0f}k", f"Top: {profits['Annualized'].max():.1f}% p.a.")
        g3.metric("平均亏损", f"-${abs(losses['Gain'].mean())/1e4:,.0f}k" if not losses.empty else "-", delta_color="inverse")
        g4.metric("最大亏损", f"-${abs(losses['Gain'].min())/1e4:,.0f}k" if not losses.empty else "-", delta_color="inverse")

        # 5.3 风险占比
        st.markdown("###### 3. 风险监控 (Loss Ratio)")
        curr_loss_rate = (len(losses)/len(resale_df))*100
        
        recent = resale_df[resale_df['Sale Date'] > (datetime.now() - timedelta(days=365*5))]
        if not recent.empty:
            recent_loss_rate = (len(recent[recent['Gain']<=0]) / len(recent)) * 100
        else: recent_loss_rate = 0
        
        l1, l2 = st.columns(2)
        l1.metric("历史总亏损率", f"{curr_loss_rate:.1f}%")
        l2.metric("近5年亏损率", f"{recent_loss_rate:.1f}%", delta=f"{recent_loss_ratio - curr_loss_rate:.1f}% vs Hist" if 'recent_loss_ratio' in locals() else None, delta_color="inverse")

        # 5.4 户型详情
        if cat_col:
            st.markdown(f"###### 4. 户型详情")
            summary = resale_df.groupby(cat_col).agg({
                'Gain': ['count', 'mean', 'max', 'min'],
                'Annualized': 'mean',
                'Hold_Years': 'mean'
            }).reset_index()
            summary.columns = ['Type', 'Count', 'Avg Gain', 'Max Gain', 'Min Gain', 'Avg Ann%', 'Avg Hold']
            st.dataframe(summary.style.format({'Avg Gain':"${:,.0f}", 'Max Gain':"${:,.0f}", 'Min Gain':"${:,.0f}", 'Avg Ann%':"{:.2f}%", 'Avg Hold':"{:.1f}"}), use_container_width=True)
