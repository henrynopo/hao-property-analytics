import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils import format_unit, natural_key

def go_to_valuation(blk, floor, stack):
    st.session_state['avm_target'] = {'blk': blk, 'floor': int(floor), 'stack': stack}
    st.session_state['trigger_tab_switch'] = True

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
    
    # 初始化选中状态
    if 'selected_blk' not in st.session_state or str(st.session_state.selected_blk) not in all_blks:
        st.session_state.selected_blk = str(all_blks[0])

    # 处理 Tab 跳转
    if st.session_state.get('trigger_tab_switch', False):
        components.html("""<script>var tabs=window.parent.document.querySelectorAll('button[data-baseweb="tab"]');if(tabs.length>2){tabs[2].click();window.parent.scrollTo(0,0);}</script>""", height=0)
        st.session_state['trigger_tab_switch'] = False

    st.subheader("🏢 楼宇透视 (Building View)")

    # 使用 st.pills (Streamlit 1.39+) 或 st.radio 替代 Button，避免被下方的 CSS 误伤
    try:
        selection = st.pills("选择楼座 (Block):", all_blks, default=st.session_state.selected_blk, key="blk_selector")
    except AttributeError:
        # 兼容旧版本
        selection = st.radio("选择楼座 (Block):", all_blks, horizontal=True, index=all_blks.index(st.session_state.selected_blk), key="blk_selector")
    
    if selection:
        st.session_state.selected_blk = selection

    # --- [关键回滚] 恢复之前的单元格 CSS 样式 ---
    # 这段 CSS 专门用于让 Grid 中的 Unit 按钮变得紧凑、显示两行文字
    st.markdown("""
        <style>
        /* 仅影响此页面后续渲染的普通按钮 */
        div.stButton > button {
            width: 100%;
            padding: 4px 2px !important;
            font-size: 11px !important; 
            line-height: 1.3 !important;
            min-height: 55px !important; /* 恢复原来的高度 */
            height: auto !important;
            background-color: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            color: #1f2937 !important;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            white-space: pre-wrap; /* 允许换行 */
        }
        div.stButton > button:hover {
            border-color: #2563eb !important;
            background-color: #eff6ff !important;
            transform: translateY(-1px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            z-index: 10;
        }
        /* 微调列间距 */
        [data-testid="column"] { padding: 0 2px !important; }
        </style>
    """, unsafe_allow_html=True)

    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    # 处理楼层排序
    floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int), reverse=True)
    
    # 交易数据映射
    tx_map = blk_df.sort_values('Sale Date').groupby(['Floor_Num', 'Stack']).tail(1).set_index(['Floor_Num', 'Stack']).to_dict('index')

    # [V209] 恢复推断逻辑
    stack_info_map = {}
    for s in all_stacks:
        s_data = blk_df[blk_df['Stack'] == s]
        if not s_data.empty:
            valid_types = s_data[~s_data['Type'].isin(['-', 'nan', 'NaN', '', '0', 'N/A'])]['Type']
            mode_type = valid_types.mode()[0] if not valid_types.empty else "-"
            mode_area = s_data['Area (sqft)'].mode()[0] if not s_data['Area (sqft)'].empty else 0
            stack_info_map[s] = {'type': mode_type, 'area': mode_area}
        else:
            stack_info_map[s] = {'type': "-", 'area': 0}

    st.markdown("---")
    
    # 渲染 Grid
    # 如果 Stack 太多，分段显示
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
                        # 有交易记录
                        u_type = shorten_type(str(tx_data.get('Type', '-')))
                        u_area = int(tx_data.get('Area (sqft)', 0))
                        ssd_icon, _, _ = calculate_ssd_info(tx_data['Sale Date'])
                    else:
                        # [V209] 无交易记录：使用推断数据
                        defaults = stack_info_map.get(s, {})
                        u_type = shorten_type(str(defaults.get('type', '-')))
                        u_area = int(defaults.get('area', 0))
                        ssd_icon = "" 
                    
                    area_str = f"{u_area:,}sf" if u_area > 0 else "-"
                    
                    # [关键回滚] 恢复之前的 Label 格式逻辑
                    # Line 1: Unit + SSD Icon
                    line1 = unit_no
                    if ssd_icon: line1 += f" {ssd_icon}"
                    
                    # Line 2: Type | Area
                    line2 = f"{u_type} | {area_str}"
                    
                    label = f"{line1}\n{line2}"
                        
                    st.button(label, key=f"btn_{selected_blk}_{f}_{s}", use_container_width=True, on_click=go_to_valuation, args=(selected_blk, f, s))
        
        if len(stack_chunks) > 1: st.divider()

    st.markdown("---")
    st.info("图例: 🟩 无SSD | 🟨 <3个月 | 🟧 <6个月 | 🟥 4% | 🛑 8% | ⛔ ≥12%")