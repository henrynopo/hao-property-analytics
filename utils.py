import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st
import plotly.graph_objects as go 

# ==================== 1. 全局配置与常量 ====================

CUSTOM_DISCLAIMER = "Disclaimer: Estimates (AVM) for reference only. Not certified valuations. Source: URA/Huttons. No warranty on accuracy."

# [V207] 增强版列名映射表
COLUMN_RENAME_MAP = {
    'Transacted Price ($)': 'Sale Price', 'Sale Price ($)': 'Sale Price', 'Price ($)': 'Sale Price',
    'Area (SQFT)': 'Area (sqft)', 'Area(sqft)': 'Area (sqft)',
    'Unit Price ($ psf)': 'Unit Price ($ psf)', 'Sale PSF': 'Unit Price ($ psf)', 'Unit Price ($ psm)': 'Unit Price ($ psm)',
    'Sale Date': 'Sale Date', 'Date of Sale': 'Sale Date',
    'Bedroom Type': 'Type', 'No. of Bedroom': 'Type', 'Property Type': 'Sub Type', 'Building Type': 'Sub Type',
    'Tenure': 'Tenure', 'Lease Commencement Date': 'Tenure From', 'Tenure Start Date': 'Tenure From'
}

# [V207] 健壮的 Agent Profile 加载逻辑
def get_agent_profile():
    try: raw = dict(st.secrets["agent"])
    except Exception: raw = {}
    defaults = {
        "name": "Henry", "title": "Associate Division Director", "agency": "Huttons Asia Pte Ltd",
        "license": "L3008899K", "contact": "+65 9123 4567", "email": "henry@huttons.com"
    }
    profile = {}
    profile['name'] = raw.get('name', raw.get('Name', defaults['name']))
    profile['title'] = raw.get('title', raw.get('Title', defaults['title']))
    profile['agency'] = raw.get('agency', raw.get('Company', raw.get('company', defaults['agency']))) 
    profile['license'] = raw.get('license', raw.get('License', defaults['license']))
    profile['contact'] = raw.get('contact', raw.get('Mobile', raw.get('mobile', defaults['contact'])))
    profile['email'] = raw.get('email', raw.get('Email', defaults['email']))
    return profile

AGENT_PROFILE = get_agent_profile()

try:
    project_config = dict(st.secrets["projects"])
    cleaned_config = {k: (None if v == "None" else v) for k, v in project_config.items()}
    PROJECTS = cleaned_config
except Exception:
    PROJECTS = {"📂 手动上传 CSV": None}

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
    try: f_num = int(float(floor)); return f"#{f_num:02d}-XX"
    except: return f"#{floor}-XX"

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
                if "Sale Date" in row_str or "BLK" in row_str or "Transacted Price" in row_str:
                    header_row = i; break
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url, header=header_row if header_row != -1 else 0)
        except:
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url)

        df.columns = df.columns.str.strip()
        df.rename(columns=COLUMN_RENAME_MAP, inplace=True)
        
        for col in ['Sale Price', 'Unit Price ($ psf)', 'Area (sqft)']:
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
        
        for col in ['Type', 'Tenure', 'Tenure From', 'Sub Type']:
            if col not in df.columns: df[col] = "N/A"

        if 'Stack' in df.columns and 'Floor_Num' in df.columns:
            df['Unit'] = df.apply(lambda row: format_unit(row['Floor_Num'], row['Stack']), axis=1)
            df['Unit_ID'] = df['BLK'].astype(str) + "-" + df['Stack'].astype(str) + "-" + df['Floor_Num'].astype(str)
        return df
    except Exception: return None

def auto_categorize(df, method):
    if method == "按卧室数量 (Bedroom Type)":
        target_cols = ['Type', 'Bedroom Type', 'Bedrooms']
        found = next((c for c in df.columns if c in target_cols), None)
        return df[found].astype(str).str.strip().str.upper() if found else pd.Series(["Unknown"] * len(df))
    elif method == "按楼座 (Block)": return df['BLK']
    else: return df['Area (sqft)'].apply(lambda x: "Small" if x<800 else "Medium" if x<1200 else "Large" if x<1600 else "X-Large" if x<2500 else "Giant")

def mark_penthouse(df):
    if 'Area (sqft)' not in df.columns or 'Category' not in df.columns: return pd.Series([False] * len(df))
    medians = df.groupby('Category')['Area (sqft)'].median()
    return df.apply(lambda row: row['Area (sqft)'] > (medians.get(row['Category'], 0) * 1.4), axis=1)

# ==================== 4. 业务逻辑与算法 ====================

def calculate_market_trend(full_df):
    """计算年化市场增长率"""
    limit_date = datetime.now() - pd.DateOffset(months=36)
    trend_data = full_df[full_df['Sale Date'] >= limit_date].copy()
    if len(trend_data) < 10: return 0.0
    trend_data['Date_Ord'] = trend_data['Sale Date'].map(datetime.toordinal)
    x, y = trend_data['Date_Ord'], trend_data['Unit Price ($ psf)']
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_price = y.mean()
        if avg_price == 0: return 0.0
        return max(-0.05, min(0.10, (slope / avg_price) * 365))
    except: return 0.0

def detect_block_step(blk_df): return 1 # (简化占位，保留接口)
def get_stack_start_floor(stack_df, block_min_f, step): return block_min_f
def estimate_inventory(df, category_col='Category'): return {}
def get_dynamic_floor_premium(df, category): return 0.005
def calculate_ssd_status(purchase_date): return 0.0, "🟢", "SSD Free"

# ==================== 5. 共享图表组件 ====================

def render_gauge(est_psf, font_size=12):
    range_min, range_max = est_psf * 0.90, est_psf * 1.10
    axis_min, axis_max = est_psf * 0.80, est_psf * 1.20
    fig = go.Figure(go.Indicator(
        mode = "gauge+number", value = est_psf, number = {'suffix': " psf", 'font': {'size': 18}}, 
        domain = {'x': [0, 1], 'y': [0, 1]},
        gauge = {
            'axis': {'range': [axis_min, axis_max], 'tickwidth': 1, 'tickcolor': "darkblue", 'tickmode': 'array', 'tickvals': [axis_min, est_psf, axis_max], 'ticktext': [f"{int(axis_min)}", f"{int(est_psf)}", f"{int(axis_max)}"]},
            'bar': {'thickness': 0}, 'bgcolor': "white", 'borderwidth': 2, 'bordercolor': "#e5e7eb",
            'steps': [{'range': [axis_min, range_min], 'color': "#f3f4f6"}, {'range': [range_min, range_max], 'color': "#2563eb"}, {'range': [range_max, axis_max], 'color': "#f3f4f6"}],
            'threshold': {'line': {'color': "#dc2626", 'width': 3}, 'thickness': 0.8, 'value': est_psf}
        }
    ))
    fig.update_layout(height=150, margin=dict(l=20, r=20, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", font={'family': "Arial", 'size': 11})
    return fig