# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import html
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 黑科技：强制跳转 Tab ---
def switch_to_tab_3():
    js = """
    <script>
        var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
        if (tabs.length > 2) {
            tabs[2].click();
        }
    </script>
    """
    components.html(js, height=0)

# --- 1. SSD 计算核心 ---
def check_ssd_status(purchase_date):
    if pd.isna(purchase_date): return False, "无数据", 0
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
        
    today = datetime.now()
    POLICY_2025 = pd.Timestamp("2025-07-04")
    POLICY_2017 = pd.Timestamp("2017-03-11")
    
    if purchase_date >= POLICY_2025:
        lock_years = 4
        desc = "4年"
    elif purchase_date >= POLICY_2017:
        lock_years = 3
        desc = "3年"
    else:
        lock_years = 4
        desc = "4年"
        
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today < ssd_deadline:
        days_left = (ssd_deadline - today).days
        short = f"🔒 SSD期内"
        full = f"状态: 🔒 锁定期 ({desc})\n剩余: {days_left} 天\n解锁: {ssd_deadline.strftime('%Y-%m-%d')}"
        return True, short, full
    else:
        return False, "✅ Free", "状态: ✅ SSD 已解禁"

# --- 2. 辅助函数 ---
def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# --- 3. 主渲染函数 ---
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")

    # A. 筛选 Block
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    if not all_blks:
        st.warning("数据为空")
        return
    selected_blk = st.selectbox("选择楼座 (Block)", all_blks, key="tab2_blk_select")
    blk_df = df[df['BLK'] == selected_blk].copy()

    # B. 构建骨架
    if 'Floor_Num' in blk_df.columns:
        blk_df['Floor_Sort'] = blk_df['Floor_Num'].fillna(0).astype(int)
    else:
        blk_df['Floor_Sort'] = blk_df['Floor'].astype(str).str.extract(r'(\d+)')[0].fillna(0).astype(int)

    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    if not blk_df.empty:
        min_floor = int(blk_df['Floor_Sort'].min())
        max_floor = int(blk_df['Floor_Sort'].max())
        floors_desc = sorted(list(range(min_floor, max_floor + 1)), reverse=True)
    else:
        floors_desc = []

    # C. 准备交易数据
    tx_map = {}
    if not blk_df.empty:
        latest_tx = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1)
        for _, row in latest_tx.iterrows():
            key = (int(row['Floor_Sort']), row['Stack'])
            tx_map[key] = row

    # D. 渲染网格 (无轴设计)
    if not all_stacks:
        st.info("该楼座无 Stack 信息")
        return

    # 直接渲染每一行，不显示顶部 Stack 号，也不显示左侧 Floor 号
    # 所有的信息都包含在卡片里
    
    num_cols = len(all_stacks)
    # 使用 container 限制宽度，防止太宽
    
    for floor in floors_desc:
        # 这里不需要左侧的 Floor 轴了，直接平铺 Stack
        cols = st.columns(num_cols)
        
        for i, stack in enumerate(all_stacks):
            with cols[i]:
                # --- 1. 准备数据 ---
                # 格式化单元号: #05-02
                unit_label = f"#{floor:02d}-{stack}"
                row_data = tx_map.get((floor, stack))
                
                # --- 2. 样式逻辑 ---
                if row_data is not None:
                    # [有交易]
                    price = f"${row_data['Sale Price']/1e6:.2f}M"
                    psf = f"${row_data['Sale PSF']:,.0f}" # 简化，不带 psf 后缀节省空间
                    s_date = row_data['Sale Date']
                    is_locked, short_status, full_ssd_msg = check_ssd_status(s_date)
                    
                    # Tooltip
                    raw_tip = f"单元: {unit_label}\n成交: {s_date.strftime('%Y-%m-%d')}\n总价: {price}\n尺价: {psf} psf\n{full_ssd_msg}"
                    safe_tip = html.escape(raw_tip, quote=True)
                    
                    # 视觉编码
                    if is_locked:
                        status_color = "#dc2626" # 红字
                        bg_css = "background-color: #fef2f2; border: 1px solid #fca5a5;"
                        icon = "🔒"
                    else:
                        status_color = "#166534" # 绿字
                        bg_css = "background-color: #ffffff; border: 1px solid #e5e7eb;"
                        icon = "✅"
                        
                    # 卡片 HTML (作为按钮的标签)
                    # Streamlit button 不支持 HTML，所以我们要用一种巧妙的方法：
                    # 按钮是透明的，覆盖在 HTML 上？不，Streamlit 按钮只能是文字。
                    # 为了美观，我们只能把核心信息写在按钮上，或者用 markdown + button 组合。
                    # 最好的交互是：按钮本身就是卡片。但 Streamlit 按钮很难自定义样式。
                    
                    # 妥协方案：使用 Button 显示 "单元号 + 价格"，下方用 Markdown 显示 SSD 条
                    # 或者：整个卡片就是一个 Button，内容多行。
                    
                    btn_label = f"{unit_label}\n{price}\n{psf} psf"
                    # 按钮 Help 显示详情
                    btn_help = raw_tip 
                    
                    # 动态改变按钮样式的 CSS (高级) - 这里不搞太复杂，用 help 替代 tooltip
                    # 关键：如果有 SSD 风险，我们在按钮文字里加个图标
                    if is_locked:
                        btn_label = f"{unit_label} 🔒\n{price}\n{psf} psf"
                    
                else:
                    # [无交易]
                    btn_label = f"{unit_label}\n-\n-"
                    btn_help = f"单元: {unit_label}\n暂无历史交易记录\n点击可查看估值"
                    status_color = "#9ca3af"
                
                # --- 3. 渲染交互 ---
                # 我们用一个 Button 代表整个格子
                # 这样点击任何地方都能跳转
                btn_key = f"btn_{selected_blk}_{floor}_{stack}"
                
                # 可以在按钮上方加一点 CSS 来区分颜色？Streamlit 原生做不到给特定按钮加颜色。
                # 但我们可以利用 type="primary" / "secondary" 来区分有无交易?
                # 为了保持整齐，统一样式，但无交易的可以灰显?
                
                clicked = st.button(
                    btn_label, 
                    key=btn_key, 
                    help=btn_help, 
                    use_container_width=True
                )
                
                # 下方加一个小细条显示状态 (这是唯一能自定义颜色的地方)
                if row_data is not None:
                    st.markdown(f"<div style='height:4px; background-color:{status_color}; border-radius:2px; margin-top:-8px; margin-bottom:8px;'></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='height:4px; background-color:#f3f4f6; border-radius:2px; margin-top:-8px; margin-bottom:8px;'></div>", unsafe_allow_html=True)

                if clicked:
                    st.session_state['avm_target'] = {
                        'blk': selected_blk,
                        'floor': floor,
                        'stack': stack
                    }
                    switch_to_tab_3()

    st.caption("💡 说明：每个卡片代表一个单元。**红色底条**表示处于SSD限售期。点击任意卡片即可跳转查看估值。")
