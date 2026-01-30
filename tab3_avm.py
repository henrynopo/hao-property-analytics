import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import re

# --- 辅助：统一数据清洗 ---
def clean_and_prepare_data(df_raw):
    df = df_raw.copy()
    rename_map = {
        'Transacted Price ($)': 'Sale Price',
        'Area (SQFT)': 'Area (sqft)',
        'Unit Price ($ psf)': 'Unit Price ($ psf)',
        'Unit Price ($ psm)': 'Unit Price ($ psm)',
        'Sale Date': 'Sale Date',
        'Bedroom Type': 'Type',   
        'No. of Bedroom': 'Type', 
        'Tenure': 'Tenure',
        'Lease Commencement Date': 'Tenure From',
        'Tenure Start Date': 'Tenure From',
        'Property Type': 'Sub Type',
        'Building Type': 'Sub Type'
    }
    df.rename(columns=rename_map, inplace=True)
    
    for col in ['Type', 'Tenure', 'Tenure From', 'Sub Type']:
        if col not in df.columns: df[col] = "N/A"
    
    df['Type'] = df['Type'].astype(str)

    if 'Sale Date' in df.columns: df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')

    if 'Unit Price ($ psf)' not in df.columns:
        if 'Sale Price' in df.columns and 'Area (sqft)' in df.columns:
            df['Unit Price ($ psf)'] = df['Sale Price'] / df['Area (sqft)']
        else:
            df['Unit Price ($ psf)'] = 0
    
    df['Floor_Int'] = pd.to_numeric(df['Floor'], errors='coerce').fillna(0).astype(int)
            
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

# --- 辅助：计算全场市场趋势 (All Units) ---
def calculate_market_trend(full_df):
    limit_date = datetime.now() - pd.DateOffset(months=36)
    trend_data = full_df[full_df['Sale Date'] >= limit_date].copy()
    
    if len(trend_data) < 10: 
        return 0.0
    
    trend_data['Date_Ord'] = trend_data['Sale Date'].map(datetime.toordinal)
    
    x = trend_data['Date_Ord']
    y = trend_data['Unit Price ($ psf)']
    
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_price = y.mean()
        if avg_price == 0: return 0.0
        
        annual_growth_rate = (slope / avg_price) * 365
        final_rate = max(-0.05, min(0.10, annual_growth_rate))
        return final_rate
    except:
        return 0.0

# --- 辅助：计算楼层修正系数 ---
def calculate_dynamic_floor_rate(comps):
    default_rate = 0.005 
    valid_data = comps[['Floor_Int', 'Unit Price ($ psf)']].dropna()
    
    if len(valid_data) < 3 or valid_data['Floor_Int'].nunique() < 2:
        return default_rate
    
    x = valid_data['Floor_Int']
    y = valid_data['Unit Price ($ psf)']
    
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_psf = y.mean()
        if avg_psf == 0: return default_rate
        calc_rate = slope / avg_psf
        final_rate = max(-0.002, min(0.015, calc_rate))
        return final_rate
    except:
        return default_rate

# --- 核心估值逻辑 ---
def calculate_avm(df, target_blk, target_floor, target_stack):
    market_annual_growth = calculate_market_trend(df)

    this_unit_exact_tx = df[
        (df['BLK'] == target_blk) & 
        (df['Stack'] == target_stack) & 
        (df['Floor_Int'] == int(target_floor))
    ]
    
    target_type = "N/A"

    if not this_unit_exact_tx.empty:
        est_area = this_unit_exact_tx.iloc[0]['Area (sqft)']
        latest_rec = this_unit_exact_tx.sort_values('Sale Date', ascending=False).iloc[0]
        target_type = latest_rec['Type']
        info_tenure = str(latest_rec.get('Tenure', '-'))
        info_from = str(latest_rec.get('Tenure From', '-'))
        info_subtype = str(latest_rec.get('Sub Type', '-'))
    else:
        same_stack_tx = df[(df['BLK'] == target_blk) & (df['Stack'] == target_stack)]
        if not same_stack_tx.empty:
            est_area = same_stack_tx['Area (sqft)'].mode()[0]
            target_type = same_stack_tx['Type'].mode()[0]
        else:
            est_area = df['Area (sqft)'].median()
            target_type = df['Type'].mode()[0]
        
        info_tenure = df['Tenure'].mode()[0] if not df['Tenure'].empty else '-'
        info_from = df['Tenure From'].mode()[0] if not df['Tenure From'].empty else '-'
        info_subtype = df['Sub Type'].mode()[0] if not df['Sub Type'].empty else '-'

    required_comps = 5
    thresholds = [0.05, 0.10, 0.15]
    
    comps = pd.DataFrame()
    used_threshold = 0.0

    for t in thresholds:
        min_area = est_area * (1 - t)
        max_area = est_area * (1 + t)
        
        current_comps = df[
            (df['Area (sqft)'] >= min_area) & 
            (df['Area (sqft)'] <= max_area)
        ].copy()
        
        if len(current_comps) >= required_comps:
            comps = current_comps
            used_threshold = t
            break
            
    if comps.empty and 'current_comps' in locals():
        comps = current_comps
        used_threshold = 0.15 
        
    if comps.empty:
        comps = df[
            (df['Area (sqft)'] >= est_area * 0.8) & 
            (df['Area (sqft)'] <= est_area * 1.2)
        ].copy()
        used_threshold = 0.20

    limit_date = datetime.now() - pd.DateOffset(months=36)
    recent_comps = comps[comps['Sale Date'] >= limit_date].copy()
    
    if recent_comps.empty:
        limit_date = datetime.now() - pd.DateOffset(months=60)
        recent_comps = comps[comps['Sale Date'] >= limit_date].copy()

    if recent_comps.empty:
        return None, None, {}, pd.DataFrame(), 0, 0, 0, 0

    floor_adj_rate = calculate_dynamic_floor_rate(recent_comps)

    recent_comps['Floor_Int'] = pd.to_numeric(recent_comps['Floor'], errors='coerce').fillna(1)
    
    def apply_adjustment(row):
        floor_multiplier = 1 + (target_floor - row['Floor_Int']) * floor_adj_rate
        years_ago = (datetime.now() - row['Sale Date']).days / 365.0
        time_multiplier = 1 + (market_annual_growth * years_ago)
        return row['Unit Price ($ psf)'] * floor_multiplier * time_multiplier

    recent_comps['Adj_PSF'] = recent_comps.apply(apply_adjustment, axis=1)
    recent_comps['Days_Diff'] = (datetime.now() - recent_comps['Sale Date']).dt.days
    recent_comps['Weight'] = 1 / (recent_comps['Days_Diff'] + 30)
    
    weighted_psf = (recent_comps['Adj_PSF'] * recent_comps['Weight']).sum() / recent_comps['Weight'].sum()
    est_psf = weighted_psf
    est_price = est_psf * est_area
    
    extra_info = {
        'tenure': info_tenure,
        'from': info_from,
        'subtype': info_subtype,
        'type': target_type
    }
    
    return est_price, est_psf, extra_info, recent_comps, est_area, floor_adj_rate, market_annual_growth, used_threshold

# --- 渲染仪表盘 ---
def render_gauge(est_psf, font_size=12):
    range_min = est_psf * 0.90
    range_max = est_psf * 1.10
    axis_min = est_psf * 0.80
    axis_max = est_psf * 1.20
        
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = est_psf,
        number = {'suffix': " psf", 'font': {'size': 18}}, 
        domain = {'x': [0, 1], 'y': [0, 1]},
        gauge = {
            'axis': {
                'range': [axis_min, axis_max], 
                'tickwidth': 1, 
                'tickcolor': "darkblue",
                'tickmode': 'array',
                'tickvals': [axis_min, est_psf, axis_max],
                'ticktext': [f"{int(axis_min)}", f"{int(est_psf)}", f"{int(axis_max)}"]
            },
            'bar': {'thickness': 0}, 
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "#e5e7eb",
            'steps': [
                {'range': [axis_min, range_min], 'color': "#f3f4f6"},
                {'range': [range_min, range_max], 'color': "#2563eb"},
                {'range': [range_max, axis_max], 'color': "#f3f4f6"}
            ],
            'threshold': {
                'line': {'color': "#dc2626", 'width': 3},
                'thickness': 0.8,
                'value': est_psf
            }
        }
    ))
    fig.update_layout(
        height=150, 
        margin=dict(l=20, r=20, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'family': "Arial", 'size': 11}
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
    
    est_price, est_psf, extra_info, comps, area, floor_adj, market_growth, used_threshold = calculate_avm(df, blk, floor, stack)
    
    if est_price is None:
        st.error(f"数据不足，无法评估 {blk} #{floor}-{stack}")
        return

    # 概览卡片
    info_parts = [f"{int(area):,} sqft"]
    if extra_info['type'] != 'N/A': info_parts.append(str(extra_info['type'])) 
    
    if extra_info['tenure'] != '-' and extra_info['tenure'] != 'N/A': info_parts.append(str(extra_info['tenure']))
    if extra_info['from'] != '-' and extra_info['from'] != 'N/A': info_parts.append(f"From {str(extra_info['from'])}")
    
    info_str = " | ".join(info_parts)

    st.markdown(f"""
    <div style="background-color:#f8fafc; padding:15px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
        <p style="margin:0 0 5px 0; color:#64748b; font-size:12px; font-weight:bold; letter-spacing:1px; text-transform:uppercase;">
            {project_name}
        </p>
        <h3 style="margin:0; color:#1e293b; font-size:24px;">BLK {blk} #{int(floor):02d}-{stack}</h3>
        <p style="margin:5px 0 0 0; color:#475569; font-size:15px; font-weight:500;">
            {info_str}
        </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1.5])
    
    low_bound = est_price * 0.90
    high_bound = est_price * 1.10
    
    with c1:
        st.metric(label="预估总价 (Est. Price)", value=f"${est_price/1e6:,.2f}M")
        
        floor_txt = f"{floor_adj*100:+.2f}%/层"
        trend_txt = f"{market_growth*100:+.1f}%/年"
        
        st.caption(f"基于 {len(comps)} 笔同面积交易 (相似度 ±{int(used_threshold*100)}%)")
        st.caption(f"修正因子: 楼层 {floor_txt} | 市场趋势 {trend_txt}")
        
        st.markdown(f"""
        <div style="margin-top:10px; padding:10px; background:#2563eb; border-radius:4px; font-size:13px; color:white;">
            <strong>合理区间 (+/- 10%):</strong><br>${low_bound/1e6:.2f}M - ${high_bound/1e6:.2f}M
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(
            "<h5 style='text-align: center; color: #64748b; font-size: 14px; margin-bottom: 0px;'>预估尺价 (Estimated PSF)</h5>", 
            unsafe_allow_html=True
        )
        # [核心修复] 添加 Key，强制每次销毁重建，解决错位问题
        st.plotly_chart(
            render_gauge(est_psf, chart_font_size), 
            use_container_width=True,
            key=f"gauge_{blk}_{floor}_{stack}" 
        )

    st.divider()

    # 本单位历史
    this_unit_hist = df[
        (df['BLK'] == blk) & 
        (df['Stack'] == stack) & 
        (df['Floor_Int'] == int(floor))
    ].copy()
    
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

    # 参考交易
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
