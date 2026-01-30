import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st
import plotly.graph_objects as go 

# ==================== 1. 全局配置与常量 ====================

CUSTOM_DISCLAIMER = "Disclaimer: Estimates (AVM) for reference only. Not certified valuations. Source: URA/Huttons. No warranty on accuracy."

COLUMN_RENAME_MAP = {
    'Transacted Price ($)': 'Sale Price',
    'Area (SQFT)': 'Area (sqft)',
    'Unit Price ($ psf)': 'Unit Price ($ psf)',
    'Unit Price ($ psm)': 'Unit Price ($ psm)',
    'Sale Date': 'Sale Date',
    'Bedroom Type': 'Type',   
    'No. of Bedroom': 'Type', 
    'Tenure': 'Tenure',
    'Lease Commencement Date': 'Tenure From',
    'Tenure Start Date': 'Tenure From',
    'Property Type': 'Sub Type',
    'Building Type': 'Sub Type'
}

try:
    AGENT_PROFILE = dict(st.secrets["agent"])
except Exception:
    AGENT_PROFILE = {
        "name": "Henry", 
        "title": "Associate Division Director",
        "agency": "Huttons Asia Pte Ltd",
        "license": "L3008899K",
        "contact": "+65 9123 4567",
        "email": "henry@huttons.com"
    }

try:
    project_config = dict(st.secrets["projects"])
    cleaned_config = {k: (None if v == "None" else v) for k, v in project_config.items()}
    PROJECTS = cleaned_config
except Exception:
    PROJECTS = {
        "📂 手动上传 CSV": None,
    }

# ==================== 2. 通用格式化工具 ====================

def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]

def format_currency(val):
    try: return f"${val:,.0f}"
    except: return val

def format_unit(floor, stack):
    try:
        f_num = int(float(floor))
        s_str = str(stack).strip()
        s_fmt = s_str.zfill(2) if s_str.isdigit() else s_str
        return f"#{f_num:02d}-{s_fmt}"
    except:
        return f"#{floor}-{stack}"

def format_unit_masked(floor):
    try:
        f_num = int(float(floor))
        return f"#{f_num:02d}-XX"
    except:
        return f"#{floor}-XX"

# ==================== 3. 数据加载与清洗 ====================

@st.cache_data(ttl=300)
def load_data(file_or_url):
    try:
        if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
        try:
            df_temp = pd.read_csv(file_or_url, header=None, nrows=20)
            header_row = -1
            for i, row in df_temp.iterrows():
                row_str = row.astype(str).str.cat(sep=',')
                if "Sale Date" in row_str or "BLK" in row_str:
                    header_row = i; break
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url, header=header_row if header_row != -1 else 0)
        except:
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url)

        df.columns = df.columns.str.strip()
        
        # 统一列名清洗
        df.rename(columns=COLUMN_RENAME_MAP, inplace=True) 
        
        for col in ['Sale Price', 'Sale PSF', 'Area (sqft)', 'Unit Price ($ psf)']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'[$,]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if 'Sale Date' in df.columns:
            df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
            df['Sale Year'] = df['Sale Date'].dt.year
            df['Date_Ordinal'] = df['Sale Date'].map(datetime.toordinal)

        if 'BLK' in df.columns: df['BLK'] = df['BLK'].astype(str).str.strip()
        if 'Stack' in df.columns: df['Stack'] = df['Stack'].astype(str).str.strip()
        if 'Floor' in df.columns: df['Floor_Num'] = pd.to_numeric(df['Floor'], errors='coerce')
        
        # 确保基础列存在，防止报错
        for col in ['Type', 'Tenure', 'Tenure From', 'Sub Type']:
            if col not in df.columns: df[col] = "N/A"

        if 'Stack' in df.columns and 'Floor_Num' in df.columns:
            df['Unit'] = df.apply(lambda row: format_unit(row['Floor_Num'], row['Stack']), axis=1)
            df['Unit_ID'] = df['BLK'].astype(str) + "-" + df['Stack'].astype(str) + "-" + df['Floor_Num'].astype(str)
            
        return df
    except Exception as e: return None

def auto_categorize(df, method):
    if method == "按卧室数量 (Bedroom Type)":
        target_cols = ['Bedroom Type', 'Bedroom_Type', 'Bedrooms', 'Type']
        found = next((c for c in df.columns if c in target_cols or 'Bedroom' in c), None)
        return df[found].astype(str).str.strip().str.upper() if found else pd.Series(["Unknown"] * len(df))
    elif method == "按楼座 (Block)": return df['BLK']
    else: return df['Area (sqft)'].apply(lambda x: "Small" if x<800 else "Medium" if x<1200 else "Large" if x<1600 else "X-Large" if x<2500 else "Giant")

def mark_penthouse(df):
    if 'Area (sqft)' not in df.columns or 'Category' not in df.columns: return pd.Series([False] * len(df))
    medians = df.groupby('Category')['Area (sqft)'].median()
    return df.apply(lambda row: row['Area (sqft)'] > (medians.get(row['Category'], 0) * 1.4), axis=1)

# ==================== 4. 业务逻辑与算法 ====================

# [V203 Moved] 从 Tab 3 移动过来的市场趋势计算
def calculate_market_trend(full_df):
    """计算年化市场增长率 (用于 AVM 和 市场分析)"""
    limit_date = datetime.now() - pd.DateOffset(months=36)
    trend_data = full_df[full_df['Sale Date'] >= limit_date].copy()
    if len(trend_data) < 10: return 0.0
    
    trend_data['Date_Ord'] = trend_data['Sale Date'].map(datetime.toordinal)
    x = trend_data['Date_Ord']
    y = trend_data['Unit Price ($ psf)']
    
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_price = y.mean()
        if avg_price == 0: return 0.0
        # 将每日斜率转换为年化增长率
        return max(-0.05, min(0.10, (slope / avg_price) * 365))
    except:
        return 0.0

def detect_block_step(blk_df):
    if blk_df.empty: return 1
    unique_stacks = blk_df['Stack'].unique()
    if len(unique_stacks) == 0: return 1
    votes_simplex = 0
    votes_maisonette = 0
    for stack in unique_stacks:
        stack_df = blk_df[blk_df['Stack'] == stack]
        floors = sorted(stack_df['Floor_Num'].dropna().unique())
        if len(floors) < 2: continue
        has_odd = any(f % 2 != 0 for f in floors)
        has_even = any(f % 2 == 0 for f in floors)
        if (has_odd and not has_even) or (not has_odd and has_even):
            votes_maisonette += 1
        else:
            votes_simplex += 1
    if votes_maisonette > votes_simplex: return 2
    else: return 1

def get_stack_start_floor(stack_df, block_min_f, step):
    if step == 1: return block_min_f
    floors = sorted(stack_df['Floor_Num'].dropna().unique())
    if not floors: return block_min_f
    odd_count = sum(1 for f in floors if f % 2 != 0)
    even_count = sum(1 for f in floors if f % 2 == 0)
    if odd_count > even_count:
        return block_min_f if block_min_f % 2 != 0 else block_min_f + 1
    else:
        return block_min_f if block_min_f % 2 == 0 else block_min_f + 1

def estimate_inventory(df, category_col='Category'):
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns: return {}
    if 'Stack' not in df.columns:
        inv_map = {}
        for cat in df[category_col].unique():
            inv_map[cat] = len(df[df[category_col] == cat])
        return inv_map

    df = df.dropna(subset=['Floor_Num']).copy()
    final_totals = {cat: 0 for cat in df[category_col].unique()}
    unique_blocks = df['BLK'].unique()
    
    for blk in unique_blocks:
        blk_df = df[df['BLK'] == blk]
        step = detect_block_step(blk_df)
        min_f = int(blk_df['Floor_Num'].min())
        max_f = int(blk_df['Floor_Num'].max())
        if min_f < 1: min_f = 1
        
        unique_stacks = blk_df['Stack'].unique()
        for stack in unique_stacks:
            stack_df = blk_df[blk_df['Stack'] == stack]
            if not stack_df.empty:
                dominant_cat = stack_df[category_col].mode()[0]
                start_f = get_stack_start_floor(stack_df, min_f, step)
                theoretical_floors = range(start_f, max_f + 1, step)
                count_per_stack = len(theoretical_floors)
                final_totals[dominant_cat] = final_totals.get(dominant_cat, 0) + count_per_stack

    observed_counts = df.groupby(category_col)['Unit_ID'].nunique().to_dict()
    for cat in final_totals:
        if final_totals[cat] < observed_counts.get(cat, 0):
            final_totals[cat] = observed_counts.get(cat, 0)
            
    return final_totals

# ==================== 5. 共享图表组件 ====================

def render_gauge(est_psf, font_size=12):
    range_min = est_psf * 0.90
    range_max = est_psf * 1.10
    axis_min = est_psf * 0.80
    axis_max = est_psf * 1.20
        
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = est_psf,
        number = {'suffix': " psf", 'font': {'size': 18}}, 
        domain = {'x': [0, 1], 'y': [0, 1]},
        gauge = {
            'axis': {
                'range': [axis_min, axis_max], 
                'tickwidth': 1, 
                'tickcolor': "darkblue",
                'tickmode': 'array',
                'tickvals': [axis_min, est_psf, axis_max],
                'ticktext': [f"{int(axis_min)}", f"{int(est_psf)}", f"{int(axis_max)}"]
            },
            'bar': {'thickness': 0}, 
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "#e5e7eb",
            'steps': [
                {'range': [axis_min, range_min], 'color': "#f3f4f6"},
                {'range': [range_min, range_max], 'color': "#2563eb"},
                {'range': [range_max, axis_max], 'color': "#f3f4f6"}
            ],
            'threshold': {
                'line': {'color': "#dc2626", 'width': 3},
                'thickness': 0.8,
                'value': est_psf
            }
        }
    ))
    fig.update_layout(
        height=150, 
        margin=dict(l=20, r=20, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'family': "Arial", 'size': 11}
    )
    return fig
