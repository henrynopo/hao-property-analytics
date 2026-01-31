import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time 
import io
import urllib.parse
import utils_address 

from utils import (
    AGENT_PROFILE, 
    CUSTOM_DISCLAIMER, 
    format_unit, 
    format_unit_masked, 
    render_gauge,
    render_transaction_table, # [V216] 引入通用表格组件
    calculate_market_trend 
)

# --- ReportLab Imports ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_RIGHT

# ==========================================
# 🛠️ AVM 核心逻辑 (保持不变)
# ==========================================

def get_address_template(project_name, blk, unit_str):
    try: street, postal = utils_address.find_address_info(project_name, blk)
    except AttributeError: street, postal = project_name, ""
    if not street: street = project_name 
    postal_str = f"Singapore {postal}" if postal else "Singapore XXXXXX"
    return f"Block {blk} {street}\n{unit_str} {project_name}\n{postal_str}"

def get_unit_specs(df, target_blk, target_floor, target_stack):
    df['Floor_Int'] = pd.to_numeric(df['Floor_Num'], errors='coerce').fillna(0).astype(int)
    this_unit = df[(df['BLK'] == target_blk) & (df['Stack'] == target_stack) & (df['Floor_Int'] == int(target_floor))]
    if not this_unit.empty:
        rec = this_unit.sort_values('Sale Date', ascending=False).iloc[0]
        return rec['Area (sqft)'], rec['Type'], 'History', rec['Sale Price'], rec['Sale Date']
    same_stack = df[(df['BLK'] == target_blk) & (df['Stack'] == target_stack)]
    if not same_stack.empty:
        mode_area = same_stack['Area (sqft)'].mode()
        area = mode_area[0] if not mode_area.empty else same_stack['Area (sqft)'].mean()
        mode_type = same_stack['Type'].mode()
        u_type = mode_type[0] if not mode_type.empty else "N/A"
        return area, u_type, 'Stack Inference', 0, None
    default_area = df['Area (sqft)'].median() if not df.empty else 1000
    default_type = df['Type'].mode()[0] if not df.empty else "3 Bedroom"
    return default_area, default_type, 'Global Default', 0, None

def calculate_dynamic_floor_rate(comps):
    default_rate = 0.005 
    valid_data = comps[['Floor_Int', 'Unit Price ($ psf)']].dropna()
    if len(valid_data) < 3 or valid_data['Floor_Int'].nunique() < 2: return default_rate
    x, y = valid_data['Floor_Int'], valid_data['Unit Price ($ psf)']
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_psf = y.mean()
        if avg_psf == 0: return default_rate
        return max(-0.002, min(0.015, slope / avg_psf))
    except: return default_rate

def calculate_avm(df, target_blk, target_floor, target_stack, override_area=None, override_type=None):
    df = df.copy()
    df['Floor_Int'] = pd.to_numeric(df['Floor_Num'], errors='coerce').fillna(0).astype(int)
    market_annual_growth = calculate_market_trend(df)
    last_tx_price, last_tx_date = 0, None
    
    if override_area is not None and override_type is not None:
        est_area, target_type = override_area, override_type
        _, _, _, hist_price, hist_date = get_unit_specs(df, target_blk, target_floor, target_stack)
        if hist_price > 0: last_tx_price, last_tx_date = hist_price, hist_date
        base_info_source = df[df['BLK'] == target_blk]
        if base_info_source.empty: base_info_source = df
        info_tenure = base_info_source['Tenure'].mode()[0] if not base_info_source['Tenure'].empty else '-'
        info_from = base_info_source['Tenure From'].mode()[0] if not base_info_source['Tenure From'].empty else '-'
        info_subtype = base_info_source['Sub Type'].mode()[0] if not base_info_source['Sub Type'].empty else '-'
    else:
        est_area, target_type, _, last_tx_price, last_tx_date = get_unit_specs(df, target_blk, target_floor, target_stack)
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
    comps, used_threshold = pd.DataFrame(), 0.0
    for t in thresholds:
        min_area, max_area = est_area * (1 - t), est_area * (1 + t)
        current_comps = df[(df['Area (sqft)'] >= min_area) & (df['Area (sqft)'] <= max_area)].copy()
        if len(current_comps) >= required_comps:
            comps, used_threshold = current_comps, t
            break
    if comps.empty and 'current_comps' in locals(): comps, used_threshold = current_comps, 0.20
    if len(comps) < 2 and target_type != "N/A":
        comps = df[df['Type'] == target_type].copy(); used_threshold = 9.99 

    limit_date = datetime.now() - pd.DateOffset(months=36)
    recent_comps = comps[comps['Sale Date'] >= limit_date].copy()
    if recent_comps.empty:
        limit_date = datetime.now() - pd.DateOffset(months=60)
        recent_comps = comps[comps['Sale Date'] >= limit_date].copy()
    if recent_comps.empty: return None, None, {}, pd.DataFrame(), 0, 0, 0, 0

    floor_adj_rate = calculate_dynamic_floor_rate(recent_comps)
    recent_comps['Floor_Int'] = pd.to_numeric(recent_comps['Floor_Num'], errors='coerce').fillna(1)
    
    def apply_adjustment(row):
        floor_multiplier = 1 + (target_floor - row['Floor_Int']) * floor_adj_rate
        years_ago = (datetime.now() - row['Sale Date']).days / 365.0
        time_multiplier = 1 + (market_annual_growth * years_ago)
        return row['Unit Price ($ psf)'] * floor_multiplier * time_multiplier

    recent_comps['Adj_PSF'] = recent_comps.apply(apply_adjustment, axis=1)
    recent_comps['Days_Diff'] = (datetime.now() - recent_comps['Sale Date']).dt.days
    recent_comps['Weight'] = 1 / (recent_comps['Days_Diff'] + 30)
    
    weighted_psf = (recent_comps['Adj_PSF'] * recent_comps['Weight']).sum() / recent_comps['Weight'].sum()
    est_price = weighted_psf * est_area
    extra_info = {'tenure': info_tenure, 'from': info_from, 'subtype': info_subtype, 'type': target_type, 'last_price': last_tx_price, 'last_date': last_tx_date}
    return est_price, weighted_psf, extra_info, recent_comps, est_area, floor_adj_rate, market_annual_growth, used_threshold

# ==========================================
# 📄 PDF 生成模块 (保持不变)
# ==========================================
def generate_pdf_letter(project_name, blk, floor, stack, area, u_type, est_price, est_psf, comps_df, mailing_address, recipient_name="Dear Homeowner", last_price=0, last_date=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RightAlign', alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Justify', alignment=TA_JUSTIFY, leading=14))
    styles.add(ParagraphStyle(name='Signature', fontSize=10, leading=12))
    styles.add(ParagraphStyle(name='ProfitStyle', parent=styles['Normal'], alignment=TA_CENTER, fontSize=16, textColor=colors.green, spaceAfter=12, spaceBefore=6))
    
    elements = []
    header_text = f"<b>{AGENT_PROFILE['agency']}</b><br/>{AGENT_PROFILE['name']} | {AGENT_PROFILE['title']}<br/>{AGENT_PROFILE['contact']} | {AGENT_PROFILE['email']}<br/>CEA Reg: {AGENT_PROFILE['license']}"
    elements.append(Paragraph(header_text, styles['RightAlign'])); elements.append(Spacer(1, 40))
    
    date_str = datetime.now().strftime("%d %B %Y")
    address_formatted = mailing_address.replace("\n", "<br/>")
    if recipient_name.lower().strip() not in ["dear homeowner", "homeowner"]: address_text = f"{date_str}<br/><br/><b>{recipient_name}</b><br/>{address_formatted}"
    else: address_text = f"{date_str}<br/><br/><b>To The Homeowner</b><br/>{address_formatted}"
    elements.append(Paragraph(address_text, styles['Normal'])); elements.append(Spacer(1, 20))
    
    elements.append(Paragraph(f"<b>Dear {recipient_name.replace('Dear ', '').strip(',')},</b>", styles['Normal'])); elements.append(Spacer(1, 12))
    
    unit_display = format_unit(floor, stack) 
    opening_text = f"I hope this letter finds you well. As a resident specialist in {project_name}, I have recently conducted a comprehensive valuation analysis for your unit at <b>BLK {blk} {unit_display}</b> ({int(area):,} sqft, {u_type})."
    elements.append(Paragraph(opening_text, styles['Justify'])); elements.append(Spacer(1, 12))
    
    val_text = """Based on the latest transaction data and adjusting for your specific floor level and unit attributes, the estimated market value of your property is:"""
    elements.append(Paragraph(val_text, styles['Justify'])); elements.append(Spacer(1, 10))
    
    est_price_m = est_price / 1e6
    highlight_style_main = ParagraphStyle('HM', parent=styles['Normal'], alignment=TA_CENTER, fontSize=16, textColor=colors.darkblue, spaceAfter=6)
    highlight_style_sub = ParagraphStyle('HS', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10, textColor=colors.grey, spaceAfter=20)
    elements.append(Paragraph(f"<b>${est_price_m:.2f} Million (${est_psf:,.0f} psf)</b>", highlight_style_main))
    elements.append(Paragraph(f"Valuation Range: ${est_price_m*0.9:.2f}M - ${est_price_m*1.1:.2f}M", highlight_style_sub))
    
    if last_price > 0 and last_date is not None:
        profit = est_price - last_price
        profit_pct = (profit / last_price) * 100
        years_held = (datetime.now() - last_date).days / 365.0
        intro_text = f"Records indicate this unit was last purchased on <b>{last_date.strftime('%d %b %Y')}</b> for <b>${last_price/1e6:.2f}M</b>. Based on our current valuation, your estimated gross capital appreciation is:"
        elements.append(Paragraph(intro_text, styles['Justify']))
        elements.append(Paragraph(f"<b>+${profit/1e6:.2f} Million ({profit_pct:.1f}%)</b>", styles['ProfitStyle']))
        elements.append(Paragraph(f"This represents a significant return over the past {years_held:.1f} years.", styles['Justify'])); elements.append(Spacer(1, 12))
    
    elements.append(Paragraph("<b>Recent Comparable Transactions Used:</b>", styles['Normal'])); elements.append(Spacer(1, 6))
    data = [['Date', 'Unit', 'Area', 'Price', 'PSF']]
    display_comps = comps_df.sort_values('Weight', ascending=False).head(5)
    for _, row in display_comps.iterrows():
        c_unit = f"BLK {row['BLK']} {format_unit_masked(row['Floor_Num'])}" 
        data.append([row['Sale Date'].strftime('%d %b %Y'), c_unit, f"{int(row['Area (sqft)']):,}", f"${row['Sale Price']/1e6:.2f}M", f"${row['Unit Price ($ psf)']:,.0f}"])
        
    t = Table(data, colWidths=[1.2*inch, 1.5*inch, 0.8*inch, 1.0*inch, 0.8*inch])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.Color(0.2, 0.2, 0.6)), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTSIZE', (0,0), (-1,-1), 8), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
    elements.append(t); elements.append(Spacer(1, 20))
    
    closing_text = f"The property market in {project_name} is dynamic. If you are considering restructuring your property portfolio or simply wish to cash out on these profits, I would be happy to share a more detailed marketing plan with you.<br/><br/>Please feel free to contact me at <b>{AGENT_PROFILE['contact']}</b>."
    elements.append(Paragraph(closing_text, styles['Justify'])); elements.append(Spacer(1, 30))
    elements.append(Paragraph(f"Sincerely,<br/><br/><b>{AGENT_PROFILE['name']}</b><br/>{AGENT_PROFILE['title']}<br/>{AGENT_PROFILE['agency']}", styles['Signature'])); elements.append(Spacer(1, 40))
    elements.append(Paragraph(f"<font size='7' color='grey'>{CUSTOM_DISCLAIMER.replace('**', '')}</font>", styles['Justify']))
    
    doc.build(elements); buffer.seek(0)
    return buffer

# ==========================================
# 🖥️ MAIN RENDER FUNCTION
# ==========================================

def render(df_raw, project_name="Project", chart_font_size=12):
    st.subheader("🤖 智能估值 (AVM)")
    target = st.session_state.get('avm_target', None)
    if not target:
        st.info("👈 请先在 **楼宇透视 (Tab 2)** 点击任意单位，即可在此查看估值详情。")
        return

    blk, floor, stack = target['blk'], target['floor'], target['stack']
    df = df_raw.copy()
    
    sys_area, sys_type, _, _, _ = get_unit_specs(df, blk, floor, stack)
    all_types = sorted(df['Type'].unique().tolist())
    if sys_type not in all_types: all_types.insert(0, sys_type)
    input_area = int(sys_area) if pd.notna(sys_area) else 0
    input_type = sys_type if sys_type in all_types else (all_types[0] if all_types else "N/A")

    widget_key_suffix = f"{blk}_{floor}_{stack}"
    with st.expander("⚙️ 调整参数 (Calibration)", expanded=True):
        c_cal1, c_cal2 = st.columns(2)
        with c_cal1: input_area = st.number_input("面积 (sqft)", value=input_area, step=10, key=f"cal_area_{widget_key_suffix}")
        with c_cal2: input_type = st.selectbox("户型 (Type)", options=all_types, index=all_types.index(input_type) if input_type in all_types else 0, key=f"cal_type_{widget_key_suffix}")
    
    est_price, est_psf, extra_info, comps, area, floor_adj, market_growth, used_threshold = calculate_avm(
        df, blk, floor, stack, override_area=input_area, override_type=input_type
    )
    
    if est_price is None: st.error(f"⚠️ 数据严重不足，无法估值。"); return

    formatted_unit_str = format_unit(floor, stack) 
    info_parts = [f"{int(area):,} sqft"]; 
    if extra_info['type'] != 'N/A': info_parts.append(str(extra_info['type']))
    if extra_info['tenure'] != '-' and extra_info['tenure'] != 'N/A': info_parts.append(str(extra_info['tenure']))
    info_str = " | ".join(info_parts)
    
    st.markdown(f"""
    <div style="background-color:#f8fafc; padding:15px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
        <p style="margin:0 0 5px 0; color:#64748b; font-size:12px; font-weight:bold; letter-spacing:1px; text-transform:uppercase;">{project_name}</p>
        <h3 style="margin:0; color:#1e293b; font-size:24px;">BLK {blk} {formatted_unit_str}</h3>
        <p style="margin:5px 0 0 0; color:#475569; font-size:15px; font-weight:500;">{info_str}</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1.5])
    low_bound, high_bound = est_price * 0.90, est_price * 1.10
    with c1:
        st.metric(label="预估总价 (Est. Price)", value=f"${est_price/1e6:,.2f}M")
        last_price = extra_info.get('last_price', 0)
        if last_price > 0:
            profit = est_price - last_price; profit_pct = (profit / last_price) * 100
            st.markdown(f"<div style='margin-top:5px; margin-bottom:10px; font-size:14px; color:#15803d; font-weight:bold;'>📈 预计增值: +${profit/1e6:.2f}M ({profit_pct:.1f}%)</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:10px; padding:10px; background:#2563eb; border-radius:4px; font-size:13px; color:white;'><strong>合理区间 (+/- 10%):</strong><br>${low_bound/1e6:.2f}M - ${high_bound/1e6:.2f}M</div>", unsafe_allow_html=True)
    with c2: st.plotly_chart(render_gauge(est_psf, chart_font_size), use_container_width=True, key=f"gauge_{blk}_{floor}_{stack}_{time.time()}")
    st.divider()

    st.markdown("#### 🏘️ 参考交易 (Comparable Transactions)")
    # [V216 Fix] 调用通用组件渲染
    comps_display = comps.sort_values('Weight', ascending=False).head(5).copy()
    render_transaction_table(comps_display)

    st.divider()
    st.markdown("### 📄 报告生成 (Report Generation)")
    default_addr = get_address_template(project_name, blk, formatted_unit_str)
    c1, c2, c3 = st.columns([1.5, 3, 1])
    with c1: r_name = st.text_input("👤 收件人称呼", value="Dear Homeowner", key=f"name_{widget_key_suffix}")
    with c2: r_addr = st.text_area("📍 确认收件地址", value=default_addr, height=100, key=f"addr_{widget_key_suffix}")
    with c3: st.write(""); st.write(""); st.write(""); st.link_button("🗺️ 核对邮编", f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(f'{project_name} Block {blk}')}")

    pdf_bytes = generate_pdf_letter(project_name, blk, floor, stack, area, extra_info['type'], est_price, est_psf, comps, r_addr, r_name, extra_info.get('last_price', 0), extra_info.get('last_date', None))
    st.download_button(label="📥 下载致业主信函 (PDF)", data=pdf_bytes, file_name=f"Letter_{blk}_{formatted_unit_str}.pdf", mime="application/pdf", type="primary", use_container_width=True, key=f"dl_pdf_{blk}_{floor}_{stack}_{time.time()}")