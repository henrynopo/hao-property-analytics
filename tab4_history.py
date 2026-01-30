import streamlit as st
import pandas as pd
import re

# --- 辅助：统一数据清洗 (与 Tab 3 保持一致) ---
def clean_and_prepare_data(df_raw):
    df = df_raw.copy()
    
    # 1. 列名映射
    rename_map = {
        'Transacted Price ($)': 'Sale Price',
        'Area (SQFT)': 'Area (sqft)',
        'Unit Price ($ psf)': 'Unit Price ($ psf)',
        'Unit Price ($ psm)': 'Unit Price ($ psm)',
        'Sale Date': 'Sale Date',
        'Bedroom Type': 'Type',   
        'No. of Bedroom': 'Type', 
        'Property Type': 'Type'   
    }
    df.rename(columns=rename_map, inplace=True)
    
    # 2. 确保列存在
    if 'Type' not in df.columns:
        df['Type'] = "N/A"
        
    if 'Sale Date' in df.columns:
        df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')

    # 3. 补全尺价
    if 'Unit Price ($ psf)' not in df.columns:
        if 'Sale Price' in df.columns and 'Area (sqft)' in df.columns:
            df['Unit Price ($ psf)'] = df['Sale Price'] / df['Area (sqft)']
        else:
            df['Unit Price ($ psf)'] = 0
            
    return df

# --- 辅助：格式化单元号 ---
def format_unit(floor, stack):
    try:
        f_num = int(float(floor))
        s_str = str(stack)
        s_fmt = s_str.zfill(2) if s_str.isdigit() else s_str
        return f"#{f_num:02d}-{s_fmt}"
    except:
        return f"#{floor}-{stack}"

# --- 主渲染函数 ---
def render(df_raw):
    st.subheader("📜 历年交易详情 (Transaction Details)")

    # 1. 数据清洗
    df = clean_and_prepare_data(df_raw)
    
    # 2. 默认按时间倒序排列
    df = df.sort_values('Sale Date', ascending=False)

    # 3. 构造显示列
    # 单位 (Unit): 拼接 BLK + Floor + Stack
    df['Unit'] = df.apply(
        lambda row: f"{row['BLK']} {format_unit(row['Floor'], row['Stack'])}", 
        axis=1
    )
    
    # 日期格式化
    df['Sale Date Str'] = df['Sale Date'].dt.strftime('%Y-%m-%d')
    
    # 价格格式化
    df['Sale Price Str'] = df['Sale Price'].apply(lambda x: f"${x/1e6:.2f}M")
    df['Unit Price Str'] = df['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}")
    
    # 4. 筛选显示的列 (完全对齐 Tab 3)
    # 列顺序：日期 | 单位 | 户型 | 面积 | 总价 | 尺价
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
