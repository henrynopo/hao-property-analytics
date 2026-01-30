# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 核心跳转逻辑 ---
def go_to_valuation(blk, floor, stack):
    st.session_state['avm_target'] = {
        'blk': blk,
        'floor': int(floor),
        'stack': stack
    }
    st.session_state['trigger_tab_switch'] = True

# --- 1. SSD 状态计算 ---
def get_ssd_display(purchase_date):
    if pd.isna(purchase_date): return "⚪", "无记录"
    
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    # 修改点：将 Safe 改为 Free，代表“自由/无税”
    if today >= ssd_deadline: return "🟩", "Free"

    days_left = (ssd_deadline - today).days
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    if days_left < 90: return "🟨", f"{rate} (剩{days_left}天)"
    elif days_left < 180: return "🟧", f"{rate} (剩{int(days_left/30)}月)"
    else: return "🟥", f"{rate} SSD"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# --- 2. 渲染主函数 ---
def render(df, chart_font_size=12):
    # 跳转执行器
    if st.session_state.get('trigger_tab_switch'):
        components.html("""<script>
            var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length > 2) { tabs[2].click(); window.parent.scrollTo(0, 0); }
        </script>""", height=0)
        st.session_state['trigger_tab_switch'] = False

    st.subheader("🏢 楼宇透视 (Building View)")
    
    # CSS: 极简白底风格
    st.markdown("""
        <style>
        div.stButton > button {
            width: 100%;
            padding: 4px 0px !important;
            font-size: 11px !important;
            line-height: 1.3 !important;
            min-height: 60px !important;
            height: auto !important;
            background-color: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            color: #1f2937 !important;
        }
        div.stButton > button:hover {
            border-color: #6b7280 !important;
            background-color: #f9fafb !important;
        }
        [data-testid="column"] { padding: 0 2px !important; }
        </style>
    """, unsafe_allow_html=True)

    # 楼座选择
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

    # 数据准备
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    st.markdown("---")
    
    # 智能分段渲染
    chunk_size = 10
    stack_chunks = [all_stacks[i:i + chunk_size] for i in range(0, len(all_stacks), chunk_size)]

    for chunk_idx, current_stacks in enumerate(stack_chunks):
        if len(stack_chunks) > 1:
            st.caption(f"📍 {selected_blk} - Part {chunk_idx + 1} (Stacks {current_stacks[0]} ~ {current_stacks[-1]})")
        
        for f in floors:
            cols = st.columns(len(current_stacks))
            for i, s in enumerate(current_stacks):
                with cols[i]:
                    unit_no = format_unit(f, s)
                    data = tx_map.get((f, s))
                    
                    label = f"{unit_no}\n-\n "
                    if data:
                        price = f"${data['Sale Price']/1e6:.1f}M"
                        icon, txt = get_ssd_display(data['Sale Date'])
                        label = f"{unit_no}\n{price}\n{icon} {txt}"
                    
                    st.button(
                        label, 
                        key=f"btn_{selected_blk}_{f}_{s}", 
                        type="secondary",
                        use_container_width=True,
                        on_click=go_to_valuation,
                        args=(selected_blk, f, s)
                    )
        if len(stack_chunks) > 1: st.divider()

    # 全局猎盘清单 (图例已更新)
    st.markdown("---")
    st.info("💡 狩猎指南：🟨 0-3月 (黄金窗口/可谈) | 🟧 3-6月 (保持关注) | 🟥 锁定中 | 🟩 Free (无税/自由)")
    
    with st.expander("🚀 全局机会扫描 (即将解禁单位)", expanded=False):
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor', 'Stack']).tail(1).copy()
        opportunity_list, watchlist = [], []
        
        for _, row in latest_txs.iterrows():
            icon, txt = get_ssd_display(row['Sale Date'])
            if "🟨" in icon:
                opportunity_list.append({"label": f"{icon} {format_unit(row['Floor'], row['Stack'])} @ {row['BLK']}\n{txt}", 
                                         "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']})
            elif "🟧" in icon:
                watchlist.append({"label": f"{icon} {format_unit(row['Floor'], row['Stack'])} @ {row['BLK']}\n{txt}",
                                  "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']})

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### ✨ 黄金机会 (0-3月)")
            if not opportunity_list: st.caption("暂无即将解禁单位")
            for item in opportunity_list:
                st.button(item['label'], key=f"opt_{item['blk']}_{item['f']}_{item['s']}", 
                          on_click=go_to_valuation, args=(item['blk'], item['f'], item['s']))
        with c2:
            st.markdown("##### ⏳ 重点观察 (3-6月)")
            if not watchlist: st.caption("暂无观察单位")
            for item in watchlist:
                st.button(item['label'], key=f"watch_{item['blk']}_{item['f']}_{item['s']}", 
                          on_click=go_to_valuation, args=(item['blk'], item['f'], item['s']))
