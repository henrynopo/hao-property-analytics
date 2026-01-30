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
    """
    将楼层和单元号格式化为本地标准: #05-02
    Stack 如果是数字字符串 '2' -> '02', '10' -> '10', '10A' -> '10A'
    """
    # 格式化 Floor: 5 -> 05
    f_str = f"{int(floor):02d}"
    
    # 格式化 Stack
    s_str = str(stack)
    if s_str.isdigit():
        s_str = f"{int(s_str):02d}"
    
    return f"#{f_str}-{s_str}"

# --- 2. SSD 计算核心 (含临期预警) ---
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
        
        # 临期预警逻辑
        if days_left < 90:
            short = f"🔥 剩{days_left}天"
            level = "critical" # < 3个月
        elif days_left < 180:
            short = f"⚠️ 剩{int(months_left)}月"
            level = "warning"  # < 6个月
        else:
            # 显示剩余年/月
            if months_left > 12:
                short = f"🔒 SSD:{months_left/12:.1f}年"
            else:
                short = f"🔒 SSD:{int(months_left)}月"
            level = "locked"

        full = f"状态: 🔒 锁定期 ({desc})\n到期: {ssd_deadline.strftime('%Y-%m-%d')}\n({short})"
        return True, short, full, level
    else:
        return False, "", "状态: ✅ SSD 已解禁", "free"

# --- 3. 自然排序 ---
def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# --- 4. 主渲染函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")

    # A. 筛选 Block
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if not all_blks:
        st.warning("数据为空")
        return
    selected_blk = st.selectbox("选择楼座 (Block)", all_blks, key="tab2_blk_select")
    blk_df = df[df['BLK'] == selected_blk].copy()

    # B. 构建骨架
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

    # C. 准备交易数据
    tx_map = {}
    if not blk_df.empty:
        latest_tx = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1)
        for _, row in latest_tx.iterrows():
            key = (int(row['Floor_Sort']), row['Stack'])
            tx_map[key] = row

    # D. 渲染网格
    if not all_stacks:
        st.info("该楼座无 Stack 信息")
        return

    num_cols = len(all_stacks)
    
    # 注入 CSS 强化视觉
    # Primary (Red/Orange/Yellow 统一样式，通过文字区分) -> 红色警戒
    # Secondary (White) -> 安全
    st.markdown("""
    <style>
    /* SSD 锁定期 (Primary) - 统一红底，强调风险 */
    div.stButton > button[kind="primary"] {
        background-color: #fef2f2 !important;
        color: #991b1b !important;
        border: 1px solid #f87171 !important;
        white-space: pre-wrap !important; /* 允许换行 */
        height: auto !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
        line-height: 1.4 !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #fee2e2 !important;
        border-color: #ef4444 !important;
    }
    
    /* SSD 安全 (Secondary) - 白底绿字hover */
    div.stButton > button[kind="secondary"] {
        background-color: #ffffff !important;
        border: 1px solid #e5e7eb !important;
        color: #1f2937 !important;
        white-space: pre-wrap !important;
        height: auto !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
        line-height: 1.4 !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        background-color: #f0fdf4 !important;
        border-color: #86efac !important;
        color: #166534 !important;
    }
    
    /* 缩小列间距 */
    [data-testid="column"] {
        padding: 0rem 0.2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 循环渲染行
    for floor in floors_desc:
        cols = st.columns(num_cols)
        
        for i, stack in enumerate(all_stacks):
            with cols[i]:
                # 1. 准备数据
                unit_label = format_unit(floor, stack)
                row_data = tx_map.get((floor, stack))
                
                # 2. 构造按钮样式
                if row_data is not None:
                    # [有交易]
                    price = f"${row_data['Sale Price']/1e6:.2f}M"
                    s_date = row_data['Sale Date']
                    is_locked, short_status, full_ssd_msg, level = check_ssd_status(s_date)
                    
                    # 按钮标签构造 (三行结构)
                    # Line 1: 单元号
                    # Line 2: 价格
                    # Line 3: SSD (仅当 Locked 时显示)
                    
                    if is_locked:
                        # 🔒 SSD 期内
                        btn_label = f"{unit_label}\n{price}\n{short_status}"
                        btn_type = "primary" # 触发红色样式
                        tooltip = f"{unit_label}\n成交: {s_date.strftime('%Y-%m-%d')}\n{full_ssd_msg}"
                    else:
                        # ✅ SSD 安全 (不显示 SSD 字样)
                        btn_label = f"{unit_label}\n{price}\n " # 第三行留空保持对齐，或者去掉
                        # 优化：为了对齐，可以不换行，或者换行但没字
                        btn_label = f"{unit_label}\n{price}"
                        btn_type = "secondary" # 触发白色样式
                        tooltip = f"{unit_label}\n成交: {s_date.strftime('%Y-%m-%d')}\n状态: SSD Free (安全)"
                        
                else:
                    # [无交易]
                    btn_label = f"{unit_label}\n-\n "
                    btn_type = "secondary"
                    tooltip = f"{unit_label}\n暂无历史记录"

                # 3. 渲染按钮
                btn_key = f"btn_{selected_blk}_{floor}_{stack}"
                
                if st.button(btn_label, key=btn_key, help=tooltip, type=btn_type, use_container_width=True):
                    st.session_state['avm_target'] = {
                        'blk': selected_blk,
                        'floor': floor,
                        'stack': stack
                    }
                    switch_to_tab_3()

    st.caption("🔴 **红色** = SSD期内 (🔥<3月 | ⚠️<6月 | 🔒>6月)；⚪ **白色** = SSD安全或无记录。点击跳转估值。")
