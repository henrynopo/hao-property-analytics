# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import html
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 跳转逻辑 ---
def switch_to_tab_3():
    js = f"""
    <script>
        var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
        if (tabs.length > 2) {{
            tabs[2].click();
        }}
    </script>
    """
    components.html(js, height=0)

# --- 1. 辅助函数 ---
def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def check_ssd_status(purchase_date):
    if pd.isna(purchase_date): return False, "", "", "#f9fafb" # 灰色
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
    
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    POLICY_2017 = pd.Timestamp("2017-03-11")
    lock_years = 3 if POLICY_2017 <= purchase_date < POLICY_2025 else 4
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today < ssd_deadline:
        days_left = (ssd_deadline - today).days
        if days_left < 90: return True, f"🔥 剩{days_left}天", "critical", "#fee2e2" # 鲜红
        if days_left < 180: return True, f"⚠️ 剩{days_left//30}月", "warning", "#ffedd5" # 橙黄
        return True, f"🔒 {days_left//30}月", "locked", "#fecaca" # 浅红
    return False, "", "free", "#f0fdf4" # 绿色

# --- 2. 主渲染 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # 注入全局透明按钮样式，确保按钮盖在 HTML 卡片上且不可见，但可点击
    st.markdown("""
        <style>
        .unit-container {
            position: relative;
            width: 100%;
            height: 85px;
            border-radius: 6px;
            margin-bottom: 8px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            border: 1px solid #e5e7eb;
            overflow: hidden;
            font-family: sans-serif;
        }
        .unit-row { line-height: 1.2; text-align: center; }
        .unit-id { font-weight: 800; font-size: 13px; color: #111827; }
        .unit-price { font-size: 12px; font-weight: 600; color: #374151; margin: 2px 0; }
        .unit-ssd { font-size: 10px; font-weight: bold; }
        
        /* 核心：让 Streamlit 按钮变透明并铺满容器 */
        .stButton button {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100% !important;
            background: transparent !important;
            border: none !important;
            color: transparent !important;
            z-index: 10;
        }
        .stButton button:hover {
            background: rgba(0,0,0,0.05) !important;
        }
        </style>
    """, unsafe_allow_html=True)

    all_blks = sorted(df['BLK'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    selected_blk = st.selectbox("选择楼座", all_blks, key="blk_sel_v115")
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    blk_df['Floor_Sort'] = pd.to_numeric(blk_df['Floor_Num'], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    
    if not blk_df.empty:
        floors = sorted(list(range(int(blk_df['Floor_Sort'].min()), int(blk_df['Floor_Sort'].max()) + 1)), reverse=True)
        tx_map = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1).set_index(['Floor_Sort', 'Stack']).to_dict('index')

        for f in floors:
            cols = st.columns(len(all_stacks))
            for i, s in enumerate(all_stacks):
                with cols[i]:
                    unit_no = format_unit(f, s)
                    data = tx_map.get((f, s))
                    
                    price_str = "-"
                    ssd_html = ""
                    bg_color = "#f9fafb" # 默认无交易灰色
                    
                    if data:
                        price_str = f"${data['Sale Price']/1e6:.2f}M"
                        is_locked, ssd_text, full_msg, bg_color = check_ssd_status(data['Sale Date'])
                        if is_locked:
                            ssd_html = f'<div class="unit-ssd" style="color:#991b1b;">{ssd_text}</div>'
                        else:
                            ssd_html = '<div class="unit-ssd" style="color:#166534;">Safe</div>'

                    # 1. 渲染视觉卡片 (HTML)
                    st.markdown(f"""
                        <div class="unit-container" style="background-color: {bg_color};">
                            <div class="unit-row unit-id">{unit_no}</div>
                            <div class="unit-row unit-price">{price_str}</div>
                            <div class="unit-row">{ssd_html}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 2. 渲染透明按钮 (交互)
                    # 放在 Markdown 后面，通过 CSS position:absolute 盖在上面
                    if st.button("", key=f"btn_{selected_blk}_{f}_{s}"):
                        st.session_state['avm_target'] = {'blk': selected_blk, 'floor': f, 'stack': s}
                        switch_to_tab_3()
    
    st.caption("🔴 红底: SSD锁定 | 🟠 橙底: 6月内到期 | 🟢 绿底: 安全 | ⚪ 灰底: 无记录。点击格子跳转。")
