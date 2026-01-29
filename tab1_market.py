# tab1_overview.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

def process_resale_data(df):
    """
    专门用于计算转售逻辑的函数
    """
    # 1. 构建唯一ID并排序
    # 确保有必要的列
    req_cols = ['BLK', 'Stack', 'Floor_Num', 'Sale Date', 'Sale Price', 'Sale PSF']
    if not all(c in df.columns for c in req_cols):
        return pd.DataFrame()

    # 排序：按单位 -> 按时间
    df_sorted = df.sort_values(['BLK', 'Stack', 'Floor_Num', 'Sale Date'])
    
    # 2. 生成 Unit_ID
    df_sorted['Unit_ID'] = df_sorted['BLK'].astype(str) + "-" + df_sorted['Stack'].astype(str) + "-" + df_sorted['Floor_Num'].astype(int).astype(str)
    
    # 3. 计算差异 (当前交易 - 上次交易)
    # GroupBy 确保只在同一个 Unit_ID 内部 shift
    df_sorted['Prev_Price'] = df_sorted.groupby('Unit_ID')['Sale Price'].shift(1)
    df_sorted['Prev_Date'] = df_sorted.groupby('Unit_ID')['Sale Date'].shift(1)
    
    # 4. 筛选出也是"转售"的记录 (必须有上一次价格)
    resales = df_sorted.dropna(subset=['Prev_Price']).copy()
    
    if resales.empty:
        return pd.DataFrame()

    # 5. 计算核心指标
    resales['Gain'] = resales['Sale Price'] - resales['Prev_Price']
    resales['Gain_Pct'] = (resales['Gain'] / resales['Prev_Price']) * 100
    resales['Hold_Days'] = (resales['Sale Date'] - resales['Prev_Date']).dt.days
    resales['Hold_Years'] = resales['Hold_Days'] / 365.25
    
    # 年化回报公式: (现价/原价)^(1/年) - 1
    # 避免持有时间极短导致除零，设置最小 0.01 年
    resales['Annualized'] = (
        (resales['Sale Price'] / resales['Prev_Price']) ** (1 / resales['Hold_Years'].apply(lambda x: max(x, 0.01))) - 1
    ) * 100

    return resales

def render(df):
    st.subheader("📊 项目全景概览 (Project Overview)")

    # ================= 1. 数据预处理 =================
    # 确保日期格式
    if 'Sale Date' in df.columns:
        df['Sale Date'] = pd.to_datetime(df['Sale Date'])
        df['Year'] = df['Sale Date'].dt.year
    else:
        st.error("数据缺少 'Sale Date' 列")
        return

    # 计算转售数据
    resale_df = process_resale_data(df)

    # ================= 2. 宏观 KPI (Row 1) =================
    st.markdown("##### 🏗️ 基础数据")
    k1, k2, k3, k4 = st.columns(4)
    
    # 单位总数 (去重后的 Unit ID)
    if 'Floor_Num' in df.columns and 'Stack' in df.columns:
        df['Temp_ID'] = df['BLK'].astype(str) + "-" + df['Stack'].astype(str) + "-" + df['Floor_Num'].astype(str)
        total_units = df['Temp_ID'].nunique()
    else:
        total_units = len(df) # 降级方案

    # 户型总数
    cat_col = next((c for c in ['Bedroom Type', 'Category', 'Type'] if c in df.columns), None)
    total_types = df[cat_col].nunique() if cat_col else 0

    # 交易时间范围
    min_date = df['Sale Date'].min().strftime('%Y-%m-%d')
    max_date = df['Sale Date'].max().strftime('%Y-%m-%d')

    k1.metric("已成交单位总数", f"{total_units:,}")
    k2.metric("户型种类", total_types)
    k3.metric("最早交易", min_date)
    k4.metric("最晚交易", max_date)

    st.markdown("---")

    # ================= 3. 历年交易趋势 (Row 2) =================
    st.markdown("##### 📈 历年量价趋势")
    
    # 按年聚合
    yearly = df.groupby('Year').agg({
        'Sale Price': ['count', 'sum'],
        'Sale PSF': 'mean'
    }).reset_index()
    yearly.columns = ['Year', 'Volume', 'Total_Value', 'Avg_PSF']

    # 创建双轴图表
    fig = go.Figure()

    # 柱状图：销量
    fig.add_trace(go.Bar(
        x=yearly['Year'], y=yearly['Volume'],
        name='成交量 (Volume)',
        marker_color='#dbeafe',
        yaxis='y'
    ))

    # 线图：PSF
    fig.add_trace(go.Scatter(
        x=yearly['Year'], y=yearly['Avg_PSF'],
        name='平均尺价 (PSF)',
        mode='lines+markers',
        line=dict(color='#1d4ed8', width=3),
        yaxis='y2'
    ))

    fig.update_layout(
        yaxis=dict(title='成交量 (单位: 套)', side='left', showgrid=False),
        yaxis2=dict(title='平均尺价 ($PSF)', side='right', overlaying='y', showgrid=True),
        hovermode='x unified',
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=20, r=20, t=40, b=20),
        height=350
    )
    st.plotly_chart(fig, use_container_width=True)

    # ================= 4. 活跃度分析 (Row 3) =================
    st.markdown("##### 🔥 市场活跃度 (总成交 vs 平均价)")
    
    # 辅助函数：获取最活跃的 Top 1
    def get_top_active(group_col):
        if group_col not in df.columns: return None, 0, 0
        stats = df.groupby(group_col).agg({'Sale Price': 'count', 'Sale PSF': 'mean'}).reset_index()
        stats.columns = [group_col, 'Count', 'Avg_PSF']
        top = stats.sort_values('Count', ascending=False).iloc[0]
        return top[group_col], top['Count'], top['Avg_PSF']

    a1, a2, a3, a4 = st.columns(4)

    # 楼栋
    blk_name, blk_count, blk_psf = get_top_active('BLK')
    a1.info(f"**最热楼栋: {blk_name}**\n\n成交: {blk_count}套\n均价: ${blk_psf:,.0f} psf")

    # Stack
    stack_name, stack_count, stack_psf = get_top_active('Stack')
    a2.info(f"**最热 Stack: {stack_name}**\n\n成交: {stack_count}套\n均价: ${stack_psf:,.0f} psf")

    # 楼层 (简单分组: 低/中/高)
    if 'Floor_Num' in df.columns:
        df['Floor_Zone'] = df['Floor_Num'].apply(lambda x: 'Low (1-05)' if x<=5 else ('Mid (06-15)' if x<=15 else 'High (16+)'))
        flr_name, flr_count, flr_psf = get_top_active('Floor_Zone')
        a3.info(f"**最热楼层段: {flr_name}**\n\n成交: {flr_count}套\n均价: ${flr_psf:,.0f} psf")
    else:
        a3.info("无楼层数据")

    # 户型
    if cat_col:
        cat_name, cat_count, cat_psf = get_top_active(cat_col)
        a4.info(f"**最热户型: {cat_name}**\n\n成交: {cat_count}套\n均价: ${cat_psf:,.0f} psf")
    else:
        a4.info("无户型数据")

    st.markdown("---")

    # ================= 5. 转售与投资回报分析 (Row 4 - 核心) =================
    st.subheader("💰 转售与投资回报分析 (Resale Performance)")

    if resale_df.empty:
        st.warning("数据集中未检测到足够的转售记录（需要同一单位至少有2次交易），无法计算增值数据。")
    else:
        # --- A. 持有时间与频率 ---
        st.markdown("###### 1. 持有与转售频率")
        
        # 总体转售次数
        # 统计每个单位出现的次数 (Count >= 2 才算有转售)
        unit_counts = df['Temp_ID'].value_counts()
        unit_counts = unit_counts[unit_counts >= 2] # 只看交易过至少2次的
        
        if not unit_counts.empty:
            max_resale = unit_counts.max()
            avg_resale = unit_counts.mean()
        else:
            max_resale = 0; avg_resale = 0
            
        r1, r2, r3 = st.columns(3)
        r1.metric("平均持有时间", f"{resale_df['Hold_Years'].mean():.1f} 年", help="所有转售交易的平均持有时长")
        r2.metric("最长持有 / 最短持有", f"{resale_df['Hold_Years'].max():.1f} 年 / {resale_df['Hold_Years'].min():.1f} 年")
        r3.metric("单位最大转售次数", f"{max_resale} 次", help="同一个单位历史上被交易过的最多次数")

        # --- B. 增值与亏损 (Gains & Losses) ---
        st.markdown("###### 2. 增值表现 (Profit & Loss)")
        
        # 分离赚钱和亏钱的交易
        profits = resale_df[resale_df['Gain'] > 0]
        losses = resale_df[resale_df['Gain'] <= 0]
        
        # 总体亏损占比
        loss_ratio = (len(losses) / len(resale_df)) * 100
        
        # 最近5年亏损占比
        cutoff_date = datetime.now() - timedelta(days=365*5)
        recent_resales = resale_df[resale_df['Sale Date'] >= cutoff_date]
        if not recent_resales.empty:
            recent_losses = recent_resales[recent_resales['Gain'] <= 0]
            recent_loss_ratio = (len(recent_losses) / len(recent_resales)) * 100
        else:
            recent_loss_ratio = 0

        # 指标展示
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("平均获利 (Avg Gain)", f"${profits['Gain'].mean()/1e4:,.0f}k", f"{profits['Annualized'].mean():.1f}% p.a.")
        g2.metric("最大获利 (Max Gain)", f"${profits['Gain'].max()/1e4:,.0f}k", f"Top: {profits['Annualized'].max():.1f}% p.a.")
        
        g3.metric("平均亏损 (Avg Loss)", f"-${abs(losses['Gain'].mean())/1e4:,.0f}k" if not losses.empty else "-", delta_color="inverse")
        g4.metric("最大亏损 (Max Loss)", f"-${abs(losses['Gain'].min())/1e4:,.0f}k" if not losses.empty else "-", delta_color="inverse")

        # --- C. 风险仪表盘 ---
        st.markdown("###### 3. 风险监控 (Loss Ratio)")
        l1, l2 = st.columns(2)
        
        l1.metric("历史总亏损交易占比", f"{loss_ratio:.1f}%", help="历史上所有转售中，亏损离场的比例")
        l2.metric("近5年亏损交易占比", f"{recent_loss_ratio:.1f}%", delta=f"{recent_loss_ratio - loss_ratio:.1f}% vs History", delta_color="inverse", help="最近5年的亏损比例，反映近期市场风险")

        # --- D. 户型详细分析 (Table) ---
        if cat_col:
            st.markdown(f"###### 4. 不同{cat_col}的转售表现")
            
            # 按户型聚合计算
            cat_stats = resale_df.groupby(cat_col).agg({
                'Gain': ['count', 'mean', 'max', 'min'],
                'Annualized': 'mean',
                'Hold_Years': 'mean'
            }).reset_index()
            
            # 展平列名
            cat_stats.columns = ['Type', 'Count', 'Avg Gain ($)', 'Max Gain ($)', 'Min Gain ($)', 'Avg Ann. Return (%)', 'Avg Hold (Yrs)']
            
            # 格式化显示
            st.dataframe(
                cat_stats.style.format({
                    'Avg Gain ($)': "${:,.0f}",
                    'Max Gain ($)': "${:,.0f}",
                    'Min Gain ($)': "${:,.0f}",
                    'Avg Ann. Return (%)': "{:.2f}%",
                    'Avg Hold (Yrs)': "{:.1f}"
                }).background_gradient(subset=['Avg Ann. Return (%)'], cmap='Greens'),
                use_container_width=True
            )
