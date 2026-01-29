# 文件名: utils.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st

# ==================== 1. 个人品牌配置 (PDF生成需要) ====================
AGENT_PROFILE = {
    "Name": "Henry GUO",
    "Title": "Associate District Director",
    "Company": "Huttons Asia Pte Ltd",
    "License": "L3008899K",
    "RES_No": "R059451F", 
    "Mobile": "+65 8808 6086",
    "Email": "henry.guo@huttons.com"
}

# ==================== 2. 项目列表配置 (修复报错的关键) ====================
try:
    # 尝试从 secrets 读取配置
    project_config = dict(st.secrets["projects"])
    PROJECTS = {"📂 手动上传 CSV": None}
    PROJECTS.update(project_config)
except:
    # 如果没有 secrets，使用默认值，防止报错
    PROJECTS = {
        "📂 手动上传 CSV": None,
        # 👇 在这里把您的项目名和链接加回去
        "🏢 Braddell View": "https://drive.google.com/uc?id=您的文件ID&export=download", 
    }

# ==================== 3. 基础工具函数 ====================
def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]

def format_currency(val):
    try: return f"${val:,.0f}"
    except: return val

@st.cache_data(ttl=300)
def load_data(file_or_url):
    """读取数据并智能清洗"""
    try:
        if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
        try:
            df_temp = pd.read_csv(file_or_url, header=None, nrows=20)
            header_row = -1
            for i, row in df_temp.iterrows():
                row_str = row.astype(str).str.cat(sep=',')
                if "Sale Date" in row_str or "BLK" in row_str:
                    header_row = i
                    break
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
            # 这里的 Date_Ordinal 用于 V42 稳健回归算法
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
                except:
                    return ""
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
            if col.strip() in target_cols:
                found_col = col
                break
        if not found_col:
            for col in df.columns:
                if 'Bedroom' in col: found_col = col; break
        
        if found_col:
            return df[found_col].astype(str).str.strip().str.upper()
        else:
            return pd.Series(["未找到卧室列"] * len(df))
    elif method == "按楼座 (Block)": 
        return df['BLK']
    else: 
        def size_bin(area):
            if area < 800: return "Small (<800sf)"
            if area < 1200: return "Medium (800-1.2k)"
            if area < 1600: return "Large (1.2k-1.6k)"
            if area < 2500: return "X-Large (1.6k-2.5k)"
            return "Giant (>2.5k)"
        return df['Area (sqft)'].apply(size_bin)

def mark_penthouse(df):
    if 'Area (sqft)' not in df.columns or 'Category' not in df.columns:
        return pd.Series([False] * len(df))
    medians = df.groupby('Category')['Area (sqft)'].median()
    def check(row):
        med = medians.get(row['Category'], 0)
        return row['Area (sqft)'] > (med * 1.4)
    return df.apply(check, axis=1)

# ==================== 4. 业务逻辑算法 ====================

def estimate_inventory(df, category_col='Category'):
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns:
        return {}
    if 'Stack' not in df.columns:
        inv_map = {}
        for cat in df[category_col].unique():
            inv_map[cat] = len(df[df[category_col] == cat])
        return inv_map

    df = df.dropna(subset=['Floor_Num']).copy()
    
    cat_benchmark_floors = {}
    for cat in df[category_col].unique():
        cat_df = df[df[category_col] == cat]
        std_df = cat_df[~cat_df['Is_Special']] 
        max_floor = std_df['Floor_Num'].max() if not std_df.empty else 1
        cat_benchmark_floors[cat] = max_floor
    
    stack_inventory_map = {}
    unique_stacks = df[['BLK', 'Stack']].drop_duplicates()
    
    for _, row in unique_stacks.iterrows():
        blk = row['BLK']
        stack = row['Stack']
        stack_df = df[(df['BLK'] == blk) & (df['Stack'] == stack)]
        
        local_floors_set = set(df[df['BLK'] == blk]['Floor_Num'].unique())
        local_max = max(local_floors_set) if local_floors_set else 0
        final_count = len(local_floors_set)
        
        if not stack_df.empty:
            top_cat = stack_df[category_col].mode()
            dominant_cat = top_cat[0] if not top_cat.empty else "Unknown"
        else:
            dominant_cat = "Unknown"
        
        benchmark = cat_benchmark_floors.get(dominant_cat, local_max)
        if (local_max < benchmark - 2) and (local_max > benchmark * 0.5):
             final_count = int(benchmark)

        stack_inventory_map[(blk, stack)] = {
            'count': final_count,
            'category': dominant_cat
        }

    category_totals = {}
    for cat in df[category_col].unique():
        category_totals[cat] = 0
    for info in stack_inventory_map.values():
        cat = info['category']
        count = info['count']
        category_totals[cat] = category_totals.get(cat, 0) + count
            
    return category_totals

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
                floor_diff = r1['Floor_Num'] - r2['Floor_Num']
                if floor_diff == 0: continue
                
                if r1['Floor_Num'] > r2['Floor_Num']: high, low, f_delta = r1, r2, floor_diff
                else: high, low, f_delta = r2, r1, -floor_diff
                
                rate = ((high['Sale PSF'] - low['Sale PSF']) / low['Sale PSF']) / f_delta
                if -0.005 < rate < 0.03: rates.append(rate)

    if len(rates) >= 3:
        fitted_rate = float(np.median(rates))
        return max(0.001, min(0.015, fitted_rate))
    else:
        return 0.005

# 🟢 V44 核心: 智能 SSD 判定 (含2025新政)
def calculate_ssd_status(purchase_date):
    """
    计算 SSD 状态 (支持 2025年7月4日 新政)
    """
    now = datetime.now()
    purchase_dt = pd.to_datetime(purchase_date)
    NEW_POLICY_DATE = datetime(2025, 7, 4)
    
    rate = 0.0
    emoji = "🟢"
    status_text = "SSD Free"
    
    held_days = (now - purchase_dt).days
    held_years = held_days / 365.25
    
    if purchase_dt >= NEW_POLICY_DATE:
        ssd_deadline = purchase_dt + relativedelta(years=4)
        remaining_days = (ssd_deadline - now).days
        
        if held_years < 1: rate, emoji, status_text = 0.16, "🔴", "SSD 16%"
        elif held_years < 2: rate, emoji, status_text = 0.12, "🔴", "SSD 12%"
        elif held_years < 3: rate, emoji, status_text = 0.08, "🔴", "SSD 8%"
        elif held_years < 4:
            rate = 0.04
            if remaining_days <= 180: emoji, status_text = "🟡", "SSD 4% (<6m)"
            else: emoji, status_text = "🔴", "SSD 4%"
            
    elif purchase_dt >= datetime(2017, 3, 11):
        ssd_deadline = purchase_dt + relativedelta(years=3)
        remaining_days = (ssd_deadline - now).days
        
        if held_years < 1: rate, emoji, status_text = 0.12, "🔴", "SSD 12%"
        elif held_years < 2: rate, emoji, status_text = 0.08, "🔴", "SSD 8%"
        elif held_years < 3:
            rate = 0.04
            if remaining_days <= 180: emoji, status_text = "🟡", "SSD 4% (<6m)"
            else: emoji, status_text = "🔴", "SSD 4%"
    
    return rate, emoji, status_text

# 🟢 V42 核心: 稳健回归模型 (使用 numpy，无 sklearn 依赖)
def get_market_trend_model(df):
    df_clean = df.dropna(subset=['Sale PSF', 'Date_Ordinal']).copy()
    if len(df_clean) < 10: return None, 0 
    
    q1 = df_clean['Sale PSF'].quantile(0.10)
    q3 = df_clean['Sale PSF'].quantile(0.90)
    df_clean = df_clean[(df_clean['Sale PSF'] >= q1) & (df_clean['Sale PSF'] <= q3)]
    
    x = df_clean['Date_Ordinal'].values
    y = df_clean['Sale PSF'].values
    
    # 1次多项式拟合
    coeffs = np.polyfit(x, y, 1) 
    trend_func = np.poly1d(coeffs)
    
    y_pred = trend_func(x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    
    return trend_func, r2

# 🟢 V49 核心: AVM 估值 (适配 PDF 输出)
def calculate_avm(df, blk, stack, floor):
    target_unit = df[(df['BLK'] == blk) & (df['Stack'] == stack) & (df['Floor_Num'] == floor)]
    
    if not target_unit.empty:
        subject_area = target_unit['Area (sqft)'].iloc[0]
        subject_cat = target_unit['Category'].iloc[0]
        last_tx = target_unit.sort_values('Sale Date', ascending=False).iloc[0]
        last_price_psf = last_tx['Sale PSF']
        last_tx_date = last_tx['Sale Date']
    else:
        neighbors = df[(df['BLK'] == blk) & (df['Stack'] == stack)]
        if not neighbors.empty:
            subject_area = neighbors['Area (sqft)'].mode()[0]
            subject_cat = neighbors['Category'].iloc[0]
            last_price_psf = None
            last_tx_date = None
        else:
            return None, None, None, None, None, pd.DataFrame(), None

    last_date = df['Sale Date'].max()
    cutoff_date = last_date - timedelta(days=365)
    
    comps = df[
        (df['Category'] == subject_cat) & 
        (df['Sale Date'] >= cutoff_date) &
        (~df['Is_Special']) &
        (df['Area (sqft)'] >= subject_area * 0.85) & 
        (df['Area (sqft)'] <= subject_area * 1.15)
    ].copy()
    
    if len(comps) < 3:
        comps = df[(df['Category'] == subject_cat) & (~df['Is_Special'])].sort_values('Sale Date', ascending=False).head(10)

    if comps.empty:
        return subject_area, 0, 0, 0, 0.005, pd.DataFrame(), subject_cat

    # 时间修正
    trend_func, r2 = get_market_trend_model(df)
    current_date_ordinal = last_date.toordinal()
    use_trend = trend_func is not None and r2 > 0.1
    
    def adjust_psf(row):
        if not use_trend: return row['Sale PSF']
        sale_ordinal = row['Sale Date'].toordinal()
        pred_then = trend_func(sale_ordinal)
        pred_now = trend_func(current_date_ordinal)
        if pred_then <= 0: return row['Sale PSF']
        ratio = pred_now / pred_then
        ratio = max(0.8, min(1.2, ratio)) # 钳制修正幅度
        return row['Sale PSF'] * ratio

    comps['Adj_PSF'] = comps.apply(adjust_psf, axis=1)

    premium_rate = get_dynamic_floor_premium(df, subject_cat)
    base_psf = comps['Adj_PSF'].median()
    base_floor = comps['Floor_Num'].median()
    
    floor_diff = floor - base_floor
    adjustment_factor = 1 + (floor_diff * premium_rate)
    model_psf = base_psf * adjustment_factor
    
    final_psf = model_psf
    # 自身历史修正 (3年内)
    if last_price_psf is not None:
        years_since_tx = (last_date - last_tx_date).days / 365.25
        if years_since_tx < 3: 
            conservative_growth_factor = (1.01) ** years_since_tx
            adjusted_hist_psf = last_price_psf * conservative_growth_factor
            if model_psf < adjusted_hist_psf:
                final_psf = adjusted_hist_psf
    
    valuation = subject_area * final_psf
    
    comps_display = comps.sort_values('Sale Date', ascending=False).head(5)
    comps_display['Sale Date'] = comps_display['Sale Date'].dt.date
    if 'Unit' not in comps_display.columns:
        comps_display['Unit'] = comps_display.apply(lambda x: f"#{int(x['Floor_Num']):02d}-{x['Stack']}", axis=1)
    
    cols_to_keep = ['Sale Date', 'BLK', 'Unit', 'Category', 'Area (sqft)', 'Sale Price', 'Sale PSF', 'Adj_PSF']
    cols_to_keep = [c for c in cols_to_keep if c in comps_display.columns]
    comps_display = comps_display[cols_to_keep]
    
    return subject_area, final_psf, valuation, floor_diff, premium_rate, comps_display, subject_cat

def calculate_resale_metrics(df):
    if 'Unit_ID' not in df.columns: return pd.DataFrame()
    
    df_sorted = df.sort_values(['Unit_ID', 'Sale Date'])
    df_sorted['Prev_Price'] = df_sorted.groupby('Unit_ID')['Sale Price'].shift(1)
    df_sorted['Prev_Date'] = df_sorted.groupby('Unit_ID')['Sale Date'].shift(1)
    
    resales = df_sorted.dropna(subset=['Prev_Price']).copy()
    
    sale_type_col = None
    for col in df.columns:
        if 'Type of Sale' in col or 'Sale Type' in col:
            sale_type_col = col
            break
            
    if sale_type_col:
        valid_types = ['Resale', 'Sub Sale', 'Resales', 'Subsales']
        mask = resales[sale_type_col].astype(str).str.strip().apply(lambda x: any(t.lower() in x.lower() for t in valid_types))
        resales = resales[mask]
    
    if resales.empty: return pd.DataFrame()
    
    resales['Gain'] = resales['Sale Price'] - resales['Prev_Price']
    resales['Hold_Days'] = (resales['Sale Date'] - resales['Prev_Date']).dt.days
    resales['Hold_Years'] = resales['Hold_Days'] / 365.25
    resales['Annualized'] = (resales['Sale Price'] / resales['Prev_Price']) ** (1 / resales['Hold_Years'].replace(0, 0.01)) - 1
    
    return resales
