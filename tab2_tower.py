# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

# --- 1. SSD 核心逻辑 ---
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

    # -------------------------------------------------------
    # A. 楼座选择 (原生按钮，保证状态切换最稳)
    # -------------------------------------------------------
    st.markdown("""
    <style>
        /* 胶囊按钮优化 */
        div.stButton > button {
            border-radius: 20px !important;
            padding: 2px 8px !important;
            font-size: 13px !important;
        }
    </style>
    """, unsafe_allow_html=True)

    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    st.write("选择楼座 (Block):")
    cols_per_row = 8
    rows = [all_blks[i:i + cols_per_row] for i in range(0, len(all_blks), cols_per_row)]
    
    for row_blks in rows:
        cols = st.columns(cols_per_row)
        for idx, blk in enumerate(row_blks):
            with cols[idx]:
                b_type = "primary" if st.session_state.selected_blk == blk else "secondary"
                if st.button(blk, key=f"blk_{blk}", type=b_type, use_container_width=True):
                    st.session_state.selected_blk = blk
                    st.rerun()

    # -------------------------------------------------------
    # B. 楼宇网格 (回归 HTML 以实现完美的 Scroll Bar)
    # -------------------------------------------------------
    # 为什么回归 HTML？因为 Streamlit 原生组件无法实现“单行横向滚动”，
    # 只有 HTML 容器能做到 overflow-x: auto。为了解决点击问题，我们使用 URL Hash 通信。
    
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # 构建 HTML 内容
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ margin: 0; padding: 0; font-family: sans-serif; overflow-y: hidden; }}
        /* 核心：横向滚动容器 */
        .grid-container {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            padding-bottom: 20px; /* 预留滚动条空间 */
        }}
        .floor-row {{
            display: flex;
            flex-wrap: nowrap; /* 禁止换行，强制横向 */
            gap: 4px;
            /* 关键：允许横向滚动 */
            overflow-x: auto; 
            padding-bottom: 5px; /* 滚动条不遮挡内容 */
        }}
        /* 隐藏默认滚动条，美化 Webkit 滚动条 */
        .floor-row::-webkit-scrollbar {{ height: 6px; }}
        .floor-row::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 4px; }}
        .floor-row::-webkit-scrollbar-track {{ background: transparent; }}

        .unit-cell {{
            flex: 0 0 85px; /* 固定宽度 85px，不许挤压 */
            height: 60px;
            border: 1px solid #e5e7eb;
            border-radius: 4px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            background: #f9fafb;
            transition: all 0.1s;
        }}
        .unit-cell:hover {{ transform: scale(1.02); border-color: #6b7280; z-index: 10; }}
        .u-no {{ font-size: 11px; font-weight: 800; color: #111827; }}
        .u-pr {{ font-size: 10px; font-weight: 600; color: #374151; margin: 1px 0; }}
        .u-ss {{ font-size: 9px; font-weight: bold; color: #9ca3af; }}
        
        /* 状态颜色 */
        .hot {{ background: #fef2f2 !important; border-color: #fca5a5 !important; }}
        .hot .u-ss {{ color: #991b1b !important; }}
        
        .warm {{ background: #fff7ed !important; border-color: #fed7aa !important; }}
        .warm .u-ss {{ color: #9a3412 !important; }}
        
        .locked {{ background: #fef2f2 !important; border-color: #fca5a5 !important; }}
        .locked .u-ss {{ color: #991b1b !important; }}
        
        .safe {{ background: #f0fdf4 !important; border-color: #bbf7d0 !important; }}
        .safe .u-ss {{ color: #166534 !important; }}
    </style>
    </head>
    <body>
    <div class="grid-container">
    """
    
    for f in floors:
        html_content += '<div class="floor-row">'
        for s in all_stacks:
            unit_no = format_unit(f, s)
            data = tx_map.get((f, s))
            
            p_str, ssd_txt, cls = "-", "", ""
            if data:
                p_str = f"${data['Sale Price']/1e6:.1f}M"
                ssd_txt, status = get_ssd_info(data['Sale Date'])
                # 映射状态到 CSS 类
                if status == "hot": cls = "hot"
                elif status == "warm": cls = "warm"
                elif status == "locked": cls = "locked"
                elif status == "safe": cls = "safe"
            
            # 点击逻辑：通过 window.parent.location.hash 修改 URL Hash
            # Streamlit 会检测到 Hash 变化并触发重跑（如果我们配置了监听）
            # 或者我们用更直接的：window.parent.postMessage
            
            # 这里我们使用一个特殊的技巧：点击后改变 URL 参数，强制 Streamlit 刷新
            click_action = f"window.parent.location.search = '?t_blk={selected_blk}&t_f={f}&t_s={s}&ts={datetime.now().timestamp()}';"
            
            html_content += f"""
            <div class="unit-cell {cls}" onclick="{click_action}" title="点击跳转">
                <div class="u-no">{unit_no}</div>
                <div class="u-pr">{p_str}</div>
                <div class="u-ss">{ssd_txt}</div>
            </div>
            """
        html_content += '</div>'
    
    html_content += """
    </div>
    <script>
        // 自动上报高度，防止截断
        window.addEventListener('load', function() {
            var height = document.body.scrollHeight + 20;
            window.parent.postMessage({type: 'streamlit:set_height', height: height}, '*');
        });
    </script>
    </body>
    </html>
    """
    
    # 渲染 HTML 组件
    # scrolling=True 允许组件内部滚动，但我们已经在内部实现了 overflow-x
    components.html(html_content, height=500, scrolling=False)

    # -------------------------------------------------------
    # C. 信号拦截与跳转
    # -------------------------------------------------------
    # 检查 URL 参数
    query = st.query_params
    if "t_blk" in query and "t_f" in query and "t_s" in query:
        # 1. 捕获目标
        target = {
            'blk': query["t_blk"],
            'floor': int(query["t_f"]),
            'stack': query["t_s"]
        }
        
        # 2. 写入 Session State
        st.session_state['avm_target'] = target
        st.session_state.selected_blk = target['blk'] # 同步 Block 显示
        
        # 3. 清除参数 (重置 URL)
        st.query_params.clear()
        
        # 4. 执行跳转脚本
        # 这个脚本不仅点 Tab，还会把页面滚动到顶部
        jump_script = """
        <script>
            var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length > 2) {
                tabs[2].click();
                window.parent.scrollTo(0, 0);
            }
        </script>
        """
        components.html(jump_script, height=0)

    # -------------------------------------------------------
    # D. 备注与预警
    # -------------------------------------------------------
    st.caption("🔴 SSD期内 (🔥0-3月/⚠️3-6月) | 🟢 Safe | ⚪ 无记录。支持横向滑动查看。")

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
                # 使用原生按钮作为备选跳转路径
                if st.button(f"{item['label']}  {item['ssd']}", key=f"hot_{item['label']}"):
                    st.query_params["t_blk"] = item['blk']
                    st.query_params["t_f"] = item['f']
                    st.query_params["t_s"] = item['s']
                    st.rerun()
        with c2:
            st.markdown("##### ⚠️ 3-6月")
            for item in warm_list:
                if st.button(f"{item['label']}  {item['ssd']}", key=f"warm_{item['label']}"):
                    st.query_params["t_blk"] = item['blk']
                    st.query_params["t_f"] = item['f']
                    st.query_params["t_s"] = item['s']
                    st.rerun()
