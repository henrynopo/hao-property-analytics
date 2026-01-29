# tab4_history.py
import streamlit as st
import plotly.express as px
import pandas as pd

# 🟢 关键修复：给 chart_font_size 加上默认值 = 12
# 这样 app.py 调用 render(df) 时就不会报 TypeError 了
def render(df, chart_font_size=12):
    st.subheader("📈 市场雷达")
    
    # 1. 销量与价格趋势 (必须有 Sale Date)
    if 'Sale Date' in df.columns and 'Sale PSF' in df.columns:
        df['Year'] = df['Sale Date'].dt.year
        
        # 按年统计
        trend = df.groupby('Year').agg({
            'Sale PSF': 'mean',
            'Sale Price': 'count'
        }).rename(columns={'Sale Price': 'Volume', 'Sale PSF': 'Avg PSF'}).reset_index()
        
        fig = px.bar(trend, x='Year', y='Volume', title='年度销量 (Volume) vs 均价 (PSF)', color_discrete_sequence=['#cccccc'])
        fig.add_scatter(x=trend['Year'], y=trend['Avg PSF'], mode='lines+markers', name='Avg PSF', yaxis='y2', line=dict(color='red', width=3))
        
        fig.update_layout(
            yaxis2=dict(title='PSF ($)', overlaying='y', side='right'),
            yaxis=dict(title='Volume (Units)'),
            hovermode='x unified',
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("缺少时间或价格数据，无法绘制趋势图")

    # 2. 高级图表区
    c1, c2 = st.columns(2)
    
    with c1:
        # 捡漏分析 (PSF Boxplot)
        # 动态寻找分类列，防止报错
        cat_col = next((c for c in ['Bedroom Type', 'Bedroom_Type', 'Category', 'Type'] if c in df.columns), None)
        
        if cat_col and 'Sale PSF' in df.columns:
            fig_box = px.box(df, x=cat_col, y='Sale PSF', title='各户型尺价分布', color=cat_col)
            st.plotly_chart(fig_box, use_container_width=True)
        else:
            if 'Sale PSF' in df.columns:
                st.info("未找到户型分类列，跳过箱线图")

    with c2:
        # 买家分析 (如果有 Sale Type 或 Purchaser Type)
        # 动态寻找列，防止报错
        type_col = next((c for c in ['Type of Sale', 'Sale Type', 'Purchaser Type'] if c in df.columns), None)
        
        if type_col:
            pie_data = df[type_col].value_counts().reset_index()
            pie_data.columns = ['Type', 'Count']
            fig_pie = px.pie(pie_data, names='Type', values='Count', title='交易类型/买家构成', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("(数据源中未包含买家类型信息)")
            
    # 3. 原始数据查询
    with st.expander("🔎 查看原始数据"):
        st.dataframe(df.sort_values('Sale Date', ascending=False), use_container_width=True)
