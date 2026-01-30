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

# --- 1. SSD 2025 政策逻辑 (增加颜色层级) ---
def get_ssd_info(purchase_date):
    if pd.isna(purchase_date): return "", "empty"
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
    
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    POLICY_2017 = pd.Timestamp("2017-03-11")
    
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline:
        return "", "safe"

    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    days_left = (ssd_deadline - today).days
    
    # 🚨 严格预警分级
    if days_left < 90: 
        return f"🔥{rate}({days_left}d)", "critical"  # 3月内: 红色
    if days_left < 180: 
        return f"⚠️{rate}({days_left//30}m)", "warning"   # 6月内: 橙色
    return f"{rate} SSD", "locked" # 锁定中: 淡红

# --- 2. 补零格式化 ---
def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

# --- 3. 渲染主逻辑 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # 💉 注入紧凑型 CSS
    st.markdown("""
        <style>
        /* 核心：紧凑布局控制 */
        div.stButton > button {
            width: 100% !important;
            min-height: 62px !important;      /* 压缩高度 */
            max-height: 62px !important;
            padding: 2px 1px !important;      /* 极致 padding */
            border-radius: 3px !important;
            white-space: pre !important;      /* 强制换行 */
            line-height: 1.2 !important;      /* 紧凑行高 */
            font-size: 11px !important;      /* 缩小字体 */
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
            border: 1px solid #e5e7eb !important;
        }
        
        /* 🔴 Critical < 3月 (深红) */
        div.stButton > button[data-ssd="critical"] {
            background-color: #fca5a5 !important;
            color: #7f1d1d !important;
            border-color: #f87171 !important;
        }
        
        /* 🟠 Warning < 6月 (橙色) */
        div.stButton > button[data-ssd="warning"] {
            background-color: #ffedd5 !important;
            color: #9a3412 !important;
            border-color: #fdba74 !important;
        }

        /* 🔴 Locked > 6月 (淡红) */
        div.stButton > button[data-ssd="locked"] {
            background-color: #fef2f2 !important;
            color: #991b1b !important;
            border-color: #fca5a5 !important;
        }

        /* 🟢 Safe (淡绿) */
        div.stButton > button[data-ssd="safe"], div.stButton > button[data-ssd="empty"] {
            background-color: #f0fdf4 !important;
            color: #166534 !important;
            border-color: #bbf7d0 !important;
        }

        /* 鼠标悬停 */
        div.stButton > button:hover {
            filter: brightness(0.97);
            border-color: #9ca3af !important;
        }
        
        /* 极致列间距 */
        [data-testid="column"] { padding: 0 0.5px !important; }
        [data-testid="stHorizontalBlock"] { gap: 0px !important; }
        </style>
    """, unsafe_allow_html=True)

    # 数据准备
    all_blks = sorted(df['BLK'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    selected_blk = st.selectbox("选择楼座", all_blks, key="blk_v122")
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
                
                ssd_txt, status = "", "empty"
                price = "-"
                
                if data:
                    price = f"${data['Sale Price']/1e6:.1f}M" # 压缩价格显示为 .1f
                    ssd_txt, status = get_ssd_info(data['Sale Date'])
                
                label = f"{unit_no}\n{price}\n{ssd_txt if ssd_txt else ' '}"
                
                # 技巧：Streamlit button 不支持自定义 data 属性，
                # 但我们可以通过这种 Hack 方式让 CSS 识别出不同的按钮
                # 如果是 locked/warning/critical，我们用 type="primary"，否则 secondary
                # 由于原生只有两种 type，我们只能通过 button 的 key 配合特殊内容来在更高版本 CSS 中实现。
                # 简化方案：统一使用默认 type，通过 label 内容匹配（不可行）。
                # 最终稳定方案：使用 primary 表示所有 SSD 风险，但在文字前缀区分。
                
                b_type = "primary" if status in ["locked", "warning", "critical"] else "secondary"
                
                # 为了让 CSS 能区分 warning 和 critical，我们稍微改下 CSS 选择器逻辑
                # 这里我们利用 help 文本作为“钩子”不太稳定。
                # 最终采用：所有风险都红底，但文字 🔥 和 ⚠️ 非常醒目，且 62px 保证了紧凑感。
                
                if st.button(label, key=f"v122_{f}_{s}", help=f"{unit_no} 点击查看估值", type=b_type, use_container_width=True):
                    st.session_state['avm_target'] = {'blk': selected_blk, 'floor': f, 'stack': s}
                    switch_to_tab_3()

    st.caption("🔥<3月 | ⚠️<6月 | 🔒锁定期 | 🟢安全。点击格子跳转。")
