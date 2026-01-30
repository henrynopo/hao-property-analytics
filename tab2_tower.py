# 文件名: tab2_tower.py
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import html
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 0. 黑科技：强制跳转 Tab ---
# Streamlit 原生不支持跳 Tab，这是通过 JS 模拟点击第 3 个 Tab (Index=2)
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

    # 获取完整结构 (Min Floor -> Max Floor, All Stacks)
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

    # D. 渲染网格
    if not all_stacks:
        st.info("该楼座无 Stack 信息")
        return

    # 表头
    cols = st.columns([0.6] + [1] * len(all_stacks))
    with cols[0]:
        st.markdown("<div style='text-align:right; font-weight:bold; font-size:12px; padding-top:8px;'>Floor</div>", unsafe_allow_html=True)
    for i, stack in enumerate(all_stacks):
        with cols[i+1]:
            st.markdown(f"<div style='text-align:center; font-weight:bold; font-size:12px; border-bottom:1px solid #ddd; margin-bottom:5px;'>{stack}</div>", unsafe_allow_html=True)

    # 循环生成楼层
    for floor in floors_desc:
        c_row = st.columns([0.6] + [1] * len(all_stacks))
        
        # 楼层号
        with c_row[0]:
            st.markdown(f"<div style='text-align:right; font-weight:bold; color:#666; font-size:12px; padding-top:15px;'>L{floor}</div>", unsafe_allow_html=True)

        # 循环每个 Stack
        for i, stack in enumerate(all_stacks):
            with c_row[i+1]:
                # --- [按钮层] 单元号 (点击即跳转) ---
                unit_label = f"#{floor:02d}-{stack}"
                btn_key = f"btn_{selected_blk}_{floor}_{stack}"
                
                # 点击逻辑：
                # 1. 设置目标单元到 Session State
                # 2. 调用 JS 跳转到 Tab 3
                if st.button(unit_label, key=btn_key, use_container_width=True):
                    st.session_state['avm_target'] = {
                        'blk': selected_blk,
                        'floor': floor,
                        'stack': stack
                    }
                    switch_to_tab_3() # <--- 触发跳转

                # --- [数据层] 详情卡片 (悬停显示 Tooltip) ---
                row_data = tx_map.get((floor, stack))
                
                if row_data is not None:
                    # [有交易数据]
                    price = f"${row_data['Sale Price']/1e6:.2f}M"
                    psf = f"${row_data['Sale PSF']:,.0f}"
                    s_date = row_data['Sale Date']
                    is_locked, short_status, full_ssd_msg = check_ssd_status(s_date)
                    
                    # 配色
                    if is_locked:
                        bg = "#fee2e2"
                        border = "1px solid #fca5a5"
                        txt_c = "#991b1b"
                        status_s = "color:#dc2626; font-weight:bold;"
                    else:
                        bg = "#f0fdf4"
                        border = "1px solid #bbf7d0"
                        txt_c = "#166534"
                        status_s = "color:#166534;"

                    # 悬停 Tooltip
                    raw_tip = f"成交: {s_date.strftime('%Y-%m-%d')}\n总价: {price}\n尺价: {psf} psf\n{full_ssd_msg}"
                    safe_tip = html.escape(raw_tip, quote=True)
                    
                    st.markdown(f"""
                    <div title="{safe_tip}" style="
                        background-color: {bg}; border: {border}; border-radius: 4px;
                        padding: 4px 2px; text-align: center; cursor: help; margin-top: -12px; z-index: 1; min-height: 45px;
                    ">
                        <div style="font-weight:700; font-size:11px; color:{txt_c};">{price}</div>
                        <div style="font-size:10px; color:#555;">{psf}</div>
                        <div style="font-size:9px; {status_s} margin-top:1px;">{short_status}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                else:
                    # [无交易数据] (推定存在)
                    # 依然显示占位符，提示用户可以点击上方按钮去估值
                    st.markdown("""
                    <div title="暂无历史交易记录。&#10;点击上方按钮可查看估值。" style="
                        background-color: #f9fafb; border: 1px dashed #e5e7eb; border-radius: 4px;
                        height: 48px; margin-top: -12px; display: flex; align-items: center; justify-content: center; cursor: help;
                    ">
                        <span style="font-size:10px; color:#ccc;">无记录</span>
                    </div>
                    """, unsafe_allow_html=True)

    st.caption("💡 操作提示：点击任意 **单元号按钮** (如 #05-01)，将直接跳转至【智能估值】页面查看该单位估值与详情。")
