# utils.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st

# ==================== 配置 ====================
AGENT_PROFILE = {
    "Name": "Henry GUO",
    "Title": "Associate District Director",
    "Company": "Huttons Asia Pte Ltd",
    "License": "L3008899K",
    "RES_No": "R059451F", 
    "Mobile": "+65 8808 6086",
    "Email": "henry.guo@huttons.com"
}

# ==================== 基础工具 ====================
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
            df['Quarter'] = df['Sale Date'].dt.to_period('Q')

        if 'BLK' in df.columns: df['BLK'] = df['BLK'].astype(str).str.strip()
        if 'Stack' in df.columns: df['Stack'] = df['Stack'].astype(str).str.strip()
        if 'Floor' in df.columns: df['Floor_Num'] = pd.to_numeric(df['Floor'], errors='coerce')

        if 'Stack' in df.columns and 'Floor_Num' in df.columns:
            def format_unit(row):
                try:
                    f = int(row['Floor_Num'])
                    s = str(row['Stack']).strip()
                    s_fmt = s.zfill(2) if s.isdigit() else s
                    return f"#{f:02d}-{s_fmt}"
                except: return ""
            df['Unit'] = df.apply(format_unit, axis=1)
            df['Unit_ID'] = df['BLK'].astype(str) + "-" + df['Stack'].astype(str) + "-" + df['Floor_Num'].astype(str)
        return df
    except Exception as e:
        return None

def auto_categorize(df, method):
    if method == "按卧室数量 (Bedroom Type)":
        target_cols = ['Bedroom Type', 'Bedroom_Type', 'Bedrooms', 'No. of Bedrooms', 'Type']
        found_col = None
        for col in df.columns:
            if col.strip() in target_cols: found_col = col; break
        if not found_col:
            for col in df.columns:
                if 'Bedroom' in col: found_col = col; break
        if found_col: return df[found_col].astype(str).str.strip().str.upper()
        else: return pd.Series(["未找到卧室列"] * len(df))
    elif method == "按楼座 (Block)": return df['BLK']
    else: 
        def size_bin(area):
            if area < 800: return "Small (<800sf)"
            if area < 1200: return "Medium (800-1.2k)"
            if area < 1600: return "Large (1.2k-1.6k)"
            if area < 2500: return "X-Large (1.6k-2.5k)"
            return "Giant (>2.5k)"
        return df['Area (sqft)'].apply(size_bin)

def mark_penthouse(df):
    if 'Area (sqft)' not in df.columns or 'Category' not in df.columns: return pd.Series([False] * len(df))
    medians = df.groupby('Category')['Area (sqft)'].median()
    def check(row):
        med = medians.get(row['Category'], 0)
        return row['Area (sqft)'] > (med * 1.4)
    return df.apply(check, axis=1)

# ==================== AVM 核心逻辑 ====================
def estimate_inventory(df, category_col='Category'):
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns: return {}
    if 'Stack' not in df.columns:
        inv_map = {}
        for cat in df[category_col].unique(): inv_map[cat] = len(df[df[category_col] == cat])
        return inv_map
    
    df = df.dropna(subset=['Floor_Num']).copy()
    cat_benchmark = {}
    for cat in df[category_col].unique():
        cat_df = df[df[category_col] == cat]
        std_df = cat_df[~cat_df['Is_Special']] 
        max_f = std_df['Floor_Num'].max() if not std_df.empty else 1
        cat_benchmark[cat] = max_f
    
    stack_inv = {}
    unique_stacks = df[['BLK', 'Stack']].drop_duplicates()
    for _, row in unique_stacks.iterrows():
        blk, stack = row['BLK'], row['Stack']
        stack_df = df[(df['BLK'] == blk) & (df['Stack'] == stack)]
        local_max = df[df['BLK'] == blk]['Floor_Num'].max() if not df.empty else 0
        dom_cat = stack_df[category_col].mode()[0] if not stack_df.empty else "Unknown"
        final = int(cat_benchmark.get(dom_cat, local_max))
        stack_inv[(blk, stack)] = {'count': final, 'category': dom_cat}

    cat_totals = {}
    for info in stack_inv.values():
        cat = info['category']
        cat_totals[cat] = cat_totals.get(cat, 0) + info['count']
    return cat_totals

def get_dynamic_floor_premium(df, category):
    cat_df = df[df['Category'] == category].copy()
    if cat_df.empty: return 0.005
    recent_limit = cat_df['Sale Date'].max() - timedelta(days=365*5)
    recent_df = cat_df[cat_df['Sale Date'] >= recent_limit]
    grouped = recent_df.groupby(['BLK', 'Stack'])
    rates = []
    for _, group in grouped:
        if len(group) < 2: continue
        recs = group.to_dict('records')
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                r1, r2 = recs[i], recs[j]
                if abs((r1['Sale Date'] - r2['Sale Date']).days) > 540: continue
                f_diff = r1['Floor_Num'] - r2['Floor_Num']
                if f_diff == 0: continue
                if r1['Floor_Num'] > r2['Floor_Num']: high, low, delta = r1, r2, f_diff
                else: high, low, delta = r2, r1, -f_diff
                rate = ((high['Sale PSF'] - low['Sale PSF']) / low['Sale PSF']) / delta
                if -0.005 < rate < 0.03: rates.append(rate)
    if len(rates) >= 3: return max(0.001, min(0.015, float(np.median(rates))))
    else: return 0.005

def calculate_ssd_status(purchase_date):
    now = datetime.now()
    purchase_dt = pd.to_datetime(purchase_date)
    NEW_POLICY_DATE = datetime(2025, 7, 4)
    rate, emoji, status_text = 0.0, "🟢", "SSD Free"
    held_years = (now - purchase_dt).days / 365.25
