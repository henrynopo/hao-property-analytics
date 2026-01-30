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
    
    # 确保时间格式
    if 'Sale Date' in df.columns:
        df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
        
    return df

def get_ssd_display(purchase_date):
    if pd.isna(purchase_date): return "", "" # 无交易记录时不显示SSD
    
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline: return "🟩", "无SSD"

    days_left = (ssd_deadline - today).days
    years_held = relativedelta(today, purchase_date).years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    # 简化显示以节省空间
    if days_left < 90: return "🟨", f"{rate}"
    elif days_left < 180: return "🟧", f"{rate}"
    else: return "🟥", f"{rate}"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

def shorten_type(type_str):
    if not isinstance(type_str, str): return "-"
    # 缩写户型名称节省空间
    return type_str.replace("Bedroom", "Bed").replace("Maisonette", "Mais").replace("Apartment", "Apt")

# --- 2. 渲染主函数 ---
def render(df_raw, chart_font_size=12):
    # 跳转执行器
    if st.session_state.get('trigger_tab_switch'):
        components.html("""<script>
            var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length > 2) { tabs[2].click(); window.parent.scrollTo(0, 0); }
        </script>""", height=0)
        st.session_state['trigger_tab_switch'] = False

    st.subheader("🏢 楼宇透视 (Building View)")
    
    # 预处理数据
    df = clean_data(df_raw)
    
    # CSS: 调整按钮高度以容纳更多信息
    st.markdown("""
        <style>
        div.stButton > button {
            width: 100%;
            padding: 2px 0px !important;
            font-size: 10px !important; 
            line-height: 1.2 !important;
            min-height: 75px !important; /* 增加高度 */
            height: auto !important;
            background-color: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            color: #1f2937 !important;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        div.stButton > button:hover {
            border-color: #2563eb !important;
            background-color: #eff6ff !important;
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
    
    # 处理楼层排序
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    
    # 构建交易映射 (最新一笔)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # 构建静态信息补全映射 (Stack -> Mode Type/Area)
    # 用于补全没有交易记录的单元
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
    
    # 分段渲染
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
                    
                    # 1. 尝试获取本单元交易数据
                    tx_data = tx_map.get((f, s))
                    
                    # 2. 准备显示数据
                    if tx_data:
                        # 有交易：显示真实数据
                        u_type = shorten_type(str(tx_data.get('Type', '-')))
                        u_area = f"{int(tx_data.get('Area (sqft)', 0)):,}"
                        ssd_icon, ssd_txt = get_ssd_display(tx_data['Sale Date'])
                    else:
                        # 无交易：从 Stack 推断 (智能补全)
                        stack_defaults = stack_info_map.get(s, {})
                        u_type = shorten_type(str(stack_defaults.get('type', '-')))
                        val_area = stack_defaults.get('area', 0)
                        u_area = f"{int(val_area):,}" if val_area > 0 else "-"
                        ssd_icon, ssd_txt = "", "" # 无交易自然无 SSD 状态

                    # 3. 组合 Label (4行结构)
                    # Line 1: 单元号
                    # Line 2: 户型
                    # Line 3: 面积
                    # Line 4: SSD
                    
                    # 如果没有SSD，为了美观可以留空或不显示
                    ssd_line = f"{ssd_icon} {ssd_txt}" if ssd_icon else "⚪" 
                    
                    label = f"{unit_no}\n{u_type}\n{u_area} sqft\n{ssd_line}"
                    
                    st.button(
                        label, 
                        key=f"btn_{selected_blk}_{f}_{s}", 
                        type="secondary",
                        use_container_width=True,
                        on_click=go_to_valuation,
                        args=(selected_blk, f, s)
                    )
        if len(stack_chunks) > 1: st.divider()

    # 图例
    st.markdown("---")
    st.info("🟨 0-3月 | 🟧 3-6月 | 🟥 6月以上 | 🟩 无SSD (已过禁售期)")
    
    # 底部列表逻辑保持精简
    with st.expander("🚀 全局机会扫描 (即将解禁)", expanded=False):
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
