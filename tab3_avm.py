import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import re
import time
import io

# --- ReportLab Imports for PDF ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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

# --- PDF 生成函数 ---
def generate_pdf(project_name, blk, floor, stack, area, u_type, est_price, est_psf, comps_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # 标题
    title_style = styles['Title']
    elements.append(Paragraph(f"Valuation Report: {project_name}", title_style))
    elements.append(Spacer(1, 12))
    
    # 单位信息
    normal_style = styles['Normal']
    unit_str = format_unit(floor, stack)
    info_text = f"""
    <b>Property:</b> BLK {blk} {unit_str}<br/>
    <b>Area:</b> {int(area):,} sqft<br/>
    <b>Type:</b> {u_type}<br/>
    <b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}
    """
    elements.append(Paragraph(info_text, normal_style))
    elements.append(Spacer(1, 20))
    
    # 估值结果
    val_style = ParagraphStyle('ValStyle', parent=styles['Heading2'], textColor=colors.darkblue)
    elements.append(Paragraph(f"Estimated Value: ${est_price/1e6:,.2f} Million", val_style))
    elements.append(Paragraph(f"Estimated PSF: ${est_psf:,.0f} psf", normal_style))
    elements.append(Spacer(1, 20))
    
    # 参考交易列表
    elements.append(Paragraph("<b>Comparable Transactions Used:</b>", styles['Heading3']))
    elements.append(Spacer(1, 10))
    
    # 准备表格数据
    data = [['Date', 'Unit', 'Area', 'Price', 'PSF']]
    
    # 按权重排序取前10个
    display_comps = comps_df.sort_values('Weight', ascending=False).head(10)
    
    for _, row in display_comps.iterrows():
        unit_fmt = format_unit(row['Floor'], row['Stack'])
        date_fmt = row['Sale Date'].strftime('%Y-%m-%d')
        price_fmt = f"${row['Sale Price']/1e6:.2f}M"
        psf_fmt = f"${row['Unit Price ($ psf)']:,.0f}"
        
        data.append([
            date_fmt,
            f"BLK {row['BLK']} {unit_fmt}",
            f"{int(row['Area (sqft)']):,}",
            price_fmt,
            psf_fmt
        ])
        
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(t)
    
    # 免责声明
    elements.append(Spacer(1, 30))
    disclaimer = """
    <font size="8" color="grey">
    Disclaimer: This is a computer-generated estimate based on historical transaction data. 
    It does not constitute a formal valuation and should not be relied upon as such.
    </font>
    """
    elements.append(Paragraph(disclaimer, normal_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- 辅助：获取单位物理属性 ---
def get_unit_specs(df, target_blk, target_floor, target_stack):
    this_unit = df[
        (df['BLK'] == target_blk) & 
        (df['Stack'] == target_stack) & 
        (df['Floor_Int'] == int(target_floor))
    ]
    
    if not this_unit.empty:
        rec = this_unit.sort_values('Sale Date', ascending=False).iloc[0]
        return rec['Area (sqft)'], rec['Type'], 'History'
    
    same_stack = df[(df['BLK'] == target_blk) & (df['Stack'] == target_stack)]
    if not same_stack.empty:
        mode_area = same_stack['Area (sqft)'].mode()
        area = mode_area[0] if not mode_area.empty else same_stack['Area (sqft)'].mean()
        
        mode_type = same_stack['Type'].mode()
        u_type = mode_type[0] if not mode_type.empty else "N/A"
        return area, u_type, 'Stack Inference'
    
    default_area = df['Area (sqft)'].median() if not df.empty else 1000
    default_type = df['Type'].mode()[0] if not df.empty else "3 Bedroom"
    return default_area, default_type, 'Global Default'

# --- 辅助：计算全场市场趋势 ---
def calculate_market_trend(full_df):
    limit_date = datetime.now() - pd.DateOffset(months=36)
    trend_data = full_df[full_df['Sale Date'] >= limit_date].copy()
    if len(trend_data) < 10: return 0.0
    
    trend_data['Date_Ord'] = trend_data['Sale Date'].map(datetime.toordinal)
    x = trend_data['Date_Ord']
    y = trend_data['Unit Price ($ psf)']
    
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_price = y.mean()
        if avg_price == 0: return 0.0
        annual_growth_rate = (slope / avg_price) * 365
        return max(-0.05, min(0.10, annual_growth_rate))
    except:
        return 0.0

# --- 辅助：计算楼层修正系数 ---
def calculate_dynamic_floor_rate(comps):
    default_rate = 0.005 
    valid_data = comps[['Floor_Int', 'Unit Price ($ psf)']].dropna()
    if len(valid_data) < 3 or valid_data['Floor_Int'].nunique() < 2: return default_rate
    
    x = valid_data['Floor_Int']
    y = valid_data['Unit Price ($ psf)']
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_psf = y.mean()
        if avg_psf == 0: return default_rate
        return max(-0.002, min(0.015, slope / avg_psf))
    except:
        return default_rate

# --- 核心估值逻辑 ---
def calculate_avm(df, target_blk, target_floor, target_stack, override_area=None, override_type=None):
    market_annual_growth = calculate_market_trend(df)

    if override_area is not None and override_type is not None:
        est_area = override_area
        target_type = override_type
        base_info_source = df[df['BLK'] == target_blk]
        if base_info_source.empty: base_info_source = df
        info_tenure = base_info_source['Tenure'].mode()[0] if not base_info_source['Tenure'].empty else '-'
        info_from = base_info_source['Tenure From'].mode()[0] if not base_info_source['Tenure From'].empty else '-'
        info_subtype = base_info_source['Sub Type'].mode()[0] if not base_info_source['Sub Type'].empty else '-'
    else:
        est_area, target_type, _ = get_unit_specs(df, target_blk, target_floor, target_stack)
        rec_matches = df[(df['BLK']==target_blk) & (df['Stack']==target_stack)]
        if not rec_matches.empty:
            rec = rec_matches.iloc[0]
            info_tenure = str(rec.get('Tenure', '-'))
            info_from = str(rec.get('Tenure From', '-'))
            info_subtype = str(rec.get('Sub Type', '-'))
        else:
            info_tenure, info_from, info_subtype = '-', '-', '-'

    required_comps = 5
    thresholds = [0.05, 0.10, 0.15, 0.20]
    
    comps = pd.DataFrame()
    used_threshold = 0.0

    for t in thresholds:
        min_area = est_area * (1 - t)
        max_area = est_area * (1 + t)
        current_comps = df[(df['Area (sqft)'] >= min_area) & (df['Area (sqft)'] <= max_area)].copy()
        if len(current_comps) >= required_comps:
            comps = current_comps
            used_threshold = t
            break
            
    if comps.empty and 'current_comps' in locals():
        comps = current_comps
        used_threshold = 0.20
        
    if len(comps) < 2 and target_type != "N/A":
        comps = df[df['Type'] == target_type].copy()
        used_threshold = 9.99 

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
    
    # 获取默认值
    sys_area, sys_type, sys_source = get_unit_specs(df, blk, floor, stack)
    
    all_types = sorted(df['Type'].unique().tolist())
    if sys_type not in all_types: all_types.insert(0, sys_type)
    
    # 手动校准 UI
    widget_key_suffix = f"{blk}_{floor}_{stack}"
    with st.expander("⚙️ 调整参数 (Calibration)", expanded=True):
        c_cal1, c_cal2 = st.columns(2)
        with c_cal1:
            input_area = st.number_input(
                "面积 (sqft)", 
                value=int(sys_area) if pd.notna(sys_area) else 0,
                step=10,
                key=f"cal_area_{widget_key_suffix}"
            )
        with c_cal2:
            input_type = st.selectbox(
                "户型 (Type)", 
                options=all_types,
                index=all_types.index(sys_type) if sys_type in all_types else 0,
                key=f"cal_type_{widget_key_suffix}"
            )
        
        if sys_source == 'Stack Inference':
            st.caption(f"ℹ️ 系统根据同列单位推测: {int(sys_area)} sqft | {sys_type}")
        elif sys_source == 'Global Default':
            st.caption("⚠️ 无历史记录，显示为默认值。请手动校准。")
    
    # 计算估值
    est_price, est_psf, extra_info, comps, area, floor_adj, market_growth, used_threshold = calculate_avm(
        df, blk, floor, stack, 
        override_area=input_area, 
        override_type=input_type
    )
    
    if est_price is None:
        st.error(f"⚠️ 数据严重不足，即使调整参数也无法找到参考交易。")
        st.info("建议：尝试将面积调整为项目中的主流户型面积 (如 1,700 sqft) 再次尝试。")
        return

    # 显示结果
    formatted_unit_str = format_unit(floor, stack)
    info_parts = [f"{int(area):,} sqft"]
    if extra_info['type'] != 'N/A': info_parts.append(str(extra_info['type'])) 
    if extra_info['tenure'] != '-' and extra_info['tenure'] != 'N/A': info_parts.append(str(extra_info['tenure']))
    info_str = " | ".join(info_parts)
    
    st.markdown(f"""
    <div style="background-color:#f8fafc; padding:15px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
        <p style="margin:0 0 5px 0; color:#64748b; font-size:12px; font-weight:bold; letter-spacing:1px; text-transform:uppercase;">
            {project_name}
        </p>
        <h3 style="margin:0; color:#1e293b; font-size:24px;">BLK {blk} {formatted_unit_str}</h3>
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
        sim_txt = f"±{int(used_threshold*100)}%" if used_threshold < 9 else "宽松匹配"
        
        st.caption(f"参考: {len(comps)}笔交易 (相似度 {sim_txt})")
        st.caption(f"修正: 楼层 {floor_txt} | 趋势 {trend_txt}")
        
        # [PDF 下载按钮]
        pdf_file = generate_pdf(project_name, blk, floor, stack, area, extra_info['type'], est_price, est_psf, comps)
        st.download_button(
            label="📄 下载估值报告 (PDF)",
            data=pdf_file,
            file_name=f"Valuation_{blk}_{formatted_unit_str}.pdf",
            mime="application/pdf",
            key=f"btn_pdf_{blk}_{floor}_{stack}"
        )
        
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
        st.plotly_chart(
            render_gauge(est_psf, chart_font_size), 
            use_container_width=True,
            key=f"gauge_{blk}_{floor}_{stack}_{time.time()}" 
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
