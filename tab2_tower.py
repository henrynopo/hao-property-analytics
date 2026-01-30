# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import html
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 黑科技：强制跳转 Tab ---
def switch_to_tab_3():
    js = """
    <script>
        var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
        if (tabs.length > 2) {
            tabs[2].click();
        }
    </script>
    """
    components.html(js, height=0)

# --- 1. 辅助：Stack/Floor 格式化 ---
def format_unit(floor, stack):
    f_str = f"{int(floor):02d}"
    s_str = str(stack)
    if s_str.isdigit():
        s_str = f"{int(s_str):02d}"
    return f"#{f_str}-{s_str}"

# --- 2. SSD 计算核心 ---
def check_ssd_status(purchase_date):
    if pd.isna(purchase_date): return False, "", "", "free"
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
        
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    POLICY_2017 = pd.Timestamp("2017-03-11")
    
    if purchase_date >= POLICY_2025:
        lock_years = 4
        desc = "4年"
    elif purchase_date >= POLICY_2017:
        lock_years = 3
        desc = "3年"
    else:
        lock_years = 4
        desc = "4年"
        
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today < ssd_deadline:
        days_left = (ssd_deadline - today).days
        months_left = days_left / 30.0
        
        if days_left < 90:
            short = f"🔥 剩{days_left}天"
        elif days_left < 180:
            short = f"⚠️ 剩{int(months_left)}月"
        else:
            if months_left > 12:
                short = f"🔒 {months_left/12:.1f}年"
            else:
                short = f"🔒 {int(months_left)}月"

        full = f"状态: 🔒 锁定期 ({desc})\n到期: {ssd_deadline.strftime('%Y-%m-%d')}\n({short})"
        return True, short, full, "locked"
    else:
        return False, "", "状态: ✅ SSD 已解禁", "free"

# --- 3. 自然排序 ---
def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# --- 4. 主渲染函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")

    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if not all_blks:
        st.warning("数据为空")
        return
    selected_blk = st.selectbox("选择楼座 (Block)", all_blks, key="tab2_blk_select")
    blk_df = df[df['BLK'] == selected_blk].copy()

    if 'Floor_Num' in blk_df.columns:
        blk_df['Floor_Sort'] = blk_df['Floor_Num'].fillna(0).astype(int)
    else:
        blk_df['Floor_Sort'] = blk_df['Floor'].astype(str).str.extract(r'(\d+)')[0].fillna(0).astype(int)

    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    if not blk_df.empty:
        min_floor = int(blk_df['Floor_Sort'].min())
        max_floor = int(blk_df['Floor_Sort'].max())
        floors_desc = sorted(list(range(min_floor, max_floor + 1)), reverse=True)
    else:
        floors_desc = []

    tx_map = {}
    if not blk_df.empty:
        latest_tx = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1)
        for _, row in latest_tx.iterrows():
            key = (int(row['Floor_Sort']), row['Stack'])
            tx_map[key] = row

    if not all_stacks:
        st.info("该楼座无 Stack 信息")
        return

    num_cols = len(all_stacks)
    
    # 🟢 CSS 核心修正：强制 white-space: pre-wrap
    st.markdown("""
    <style>
    [data-testid="column"] {
        padding: 0rem 0.15rem !important;
    }
    
    /* 强制按钮内容原样显示，支持换行符 */
    div.stButton > button {
        width: 100%;
        white-space: pre !important;  /* 关键：pre 才能严格保留换行 */
        min-height: 80px !important;  /* 增加高度，确保三行不拥挤 */
        height: auto !important;
        padding: 6px 2px !important;
        line-height: 1.5 !important;  /* 增加行间距 */
        font-size: 13px !important;
        display: block !important;    /* 块级显示 */
    }
    
    /* 按钮内部的 span 也要配合 */
    div.stButton > button > div {
        display: block !important;
    }

    div.stButton > button[kind="primary"] {
        background-color: #fef2f2 !important;
        color: #991b1b !important;
        border: 1px solid #f87171 !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #fee2e2 !important;
        border-color: #ef4444 !important;
    }
    
    div.stButton > button[kind="secondary"] {
        background-color: #f0fdf4 !important;
        border: 1px solid #bbf7d0 !important;
        color: #166534 !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        background-color: #dcfce7 !important;
        border-color: #86efac !important;
    }
    </style>
    """, unsafe_allow_html=True)

    for floor in floors_desc:
        cols = st.columns(num_cols)
        
        for i, stack in enumerate(all_stacks):
            with cols[i]:
                unit_label = format_unit(floor, stack)
                row_data = tx_map.get((floor, stack))
                
                if row_data is not None:
                    price = f"${row_data['Sale Price']/1e6:.2f}M"
                    s_date = row_data['Sale Date']
                    is_locked, short_status, full_ssd_msg, level = check_ssd_status(s_date)
                    
                    if is_locked:
                        # 🔴 三行结构 (强制换行)
                        btn_label = f"{unit_label}\n{price}\n{short_status}"
                        btn_type = "primary"
                        tooltip = f"{unit_label}\n成交: {s_date.strftime('%Y-%m-%d')}\n{full_ssd_msg}"
                    else:
                        # 🟢 三行结构 (第三行放个空格占位，保证对齐)
                        btn_label = f"{unit_label}\n{price}\n " 
                        btn_type = "secondary"
                        tooltip = f"{unit_label}\n成交: {s_date.strftime('%Y-%m-%d')}\n状态: ✅ SSD Free"
                        
                else:
                    # ⚪ 三行结构
                    btn_label = f"{unit_label}\n-\n "
                    btn_type = "secondary"
                    tooltip = f"{unit_label}\n暂无历史交易"

                btn_key = f"btn_{selected_blk}_{floor}_{stack}"
                
                if st.button(btn_label, key=btn_key, help=tooltip, type=btn_type, use_container_width=True):
                    st.session_state['avm_target'] = {
                        'blk': selected_blk,
                        'floor': floor,
                        'stack': stack
                    }
                    switch_to_tab_3()

    st.caption("🔴 **红底**：SSD 期内；🟢 **绿底**：SSD 安全或无记录。信息分为三行：单元号、价格、状态。")
