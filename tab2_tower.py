# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time

# ==============================================================================
# 0. 启动拦截：处理跳转信号 (必须在最前)
# ==============================================================================
if "target" in st.query_params:
    try:
        # 1. 解码参数: 10K_5_40
        raw = st.query_params["target"]
        blk, f, s = raw.split('_')
        
        # 2. 存入 Session
        st.session_state['avm_target'] = {'blk': blk, 'floor': int(f), 'stack': s}
        st.session_state.selected_blk = blk
        
        # 3. 清除参数 (防止死循环)
        st.query_params.clear()
        
        # 4. 注入强力跳转脚本 (Repeater)
        # 这段脚本会每50ms尝试点击一次Tab 3，尝试20次，确保页面加载慢也能点到
        js_clicker = """
        <script>
            var attempts = 0;
            var interval = setInterval(function() {
                // 查找 Streamlit 的 Tab 按钮
                var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                if (tabs.length > 2) {
                    tabs[2].click(); // 点击第三个 Tab
                    window.parent.scrollTo(0, 0); // 滚回顶部
                    clearInterval(interval); // 成功后停止
                    console.log("Tab 3 clicked successfully");
                }
                attempts++;
                if (attempts > 40) clearInterval(interval); // 2秒后放弃
            }, 50);
        </script>
        """
        components.html(js_clicker, height=0)
        
    except Exception as e:
        st.error(f"跳转失败: {e}")

# ==============================================================================
# 1. 业务逻辑
# ==============================================================================
def get_ssd_class(purchase_date):
    # 返回 CSS 类名和文案
    if pd.isna(purchase_date): return "na", "", "-"
    
    if not isinstance(purchase_date, datetime): purchase_date = pd.to_datetime(purchase_date)
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline: return "safe", "", "" # 绿色

    days_left = (ssd_deadline - today).days
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    if days_left < 90: return "hot", f"🔥{rate}", f"{days_left}d"
    elif days_left < 180: return "warm", f"⚠️{rate}", f"{int(days_left/30)}m"
    else: return "locked", f"🔒{rate}", "SSD"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# ==============================================================================
# 2. 渲染主界面
# ==============================================================================
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # --- Block Selector (Native Button) ---
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    st.write("选择楼座 (Block):")
    # CSS 优化按钮
    st.markdown("""<style>
        div.stButton > button { border-radius: 20px; padding: 2px 10px; font-size: 13px; }
        div.stButton > button:focus { border-color: #2563eb; color: #2563eb; }
    </style>""", unsafe_allow_html=True)

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

    # --- Grid View (Iframe HTML) ---
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # 构建完整的 HTML 页面
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ margin: 0; padding: 0; font-family: sans-serif; overflow-y: hidden; }}
        .grid-container {{ display: flex; flex-direction: column; gap: 4px; padding-bottom: 20px; }}
        .row {{ display: flex; gap: 4px; overflow-x: auto; padding-bottom: 5px; }}
        /* 隐藏滚动条但保留功能 */
        .row::-webkit-scrollbar {{ height: 6px; }}
        .row::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}
        
        .cell {{
            flex: 0 0 85px; height: 62px;
            border: 1px solid #e5e7eb; border-radius: 4px;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            cursor: pointer; transition: transform 0.1s; background: #f9fafb; text-decoration: none;
        }}
        .cell:hover {{ transform: scale(1.03); z-index: 10; border-color: #6b7280; }}
        
        .u-no {{ font-size: 11px; font-weight: 800; color: #111827; }}
        .u-pr {{ font-size: 10px; font-weight: 600; color: #374151; margin: 1px 0; }}
        .u-ss {{ font-size: 9px; font-weight: bold; color: #9ca3af; }}
        
        /* 颜色定义 */
        .hot {{ background: #fef9c3; border-color: #fde047; }} .hot .u-ss {{ color: #854d0e; }}
        .warm {{ background: #ffedd5; border-color: #fed7aa; }} .warm .u-ss {{ color: #9a3412; }}
        .locked {{ background: #fee2e2; border-color: #fca5a5; }} .locked .u-ss {{ color: #991b1b; }}
        .safe {{ background: #f0fdf4; border-color: #bbf7d0; }} .safe .u-ss {{ color: #166534; }}
    </style>
    </head>
    <body>
    <div class="grid-container">
    """

    for f in floors:
        html_content += '<div class="row">'
        for s in all_stacks:
            unit_no = format_unit(f, s)
            data = tx_map.get((f, s))
            
            p_str, ssd_line1, ssd_line2, cls = "-", "", "", "na"
            
            if data:
                p_str = f"${data['Sale Price']/1e6:.1f}M"
                cls, ssd_line1, ssd_line2 = get_ssd_class(data['Sale Date'])
            
            # 核心跳转逻辑：修改父窗口 URL
            # 使用下划线 _ 代替 | 防止 URL 编码问题
            target_val = f"{selected_blk}_{f}_{s}"
            click_js = f"window.parent.location.search = '?target={target_val}';"
            
            html_content += f"""
            <div class="cell {cls}" onclick="{click_js}">
                <div class="u-no">{unit_no}</div>
                <div class="u-pr">{p_str}</div>
                <div class="u-ss">{ssd_line1} {ssd_line2}</div>
            </div>
            """
        html_content += '</div>'
    
    html_content += """</div>
    <script>
        // 自动上报高度
        window.addEventListener('load', function() {
            var h = document.body.scrollHeight + 30;
            window.parent.postMessage({type: 'streamlit:set_height', height: h}, '*');
        });
    </script>
    </body></html>
    """
    
    # 渲染 HTML Iframe
    components.html(html_content, height=500, scrolling=False)

    # --- 预警列表 ---
    st.markdown("---")
    st.caption("🔥 0-3月 | ⚠️ 3-6月 | 🔒 6月+ | 🟢 Safe")
    
    # 简单的原生按钮列表作为备用
    with st.expander("🚀 全局 SSD 临期预警快报", expanded=False):
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor', 'Stack']).tail(1).copy()
        hot_list = []
        for _, row in latest_txs.iterrows():
            cls, t1, t2 = get_ssd_class(row['Sale Date'])
            if cls in ["hot", "warm"]:
                hot_list.append({
                    "label": f"{t1} {format_unit(row['Floor'], row['Stack'])} @ {row['BLK']}",
                    "blk": row['BLK'], "f": row['Floor'], "s": row['Stack']
                })
        
        if hot_list:
            cols = st.columns(4)
            for i, item in enumerate(hot_list):
                with cols[i % 4]:
                    if st.button(item["label"], key=f"alert_{i}"):
                        st.session_state['avm_target'] = {'blk': item['blk'], 'floor': int(item['f']), 'stack': item['s']}
                        # 注入简单跳转脚本
                        components.html("""<script>
                            setTimeout(function(){ 
                                window.parent.document.querySelectorAll('button[data-baseweb="tab"]')[2].click(); 
                            }, 300);
                        </script>""", height=0)
