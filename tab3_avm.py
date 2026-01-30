import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import re

# --- 辅助：统一数据清洗 ---
def clean_and_prepare_data(df_raw):
    df = df_raw.copy()
    
    # 1. 列名映射 (新增 Tenure 等字段)
    rename_map = {
        'Transacted Price ($)': 'Sale Price',
        'Area (SQFT)': 'Area (sqft)',
        'Unit Price ($ psf)': 'Unit Price ($ psf)',
        'Unit Price ($ psm)': 'Unit Price ($ psm)',
        'Sale Date': 'Sale Date',
        'Bedroom Type': 'Type',   
        'No. of Bedroom': 'Type', 
        # 新增字段映射
        'Tenure': 'Tenure',
        'Lease Commencement Date': 'Tenure From', # 常见变体 1
        'Tenure Start Date': 'Tenure From',       # 常见变体 2
        'Property Type': 'Sub Type',              # 公寓分类
        'Building Type': 'Sub Type'               # 备选
    }
    df.rename(columns=rename_map, inplace=True)
    
    # 2. 补全缺失列 (防止报错)
    for col in ['Type', 'Tenure', 'Tenure From', 'Sub Type']:
        if col not in df.columns:
            df[col] = "-" # 默认显示横杠

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
    maisonette_blks = ['10J', '10K', '10L', '10M']
    is_maisonette = target_blk in maisonette_blks
    
    # 1. 筛选逻辑
    if is_maisonette:
        comps = df[df['BLK'].isin(maisonette_blks)].copy()
        # type_tag 已移除，不再需要
    else:
        comps = df[~df['BLK'].isin(maisonette_blks)].copy()
    
    # 2. 获取项目级信息 (Tenure, Sub Type 等)
    # 优先尝试从本单位的历史记录获取
    this_stack_tx = df[(df['BLK'] == target_blk) & (df['Stack'] == target_stack)]
    
    if not this_stack_tx.empty:
        est_area = this_stack_tx.iloc[0]['Area (sqft)']
        # 获取最新的属性信息
        latest_rec = this_stack_tx.sort_values('Sale Date', ascending=False).iloc[0]
        info_tenure = str(latest_rec.get('Tenure', '-'))
        info_from = str(latest_rec.get('Tenure From', '-'))
        info_subtype = str(latest_rec.get('Sub Type', '-'))
    else:
        # 如果本单位没交易，从 comps 里取众数 (最常见的值)
        est_area = recent_comps['Area (sqft)'].median() if 'recent_comps' in locals() else comps['Area (sqft)'].median()
        info_tenure = comps['Tenure'].mode()[0] if not comps['Tenure'].empty else '-'
        info_from = comps['Tenure From'].mode()[0] if not comps['Tenure From'].empty else '-'
        info_subtype = comps['Sub Type'].mode()[0] if not comps['Sub Type'].empty else '-'

    # 3. 时间权重
    limit_date = datetime.now() - pd.DateOffset(months=18)
    recent_comps = comps[comps['Sale Date'] >= limit_date].copy()
    
    if recent_comps.empty:
        limit_date = datetime.now() - pd.DateOffset(months=36)
        recent_comps = comps[comps['Sale Date'] >= limit_date].copy()
    
    if recent_comps.empty:
        return None, None, {}, pd.DataFrame(), 0

    # 4. 估值计算
    recent_comps['Floor_Num'] = pd.to_numeric(recent_comps['Floor'], errors='coerce').fillna(1)
    recent_comps['Adj_PSF'] = recent_comps.apply(
        lambda row: row['Unit Price ($ psf)'] * (1 + (target_floor - row['Floor_Num']) * 0.005), 
        axis=1
    )
    
    recent_comps['Days_Diff'] = (datetime.now() - recent_comps['Sale Date']).dt.days
    recent_comps['Weight'] = 1 / (recent_comps['Days_Diff'] + 30)
    
    weighted_psf = (recent_comps['Adj_PSF'] * recent_comps['Weight']).sum() / recent_comps['Weight'].sum()
    est_psf = weighted_psf
    est_price = est_psf * est_area
    
    # 打包附加信息
    extra_info = {
        'tenure': info_tenure,
        'from': info_from,
        'subtype': info_subtype
    }
    
    return est_price, est_psf, extra_info, recent_comps, est_area

# --- 渲染仪表盘 (保持 V159 微缩版) ---
def render_gauge(est_psf, min_psf, max_psf, font_size=12):
    if min_psf == max_psf:
        min_psf = est_psf * 0.8
        max_psf = est_psf * 1.2
        
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = est_psf,
        number = {'suffix': " psf", 'font': {'size': 20}},
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "预估尺价 (Estimated PSF)", 'font': {'size': 14, 'color': "gray"}},
        gauge = {
            'axis': {'range': [min_psf*0.9, max_psf*1.1], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'thickness': 0}, 
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [min_psf, max_psf], 'color': "#2563eb"}, 
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
        height=180, 
        margin=dict(l=25, r=25, t=30, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'family': "Arial", 'size': 12}
    )
    return fig

# --- 主渲染函数 ---
def render(df_raw, project_name="Project", chart_font_size=12):
    st.subheader("🤖 智能估值 (AVM)")

    target = st.session_state.get('avm_target', None)
    if not target:
        st.info("👈 请先在 **楼宇透视 (Tab 2)** 点击任意单位，即可在此查看估值详情。")
        return

    blk, floor, stack = target['blk'], target['floor'], target['stack']

    df = clean_and_prepare_data(df_raw)
    
    # 调用估值
    # 注意：返回值结构有变化，新增了 extra_info
    est_price, est_psf, extra_info, comps, area = calculate_avm(df, blk, floor, stack)
    
    if est_price is None:
        st.error(f"数据不足，无法评估 {blk} #{floor}-{stack}")
        return

    # 4. 顶部概览卡片 (V160 核心修改)
    # 格式：面积 | 地契 | 地契时间 | 分类
    # 如果字段是 '-' 则不显示，避免看起来乱
    
    info_parts = [f"{int(area):,} sqft"] # 始终显示面积
    
    if extra_info['tenure'] != '-': info_parts.append(str(extra_info['tenure']))
    if extra_info['from'] != '-': info_parts.append(f"From {str(extra_info['from'])}")
    if extra_info['subtype'] != '-': info_parts.append(str(extra_info['subtype']))
    
    info_str = " | ".join(info_parts)

    st.markdown(f"""
    <div style="background-color:#f8fafc; padding:15px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
        <h3 style="margin:0; color:#1e293b;">BLK {blk} #{int(floor):02d}-{stack}</h3>
        <p style="margin:5px 0 0 0; color:#64748b; font-size:15px; font-weight:500;">
            {info_str}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 5. 核心展示
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        st.metric(label="预估总价 (Est. Price)", value=f"${est_price/1e6:,.2f}M")
        st.caption(f"基于 {len(comps)} 笔近期参考交易")
        low_bound = est_price * 0.95
        high_bound = est_price * 1.05
        st.markdown(f"""
        <div style="margin-top:10px; padding:10px; background:#2563eb; border-radius:4px; font-size:13px; color:white;">
            <strong>合理区间:</strong><br>${low_bound/1e6:.2f}M - ${high_bound/1e6:.2f}M
        </div>
        """, unsafe_allow_html=True)

    with c2:
        if not comps.empty:
            min_p = comps['Unit Price ($ psf)'].min()
            max_p = comps['Unit Price ($ psf)'].max()
            st.plotly_chart(render_gauge(est_psf, min_p, max_p, chart_font_size), use_container_width=True)

    st.divider()

    # 6. 本单位历史
    st.markdown("#### 📜 本单位历史 (Unit History)")
    this_unit_hist = df[(df['BLK'] == blk) & (df['Stack'] == stack) & (pd.to_numeric(df['Floor'], errors='coerce') == floor)].copy()
    
    final_cols = ['Sale Date', 'Unit', 'Type', 'Area (sqft)', 'Sale Price', 'Unit Price ($ psf)']
    col_config = {
        "Sale Date": "日期", "Unit": "单位", "Type": "户型",
        "Area (sqft)": "面积", "Sale Price": "总价", "Unit Price ($ psf)": "尺价"
    }

    if not this_unit_hist.empty:
        this_unit_hist = this_unit_hist.sort_values('Sale Date', ascending=False)
        display_hist = this_unit_hist.copy()
        display_hist['Unit'] = display_hist.apply(
            lambda row: f"BLK {row['BLK']} {format_unit(row['Floor'], row['Stack'])}", 
            axis=1
        )
        display_hist['Sale Date'] = display_hist['Sale Date'].dt.strftime('%Y-%m-%d')
        display_hist['Sale Price'] = display_hist['Sale Price'].apply(lambda x: f"${x/1e6:.2f}M")
        display_hist['Unit Price ($ psf)'] = display_hist['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}")
        
        st.dataframe(display_hist[final_cols], use_container_width=True, hide_index=True, column_config=col_config)
    else:
        st.caption("该单位在记录周期内无历史交易。")

    st.divider()

    # 7. 参考交易
    st.markdown("#### 🏘️ 参考交易 (Comparable Transactions)")
    comps = comps.sort_values('Weight', ascending=False).head(6)
    
    comp_display = comps.copy()
    comp_display['Sale Date'] = comp_display['Sale Date'].dt.strftime('%Y-%m-%d')
    comp_display['Sale Price'] = comp_display['Sale Price'].apply(lambda x: f"${x/1e6:.2f}M")
    comp_display['Unit Price ($ psf)'] = comp_display['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}")
    
    comp_display['Unit'] = comp_display.apply(
        lambda row: f"BLK {row['BLK']} {format_unit(row['Floor'], row['Stack'])}", 
        axis=1
    )
    
    st.dataframe(comp_display[final_cols], use_container_width=True, hide_index=True, column_config=col_config)
