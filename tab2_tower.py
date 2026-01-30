# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 核心跳转逻辑 (无刷新) ---
# 使用 Streamlit 回调机制，这是最稳的方式
def go_to_valuation(blk, floor, stack):
    # 1. 更新数据目标
    st.session_state['avm_target'] = {
        'blk': blk,
        'floor': int(f),
        'stack': stack
    }
    # 2. 设置触发器，渲染完成后由 JS 负责切换 Tab
    st.session_state['trigger_tab_switch'] = True

# --- 1. SSD 状态计算 ---
def get_ssd_display(purchase_date):
    if pd.isna(purchase_date): return "⚪", "无记录", "secondary"
    
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline: return "🟩", "Safe", "secondary"

    days_left = (ssd_deadline - today).days
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    # 返回: (图标, 简短文字, 按钮样式)
    # 注意: Streamlit 原生按钮只有 primary(红) 和 secondary(白)
    if days_left < 90: return "🟨", f"{rate} ({days_left}d)", "primary"
    elif days_left < 180: return "🟧", f"{rate} ({int(days_left/30)}m)", "primary"
    else: return "🟥", f"{rate} SSD", "primary"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# --- 2. 渲染主函数 ---
def render(df, chart_font_size=12):
    # A. 检查并执行跳转 (仅在 Python 状态更新后执行一次 JS)
    if st.session_state.get('trigger_tab_switch'):
        js = """
        <script>
            // 简单直接：找到第三个Tab并点击
            var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length > 2) {
                tabs[2].click();
                window.parent.scrollTo(0, 0);
            }
        </script>
        """
        components.html(js, height=0)
        st.session_state['trigger_tab_switch'] = False # 重置，防止反复跳转

    st.subheader("🏢 楼宇透视 (Building View)")
    
    # CSS: 紧凑化原生按钮
    st.markdown("""
        <style>
        /* 让按钮更紧凑，适合网格显示 */
        div.stButton > button {
            width: 100%;
            padding: 4px 0px !important;
            font-size: 11px !important;
            line-height: 1.2 !important;
            min-height: 55px !important;
            height: auto !important;
        }
        /* 稍微调整列间距 */
        [data-testid="column"] { padding: 0 2px !important; }
        </style>
    """, unsafe_allow_html=True)

    # B. 楼座选择
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    st.write("选择楼座 (Block):")
    cols_per_row = 8
    rows = [all_blks[i:i + cols_per_row] for i in range(0, len(all_blks), cols_per_row)]
    for row_blks in rows:
        cols = st.columns(len(row_blks))
        for idx, blk in enumerate(row_blks):
            with cols[idx]:
                b_type = "primary" if st.session_state.selected_blk == blk else "secondary"
                if st.button(blk, key=f"blk_{blk}", type=b_type, use_container_width=True):
                    st.session_state.selected_blk = blk
                    st.rerun()

    # C. 楼宇数据准备
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    st.markdown("---")
    
    # D. 智能分段渲染 (解决 10M 横向太宽的问题)
    # 如果 Stack 超过 10 个，我们把它切分成多组显示
    chunk_size = 10
    stack_chunks = [all_stacks[i:i + chunk_size] for i in range(0, len(all_stacks), chunk_size)]

    for chunk_idx, current_stacks in enumerate(stack_chunks):
        # 如果有多个分段，显示分段标题
        if len(stack_chunks) > 1:
            st.caption(f"📍 {selected_blk} - Part {chunk_idx + 1} (Stacks {current_stacks[0]} ~ {current_stacks[-1]})")
        
        # 遍历楼层渲染按钮
        for f in floors:
            cols = st.columns(len(current_stacks))
            for i, s in enumerate(current_stacks):
                with cols[i]:
                    unit_no = format_unit(f, s)
                    data = tx_map.get((f, s))
                    
                    # 默认空状态
                    label = f"{unit_no}\n-\n "
                    b_type = "secondary"
                    
                    if data:
                        price = f"${data['Sale Price']/1e6:.1f}M"
                        icon, txt, b_style = get_ssd_display(data['Sale Date'])
                        
                        # 按钮文字布局:
                        # #05-40
                        # $1.5M
                        # 🟥 12% SSD
                        label = f"{unit_no}\n{price}\n{icon} {txt}"
                        b_type = b_style # 只要有SSD风险就是 Primary(红)，具体颜色看 Emoji
                    
                    # 原生按钮点击
                    # 注意：这里使用 on_click 回调，不涉及 URL，绝对稳定
                    st.button(
                        label, 
                        key=f"btn_{selected_blk}_{f}_{s}", 
                        type=b_type, 
                        use_container_width=True,
                        on_click=go_to_valuation,
                        args=(selected_blk, f, s)
                    )
        
        # 分段之间加一点间隔
        if len(stack_chunks) > 1:
            st.divider()

    # E. 图例说明
    st.info("图例说明：🟩 Safe (无税) | 🟨 0-3月 (极危) | 🟧 3-6月 (高危) | 🟥 6月+ (锁定)")
