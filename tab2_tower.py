# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 跳转脚本 ---
def switch_to_tab_3():
    js = """
    <script>
        var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
        if (tabs.length > 2) { tabs[2].click(); }
    </script>
    """
    components.html(js, height=0)

# --- 1. SSD 逻辑 ---
def get_ssd_info(purchase_date):
    if pd.isna(purchase_date): return "", "none"
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    if today >= ssd_deadline: return "", "safe"
    days_left = (ssd_deadline - today).days
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    if days_left < 90: return f"🔥{rate}({days_left}d)", "hot" 
    elif days_left < 180: return f"⚠️{rate}({days_left//30}m)", "warm" 
    else: return f"🔒{rate}", "locked"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# --- 2. 渲染主函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # 💉 CSS 魔法：启用横向滚动条 (Scroll Bar)
    st.markdown("""
        <style>
        /* 1. 强制列容器允许横向滚动 */
        div[data-testid="stHorizontalBlock"] {
            overflow-x: auto !important;
            flex-wrap: nowrap !important; /* 禁止换行，强制在同一行 */
            padding-bottom: 5px; /* 给滚动条留点空间 */
        }
        
        /* 2. 强制每个列（单元格）保持最小宽度，不被挤压 */
        div[data-testid="column"] {
            flex: 0 0 auto !important; /* 禁止自动收缩 */
            min-width: 80px !important; /* 设定最小宽度，确保内容完整 */
            width: auto !important;
        }

        /* 3. 美化滚动条 (Webkit) */
        div[data-testid="stHorizontalBlock"]::-webkit-scrollbar {
            height: 6px;
        }
        div[data-testid="stHorizontalBlock"]::-webkit-scrollbar-thumb {
            background-color: #d1d5db;
            border-radius: 4px;
        }

        /* 4. 按钮样式微调 */
        div.stButton > button {
            width: 100%;
            padding: 2px !important;
            font-size: 12px !important;
            line-height: 1.2 !important;
            border-radius: 4px !important;
            min-height: 60px !important;
            height: 60px !important;
            white-space: pre !important;
        }
        
        /* 颜色定义 */
        div.stButton > button[kind="primary"] {
            background-color: #fef2f2 !important; color: #991b1b !important; border: 1px solid #fca5a5 !important;
        }
        div.stButton > button[kind="secondary"] {
            background-color: #f9fafb !important; color: #111827 !important; border: 1px solid #e5e7eb !important;
        }
        
        /* 楼座选择按钮单独样式覆盖 (让它们看起来像 Tag) */
        /* 由于无法单独区分，我们接受它们也变宽，或者在下方单独处理 */
        </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------
    # A. 楼座选择
    # -------------------------------------------------------
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    st.write("选择楼座 (Block):")
    # 为了让楼座按钮不出现长长的横向滚动条，我们还是手动分行
    # CSS 会让每一行都变成 scrollable，但如果只有 8 个按钮，不会触发 scroll
    cols_per_row = 8
    rows = [all_blks[i:i + cols_per_row] for i in range(0, len(all_blks), cols_per_row)]
    
    for row_blks in rows:
        cols = st.columns(len(row_blks)) # 动态长度
        for idx, blk in enumerate(row_blks):
            with cols[idx]:
                b_type = "primary" if st.session_state.selected_blk == blk else "secondary"
                if st.button(blk, key=f"blk_{blk}", type=b_type, use_container_width=True):
                    st.session_state.selected_blk = blk
                    st.rerun()

    # -------------------------------------------------------
    # B. 楼宇网格 (带 Scroll Bar)
    # -------------------------------------------------------
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    st.markdown("---")
    st.caption(f"当前显示: Block {selected_blk} | ↔️ 内容较宽时，请左右滑动或按住 Shift+滚轮查看")
    
    for f in floors:
        # 这里 st.columns 会被 CSS 强制不换行，且溢出滚动
        cols = st.columns(len(all_stacks))
        for i, s in enumerate(all_stacks):
            with cols[i]:
                unit_no = format_unit(f, s)
                data = tx_map.get((f, s))
                
                label = f"{unit_no}\n-\n "
                b_type = "secondary"
                help_txt = "无历史记录"
                
                if data:
                    price = f"${data['Sale Price']/1e6:.1f}M"
                    ssd_txt, status = get_ssd_info(data['Sale Date'])
                    if status in ["hot", "warm", "locked"]: b_type = "primary"
                    label = f"{unit_no}\n{price}\n{ssd_txt if ssd_txt else ' '}"
                    help_txt = f"点击跳转估值\n成交价: {price}\n日期: {data['Sale Date'].strftime('%Y-%m-%d')}"

                if st.button(label, key=f"u_{selected_blk}_{f}_{s}", type=b_type, help=help_txt, use_container_width=True):
                    st.session_state['avm_target'] = {'blk': selected_blk, 'floor': f, 'stack': s}
                    switch_to_tab_3()

    # -------------------------------------------------------
    # C. 备注 & 预警
    # -------------------------------------------------------
    st.markdown("---")
    st.caption("🔴 SSD期内 (含 🔥3月内 / ⚠️6月内) | ⚪ 安全/无记录")

    with st.expander("🚀 全局 SSD 临期预警快报 (0-6个月)", expanded=False):
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor', 'Stack']).tail(1).copy()
        hot_list, warm_list = [], []
        for _, row in latest_txs.iterrows():
            txt, status = get_ssd_info(row['Sale Date'])
            if status in ["hot", "warm"]:
                info = {"label": f"{format_unit(row['Floor'], row['Stack'])} @ {row['BLK']}", "ssd": txt, 
                        "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']}
                if status == "hot": hot_list.append(info)
                else: warm_list.append(info)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🔥 0-3月 (Yellow/Red)")
            for item in hot_list:
                if st.button(f"{item['label']}  {item['ssd']}", key=f"hot_{item['label']}"):
                    st.session_state.selected_blk = item['blk']
                    st.session_state['avm_target'] = {'blk': item['blk'], 'floor': int(item['f']), 'stack': item['s']}
                    switch_to_tab_3()
        with c2:
            st.markdown("##### ⚠️ 3-6月 (Orange)")
            for item in warm_list:
                if st.button(f"{item['label']}  {item['ssd']}", key=f"warm_{item['label']}"):
                    st.session_state.selected_blk = item['blk']
                    st.session_state['avm_target'] = {'blk': item['blk'], 'floor': int(item['f']), 'stack': item['s']}
                    switch_to_tab_3()
