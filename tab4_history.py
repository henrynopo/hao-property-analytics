import streamlit as st
import pandas as pd
from utils import format_unit # [V204] 引用通用工具

# --- 主渲染函数 ---
def render(df):
    st.subheader("📜 历年交易详情 (Transaction Details)")

    # 1. 简单排序 (不再需要重复清洗)
    if 'Sale Date' in df.columns:
        df = df.sort_values('Sale Date', ascending=False)

    # 2. 构造显示列
    # [V204] 使用 utils.format_unit，保持 #01-05 格式统一
    if 'Unit' not in df.columns:
        df['Unit'] = df.apply(
            lambda row: f"BLK {row['BLK']} {format_unit(row['Floor_Num'], row['Stack'])}", 
            axis=1
        )
    
    # 3. 格式化用于显示的列
    # 注意：不要修改原 df 的数值列，而是创建新的 Str 列用于显示
    if 'Sale Date' in df.columns:
        df['Sale Date Str'] = df['Sale Date'].dt.strftime('%Y-%m-%d')
    else:
        df['Sale Date Str'] = "-"
        
    df['Sale Price Str'] = df['Sale Price'].apply(lambda x: f"${x/1e6:.2f}M" if pd.notnull(x) else "-")
    df['Unit Price Str'] = df['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "-")
    
    # 4. 筛选显示的列
    # 确保 'Type' 列存在 (utils.load_data 已处理，但为了保险)
    if 'Type' not in df.columns: df['Type'] = "N/A"
    
    display_cols = ['Sale Date Str', 'Unit', 'Type', 'Area (sqft)', 'Sale Price Str', 'Unit Price Str']
    
    # 5. 渲染表格
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Sale Date Str": "日期",
            "Unit": "单位",
            "Type": "户型",
            "Area (sqft)": "面积 (sqft)",
            "Sale Price Str": "总价",
            "Unit Price Str": "尺价 (psf)"
        }
    )
