# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# ==============================================================================
# 0. 核心拦截器 (必须放在最前面)
# ==============================================================================
# 逻辑：检测 URL 是否带有跳转参数 -> 更新 Session -> 注入 JS 切换 Tab
# ==============================================================================
if "jump_target" in st.query_params:
    try:
        # 1. 解析参数 (格式: BLK|FLOOR|STACK)
        raw_val = st.query_params["jump_target"]
        blk, f, s = raw_val.split('|')
        
        # 2. 更新 Session State
        st.session_state['avm_target'] = {'blk': blk, 'floor': int(f), 'stack': s}
        st.session_state.selected_blk = blk
        
        # 3. 清理参数 (防止刷新死循环)
        st.query_params.clear()
        
        # 4. 强制 JS 动作：等待页面加载 -> 点击 Tab 3 -> 滚动顶部
        js_force_switch = """
        <script>
            window.addEventListener('load', function() {
                setTimeout(function() {
                    const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                    if (tabs.length > 2) {
                        tabs[2].click();
                        window.parent.scrollTo(0, 0);
                        console.log("Tab 3 activated via V141 logic");
                    }
                }, 800); // 延时确保页面渲染完毕
            });
        </script>
        """
        components.html(js_force_switch, height=0)
        
    except Exception as e:
        st.error(f"跳转解析错误: {e}")

# ==============================================================================
# 1. 业务逻辑区
# ==============================================================================
def get_ssd_style(purchase_date):
    if pd.isna(purchase_date): 
        # 无记录：白色背景，灰色字
        return "N/A", "background-color: #f9fafb; color: #9ca3af; border: 1px solid #e5e7eb;"
    
    if not isinstance(purchase_date, datetime): 
        purchase_date = pd.to_datetime(purchase_date)
    
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    lock_years = 4 if purchase_date >= POLICY_2025 else 3
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today >= ssd_deadline:
        # 安全：绿色背景
        return "", "background-color: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;"

    days_left = (ssd_deadline - today).days
    diff = relativedelta(today, purchase_date)
    years_held = diff.years + 1
    rates = {1: "16%", 2: "12%", 3: "8%", 4: "4%"} if lock_years == 4 else {1: "12%", 2: "8%", 3: "4%"}
    rate = rates.get(years_held, "4%")
    
    if days_left < 90:
        # 0-3月：黄色背景 (Yellow)
        return f"🔥{rate}({days_left}d)", "background-color: #fef9c3; color: #854d0e; border: 1px solid #fde047;"
    elif days_left < 180:
        # 3-6月：橙色背景 (Orange)
        return f"⚠️{rate}({int(days_left/30)}m)", "background-color: #ffedd5; color: #9a3412; border: 1px solid #fed7aa;"
    else:
        # >6月：红色背景 (Red)
        return f"🔒{rate} SSD", "background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;"

def format_unit(floor, stack):
    return f"#{int(floor):02d}-{str(stack).zfill(2) if str(stack).isdigit() else stack}"

def natural_key(string_):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', str(string_))]

# ==============================================================================
# 2. 渲染主函数
# ==============================================================================
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")
    
    # --------------------------------------------------------------------------
    # A. 楼座选择 (保留原生按钮，因为这里只需要简单切换)
    # --------------------------------------------------------------------------
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if 'selected_blk' not in st.session_state: st.session_state.selected_blk = all_blks[0]

    st.write("选择楼座 (Block):")
    # CSS 优化原生按钮外观
    st.markdown("""
        <style>
        div.stButton > button {
            border-radius: 20px; padding: 2px 10px; font-size: 13px;
        }
        div.stButton > button:focus { border-color: #2563eb; color: #2563eb; }
        </style>
    """, unsafe_allow_html=True)
    
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

    # --------------------------------------------------------------------------
    # B. 楼宇网格 - 纯 HTML 注入 (解决颜色 + 滚动 + 点击 的终极方案)
    # --------------------------------------------------------------------------
    selected_blk = st.session_state.selected_blk
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    f_col = 'Floor_Num' if 'Floor_Num' in blk_df.columns else 'Floor'
    blk_df['F_Sort'] = pd.to_numeric(blk_df[f_col], errors='coerce').fillna(0).astype(int)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    floors = sorted(blk_df['F_Sort'].unique(), reverse=True)
    tx_map = blk_df.sort_values('Sale Date').groupby(['F_Sort', 'Stack']).tail(1).set_index(['F_Sort', 'Stack']).to_dict('index')

    # 生成 HTML 字符串
    html_out = """
    <style>
        /* 容器样式：允许横向滚动 */
        .tower-grid-container {
            width: 100%;
            overflow-x: auto;
            white-space: nowrap;
            padding-bottom: 15px;
            font-family: sans-serif;
        }
        .tower-grid-container::-webkit-scrollbar { height: 8px; }
        .tower-grid-container::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        
        .grid-row { display: flex; gap: 4px; margin-bottom: 4px; }
        
        /* 单元格链接样式：表现得像个按钮，实际是超链接 */
        .unit-link {
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 85px; /* 固定宽度，防止挤压 */
            height: 60px;
            text-decoration: none !important;
            border-radius: 4px;
            transition: transform 0.1s;
            flex-shrink: 0; /* 关键：禁止缩小 */
        }
        .unit-link:hover { transform: scale(1.05); z-index: 10; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        
        .u-txt-no { font-size: 11px; font-weight: 800; color: #111827; margin: 0; line-height: 1.2; }
        .u-txt-pr { font-size: 10px; font-weight: 600; color: #374151; margin: 1px 0; line-height: 1.2; }
        .u-txt-ss { font-size: 9px; font-weight: bold; margin: 0; line-height: 1.2; }
    </style>
    
    <div class="tower-grid-container">
    """
    
    for f in floors:
        html_out += '<div class="grid-row">'
        for s in all_stacks:
            unit_no = format_unit(f, s)
            data = tx_map.get((f, s))
            
            p_str = "-"
            ssd_display = ""
            # 默认样式
            style_str = "background-color: #f9fafb; color: #9ca3af; border: 1px solid #e5e7eb;"
            
            if data:
                p_str = f"${data['Sale Price']/1e6:.1f}M"
                ssd_display, style_str = get_ssd_style(data['Sale Date'])
            
            # 构造跳转链接：target="_self" 确保在当前页刷新
            # 参数: jump_target = BLK|FLOOR|STACK
            # 使用 encodeURI 防止特殊字符问题
            link_href = f"?jump_target={selected_blk}|{f}|{s}"
            
            html_out += f"""
            <a href="{link_href}" target="_self" class="unit-link" style="{style_str}">
                <div class="u-txt-no">{unit_no}</div>
                <div class="u-txt-pr">{p_str}</div>
                <div class="u-txt-ss">{ssd_display}</div>
            </a>
            """
        html_out += '</div>'
    
    html_out += "</div>"
    
    # 将 HTML 注入页面
    st.markdown(html_out, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # C. 全局预警 (使用同样的 Link 机制)
    # --------------------------------------------------------------------------
    st.markdown("---")
    st.caption("🔥 0-3月(Yellow) | ⚠️ 3-6月(Orange) | 🔒 >6月(Red) | 🟢 Safe(Green)")

    with st.expander("🚀 全局 SSD 临期预警快报 (0-6个月)", expanded=False):
        latest_txs = df.sort_values('Sale Date').groupby(['BLK', 'Floor', 'Stack']).tail(1).copy()
        hot_list, warm_list = [], []
        for _, row in latest_txs.iterrows():
            txt, style = get_ssd_style(row['Sale Date'])
            # 简单判断颜色来归类
            if "fde047" in style: status = "hot" # yellow border
            elif "fed7aa" in style: status = "warm" # orange border
            else: status = "safe"
            
            if status in ["hot", "warm"]:
                # 构造 HTML Link Button
                link_href = f"?jump_target={row['BLK']}|{row['Floor']}|{row['Stack']}"
                # 提取纯文本颜色
                item_html = f"""
                <a href="{link_href}" target="_self" style="
                    display:inline-block; margin:4px; padding:6px 12px; border-radius:4px; 
                    text-decoration:none; font-size:12px; font-weight:bold; {style}">
                    {format_unit(row['Floor'], row['Stack'])} @ {row['BLK']} <br> {txt}
                </a>
                """
                if status == "hot": hot_list.append(item_html)
                else: warm_list.append(item_html)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🔥 0-3月 (Yellow)")
            if hot_list:
                st.markdown("".join(hot_list), unsafe_allow_html=True)
            else: st.caption("无")
        with c2:
            st.markdown("##### ⚠️ 3-6月 (Orange)")
            if warm_list:
                st.markdown("".join(warm_list), unsafe_allow_html=True)
            else: st.caption("无")
