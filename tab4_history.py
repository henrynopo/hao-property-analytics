# tab4_market.py
import streamlit as st
import plotly.express as px
import pandas as pd

def render(df, chart_font_size):
    st.subheader("📈 市场雷达")
    
    if 'Sale Date' in df.columns and 'Sale PSF' in df.columns:
        df['Year'] = df['Sale Date'].dt.year
        trend = df.groupby('Year').agg({'Sale PSF':'mean', 'Sale Price':'count'}).reset_index()
        trend.columns = ['Year', 'Avg PSF', 'Volume']
        
        fig = px.bar(trend, x='Year', y='Volume', title='量价趋势', color_discrete_sequence=['#ddd'])
        fig.add_scatter(x=trend['Year'], y=trend['Avg PSF'], mode='lines+markers', name='PSF', yaxis='y2', line=dict(color='red'))
        fig.update_layout(yaxis2=dict(overlaying='y', side='right'), hovermode='x unified', height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    # 安全的饼图
    c1, c2 = st.columns(2)
    with c1:
        # 捡漏图
        cat_col = next((c for c in ['Bedroom Type', 'Category', 'Type'] if c in df.columns), None)
        if cat_col and 'Sale PSF' in df.columns:
            st.plotly_chart(px.box(df, x=cat_col, y='Sale PSF', title='户型价格分布', color=cat_col), use_container_width=True)
            
    with c2:
        # 买家图 (只在列存在时画)
        type_col = next((c for c in ['Type of Sale', 'Sale Type'] if c in df.columns), None)
        if type_col:
            st.plotly_chart(px.pie(df, names=type_col, title='交易类型'), use_container_width=True)
        else:
            st.info("无买家类型数据，跳过饼图")
