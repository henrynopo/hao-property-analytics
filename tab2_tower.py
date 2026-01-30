# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 1. 2025 最新 SSD 政策逻辑 ---
def get_ssd_info(purchase_date):
    if pd.isna(purchase_date): return "", "#f3f4f6", "#9ca3af" # 灰
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
    
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    POLICY_2017 = pd.Timestamp("2017-03-11")
    
    # 判定锁定期
    if purchase_date >= POLICY_2025:
        lock_years = 4
        rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"}
    else:
        lock_years = 3
        rates = {1: "12%", 2: "8%", 3: "4%"}
        
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline:
        return "", "#f0fdf4", "#166534" # Safe: 绿底无字

    # 计算已持有时长（年）
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1 # 第几年
    current_rate = rates.get(years_held, "4%")
    
    days_left = (ssd_deadline - today).days
    
    # 颜色与预警逻辑
    if days_left < 90:
        return f"🔥 {current_rate} ({days_left}d)", "#fee2e2", "#991b1b" # 3个月内
    elif days_left < 180:
        return f"⚠️ {current_rate} ({days_left//30}m)", "#ffedd5", "#9a3412" # 6个月内
    else:
        bg = "#fee2e2" if lock_years == 4 else "#fef2f2"
        return f"{current_rate} SSD", bg, "#991b1b"

# --- 2. 辅助函数 ---
def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

# --- 3. 渲染主函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # CSS 注入：确保透明按钮 100% 覆盖且可点击
    st.markdown("""
        <style>
        [data-testid="column"] { padding: 0 2px !important; }
        .stButton button {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 75px !important;
            background: transparent !important;
            color: transparent !important;
            border: none !important;
            z-index: 10;
        }
        .stButton button:hover { background: rgba(0,0,0,0.05) !important; }
        </style>
    """, unsafe_allow_html=True)

    all_blks = sorted(df['BLK'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    selected_blk = st.selectbox("选择楼座", all_blks, key="blk_v117")
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    # 处理楼层
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
                
                price_str, ssd_text, bg_color, text_color = "-", "", "#f9fafb", "#9ca3af"
                
                if data:
                    price_str = f"${data['Sale Price']/1e6:.2f}M"
                    ssd_text, bg_color, text_color = get_ssd_info(data['Sale Date'])

                # HTML 渲染三行布局
                st.markdown(f"""
                    <div style="background-color:{bg_color}; border:1px solid #e5e7eb; border-radius:6px; height:75px; 
                                display:flex; flex-direction:column; justify-content:center; align-items:center; font-family:sans-serif;">
                        <div style="font-size:13px; font-weight:800; color:#111827;">{unit_no}</div>
                        <div style="font-size:12px; font-weight:600; color:#374151; margin:2px 0;">{price_str}</div>
                        <div style="font-size:10px; font-weight:bold; color:{text_color};">{ssd_text}</div>
                    </div>
                """, unsafe_allow_html=True)
                
                # 透明按钮处理点击跳转
                if st.button("", key=f"v117_{selected_blk}_{f}_{s}"):
                    st.session_state['avm_target'] = {'blk': selected_blk, 'floor': f, 'stack': s}
                    components.html("<script>window.parent.document.querySelectorAll('button[data-baseweb=\"tab\"]')[2].click();</script>", height=0)
