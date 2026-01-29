# 文件名: tab2_tower.py
import streamlit as st
import pandas as pd
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 核心：精准 SSD 政策计算器 (2025新政版) ---
def check_ssd_status(purchase_date):
    if pd.isna(purchase_date): return False, "无数据", 0
    
    # 确保是 datetime
    if not isinstance(purchase_date, datetime):
        purchase_date = pd.to_datetime(purchase_date)
        
    today = datetime.now()
    
    # 关键政策时间点
    POLICY_2025 = pd.Timestamp("2025-07-04") # 恢复为 4 年
    POLICY_2017 = pd.Timestamp("2017-03-11") # 降为 3 年
    
    # 判定锁定期 (Holding Period)
    if purchase_date >= POLICY_2025:
        lock_years = 4
        rule_desc = "新政(4年)"
    elif purchase_date >= POLICY_2017:
        lock_years = 3
        rule_desc = "旧政(3年)"
    else:
        lock_years = 4 # 2011-2017 也是4年
        rule_desc = "老政(4年)"
        
    ssd_deadline = purchase_date + relativedelta(years=lock_years)
    
    if today < ssd_deadline:
        days_left = (ssd_deadline - today).days
        years_held = (today - purchase_date).days / 365.25
        
        # 估算当前税率 (简化版)
        if years_held <= 1: rate = "16%" if lock_years==4 else "12%"
        elif years_held <= 2: rate = "12%" if lock_years==4 else "8%"
        elif years_held <= 3: rate = "8%" if lock_years==4 else "4%"
        else: rate = "4%" # 仅针对4年期的第4年
        
        msg = f"🔒 SSD锁定期 ({rule_desc})\n剩余: {days_left} 天\n当前税率: {rate}\n解锁日期: {ssd_deadline.strftime('%Y-%m-%d')}"
        return True, msg, lock_years
    else:
        return False, "✅ SSD Free (已满限售期)", lock_years

# 自然排序
def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# 渲染主函数
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")

    # 1. 筛选
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    selected_blk = st.selectbox("选择楼座 (Block)", all_blks, key="tab2_blk_select")
    blk_df = df[df['BLK'] == selected_blk].copy()

    # 2. 楼层排序 (数字)
    if 'Floor_Num' in blk_df.columns:
        blk_df['Floor_Sort'] = blk_df['Floor_Num'].fillna(0).astype(int)
    else:
        blk_df['Floor_Sort'] = blk_df['Floor'].astype(str).str.extract(r'(\d+)')[0].fillna(0).astype(int)

    # 3. 取最新交易
    latest_tx = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1)

    # 4. 生成 HTML (极简紧凑风格)
    def make_cell_html(row):
        price = f"${row['Sale Price']/1e6:.2f}M"
        psf = f"${row['Sale PSF']:,.0f}"
        sale_date = row['Sale Date']
        date_str = sale_date.strftime('%y-%m')
        
        # 计算 SSD
        is_locked, ssd_msg, _ = check_ssd_status(sale_date)
        
        # 样式逻辑：锁定期(红色) vs 自由期(白色/灰色)
        if is_locked:
            # 🔴 SSD 锁定期：红底白字，警示极强
            bg_style = "background-color: #fee2e2; border: 1px solid #ef4444;"
            text_color = "#991b1b" # 深红字
            badge = "🔒"
        else:
            # ⚪ 正常：极简白底
            bg_style = "background-color: #ffffff; border: 1px solid #e5e7eb;"
            text_color = "#374151"
            badge = ""

        # Tooltip 完整信息
        full_tooltip = f"成交: {sale_date.strftime('%Y-%m-%d')}&#10;总价: {price}&#10;尺价: {psf} psf&#10;----------------&#10;{ssd_msg}"

        return f"""
        <div title="{full_tooltip}" style="
            {bg_style}
            border-radius: 4px;
            padding: 2px 4px;
            margin-bottom: 2px;
            text-align: center;
            cursor: help;
            height: 100%;
            display: flex; flex-direction: column; justify-content: center;
        ">
            <div style="font-weight: 700; font-size: 13px; color: {text_color}; line-height: 1.1;">
                {price} {badge}
            </div>
            <div style="font-size: 11px; color: #6b7280; margin-top: 1px;">
                {psf}
            </div>
            <div style="font-size: 9px; color: #9ca3af;">
                {date_str}
            </div>
        </div>
        """
    
    latest_tx['display_html'] = latest_tx.apply(make_cell_html, axis=1)

    if not latest_tx.empty:
        # 透视表
        unit_grid = latest_tx.pivot(index='Floor_Sort', columns='Stack', values='display_html')
        # 排序
        sorted_cols = sorted(unit_grid.columns.tolist(), key=natural_key)
        unit_grid = unit_grid.reindex(columns=sorted_cols).sort_index(ascending=False)
        
        # 5. 渲染网格 (高密度布局)
        # 调整列宽：楼层列窄，数据列均分
        cols = st.columns([0.6] + [1] * len(unit_grid.columns))
        
        with cols[0]:
            st.markdown(f"<div style='font-size:12px; font-weight:bold; padding-top:15px; text-align:right; padding-right:5px;'>Floor</div>", unsafe_allow_html=True)
            
        for i, stack_name in enumerate(unit_grid.columns):
            with cols[i+1]:
                st.markdown(f"<div style='text-align: center; font-weight: bold; font-size:12px; border-bottom:1px solid #ccc; padding-bottom:4px; margin-bottom:4px;'>{stack_name}</div>", unsafe_allow_html=True)

        for floor_num, row in unit_grid.iterrows():
            c_row = st.columns([0.6] + [1] * len(unit_grid.columns))
            
            with c_row[0]:
                st.markdown(f"<div style='font-size:12px; font-weight:bold; color:#666; text-align:right; padding-right:5px; padding-top:10px;'>L{floor_num}</div>", unsafe_allow_html=True)
                
            for i, stack_name in enumerate(unit_grid.columns):
                content = row[stack_name]
                with c_row[i+1]:
                    if pd.isna(content):
                        # 空白格占位
                        st.markdown("<div style='height: 50px; border: 1px dashed #f3f4f6; margin-bottom: 2px; border-radius:4px;'></div>", unsafe_allow_html=True)
                    else:
                        st.markdown(content, unsafe_allow_html=True)
        
        st.caption("🔒 **红色高亮**表示该单位受 SSD 限制（含2025新政4年期）。鼠标悬停可查看剩余天数与税率。")
    else:
        st.info("该楼座暂无交易数据")
