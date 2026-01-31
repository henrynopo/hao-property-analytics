import streamlit as st
import pandas as pd
from utils import format_unit 

def render(df):
    st.subheader("📜 历年交易详情 (Transaction Details)")

    # 1. 筛选逻辑
    with st.expander("🔍 筛选 (Filter)", expanded=True): # 默认展开方便点击
        c1, c2 = st.columns(2)
        
        # --- Block 筛选 (Button Style) ---
        all_blks = sorted(df['BLK'].unique())
        try:
            # 尝试使用新版 pills (按钮样式)
            sel_blks = c1.pills(
                "楼座 (Block)", 
                options=all_blks, 
                selection_mode="multi", 
                key="filter_blk_pills"
            )
        except AttributeError:
            # 回退到旧版 multiselect
            sel_blks = c1.multiselect("楼座 (Block)", all_blks, key="filter_blk_multi")
        
        # --- Type 筛选 (Button Style) ---
        type_col = 'Type' if 'Type' in df.columns else 'Category'
        all_types = sorted(df[type_col].unique())
        try:
            sel_types = c2.pills(
                "户型 (Type)", 
                options=all_types, 
                selection_mode="multi", 
                key="filter_type_pills"
            )
        except AttributeError:
            sel_types = c2.multiselect("户型 (Type)", all_types, key="filter_type_multi")
        
    filtered_df = df.copy()
    if sel_blks: filtered_df = filtered_df[filtered_df['BLK'].isin(sel_blks)]
    if sel_types: filtered_df = filtered_df[filtered_df[type_col].isin(sel_types)]
    
    filtered_df = filtered_df.sort_values('Sale Date', ascending=False)

    # 2. 构造显示列
    if 'Unit' not in filtered_df.columns:
        filtered_df['Unit'] = filtered_df.apply(
            lambda row: f"BLK {row['BLK']} {format_unit(row['Floor_Num'], row['Stack'])}", 
            axis=1
        )
    
    # 3. 格式化用于显示的列
    if 'Sale Date Str' not in filtered_df.columns:
        filtered_df['Sale Date Str'] = filtered_df['Sale Date'].dt.strftime('%Y-%m-%d')
        
    filtered_df['Sale Price Str'] = filtered_df['Sale Price'].apply(lambda x: f"${x/1e6:.2f}M" if pd.notnull(x) else "-")
    filtered_df['Unit Price Str'] = filtered_df['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "-")
    
    display_cols = ['Sale Date Str', 'Unit', type_col, 'Area (sqft)', 'Sale Price Str', 'Unit Price Str']
    
    # 4. 渲染表格
    st.dataframe(
        filtered_df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Sale Date Str": "日期",
            "Unit": "单位",
            type_col: "户型",
            "Area (sqft)": "面积 (sqft)",
            "Sale Price Str": "总价",
            "Unit Price Str": "尺价 (psf)"
        }
    )