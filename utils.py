# 文件名: utils.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st

# ==================== 1. 个人品牌与项目配置 (从 Secrets 读取) ====================

# 🟢 读取个人信息
try:
    AGENT_PROFILE = dict(st.secrets["agent"])
except Exception:
    # 如果 secrets 不存在，使用默认占位符防止报错
    AGENT_PROFILE = {
        "Name": "Agent Name",
        "Title": "Property Agent",
        "Company": "Real Estate Agency",
        "License": "L300XXXXX",
        "RES_No": "R0123456Z", 
        "Mobile": "+65 9123 4567",
        "Email": "agent@email.com"
    }

# 🟢 读取项目列表
try:
    project_config = dict(st.secrets["projects"])
    # 过滤掉值为 "None" 的字符串占位符，转为真正的 None
    cleaned_config = {k: (None if v == "None" else v) for k, v in project_config.items()}
    PROJECTS = cleaned_config
except Exception:
    PROJECTS = {
        "📂 手动上传 CSV": None,
    }

# ==================== 2. 基础工具 ====================
def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]

def format_currency(val):
    try: return f"${val:,.0f}"
    except: return val

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
        for col in ['Sale Price', 'Sale PSF', 'Area (sqft)']:
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

        if 'Stack' in df.columns and 'Floor_Num' in df.columns:
            def format_unit(row):
                try:
                    f = int(row['Floor_Num'])
                    s = str(row['Stack']).strip()
                    return f"#{f:02d}-{s.zfill(2) if s.isdigit() else s}"
                except: return ""
            df['Unit'] = df.apply(format_unit, axis=1)
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

# ==================== 3. 业务算法 ====================
def estimate_inventory(df, category_col='Category'):
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns: return {}
    df_clean = df.dropna(subset=['Floor_Num'])
    cat_max = {cat: df_clean[df_clean[category_col]==cat]['Floor_Num'].max() for cat in df_clean[category_col].unique()}
    
    stack_inv = {}
    for (blk, stack), group in df_clean.groupby(['BLK', 'Stack']):
        cat = group[category_col].mode()[0] if not group.empty else "Unknown"
        stack_inv[(blk, stack)] = {'count': int(cat_max.get(cat, group['Floor_Num'].max())), 'category': cat}
        
    return {cat: sum(1 for v in stack_inv.values() if v['category'] == cat) * 10 for cat in df_clean[category_col].unique()}

def get_dynamic_floor_premium(df, category):
    return 0.005

def calculate_ssd_status(purchase_date):
    now, p_dt = datetime.now(), pd.to_datetime(purchase_date)
    held_years = (now - p_dt).days / 365.25
    rate, emoji, text = 0.0, "🟢", "SSD Free"
    
    # 2025 新政
    if p_dt >= datetime(2025, 7, 4):
        if held_years < 1: rate, emoji, text = 0.16, "🔴", "SSD 16%"
        elif held_years < 2: rate, emoji, text = 0.12, "🔴", "SSD 12%"
        elif held_years < 3: rate, emoji, text = 0.08, "🔴", "SSD 8%"
        elif held_years < 4: rate, emoji, text = 0.04, "🔴", "SSD 4%"
    elif p_dt >= datetime(2017, 3, 11):
        if held_years < 1: rate, emoji, text = 0.12, "🔴", "SSD 12%"
        elif held_years < 2: rate, emoji, text = 0.08, "🔴", "SSD 8%"
        elif held_years < 3: rate, emoji, text = 0.04, "🔴", "SSD 4%"
    return rate, emoji, text

def get_market_trend_model(df):
    df = df.dropna(subset=['Sale PSF', 'Date_Ordinal'])
    if len(df) < 10: return None, 0
    try:
        z = np.polyfit(df['Date_Ordinal'], df['Sale PSF'], 1)
        return np.poly1d(z), 0.5
    except: return None, 0

def calculate_avm(df, blk, stack, floor):
    target = df[(df['BLK'] == blk) & (df['Stack'] == stack) & (df['Floor_Num'] == floor)]
    if target.empty: return None, None, None, None, None, pd.DataFrame(), None
    
    area = target['Area (sqft)'].iloc[0]
    cat = target['Category'].iloc[0]
    
    comps = df[(df['Category'] == cat) & (df['Sale Date'] > df['Sale Date'].max() - timedelta(days=365))]
    if comps.empty: comps = df[df['Category'] == cat].sort_values('Sale Date', ascending=False).head(5)
    
    base_psf = comps['Sale PSF'].median() if not comps.empty else 1000
    est_psf = base_psf 
    valuation = area * est_psf
    
    return area, est_psf, valuation, 0, 0.005, comps.head(5), cat

def calculate_resale_metrics(df):
    if 'Unit_ID' not in df.columns: return pd.DataFrame()
    df = df.sort_values(['Unit_ID', 'Sale Date'])
    df['Prev_Price'] = df.groupby('Unit_ID')['Sale Price'].shift(1)
    df['Prev_Date'] = df.groupby('Unit_ID')['Sale Date'].shift(1)
    res = df.dropna(subset=['Prev_Price']).copy()
    res['Gain'] = res['Sale Price'] - res['Prev_Price']
    res['Hold_Years'] = (res['Sale Date'] - res['Prev_Date']).dt.days / 365.25
    res['Annualized'] = (res['Sale Price'] / res['Prev_Price']) ** (1/res['Hold_Years'].replace(0, 0.01)) - 1
    return res
