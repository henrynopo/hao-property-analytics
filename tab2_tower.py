# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 核心修复：优先处理跳转信号 ---
# 在渲染任何内容前，先检查 URL 是否带有跳转指令
# 这样即使页面刷新，也能第一时间拦截并执行跳转
if "target_unit" in st.query_params:
    try:
        # 解析参数
        t_blk, t_f, t_s = st.query_params["target_unit"].split('|')
        
        # 1. 设置 AVM 目标
        st.session_state['avm_target'] = {
            'blk': t_blk, 
            'floor': int(t_f), 
            'stack': t_s
        }
        
        # 2. 同步更新当前选中的 Block（防止试图跳转 Block 不变）
        st.session_state.selected_blk = t_blk
        
        # 3. 清除参数防止死循环
        st.query_params.clear()
        
        # 4. 执行 Tab 切换 JS
        # 注意：这里使用更暴力的 JS 寻找 Tab，增加兼容性
        jump_js = """
        <script>
            setTimeout(function(){
                var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                if (tabs.length > 2) { tabs[2].click(); }
            }, 500);
        </script>
        """
        components.html(jump_js, height=0)
        
    except Exception as e:
        st.error(f"跳转错误: {e}")
        st.query_params.clear()

# --- 1. SSD 逻辑 ---
def get_ssd_status(purchase_date):
    if pd.isna(purchase_date): return "", "#f9fafb", "#9ca3af", "none"
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    if today >= ssd_deadline: return "", "#f0fdf4", "#166534", "safe"
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

# --- 2. 渲染主函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # -------------------------------------------------------
    # A. 楼座选择器 (回归原生 Button 以保证 100% 点击有效)
    # -------------------------------------------------------
    # 我们使用 CSS 欺骗视觉，让原生 Button 看起来像胶囊 Tag
    st.markdown("""
    <style>
        /* 让按钮像胶囊一样排列 */
        div.stButton > button {
            border-radius: 20px !important;
            padding: 2px 10px !important;
            font-size: 13px !important;
            border: 1px solid #d1d5db;
        }
        /* 选中状态的高亮 */
        div.stButton > button:focus, div.stButton > button:active {
            border-color: #2563eb !important;
            color: #2563eb !important;
        }
    </style>
    """, unsafe_allow_html=True)

    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    # 使用 columns 布局来实现自动换行效果 (每行 6-8 个)
    # 这样既保证了是原生按钮(可点击)，又不会占太高空间
    st.write("选择楼座 (Block):")
    
    # 动态计算列数，防止报错
    cols_per_row = 8
    rows = [all_blks[i:i + cols_per_row] for i in range(0, len(all_blks), cols_per_row)]
    
    for row_blks in rows:
        cols = st.columns(cols_per_row)
        for idx, blk in enumerate(row_blks):
            with cols[idx]:
                # 选中态视觉区分
                b_type = "primary" if st.session_state.selected_blk == blk else "secondary"
                if st.button(blk, key=f"btn_blk_{blk}", type=b_type, use_container_width=True):
                    st.session_state.selected_blk = blk
                    st.rerun()

    # -------------------------------------------------------
    # B. 楼宇网格 (HTML)
    # -------------------------------------------------------
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

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
    <div id="grid-content" style="padding-bottom: 40px;">
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
                ssd_txt, bg, tc, _ = get_ssd_status(data['Sale Date'])
            
            # 点击触发 URL 变更
            click_js = f"window.parent.location.search = '?target_unit={selected_blk}|{f}|{s}';"
            
            html_grid += f"""
            <td><div class="unit-btn" style="background-color: {bg};" onclick="{click_js}">
                <div class="u-no">{unit_no}</div><div class="u-pr">{p_str}</div><div class="u-ss" style="color: {tc};">{ssd_txt}</div>
            </div></td>
            """
        html_grid += "</tr>"
    html_grid += "</table></div>"
    
    # 简单粗暴的高度计算，不依赖回调
    components.html(html_grid, height=(len(floors) * 70) + 50)

    # -------------------------------------------------------
    # C. 颜色图例 (Legend)
    # -------------------------------------------------------
    st.markdown("""
        <div style="display:flex; flex-wrap:wrap; gap:15px; font-size:12px; margin-top:-20px; margin-bottom:15px; color:#4b5563;">
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#fca5a5; border-radius:2px; margin-right:5px;"></div> 🔴 > 6月</div>
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#fed7aa; border-radius:2px; margin-right:5px;"></div> 🟠 3-6月</div>
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#fef08a; border-radius:2px; margin-right:5px;"></div> 🟡 0-3月</div>
            <div style="display:flex; align-items:center;"><div style="width:12px; height:12px; background:#f0fdf4; border-radius:2px; margin-right:5px;"></div> 🟢 Safe / 无记录</div>
        </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------
    # D. SSD 临期全局快报
    # -------------------------------------------------------
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
            st.info("无临期单位")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 🟡 0-3月 (🔥)")
                for item in hot_list:
                    # 使用 URL 参数跳转法
                    if st.button(f"{item['label']}\n{item['ssd']}", key=f"h_{item['label']}"):
                        st.query_params['target_unit'] = f"{item['blk']}|{item['f']}|{item['s']}"
                        st.rerun()
            with c2:
                st.markdown("##### 🟠 3-6月 (⚠️)")
                for item in warm_list:
                    if st.button(f"{item['label']}\n{item['ssd']}", key=f"w_{item['label']}"):
                        st.query_params['target_unit'] = f"{item['blk']}|{item['f']}|{item['s']}"
                        st.rerun()
