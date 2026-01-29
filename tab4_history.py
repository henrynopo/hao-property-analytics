# 文件名: tab4_history.py
import streamlit as st
import plotly.express as px
import pandas as pd

# 🟢 关键：chart_font_size 必须有默认值
def render(df, chart_font_size=12):
    st.subheader("📈 市场雷达")
    
    if 'Sale Date' not in df.columns or 'Sale PSF' not in df.columns:
        st.warning("数据不足"); return

    # 1. 量价趋势
    df['Year'] = df['Sale Date'].dt.year
    trend = df.groupby('Year').agg({'Sale PSF':'mean', 'Sale Price':'count'}).reset_index()
    trend.columns = ['Year', 'Avg PSF', 'Volume']
    
    fig = px.bar(trend, x='Year', y='Volume', title='量价趋势', color_discrete_sequence=['#ddd'])
    fig.add_scatter(x=trend['Year'], y=trend['Avg PSF'], mode='lines+markers', name='PSF', yaxis='y2', line=dict(color='red'))
    fig.update_layout(yaxis2=dict(overlaying='y', side='right'), hovermode='x unified', height=400)
    st.plotly_chart(fig, use_container_width=True)

    # 2. 饼图与箱线图 (防崩版)
    c1, c2 = st.columns(2)
    with c1:
        cat_col = next((c for c in ['Bedroom Type', 'Category', 'Type'] if c in df.columns), None)
        if cat_col: st.plotly_chart(px.box(df, x=cat_col, y='Sale PSF', title='户型分布', color=cat_col), use_container_width=True)
    with c2:
        typ_col = next((c for c in ['Type of Sale', 'Sale Type', 'Purchaser Type'] if c in df.columns), None)
        if typ_col: st.plotly_chart(px.pie(df, names=typ_col, title='交易类型'), use_container_width=True)
