# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 1. SSD 颜色逻辑 ---
def get_ssd_status(purchase_date):
    if pd.isna(purchase_date): 
        return "", "#f9fafb", "#9ca3af" # 灰
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
    
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline:
        return "", "#f0fdf4", "#166534" # 绿 (Safe)

    days_left = (ssd_deadline - today).days
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    if days_left < 90: # 0-3月 (黄)
        return f"🔥{rate}({days_left}d)", "#fef08a", "#854d0e"
    elif days_left < 180: # 3-6月 (橙)
        return f"⚠️{rate}({days_left//30}m)", "#fed7aa", "#9a3412"
    else: # > 6月 (红)
        return f"{rate} SSD", "#fca5a5", "#7f1d1d"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

# --- 2. 渲染函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    all_blks = sorted(df['BLK'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    selected_blk = st.selectbox("选择楼座", all_blks, key="blk_v126")
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    if blk_df.empty: return

    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=lambda x: [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(x))])
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # --- HTML 表格构造 ---
    html_grid = f"""
    <style>
        .grid-container {{
            width: 100%;
            padding-bottom: 30px; /* 关键：增加底部内边距，防止被截断 */
            overflow-x: auto;
        }}
        .grid-table {{ 
            border-collapse: separate; 
            border-spacing: 4px; 
            margin-left: 0;
            table-layout: fixed;
        }}
        .unit-btn {{
            width: 85px; 
            height: 60px; 
            border-radius: 4px; 
            border: 1px solid #e5e7eb;
            text-align: center; 
            cursor: pointer; 
            display: flex; 
            flex-direction: column; 
            justify-content: center; 
            align-items: center;
            font-family: sans-serif;
            transition: transform 0.1s;
        }}
        .unit-btn:hover {{ border-color: #4b5563; transform: scale(1.03); z-index: 50; }}
        .u-no {{ font-size: 11px; font-weight: 800; color: #111827; margin: 0; }}
        .u-pr {{ font-size: 10px; font-weight: 600; color: #374151; margin: 1px 0; }}
        .u-ss {{ font-size: 9px; font-weight: bold; margin: 0; }}
    </style>
    <div class="grid-container">
    <table class="grid-table">
    """

    for f in floors:
        html_grid += "<tr>"
        for s in all_stacks:
            unit_no = format_unit(f, s)
            data = tx_map.get((f, s))
            
            p_str, ssd_txt, bg, tc = "-", "", "#f9fafb", "#9ca3af"
            if data:
                p_str = f"${data['Sale Price']/1e6:.1f}M"
                ssd_txt, bg, tc = get_ssd_status(data['Sale Date'])

            # 点击回调
            click_js = f"window.parent.postMessage({{type: 'streamlit:set_component_value', value: '{selected_blk}|{f}|{s}', key: 'grid_click'}}, '*')"
            
            html_grid += f"""
            <td>
                <div class="unit-btn" style="background-color: {bg};" onclick="{click_js}">
                    <div class="u-no">{unit_no}</div>
                    <div class="u-pr">{p_str}</div>
                    <div class="u-ss" style="color: {tc};">{ssd_txt}</div>
                </div>
            </td>
            """
        html_grid += "</tr>"
    html_grid += "</table></div>"

    # --- 渲染组件：赋予充足的高度缓冲区 ---
    # 使用 75 像素每行 + 80 像素的额外空间，确保完全不被遮挡
    dynamic_height = (len(floors) * 75) + 80
    components.html(html_grid, height=dynamic_height)

    # 捕获跳转信号
    st.markdown("""
        <script>
        window.addEventListener('message', function(event) {
            if (event.data.type === 'streamlit:set_component_value' && event.data.key === 'grid_click') {
                const url = new URL(window.location);
                url.searchParams.set('target_unit', event.data.value);
                window.parent.location.search = url.searchParams.toString();
            }
        });
        </script>
    """, unsafe_allow_html=True)

    params = st.query_params
    if "target_unit" in params:
        blk, f, s = params["target_unit"].split('|')
        st.session_state['avm_target'] = {'blk': blk, 'floor': int(f), 'stack': s}
        st.query_params.clear()
        components.html("<script>window.parent.document.querySelectorAll('button[data-baseweb=\"tab\"]')[2].click();</script>", height=0)
        st.rerun()

    st.caption("🔴>6月 | 🟠3-6月 | 🟡0-3月 | 🟢Safe。表格左对齐，底部已增加缓冲空间。")
