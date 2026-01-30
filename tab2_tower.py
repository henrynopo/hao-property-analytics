# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 强力跳转 JS ---
def switch_to_tab_3():
    # 通过 JS 模拟点击 Tab 3 按钮
    js = """
    <script>
        window.parent.document.querySelectorAll('button[data-baseweb="tab"]')[2].click();
    </script>
    """
    components.html(js, height=0)

# --- 1. SSD 2025 政策逻辑 ---
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

    # 计算税率 (4年制: 16/12/8/4; 3年制: 12/8/4)
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    days_left = (ssd_deadline - today).days
    
    if days_left < 90: return f"🔥{rate}({days_left}d)", "critical"  # 3月内
    if days_left < 180: return f"⚠️{rate}({days_left//30}m)", "warning" # 6月内
    return f"{rate} SSD", "locked"

# --- 2. 补零格式化 ---
def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

# --- 3. 渲染主逻辑 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # 💉 暴力 CSS：锁定布局与颜色
    st.markdown("""
        <style>
        /* 强制按钮样式：三行对齐，尊重换行 */
        div.stButton > button {
            width: 100% !important;
            min-height: 85px !important;
            padding: 5px 2px !important;
            border-radius: 4px !important;
            white-space: pre !important;  /* 强制保留 Python 的 \\n */
            line-height: 1.4 !important;
            font-size: 13px !important;
            font-family: monospace !important; /* 等宽字体对齐更好 */
            border: 1px solid #e5e7eb !important;
            transition: all 0.1s !important;
        }
        
        /* 🔴 SSD 锁定 (红) */
        div.stButton > button[kind="primary"] {
            background-color: #fef2f2 !important;
            color: #991b1b !important;
            border-color: #f87171 !important;
        }

        /* 🟢 SSD 安全/无记录 (绿/白) */
        div.stButton > button[kind="secondary"] {
            background-color: #f0fdf4 !important;
            color: #166534 !important;
            border-color: #bbf7d0 !important;
        }

        /* 统一 Hover 效果 */
        div.stButton > button:hover {
            filter: brightness(0.95);
            transform: scale(1.02);
            z-index: 10;
        }
        
        /* 调整列间距 */
        [data-testid="column"] { padding: 0 1px !important; }
        </style>
    """, unsafe_allow_html=True)

    # 数据准备
    all_blks = sorted(df['BLK'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    selected_blk = st.selectbox("选择楼座", all_blks, key="blk_v121")
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    
    if blk_df.empty: return
    
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # 循环渲染格子
    for f in floors:
        cols = st.columns(len(all_stacks))
        for i, s in enumerate(all_stacks):
            with cols[i]:
                unit_no = format_unit(f, s)
                data = tx_map.get((f, s))
                
                if data:
                    price = f"${data['Sale Price']/1e6:.2f}M"
                    ssd_txt, status = get_ssd_info(data['Sale Date'])
                    # 构造三行：单元号 \n 价格 \n SSD信息
                    label = f"{unit_no}\n{price}\n{ssd_txt if ssd_txt else ' '}"
                    # 只有锁定的用 primary (红色)，安全的用 secondary (绿色)
                    b_type = "primary" if status in ["locked", "warning", "critical"] else "secondary"
                else:
                    # 无数据单元格 (显示为绿色安全背景，但文字为空)
                    label = f"{unit_no}\n-\n "
                    b_type = "secondary"

                # 渲染按钮，点击即触发跳转
                if st.button(label, key=f"btn_v121_{f}_{s}", type=b_type, use_container_width=True):
                    st.session_state['avm_target'] = {'blk': selected_blk, 'floor': f, 'stack': s}
                    switch_to_tab_3()

    st.caption("🔴 红底: SSD期内 (显示%及剩余时间) | 🟢 绿底: 安全/无记录。点击格子直接跳转估值。")
