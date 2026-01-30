# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 1. SSD 核心逻辑 ---
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
    
    if days_left < 90: return f"🔥{rate}({days_left}d)", "#fef08a", "#854d0e", "hot" 
    elif days_left < 180: return f"⚠️{rate}({days_left//30}m)", "#fed7aa", "#9a3412", "warm" 
    else: return f"{rate} SSD", "#fca5a5", "#7f1d1d", "locked"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# --- 2. 渲染函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # A. 楼座选择 (Python 估算高度，放弃 JS 自适应)
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: 
        st.session_state.selected_blk = all_blks[0]

    # 估算高度：假设每行能放 6-7 个按钮（移动端/窄屏保守估计），每行高度 45px
    # 这样可以确保无论是一行还是三行，容器都足够大，不会遮掩按钮
    estimated_rows = (len(all_blks) // 6) + 1
    safe_height = estimated_rows * 50 

    blk_options_html = """
    <div id="blk-container" style="display:flex; flex-wrap:wrap; gap:8px; padding:2px;">
    """
    for blk_name in all_blks:
        is_active = st.session_state.selected_blk == blk_name
        bg = "#2563eb" if is_active else "#ffffff"
        color = "#ffffff" if is_active else "#374151"
        border = "#2563eb" if is_active else "#d1d5db"
        blk_options_html += f"""
        <div onclick="window.parent.postMessage({{type: 'streamlit:set_component_value', value: '{blk_name}', key: 'blk_click'}}, '*')"
             style="padding: 6px 14px; border-radius: 4px; border: 1px solid {border}; background-color: {bg}; 
                    color: {color}; cursor: pointer; font-size: 13px; font-weight: 600; font-family: sans-serif; 
                    transition: all 0.2s; margin-bottom: 4px; white-space: nowrap;">
            {blk_name}
        </div>
        """
    blk_options_html += '</div>'
    
    # 注入交互 JS
    blk_options_html += """
        <script>
        window.addEventListener('message', function(event) {
            if (event.data.type === 'streamlit:set_component_value' && event.data.key === 'blk_click') {
                const url = new URL(window.location);
                url.searchParams.set('set_blk', event.data.value);
                window.parent.location.search = url.searchParams.toString();
            }
        });
        </script>
    """
    # 使用 Python 计算出的安全高度
    components.html(blk_options_html, height=safe_height, scrolling=False)

    if "set_blk" in st.query_params:
        st.session_state.selected_blk = st.query_params["set_blk"]
        st.query_params.clear()
        st.rerun()

    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    # B. 楼宇网格
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # CSS 增加底部 Padding
    html_grid = f"""
    <style>
        body {{ margin: 0; padding: 0; overflow: hidden; }}
        .grid-table {{ border-collapse: separate; border-spacing: 4px; table-layout: fixed; }}
        .unit-btn {{
            width: 85px; height: 62px; border-radius: 4px; border: 1px solid #e5e7eb;
            text-align: center; cursor: pointer; display: flex; flex-direction: column; 
            justify-content: center; align-items: center; font-family: sans-serif; transition: transform 0.1s;
        }}
        .unit-btn:hover {{ border-color: #4b5563; transform: scale(1.03); }}
        .u-no {{ font-size: 11px; font-weight: 800; color: #111827; margin: 0; }}
        .u-pr {{ font-size: 10px; font-weight: 600; color: #374151; margin: 1px 0; }}
        .u-ss {{ font-size: 9px; font-weight: bold; margin: 0; }}
    </style>
    <div id="grid-content" style="padding-bottom: 40px;"> <table class="grid-table">
    """
    for f in floors:
        html_grid += "<tr>"
        for s in all_stacks:
            unit_no = format_unit(f, s)
            data = tx_map.get((f, s))
            p_str, ssd_txt, bg, tc = "-", "", "#f9fafb", "#9ca3af"
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
    
    # 增加高度计算的缓冲值
    html_grid += """<script>
        function updateHeight() {
            const h = document.getElementById('grid-content').offsetHeight + 10;
            window.parent.postMessage({type: 'streamlit:set_height', height: h}, '*');
        }
        window.onload = updateHeight; window.onresize = updateHeight;
    </script>"""
    
    # 基础高度 + 额外缓冲
    components.html(html_grid, height=(len(floors) * 70) + 50)

    # C. SSD 备注 (Legend)
    st.markdown("""
        <div style="display:flex; flex-wrap:wrap; gap:15px; font-size:12px; margin-top:-20px; margin-bottom:15px; color:#4b5563;">
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#fca5a5; border-radius:2px; margin-right:5px;"></div> 🔴 > 6月</div>
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#fed7aa; border-radius:2px; margin-right:5px;"></div> 🟠 3-6月</div>
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#fef08a; border-radius:2px; margin-right:5px;"></div> 🟡 0-3月</div>
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#f0fdf4; border-radius:2px; margin-right:5px;"></div> 🟢 Safe / 无记录</div>
        </div>
    """, unsafe_allow_html=True)

    # D. SSD 临期全局快报
    with st.expander("🚀 全局 SSD 临期预警快报 (全项目 0-6个月单位)", expanded=False):
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor', 'Stack']).tail(1).copy()
        hot_list, warm_list = [], []
        for _, row in latest_txs.iterrows():
            txt, bg, tc, status = get_ssd_status(row['Sale Date'])
            if status in ["hot", "warm"]:
                info = {"label": f"{format_unit(row['Floor'], row['Stack'])} @ {row['BLK']}", "ssd": txt, "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']}
                if status == "hot": hot_list.append(info)
                else: warm_list.append(info)
        if not hot_list and not warm_list:
            st.info("当前项目中没有即将解禁的单位。")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 🟡 0-3月内解禁 (🔥)")
                for item in hot_list:
                    if st.button(f"{item['label']} ({item['ssd']})", key=f"h_{item['label']}"):
                        st.session_state.selected_blk = item['blk']
                        st.session_state['avm_target'] = {'blk': item['blk'], 'floor': int(item['f']), 'stack': item['s']}
                        st.query_params['target_unit'] = f"{item['blk']}|{item['f']}|{item['s']}"
                        st.rerun()
            with c2:
                st.markdown("##### 🟠 3-6月内解禁 (⚠️)")
                for item in warm_list:
                    if st.button(f"{item['label']} ({item['ssd']})", key=f"w_{item['label']}"):
                        st.session_state.selected_blk = item['blk']
                        st.session_state['avm_target'] = {'blk': item['blk'], 'floor': int(item['f']), 'stack': item['s']}
                        st.query_params['target_unit'] = f"{item['blk']}|{item['f']}|{item['s']}"
                        st.rerun()

    # E. 全局跳转监听
    st.markdown("""<script>
        window.addEventListener('message', function(event) {
            if (event.data.type === 'streamlit:set_component_value' && event.data.key === 'grid_click') {
                const url = new URL(window.location);
                url.searchParams.set('target_unit', event.data.value);
                window.parent.location.search = url.searchParams.toString();
            }
        });
    </script>""", unsafe_allow_html=True)
    if "target_unit" in st.query_params:
        blk, f, s = st.query_params["target_unit"].split('|')
        st.session_state['avm_target'] = {'blk': blk, 'floor': int(f), 'stack': s}
        st.query_params.clear()
        components.html("<script>window.parent.document.querySelectorAll('button[data-baseweb=\"tab\"]')[2].click();</script>", height=0)
        st.rerun()
