import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import re

# --- 辅助：统一数据清洗 ---
def clean_and_prepare_data(df_raw):
    """
    统一处理列名映射和缺失值，确保后续逻辑使用的字段都存在。
    """
    df = df_raw.copy()
    
    # 1. 列名映射字典 (新增 Bedroom Type)
    rename_map = {
        'Transacted Price ($)': 'Sale Price',
        'Area (SQFT)': 'Area (sqft)',
        'Unit Price ($ psf)': 'Unit Price ($ psf)',
        'Unit Price ($ psm)': 'Unit Price ($ psm)',
        'Sale Date': 'Sale Date',
        'Bedroom Type': 'Type',   # <--- 核心修复：精准匹配您的数据列名
        'No. of Bedroom': 'Type', # 兼容旧格式
        'Property Type': 'Type'   # 备选
    }
    df.rename(columns=rename_map, inplace=True)
    
    # 2. 确保核心列存在
    if 'Type' not in df.columns:
        df['Type'] = "N/A"
        
    if 'Sale Date' in df.columns:
        df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')

    # 3. 补全尺价
    if 'Unit Price ($ psf)' not in df.columns:
        if 'Sale Price' in df.columns and 'Area (sqft)' in df.columns:
            df['Unit Price ($ psf)'] = df['Sale Price'] / df['Area (sqft)']
        else:
            df['Unit Price ($ psf)'] = 0
            
    return df

# --- 辅助：格式化单元号 ---
def format_unit(floor, stack):
    try:
        f_num = int(float(floor))
        s_str = str(stack)
        s_fmt = s_str.zfill(2) if s_str.isdigit() else s_str
        return f"#{f_num:02d}-{s_fmt}"
    except:
        return f"#{floor}-{stack}"

# --- 核心估值逻辑 ---
def calculate_avm(df, target_blk, target_floor, target_stack):
    # 1. 寻找同类户型
    maisonette_blks = ['10J', '10K', '10L', '10M']
    is_maisonette = target_blk in maisonette_blks
    
    if is_maisonette:
        comps = df[df['BLK'].isin(maisonette_blks)].copy()
        type_tag = "Maisonette (复式)"
    else:
        comps = df[~df['BLK'].isin(maisonette_blks)].copy()
        type_tag = "Apartment (平层)"
    
    # 2. 时间权重
    limit_date = datetime.now() - pd.DateOffset(months=18)
    recent_comps = comps[comps['Sale Date'] >= limit_date].copy()
    
    if recent_comps.empty:
        limit_date = datetime.now() - pd.DateOffset(months=36)
        recent_comps = comps[comps['Sale Date'] >= limit_date].copy()
    
    if recent_comps.empty:
        return None, None, type_tag, pd.DataFrame(), 0

    # 3. 楼层调整
    recent_comps['Floor_Num'] = pd.to_numeric(recent_comps['Floor'], errors='coerce').fillna(1)
    
    # Target PSF = Comp PSF * (1 + diff * 0.5%)
    recent_comps['Adj_PSF'] = recent_comps.apply(
        lambda row: row['Unit Price ($ psf)'] * (1 + (target_floor - row['Floor_Num']) * 0.005), 
        axis=1
    )
    
    # 4. 加权平均
    recent_comps['Days_Diff'] = (datetime.now() - recent_comps['Sale Date']).dt.days
    recent_comps['Weight'] = 1 / (recent_comps['Days_Diff'] + 30)
    
    weighted_psf = (recent_comps['Adj_PSF'] * recent_comps['Weight']).sum() / recent_comps['Weight'].sum()
    
    est_psf = weighted_psf
    
    # 寻找本单位面积
    this_stack_tx = df[(df['BLK'] == target_blk) & (df['Stack'] == target_stack)]
    if not this_stack_tx.empty:
        est_area = this_stack_tx.iloc[0]['Area (sqft)']
    else:
        est_area = recent_comps['Area (sqft)'].median()
        
    est_price = est_psf * est_area
    
    return est_price, est_psf, type_tag, recent_comps, est_area

# --- 渲染仪表盘 ---
def render_gauge(est_psf, min_psf, max_psf, font_size=12):
    if min_psf == max_psf:
        min_psf = est_psf * 0.8
        max_psf = est_psf * 1.2
        
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = est_psf,
        number = {'suffix': " psf", 'font': {'size': font_size * 2}}, 
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "预估尺价 (Estimated PSF)", 'font': {'size': font_size + 2, 'color': "gray"}},
        gauge = {
            'axis': {'range': [min_psf*0.9, max_psf*1.1], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "#2563eb"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [min_psf, max_psf], 'color': "#e0f2fe"},
                {'range': [min_psf*0.9, min_psf], 'color': "#fef2f2"},
                {'range': [max_psf, max_psf*1.1], 'color': "#fef2f2"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': est_psf
            }
        }
    ))
    fig.update_layout(
        height=250, 
        margin=dict(l=30, r=30, t=50, b=50),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'family': "Arial", 'size': font_size}
    )
    return fig

# --- 主渲染函数 ---
def render(df_raw, project_name="Project", chart_font_size=12):
    st.subheader("🤖 智能估值 (AVM)")

    # 1. 接收参数
    target = st.session_state.get('avm_target', None)
    
    if not target:
        st.info("👈 请先在 **楼宇透视 (Tab 2)** 点击任意单位，即可在此查看估值详情。")
        return

    blk, floor, stack = target['blk'], target['floor'], target['stack']

    # 2. 全局数据清洗
    df = clean_and_prepare_data(df_raw)
    
    # 3. 计算估值
    est_price, est_psf, type_tag, comps, area = calculate_avm(df, blk, floor, stack)
    
    if est_price is None:
        st.error(f"数据不足，无法评估 {blk} #{floor}-{stack}")
        return

    # 4. 顶部概览卡片
    st.markdown(f"""
    <div style="background-color:#f8fafc; padding:15px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
        <h3 style="margin:0; color:#1e293b;">{blk} #{int(floor):02d}-{stack}</h3>
        <p style="margin:5px 0 0 0; color:#64748b; font-size:14px;">
            {type_tag} | {int(area):,} sqft | 楼层: {floor}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 5. 估值核心展示
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        st.metric(
            label="预估总价 (Est. Price)",
            value=f"${est_price/1e6:,.2f}M",
            delta=None
        )
        st.caption(f"基于 {len(comps)} 笔近期参考交易")
        
        low_bound = est_price * 0.95
        high_bound = est_price * 1.05
        st.markdown(f"""
        <div style="margin-top:10px; padding:10px; background:#eff6ff; border-radius:4px; font-size:13px; color:#1e40af;">
            <strong>合理区间:</strong><br>
            ${low_bound/1e6:.2f}M - ${high_bound/1e6:.2f}M
        </div>
        """, unsafe_allow_html=True)

    with c2:
        if not comps.empty:
            min_p = comps['Unit Price ($ psf)'].min()
            max_p = comps['Unit Price ($ psf)'].max()
            st.plotly_chart(render_gauge(est_psf, min_p, max_p, chart_font_size), use_container_width=True)

    st.divider()

    # 6. 本单位历史 (按时间倒序)
    st.markdown("#### 📜 本单位历史 (Unit History)")
    this_unit_hist = df[(df['BLK'] == blk) & (df['Stack'] == stack) & (pd.to_numeric(df['Floor'], errors='coerce') == floor)].copy()
    
    if not this_unit_hist.empty:
        this_unit_hist = this_unit_hist.sort_values('Sale Date', ascending=False)
        
        display_hist = this_unit_hist[['Sale Date', 'Sale Price', 'Unit Price ($ psf)', 'Type']].copy()
        display_hist['Sale Date'] = display_hist['Sale Date'].dt.strftime('%Y-%m-%d')
        display_hist['Sale Price'] = display_hist['Sale Price'].apply(lambda x: f"${x:,.0f}")
        display_hist['Unit Price ($ psf)'] = display_hist['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}")
        
        st.dataframe(
            display_hist,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sale Date": "交易日期",
                "Sale Price": "成交价",
                "Unit Price ($ psf)": "尺价 (psf)",
                "Type": "户型"
            }
        )
    else:
        st.caption("该单位在记录周期内无历史交易。")

    st.divider()

    # 7. 参考交易 (Surrounding Reference)
    st.markdown("#### 🏘️ 参考交易 (Comparable Transactions)")
    
    comps = comps.sort_values('Weight', ascending=False).head(10)
    
    comp_display = comps[['Sale Date', 'BLK', 'Floor', 'Stack', 'Type', 'Area (sqft)', 'Sale Price', 'Unit Price ($ psf)']].copy()
    comp_display['Sale Date'] = comp_display['Sale Date'].dt.strftime('%Y-%m-%d')
    comp_display['Sale Price'] = comp_display['Sale Price'].apply(lambda x: f"${x/1e6:.2f}M")
    comp_display['Unit Price ($ psf)'] = comp_display['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}")
    
    # 使用安全的格式化拼接
    comp_display['Unit'] = comp_display.apply(
        lambda row: f"{row['BLK']} {format_unit(row['Floor'], row['Stack'])}", 
        axis=1
    )
    
    final_cols = ['Sale Date', 'Unit', 'Type', 'Area (sqft)', 'Sale Price', 'Unit Price ($ psf)']
    
    st.dataframe(
        comp_display[final_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Sale Date": "日期",
            "Unit": "单位",
            "Type": "户型",
            "Area (sqft)": "面积",
            "Sale Price": "总价",
            "Unit Price ($ psf)": "尺价"
        }
    )
