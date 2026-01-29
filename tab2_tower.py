# 文件名: tab2_tower.py (请务必确认文件名是这个！)
import streamlit as st
import pandas as pd
import re

# --- UI组件: 统一 KPI 卡片 ---
def kpi_card(label, value, sub_value=None, color="default"):
    color_map = {"default": "#111827", "blue": "#2563eb"}
    text_color = color_map.get(color, "#111827")
    sub_html = f'<div style="font-size: 12px; color: #6b7280; margin-top: 2px;">{sub_value}</div>' if sub_value else ""
    return f"""
    <div style="background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; text-align: center;">
        <div style="font-size: 13px; color: #6b7280; margin-bottom: 4px;">{label}</div>
        <div style="font-size: 18px; font-weight: 700; color: {text_color};">{value}</div>
        {sub_html}
    </div>
    """

def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# 🟢 核心：接收 chart_font_size 参数，修复 TypeError
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")

    # 1. 筛选
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    selected_blk = st.selectbox("选择楼座 (Block)", all_blks, key="tab2_blk_select")

    # 2. 数据准备
    blk_df = df[df['BLK'] == selected_blk].copy()
    
    # Block 概览 KPI
    if not blk_df.empty:
        vol = len(blk_df)
        avg_psf = blk_df['Sale PSF'].mean()
        max_price = blk_df['Sale Price'].max()
        
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(kpi_card("本座成交量", f"{vol} 笔", color="default"), unsafe_allow_html=True)
        with c2: st.markdown(kpi_card("本座均价", f"${avg_psf:,.0f} psf", color="blue"), unsafe_allow_html=True)
        with c3: st.markdown(kpi_card("本座最高价", f"${max_price/1e6:.2f}M", color="default"), unsafe_allow_html=True)
        st.markdown("---")

    # 3. 网格逻辑
    if 'Floor_Num' in blk_df.columns:
        blk_df['Floor_Sort'] = blk_df['Floor_Num'].fillna(0).astype(int)
    else:
        blk_df['Floor_Sort'] = blk_df['Floor'].astype(str).str.extract(r'(\d+)')[0].fillna(0).astype(int)

    latest_tx = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1)
    
    # 🟢 动态字体逻辑：基于 chart_font_size 调整网格内文字大小
    scale_ratio = chart_font_size / 12.0
    fs_price = int(14 * scale_ratio)
    fs_psf = int(12 * scale_ratio)
    fs_date = int(10 * scale_ratio)

    def make_cell_html(row):
        price = f"${row['Sale Price']/1e6:.2f}M"
        psf = f"${row['Sale PSF']:,.0f} psf"
        date = row['Sale Date'].strftime('%y-%m') if isinstance(row['Sale Date'], pd.Timestamp) else str(row['Sale Date'])[:7]
        return f"""
        <div style="text-align: center; line-height: 1.2;">
            <div style="font-weight: bold; font-size: {fs_price}px;">{price}</div>
            <div style="font-size: {fs_psf}px; color: #555;">{psf}</div>
            <div style="font-size: {fs_date}px; color: #999;">{date}</div>
        </div>
        """
    
    latest_tx['display_html'] = latest_tx.apply(make_cell_html, axis=1)

    if not latest_tx.empty:
        unit_grid = latest_tx.pivot(index='Floor_Sort', columns='Stack', values='display_html')
        # 严谨排序 Stack
        sorted_cols = sorted(unit_grid.columns.tolist(), key=natural_key)
        unit_grid = unit_grid.reindex(columns=sorted_cols).sort_index(ascending=False)
        
        # 渲染
        cols = st.columns([1] + [2] * len(unit_grid.columns))
        with cols[0]: st.markdown(f"<div style='font-size:{chart_font_size}px; font-weight:bold'>Floor</div>", unsafe_allow_html=True)
        for i, stack_name in enumerate(unit_grid.columns):
            with cols[i+1]: st.markdown(f"<div style='text-align: center; font-weight: bold; font-size:{chart_font_size}px'>{stack_name}</div>", unsafe_allow_html=True)
            
        st.markdown("---")

        for floor_num, row in unit_grid.iterrows():
            c_row = st.columns([1] + [2] * len(unit_grid.columns))
            with c_row[0]: st.markdown(f"<div style='font-size:{chart_font_size}px; font-weight:bold'>L{floor_num}</div>", unsafe_allow_html=True)
            for i, stack_name in enumerate(unit_grid.columns):
                content = row[stack_name]
                with c_row[i+1]:
                    if pd.isna(content):
                        st.markdown("<div style='background-color: #f0f2f6; border-radius: 4px; height: 60px; display: flex; align-items: center; justify-content: center; color: #ccc;'>-</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 4px; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);'>{content}</div>", unsafe_allow_html=True)
    else:
        st.info("该楼座暂无交易数据")

    st.caption(f"显示 Block {selected_blk} 最新成交。")
