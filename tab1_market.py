import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta
from utils import calculate_resale_metrics, format_currency

def render(df, chart_color, chart_font_size, inventory_map):
    st.subheader("1. 基础数据概览")
    c1, c2, c3, c4 = st.columns(4)
    total_inv = sum(inventory_map.values())
    c1.metric("📦 单位总数 (Est.)", f"{total_inv} 户")
    c2.metric("📐 户型总数", f"{df['Category'].nunique()} 类")
    c3.metric("📅 交易周期", f"{df['Sale Date'].min():%Y-%m} ~ {df['Sale Date'].max():%Y-%m}")
    total_vol = df['Sale Price'].sum()
    c4.metric("💰 总成交额", f"${total_vol/1e9:.2f}B" if total_vol > 1e9 else f"${total_vol/1e6:.1f}M")

    st.markdown("---")
    st.subheader("2. 历年交易趋势")
    yearly = df.groupby('Sale Year').agg({'Sale Price': 'sum', 'BLK': 'count'}).rename(columns={'BLK': 'Count'})
    
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        fig_vol = px.bar(yearly, x=yearly.index, y='Count', title="历年成交量 (宗)", color_discrete_sequence=[chart_color])
        fig_vol.update_layout(font=dict(size=chart_font_size))
        st.plotly_chart(fig_vol, use_container_width=True)
    with c_chart2:
        fig_val = px.line(yearly, x=yearly.index, y='Sale Price', title="历年成交金额 ($)", markers=True)
        fig_val.update_layout(font=dict(size=chart_font_size))
        st.plotly_chart(fig_val, use_container_width=True)

    st.markdown("---")
    st.subheader("3. 投资回报深度分析 (Resale Analysis)")
    df_resale = calculate_resale_metrics(df)
    
    if not df_resale.empty:
        unit_counts = df['Unit_ID'].value_counts()
        avg_turns = unit_counts.mean() - 1
        kp1, kp2, kp3, kp4 = st.columns(4)
        kp1.metric("🔄 平均转售次数", f"{max(0, avg_turns):.2f} 次")
        kp2.metric("⏳ 平均持有时间", f"{df_resale['Hold_Years'].mean():.1f} 年")
        profit_count = len(df_resale[df_resale['Gain'] > 0])
        kp3.metric("💸 盈利交易占比", f"{(profit_count/len(df_resale)*100):.1f}%", f"{profit_count} 宗")
        
        recent5y = df_resale[df_resale['Sale Date'] > (datetime.now() - timedelta(days=365*5))]
        loss_5y = len(recent5y[recent5y['Gain'] < 0]) if not recent5y.empty else 0
        den = len(recent5y) if not recent5y.empty else 1
        kp4.metric("📉 近5年亏损占比", f"{(loss_5y/den*100):.1f}%" if not recent5y.empty else "无数据")

        st.write("##### 📊 各户型投资表现")
        cat_stats = df_resale.groupby('Category').agg({
            'Hold_Years': ['mean', 'min', 'max'],
            'Gain': ['mean', 'min', 'max'],
            'Annualized': ['mean']
        }).reset_index()
        cat_stats.columns = ['Category', 'Avg Hold', 'Min Hold', 'Max Hold', 'Avg Gain', 'Max Loss/Min Gain', 'Max Gain', 'Avg Annualized']
        
        cat_stats['Avg Gain'] = cat_stats['Avg Gain'].apply(format_currency)
        cat_stats['Max Loss/Min Gain'] = cat_stats['Max Loss/Min Gain'].apply(format_currency)
        cat_stats['Max Gain'] = cat_stats['Max Gain'].apply(format_currency)
        
        st.dataframe(cat_stats, use_container_width=True, column_config={
            "Avg Hold": st.column_config.NumberColumn("平均持有 (年)", format="%.1f yrs"),
            "Min Hold": st.column_config.NumberColumn("最短", format="%.1f"),
            "Max Hold": st.column_config.NumberColumn("最长", format="%.1f"),
            "Avg Annualized": st.column_config.NumberColumn("平均年化", format="%.2%"),
        })
    else:
        st.info("暂未发现转售记录。")
