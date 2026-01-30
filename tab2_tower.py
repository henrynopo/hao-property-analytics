# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 1. SSD 核心计算函数 (共用) ---
def get_ssd_status(purchase_date):
    if pd.isna(purchase_date): 
        return "", "#f9fafb", "#9ca3af", "none"
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
    
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline:
        return "", "#f0fdf4", "#166534", "safe"

    days_left = (ssd_deadline - today).days
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    if days_left < 90: 
        return f"🔥{rate}({days_left}d)", "#fef08a", "#854d0e", "hot" # 黄色
    elif days_left < 180: 
        return f"⚠️{rate}({days_left//30}m)", "#fed7aa", "#9a3412", "warm" # 橙色
    else: 
        return f"{rate} SSD", "#fca5a5", "#7f1d1d", "locked" # 红色

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# --- 2. 渲染函数 ---
def render(df, chart_font_size=12):
    # --- 新增功能：SSD 0-6个月全局快报 ---
    with st.expander("🚀 全局 SSD 临期预警 (0-6个月单位快报)", expanded=True):
        # 扫描逻辑
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor', 'Stack']).tail(1).copy()
        
        hot_list = [] # 0-3月
        warm_list = [] # 3-6月
        
        for _, row in latest_txs.iterrows():
            txt, bg, tc, status = get_ssd_status(row['Sale Date'])
            unit_label = f"{format_unit(row['Floor'], row['Stack'])} @ {row['BLK']}"
            info = {"label": unit_label, "ssd": txt, "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']}
            
            if status == "hot": hot_list.append(info)
            elif status == "warm": warm_list.append(info)
            
        if not hot_list and not warm_list:
            st.info("当前项目中没有 0-6 个月内即将解禁的单位。")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 🟡 0-3月内解禁 (🔥)")
                for item in hot_list:
                    if st.button(f"{item['label']} ({item['ssd']})", key=f"hot_{item['label']}"):
                        st.session_state.selected_blk = item['blk']
                        st.session_state['avm_target'] = {'blk': item['blk'], 'floor': int(item['f']), 'stack': item['s']}
                        st.query_params['target_unit'] = f"{item['blk']}|{item['f']}|{item['s']}"
                        st.rerun()
            with c2:
                st.markdown("##### 🟠 3-6月内解禁 (⚠️)")
                for item in warm_list:
                    if st.button(f"{item['label']} ({item['ssd']})", key=f"warm_{item['label']}"):
                        st.session_state.selected_blk = item['blk']
                        st.session_state['avm_target'] = {'blk': item['blk'], 'floor': int(item['f']), 'stack': item['s']}
                        st.query_params['target_unit'] = f"{item['blk']}|{item['f']}|{item['s']}"
                        st.rerun()

    st.divider()
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # A. 楼座按钮组
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if not all_blks: return
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    st.write("选择楼座 (Block):")
    blk_cols = st.columns(len(all_blks))
    for idx, blk_name in enumerate(all_blks):
        with blk_cols[idx]:
            style_type = "primary" if st.session_state.selected_blk == blk_name else "secondary"
            if st.button(blk_name, key=f"blk_btn_{blk_name}", type=style_type, use_container_width=True):
                st.session_state.selected_blk = blk_name
                st.rerun()

    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    # B. 数据处理
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # C. HTML 网格
    html_grid = f"""
    <style>
        body {{ margin: 0; padding: 0; overflow: hidden; }}
        .grid-table {{ border-collapse: separate; border-spacing: 4px; margin: 0; table-layout: fixed; }}
        .unit-btn {{
            width: 85px; height: 60px; border-radius: 4px; border: 1px solid #e5e7eb;
            text-align: center; cursor: pointer; display: flex; flex-direction: column; 
            justify-content: center; align-items: center; font-family: sans-serif; transition: transform 0.1s;
        }}
        .unit-btn:hover {{ border-color: #4b5563; transform: scale(1.03); }}
        .u-no {{ font-size: 11px; font-weight: 800; color: #111827; margin: 0; }}
        .u-pr {{ font-size: 10px; font-weight: 600; color: #374151; margin: 1px 0; }}
        .u-ss {{ font-size: 9px; font-weight: bold; margin: 0; }}
    </style>
    <div id="content"><table class="grid-table">
    """

    for f in floors:
        html_grid += "<tr>"
        for s in all_stacks:
            unit_no = format_unit(f, s)
            data = tx_map.get((f, s))
            p_str, ssd_txt, bg, tc, _ = "-", "", "#f9fafb", "#9ca3af", ""
            if data:
                p_str = f"${data['Sale Price']/1e6:.1f}M"
                ssd_txt, bg, tc, _ = get_ssd_status(data['Sale Date'])

            click_js = f"window.parent.postMessage({{type: 'streamlit:set_component_value', value: '{selected_blk}|{f}|{s}', key: 'grid_click'}}, '*')"
            html_grid += f"""
            <td><div class="unit-btn" style="background-color: {bg};" onclick="{click_js}">
                <div class="u-no">{unit_no}</div><div class="u-pr">{p_str}</div><div class="u-ss" style="color: {tc};">{ssd_txt}</div>
            </div></td>
            """
        html_grid += "</tr>"
    html_grid += "</table></div>"
    html_grid += """<script>
        function sendHeight() {
            const height = document.getElementById('content').offsetHeight + 5;
            window.parent.postMessage({type: 'streamlit:set_height', height: height}, '*');
        }
        window.onload = sendHeight; window.onresize = sendHeight;
    </script>"""

    components.html(html_grid, height=(len(floors) * 66) + 10)

    # D. 跳转监听
    st.markdown("""<script>
        window.addEventListener('message', function(event) {
            if (event.data.type === 'streamlit:set_component_value' && event.data.key === 'grid_click') {
                const url = new URL(window.location);
                url.searchParams.set('target_unit', event.data.value);
                window.parent.location.search = url.searchParams.toString();
            }
        });
    </script>""", unsafe_allow_html=True)

    params = st.query_params
    if "target_unit" in params:
        blk, f, s = params["target_unit"].split('|')
        st.session_state['avm_target'] = {'blk': blk, 'floor': int(f), 'stack': s}
        st.query_params.clear()
        components.html("<script>window.parent.document.querySelectorAll('button[data-baseweb=\"tab\"]')[2].click();</script>", height=0)
        st.rerun()
