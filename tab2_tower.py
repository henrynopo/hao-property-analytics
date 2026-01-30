# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 核心跳转逻辑 ---
# 使用回调函数确保 Session State 在 Rerun 前被安全更新
def go_to_valuation(blk, floor, stack):
    st.session_state['avm_target'] = {
        'blk': blk,
        'floor': int(floor),
        'stack': stack
    }
    # 注入一段一次性 JS 来点击 Tab 3
    # 这种方式比 URL Hack 稳得多
    st.session_state['trigger_jump'] = True

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
    
    # 使用 Emoji 做视觉区分，因为原生按钮背景色只有两种
    if days_left < 90: return f"🔥{rate}({days_left}d)", "hot" 
    elif days_left < 180: return f"⚠️{rate}({days_left//30}m)", "warm" 
    else: return f"🔒{rate}", "locked"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# --- 2. 渲染主函数 ---
def render(df, chart_font_size=12):
    # 处理跳转触发
    if st.session_state.get('trigger_jump'):
        js = """
        <script>
            var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length > 2) { tabs[2].click(); }
        </script>
        """
        components.html(js, height=0)
        st.session_state['trigger_jump'] = False # 重置触发器

    st.subheader("🏢 楼宇透视 (Building View)")
    
    # 💉 CSS 魔法：强制启用原生组件的横向滚动
    st.markdown("""
        <style>
        /* 1. 强制让 st.columns 的容器不换行，且允许横向滚动 */
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            padding-bottom: 10px !important; /* 预留滚动条空间 */
        }
        
        /* 2. 强制每个列（单元格）保持最小宽度，防止 10M 挤压 */
        div[data-testid="column"] {
            flex: 0 0 auto !important;
            min-width: 90px !important; /* 核心：每个格子至少90px宽 */
            width: auto !important;
        }

        /* 3. 美化滚动条 */
        div[data-testid="stHorizontalBlock"]::-webkit-scrollbar { height: 8px; }
        div[data-testid="stHorizontalBlock"]::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }

        /* 4. 按钮样式微调 (紧凑化) */
        div.stButton > button {
            width: 100%;
            padding: 4px 2px !important;
            font-size: 12px !important;
            line-height: 1.3 !important;
            height: auto !important;
            min-height: 64px !important;
            white-space: pre !important; /* 允许换行 */
        }
        
        /* 红色高亮按钮样式微调 */
        div.stButton > button[kind="primary"] {
            background-color: #fef2f2 !important;
            color: #991b1b !important;
            border: 1px solid #fca5a5 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------
    # A. 楼座选择 (原生按钮，稳)
    # -------------------------------------------------------
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    st.write("选择楼座 (Block):")
    # 为了避免楼座选择器也出现横向滚动条，我们手动控制它的分行
    # 这里我们不用 st.columns(len)，而是分批次显示
    cols_per_row = 8
    rows = [all_blks[i:i + cols_per_row] for i in range(0, len(all_blks), cols_per_row)]
    
    for row_blks in rows:
        # 使用 standard columns 布局（不受上面 CSS min-width 影响太严重，因为我们手动控制了数量）
        cols = st.columns(len(row_blks)) 
        for idx, blk in enumerate(row_blks):
            with cols[idx]:
                b_type = "primary" if st.session_state.selected_blk == blk else "secondary"
                if st.button(blk, key=f"blk_{blk}", type=b_type, use_container_width=True):
                    st.session_state.selected_blk = blk
                    st.rerun()

    # -------------------------------------------------------
    # B. 楼宇网格 (原生按钮 + CSS Scroll)
    # -------------------------------------------------------
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    st.markdown("---")
    st.caption(f"当前显示: Block {selected_blk} (共 {len(all_stacks)} 个 Stack) | ↔️ 内容较宽时请左右滑动")
    
    for f in floors:
        # 这里的 st.columns 会被 CSS 强制变成横向滚动容器
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
                    
                    # 只要有 SSD 风险，就用 Primary (红色边框)
                    # 具体的黄/橙/红靠文字前缀区分
                    if status in ["hot", "warm", "locked"]: 
                        b_type = "primary"
                    
                    label = f"{unit_no}\n{price}\n{ssd_txt if ssd_txt else ' '}"
                    help_txt = f"点击估值\n成交价: {price}\nSSD状态: {ssd_txt}"

                # 原生回调：点击直接修改 Session State
                st.button(label, key=f"u_{selected_blk}_{f}_{s}", type=b_type, help=help_txt, 
                          use_container_width=True, 
                          on_click=go_to_valuation, args=(selected_blk, f, s))

    # -------------------------------------------------------
    # C. 全局预警 (原生列表)
    # -------------------------------------------------------
    st.markdown("---")
    st.caption("🔴 SSD锁定 | 🔥 0-3月 | ⚠️ 3-6月 | ⚪ 安全")

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
            st.markdown("##### 🔥 0-3月")
            for item in hot_list:
                st.button(f"{item['label']}  {item['ssd']}", key=f"hot_{item['label']}",
                          on_click=go_to_valuation, args=(item['blk'], item['f'], item['s']))
        with c2:
            st.markdown("##### ⚠️ 3-6月")
            for item in warm_list:
                st.button(f"{item['label']}  {item['ssd']}", key=f"warm_{item['label']}",
                          on_click=go_to_valuation, args=(item['blk'], item['f'], item['s']))
