# 文件名: tab2_tower.py
import streamlit as st
import pandas as pd
import re
import html
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 核心：SSD 计算器 ---
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
        short_status = f"🔒 SSD:{desc}"
        full_msg = f"状态: 🔒 锁定期 ({desc})\n剩余: {days_left} 天\n解锁: {ssd_deadline.strftime('%Y-%m-%d')}"
        return True, short_status, full_msg
    else:
        return False, "✅ Free", "状态: ✅ SSD 已解禁"

def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")

    # 1. 筛选
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    selected_blk = st.selectbox("选择楼座 (Block)", all_blks, key="tab2_blk_select")
    blk_df = df[df['BLK'] == selected_blk].copy()

    # 2. 楼层排序与准备
    if 'Floor_Num' in blk_df.columns:
        blk_df['Floor_Sort'] = blk_df['Floor_Num'].fillna(0).astype(int)
    else:
        blk_df['Floor_Sort'] = blk_df['Floor'].astype(str).str.extract(r'(\d+)')[0].fillna(0).astype(int)

    # 3. 构建完整骨架 (解决单元消失问题)
    # 找出该楼座所有的 Stack (自然排序)
    all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
    
    # 找出楼层范围 (Min 到 Max)
    # 注意：如果数据太少可能不准，但通常这是推断楼宇结构的最好方法
    if not blk_df.empty:
        min_floor = int(blk_df['Floor_Sort'].min())
        max_floor = int(blk_df['Floor_Sort'].max())
        # 生成连续的楼层列表
        all_floors = list(range(min_floor, max_floor + 1))
    else:
        all_floors = []

    # 4. 取最新交易数据
    latest_tx = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1)

    # 5. 生成 HTML
    def make_cell_html(row):
        # 如果是空数据(填充出来的)，row里全是NaN
        if pd.isna(row['Sale Date']):
            return None
            
        price = f"${row['Sale Price']/1e6:.2f}M"
        psf = f"${row['Sale PSF']:,.0f}"
        sale_date = row['Sale Date']
        
        is_locked, short_status, full_ssd_msg = check_ssd_status(sale_date)
        
        if is_locked:
            bg_color = "#fee2e2"
            border = "1px solid #f87171"
            text_color = "#991b1b"
            status_style = "color: #dc2626; font-weight: bold;"
        else:
            bg_color = "#ffffff"
            border = "1px solid #e5e7eb"
            text_color = "#1f2937"
            status_style = "color: #059669;"

        raw_tooltip = f"成交日期: {sale_date.strftime('%Y-%m-%d')}\n总价: {price}\n尺价: {psf} psf\n{full_ssd_msg}"
        safe_tooltip = html.escape(raw_tooltip, quote=True)

        return f"""
        <div title="{safe_tooltip}" style="
            background-color: {bg_color};
            border: {border};
            border-radius: 4px;
            padding: 2px;
            margin-bottom: 2px;
            text-align: center;
            height: 100%;
            cursor: pointer;
        ">
            <div style="font-weight: 700; font-size: 13px; color: {text_color}; line-height: 1.1;">{price}</div>
            <div style="font-size: 11px; color: #4b5563;">{psf}</div>
            <div style="font-size: 10px; {status_style} margin-top:1px;">{short_status}</div>
        </div>
        """
    
    # 这里的 apply 可能会遇到全 NaN 的行，需要注意
    # 我们先对 latest_tx 生成 display_html，此时只有有数据的行
    latest_tx['display_html'] = latest_tx.apply(make_cell_html, axis=1)

    if not latest_tx.empty and all_floors:
        # 6. 透视表与强制重索引 (核心修复步骤)
        unit_grid = latest_tx.pivot(index='Floor_Sort', columns='Stack', values='display_html')
        
        # 强制使用完整的 Stack 列表作为列 (即使某些 Stack 没交易也要显示)
        unit_grid = unit_grid.reindex(columns=all_stacks)
        
        # 强制使用完整的 Floor 列表作为索引 (即使某层没交易也要显示)
        # 倒序排列：高层在上
        unit_grid = unit_grid.reindex(index=sorted(all_floors, reverse=True))
        
        # 7. 渲染
        # 动态列宽
        cols = st.columns([0.6] + [1.2] * len(all_stacks))
        
        # 表头
        with cols[0]:
            st.markdown(f"<div style='font-size:12px; font-weight:bold; text-align:right; padding-right:8px;'>Floor</div>", unsafe_allow_html=True)
        for i, stack_name in enumerate(all_stacks):
            with cols[i+1]:
                st.markdown(f"<div style='text-align: center; font-weight: bold; font-size:12px; border-bottom:1px solid #ccc;'>{stack_name}</div>", unsafe_allow_html=True)

        # 表体
        for floor_num, row in unit_grid.iterrows():
            c_row = st.columns([0.6] + [1.2] * len(all_stacks))
            
            # 楼层号
            with c_row[0]:
                st.markdown(f"<div style='font-size:12px; font-weight:bold; color:#666; text-align:right; padding-right:8px; padding-top:12px;'>L{floor_num}</div>", unsafe_allow_html=True)
            
            # 单元格
            for i, stack_name in enumerate(all_stacks):
                content = row[stack_name]
                with c_row[i+1]:
                    if pd.isna(content):
                        # 空白格：显示灰色占位符，表示该单元物理存在但无交易
                        st.markdown("<div style='height: 50px; background-color: #f3f4f6; margin-bottom: 2px; border-radius:4px; border:1px dashed #d1d5db;'></div>", unsafe_allow_html=True)
                    else:
                        st.markdown(content, unsafe_allow_html=True)
                        
        st.caption("注：灰色虚线框表示该单位在数据集中无历史交易记录，但根据楼宇结构推定存在。")
    else:
        st.info("该楼座暂无交易数据")
