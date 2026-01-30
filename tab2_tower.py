import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils import format_unit, natural_key  # 引用通用工具

def go_to_valuation(blk, floor, stack):
    st.session_state['avm_target'] = {'blk': blk, 'floor': int(floor), 'stack': stack}
    st.session_state['trigger_tab_switch'] = True

def select_block(blk):
    st.session_state.selected_blk = str(blk)

def calculate_ssd_info(purchase_date):
    if pd.isna(purchase_date): return "", "", 0
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline: return "🟩", "无SSD", 0
    
    days_left = (ssd_deadline - today).days
    years_held = relativedelta(today, purchase_date).years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate_str = rates.get(years_held, "4%")
    
    if days_left < 90: icon = "🟨"
    elif days_left < 180: icon = "🟧"
    else: icon = "🟥" if int(rate_str.strip('%')) < 12 else "⛔"
    return icon, rate_str, days_left // 30

def shorten_type(type_str):
    if not isinstance(type_str, str): return "-"
    s = type_str.strip()
    if s.lower() in ['nan', 'none', '', 'null', '0', 'n/a']: return "-"
    return s.replace("Bedroom", "Bed").replace("Maisonette", "Mais").replace("Apartment", "Apt")

def render(df, chart_font_size=12):
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    
    if 'selected_blk' not in st.session_state or str(st.session_state.selected_blk) not in all_blks:
        st.session_state.selected_blk = str(all_blks[0])

    if st.session_state.get('trigger_tab_switch', False):
        components.html("""<script>var tabs=window.parent.document.querySelectorAll('button[data-baseweb="tab"]');if(tabs.length>2){tabs[2].click();window.parent.scrollTo(0,0);}</script>""", height=0)
        st.session_state['trigger_tab_switch'] = False

    st.subheader("🏢 楼宇透视 (Building View)")
    st.markdown("""<style>div.stButton>button{width:100%;padding:4px 2px!important;font-size:11px!important;line-height:1.3!important;min-height:55px!important;height:auto!important;background-color:#ffffff!important;border:1px solid #e5e7eb!important;color:#1f2937!important;display:flex;flex-direction:column;justify-content:center;align-items:center;white-space:pre-wrap;}div.stButton>button:hover{border-color:#2563eb!important;background-color:#eff6ff!important;transform:translateY(-1px);box-shadow:0 2px 4px rgba(0,0,0,0.05);}div.stButton>button:focus:not(:active){border-color:#ff4b4b!important;color:#ff4b4b!important;}[data-testid="column"]{padding:0 2px!important;}</style>""", unsafe_allow_html=True)

    rows = [all_blks[i:i + 8] for i in range(0, len(all_blks), 8)]
    for row_blks in rows:
        cols = st.columns(len(row_blks))
        for idx, blk in enumerate(row_blks):
            is_selected = str(st.session_state.selected_blk) == str(blk)
            st.button(f"🔴 {blk}" if is_selected else blk, key=f"blk_{blk}", type="primary" if is_selected else "secondary", use_container_width=True, on_click=select_block, args=(blk,))

    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['Floor_Num', 'Stack']).tail(1).set_index(['Floor_Num', 'Stack']).to_dict('index')

    st.markdown("---")
    stack_chunks = [all_stacks[i:i + 10] for i in range(0, len(all_stacks), 10)]

    for chunk_idx, current_stacks in enumerate(stack_chunks):
        if len(stack_chunks) > 1: st.caption(f"📍 {selected_blk} - Part {chunk_idx + 1}")
        for f in floors:
            cols = st.columns(len(current_stacks))
            for i, s in enumerate(current_stacks):
                with cols[i]:
                    unit_no = format_unit(f, s)
                    tx_data = tx_map.get((f, s))
                    if tx_data:
                        u_type = shorten_type(str(tx_data.get('Type', '-')))
                        u_area = int(tx_data.get('Area (sqft)', 0))
                        ssd_icon, _, _ = calculate_ssd_info(tx_data['Sale Date'])
                    else:
                        u_type, u_area, ssd_icon = "-", "-", ""
                    
                    area_str = f"{u_area:,}sf" if u_area != "-" else "-"
                    label = f"{unit_no} {ssd_icon}\n{u_type} | {area_str}"
                    st.button(label, key=f"btn_{selected_blk}_{f}_{s}", use_container_width=True, on_click=go_to_valuation, args=(selected_blk, f, s))
        if len(stack_chunks) > 1: st.divider()

    st.markdown("---")
    st.info("图例: 🟩 无SSD | 🟨 <3个月 | 🟧 <6个月 | 🟥 4% | 🛑 8% | ⛔ ≥12%")
