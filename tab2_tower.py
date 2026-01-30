# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 跳转逻辑 ---
def switch_to_tab_3():
    js = "<script>window.parent.document.querySelectorAll('button[data-baseweb=\"tab\"]')[2].click();</script>"
    components.html(js, height=0)

# --- 1. SSD 2025 政策逻辑 ---
def get_ssd_info(purchase_date):
    if pd.isna(purchase_date): return "", "normal"
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
    
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    POLICY_2017 = pd.Timestamp("2017-03-11")
    
    # 判定政策周期
    is_new_policy = purchase_date >= POLICY_2025
    lock_years = 4 if is_new_policy else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline:
        return "", "safe"

    # 计算税率
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    
    if is_new_policy:
        rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"}
    else:
        rates = {1: "12%", 2: "8%", 3: "4%"}
    
    current_rate = rates.get(years_held, "4%")
    days_left = (ssd_deadline - today).days
    
    # 预警标签
    if days_left < 90: label = f"🔥 {current_rate} ({days_left}d)"
    elif days_left < 180: label = f"⚠️ {current_rate} ({days_left//30}m)"
    else: label = f"{current_rate} SSD"
    
    return label, "locked"

# --- 2. 辅助 ---
def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

# --- 3. 渲染 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # 💉 注入最强 CSS：重塑 Streamlit 按钮
    st.markdown(f"""
        <style>
        /* 布局微调 */
        [data-testid="column"] {{ padding: 0 1px !important; }}
        
        /* 核心：重写按钮样式 */
        div.stButton > button {{
            width: 100% !important;
            height: 85px !important;
            border-radius: 6px !important;
            border: 1px solid #e5e7eb !important;
            padding: 5px !important;
            white-space: pre-wrap !important; /* 强制换行 */
            line-height: 1.4 !important;
            display: block !important;
            font-family: sans-serif !important;
            transition: all 0.2s !important;
        }}
        
        /* 🔴 SSD Locked (Primary) */
        div.stButton > button[kind="primary"] {{
            background-color: #fef2f2 !important;
            color: #991b1b !important;
            border-color: #f87171 !important;
        }}
        
        /* 🟢 SSD Safe (Secondary) */
        div.stButton > button[kind="secondary"] {{
            background-color: #f0fdf4 !important;
            color: #166534 !important;
            border-color: #bbf7d0 !important;
        }}

        /* ⚪ No Data (We'll use a specific logic for this) */
        /* 由于 Streamlit 只有两种颜色，我们通过 CSS 过滤掉没字的价格来变灰 */
        
        div.stButton > button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        </style>
    """, unsafe_allow_html=True)

    all_blks = sorted(df['BLK'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    selected_blk = st.selectbox("选择楼座", all_blks, key="blk_v118")
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    
    if blk_df.empty: return

    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    for f in floors:
        cols = st.columns(len(all_stacks))
        for i, s in enumerate(all_stacks):
            with cols[i]:
                unit_no = format_unit(f, s)
                data = tx_map.get((f, s))
                
                if data:
                    price_str = f"${data['Sale Price']/1e6:.2f}M"
                    ssd_text, status = get_ssd_info(data['Sale Date'])
                    
                    # 构造三行内容
                    # 强制加 \n 配合 pre-wrap
                    btn_label = f"{unit_no}\n{price_str}\n{ssd_text if ssd_text else ' '}"
                    btn_type = "primary" if status == "locked" else "secondary"
                    help_text = f"成交: {data['Sale Date'].strftime('%Y-%m-%d')}"
                else:
                    # 无数据单元格
                    btn_label = f"{unit_no}\n-\n "
                    btn_type = "secondary"
                    help_text = "无历史记录"

                if st.button(btn_label, key=f"v118_{f}_{s}", help=help_text, type=btn_type, use_container_width=True):
                    st.session_state['avm_target'] = {'blk': selected_blk, 'floor': f, 'stack': s}
                    switch_to_tab_3()
