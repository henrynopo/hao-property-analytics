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

# --- 1. SSD 计算核心 ---
def check_ssd_status(purchase_date):
    if pd.isna(purchase_date): return False, "无数据", 0
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
        short = f"SSD期内"
        full = f"状态: 🔒 锁定期 ({desc})\n剩余: {days_left} 天\n解锁: {ssd_deadline.strftime('%Y-%m-%d')}"
        return True, short, full
    else:
        return False, "Free", "状态: ✅ SSD 已解禁"

# --- 2. 辅助函数 ---
def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# --- 3. 主渲染函数 ---
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

    # 这里采用“伪装成卡片的按钮”策略
    # 我们构造按钮的 label，让它包含所有信息（通过换行符）
    
    num_cols = len(all_stacks)
    for floor in floors_desc:
        cols = st.columns(num_cols)
        
        for i, stack in enumerate(all_stacks):
            with cols[i]:
                # 1. 准备数据
                unit_label = f"#{floor:02d}-{stack}"
                row_data = tx_map.get((floor, stack))
                
                # 2. 构造按钮内容
                if row_data is not None:
                    # [有交易]
                    price = f"${row_data['Sale Price']/1e6:.2f}M"
                    psf = f"${row_data['Sale PSF']:,.0f} psf"
                    s_date = row_data['Sale Date']
                    is_locked, short_status, full_ssd_msg = check_ssd_status(s_date)
                    
                    # 关键逻辑：用 emoji 和文字排版来模拟“卡片”
                    # 🔒 #05-02
                    # $2.50M | $1200 psf
                    # SSD期内
                    
                    icon = "🔒" if is_locked else "✅"
                    status_line = "⛔ SSD期内" if is_locked else "🟢 SSD Free"
                    
                    btn_label = f"{unit_label} {icon}\n{price}\n{status_line}"
                    btn_help = f"单元: {unit_label}\n成交: {s_date.strftime('%Y-%m-%d')}\n总价: {price}\n尺价: {psf}\n{full_ssd_msg}"
                    
                    # 颜色提示：Streamlit 按钮只有 primary (红/主题色) 和 secondary (灰)
                    # 我们用 primary 标记有 SSD 风险的，用 secondary 标记安全的
                    btn_type = "primary" if is_locked else "secondary"
                    
                else:
                    # [无交易]
                    btn_label = f"{unit_label}\n-\n无记录"
                    btn_help = f"单元: {unit_label}\n暂无历史交易\n点击查看估值"
                    btn_type = "secondary"
                
                # 3. 渲染按钮 (作为卡片)
                btn_key = f"btn_{selected_blk}_{floor}_{stack}"
                
                # 使用 CSS Hack 调整 Primary 按钮颜色 (让它看起来是警告红)
                # 这段 CSS 只需要注入一次，这里为了代码简洁不重复注入
                
                if st.button(btn_label, key=btn_key, help=btn_help, type=btn_type, use_container_width=True):
                    st.session_state['avm_target'] = {
                        'blk': selected_blk,
                        'floor': floor,
                        'stack': stack
                    }
                    switch_to_tab_3()

    st.caption("🔴 **红色高亮按钮** (Primary) 表示 SSD 期内单位；⚪ **灰色按钮** (Secondary) 表示 SSD 安全或无记录。")
    
    # 注入 CSS 强化视觉区分
    # 让 primary button (SSD期内) 变红，让 secondary button (安全) 变白/绿
    # 注意：这会影响页面上所有的 primary button，但在这个 Tab 页面内是可以接受的
    st.markdown("""
    <style>
    /* 针对 SSD 期内的红色按钮 */
    div.stButton > button[kind="primary"] {
        background-color: #fee2e2;
        color: #991b1b;
        border: 1px solid #fca5a5;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #fecaca;
        border-color: #f87171;
        color: #7f1d1d;
    }
    
    /* 针对安全的灰色按钮 */
    div.stButton > button[kind="secondary"] {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        color: #374151;
    }
    div.stButton > button[kind="secondary"]:hover {
        background-color: #f0fdf4;
        border-color: #bbf7d0;
        color: #166534;
    }
    </style>
    """, unsafe_allow_html=True)
