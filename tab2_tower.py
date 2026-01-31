import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import time
from datetime import datetime
from utils import format_unit, natural_key, calculate_ssd_status 

def go_to_valuation(blk, floor, stack):
    st.session_state['avm_target'] = {'blk': blk, 'floor': int(floor), 'stack': stack}
    st.session_state['trigger_tab_switch'] = True

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
        js = f"""<script>var tabs=window.parent.document.querySelectorAll('button[data-baseweb="tab"]');if(tabs.length>2){{tabs[2].click();window.parent.scrollTo(0, 0);}}</script>"""
        components.html(js, height=0)
        st.session_state['trigger_tab_switch'] = False

    st.subheader("🏢 楼宇透视 (Building View)")

    try: selection = st.pills("选择楼座 (Block):", all_blks, default=st.session_state.selected_blk, key="blk_selector")
    except AttributeError: selection = st.radio("选择楼座 (Block):", all_blks, horizontal=True, index=all_blks.index(st.session_state.selected_blk), key="blk_selector")
    
    if selection: st.session_state.selected_blk = selection

    st.markdown("""
        <style>
        div.stButton > button {width: 100%; padding: 4px 2px !important; font-size: 11px !important; line-height: 1.3 !important; min-height: 55px !important; height: auto !important; background-color: #ffffff !important; border: 1px solid #e5e7eb !important; color: #1f2937 !important; display: flex; flex-direction: column; justify-content: center; align-items: center; white-space: pre-wrap;}
        div.stButton > button:hover {border-color: #2563eb !important; background-color: #eff6ff !important; transform: translateY(-1px); box-shadow: 0 2px 4px rgba(0,0,0,0.05); z-index: 10;}
        [data-testid="column"] { padding: 0 2px !important; }
        </style>
    """, unsafe_allow_html=True)

    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['Floor_Num', 'Stack']).tail(1).set_index(['Floor_Num', 'Stack']).to_dict('index')

    stack_info_map = {}
    for s in all_stacks:
        s_data = blk_df[blk_df['Stack'] == s]
        if not s_data.empty:
            valid_types = s_data[~s_data['Type'].isin(['-', 'nan', 'NaN', '', '0', 'N/A'])]['Type']
            mode_type = valid_types.mode()[0] if not valid_types.empty else "-"
            mode_area = s_data['Area (sqft)'].mode()[0] if not s_data['Area (sqft)'].empty else 0
            stack_info_map[s] = {'type': mode_type, 'area': mode_area}
        else: stack_info_map[s] = {'type': "-", 'area': 0}

    st.markdown("---")
    chunk_size = 10
    stack_chunks = [all_stacks[i:i + chunk_size] for i in range(0, len(all_stacks), chunk_size)]

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
                        _, ssd_icon, _, _ = calculate_ssd_status(tx_data['Sale Date'])
                    else:
                        defaults = stack_info_map.get(s, {})
                        u_type = shorten_type(str(defaults.get('type', '-')))
                        u_area = int(defaults.get('area', 0))
                        ssd_icon = "" 
                    
                    area_str = f"{u_area:,}sf" if u_area > 0 else "-"
                    label = f"{unit_no} {ssd_icon}\n{u_type} | {area_str}" if ssd_icon else f"{unit_no}\n{u_type} | {area_str}"
                    st.button(label, key=f"btn_{selected_blk}_{f}_{s}", use_container_width=True, on_click=go_to_valuation, args=(selected_blk, f, s))
        if len(stack_chunks) > 1: st.divider()

    st.markdown("---")
    
    # [V219 Fix] 恢复全局机会扫描功能
    with st.expander("🚀 全局机会扫描 (即将解禁 / Opportunity Scan)", expanded=False):
        # 筛选最新交易
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor_Num', 'Stack']).tail(1).copy()
        
        opp_list, watch_list = [], []
        
        for _, row in latest_txs.iterrows():
            # 使用 utils 计算精确状态
            _, emoji, _, months = calculate_ssd_status(row['Sale Date'])
            
            if emoji in ["🟨", "🟧"]:
                blk_val, f_val, s_val = row['BLK'], row['Floor_Num'], row['Stack']
                unit_str = format_unit(f_val, s_val)
                u_type = shorten_type(str(row.get('Type', '-')))
                area = int(row.get('Area (sqft)', 0))
                
                label = f"{emoji} BLK {blk_val} {unit_str}\n{u_type} | {area}sf"
                item_key = f"scan_{blk_val}_{f_val}_{s_val}"
                
                item_data = {"label": label, "key": item_key, "b": blk_val, "f": f_val, "s": s_val, "help": f"SSD Expires in ~{months} months"}
                
                if emoji == "🟨": opp_list.append(item_data)
                else: watch_list.append(item_data)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🟨 0-3 Months Left")
            if not opp_list: st.caption("暂无")
            for item in opp_list:
                st.button(item['label'], key=item['key'], help=item['help'], use_container_width=True, on_click=go_to_valuation, args=(item['b'], item['f'], item['s']))
        
        with c2:
            st.markdown("##### 🟧 3-6 Months Left")
            if not watch_list: st.caption("暂无")
            for item in watch_list:
                st.button(item['label'], key=item['key'], help=item['help'], use_container_width=True, on_click=go_to_valuation, args=(item['b'], item['f'], item['s']))

    st.info("图例: 🟩 无SSD | 🟨 <3个月 | 🟧 <6个月 | 🟥 4% | 🛑 8% | ⛔ ≥12%")