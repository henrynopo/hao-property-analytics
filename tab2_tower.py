import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 核心跳转逻辑 (回调函数) ---
def go_to_valuation(blk, floor, stack):
    st.session_state['avm_target'] = {
        'blk': blk,
        'floor': int(floor),
        'stack': stack
    }
    st.session_state['trigger_tab_switch'] = True

# --- 1. 数据清洗与辅助 ---
def clean_data(df_raw):
    df = df_raw.copy()
    rename_map = {
        'Bedroom Type': 'Type',
        'No. of Bedroom': 'Type',
        'Area (SQFT)': 'Area (sqft)',
        'Sale Date': 'Sale Date'
    }
    df.rename(columns=rename_map, inplace=True)
    if 'Sale Date' in df.columns:
        df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
    return df

def get_ssd_display(purchase_date):
    if pd.isna(purchase_date): return "", "" 
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline: return "🟩", "无SSD"

    days_left = (ssd_deadline - today).days
    years_held = relativedelta(today, purchase_date).years + 1
    
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate_str = rates.get(years_held, "4%")
    rate_val = int(rate_str.strip('%'))

    if days_left < 90: return "🟨", f"{rate_str}"
    elif days_left < 180: return "🟧", f"{rate_str}"
    
    if rate_val >= 12: return "⛔", f"{rate_str}"
    elif rate_val == 8: return "🛑", f"{rate_str}"
    else: return "🟥", f"{rate_str}"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

def shorten_type(type_str):
    if not isinstance(type_str, str): return "-"
    return type_str.replace("Bedroom", "Bed").replace("Maisonette", "Mais").replace("Apartment", "Apt")

# --- 2. 渲染主函数 ---
def render(df_raw, chart_font_size=12):
    df = clean_data(df_raw)
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    
    # 状态初始化
    if 'selected_blk' not in st.session_state:
        st.session_state.selected_blk = all_blks[0]
    elif st.session_state.selected_blk not in all_blks:
        st.session_state.selected_blk = all_blks[0]

    # [核心修复] 移除 key 参数，通过改变 HTML 内容(添加时间戳注释)来强制刷新
    if st.session_state.get('trigger_tab_switch', False):
        js_code = f"""
        <script>
            // Timestamp: {time.time()} (Force Re-run)
            var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length > 2) {{
                tabs[2].click();
                window.parent.scrollTo(0, 0);
            }}
        </script>
        """
        components.html(js_code, height=0) # 移除了 key 参数
        st.session_state['trigger_tab_switch'] = False

    st.subheader("🏢 楼宇透视 (Building View)")
    
    st.markdown("""
        <style>
        div.stButton > button {
            width: 100%;
            padding: 4px 2px !important;
            font-size: 11px !important; 
            line-height: 1.3 !important;
            min-height: 55px !important;
            height: auto !important;
            background-color: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            color: #1f2937 !important;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            white-space: pre-wrap;
        }
        div.stButton > button:hover {
            border-color: #2563eb !important;
            background-color: #eff6ff !important;
            transform: translateY(-1px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        [data-testid="column"] { padding: 0 2px !important; }
        </style>
    """, unsafe_allow_html=True)

    # Block Selector
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

    # Grid Render
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    stack_info_map = {}
    for s in all_stacks:
        s_data = blk_df[blk_df['Stack'] == s]
        if not s_data.empty:
            mode_type = s_data['Type'].mode()[0] if not s_data['Type'].empty else "-"
            mode_area = s_data['Area (sqft)'].mode()[0] if not s_data['Area (sqft)'].empty else 0
            stack_info_map[s] = {'type': mode_type, 'area': mode_area}
        else:
            stack_info_map[s] = {'type': "-", 'area': 0}

    st.markdown("---")
    
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
                    tx_data = tx_map.get((f, s))
                    
                    if tx_data:
                        u_type = shorten_type(str(tx_data.get('Type', '-')))
                        u_area = int(tx_data.get('Area (sqft)', 0))
                        ssd_icon, _ = get_ssd_display(tx_data['Sale Date'])
                    else:
                        stack_defaults = stack_info_map.get(s, {})
                        u_type = shorten_type(str(stack_defaults.get('type', '-')))
                        u_area = int(stack_defaults.get('area', 0))
                        ssd_icon = "" 

                    area_str = f"{u_area:,}sf" if u_area > 0 else "-"
                    line2_parts = [u_type, area_str]
                    if ssd_icon: line2_parts.append(ssd_icon)
                    line2_str = " | ".join(line2_parts)
                    label = f"{unit_no}\n{line2_str}"
                    
                    st.button(
                        label, 
                        key=f"btn_{selected_blk}_{f}_{s}", 
                        type="secondary",
                        use_container_width=True,
                        on_click=go_to_valuation,
                        args=(selected_blk, f, s)
                    )
        if len(stack_chunks) > 1: st.divider()

    st.markdown("---")
    st.info("图例: 🟩 无SSD | 🟨 <3个月 | 🟧 <6个月 | 🟥 4% | 🛑 8% | ⛔ ≥12%")
    
    with st.expander("🚀 全局机会扫描 (即将解禁)", expanded=False):
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor', 'Stack']).tail(1).copy()
        opportunity_list, watchlist = [], []
        
        for _, row in latest_txs.iterrows():
            icon, txt = get_ssd_display(row['Sale Date'])
            if "🟨" in icon:
                opportunity_list.append({"label": f"{icon} {format_unit(row['Floor'], row['Stack'])} @ {row['BLK']} ({txt})", 
                                         "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']})
            elif "🟧" in icon:
                watchlist.append({"label": f"{icon} {format_unit(row['Floor'], row['Stack'])} @ {row['BLK']} ({txt})",
                                  "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']})

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🟨 0-3月")
            if not opportunity_list: st.caption("暂无")
            for item in opportunity_list:
                st.button(item['label'], key=f"opt_{item['blk']}_{item['f']}_{item['s']}", 
                          on_click=go_to_valuation, args=(item['blk'], item['f'], item['s']))
        with c2:
            st.markdown("##### 🟧 3-6月")
            if not watchlist: st.caption("暂无")
            for item in watchlist:
                st.button(item['label'], key=f"watch_{item['blk']}_{item['f']}_{item['s']}", 
                          on_click=go_to_valuation, args=(item['blk'], item['f'], item['s']))
