# utils.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st

# ==================== 1. 个人品牌与项目配置 ====================
try:
    AGENT_PROFILE = dict(st.secrets["agent"])
except Exception:
    AGENT_PROFILE = {
        "Name": "Henry GUO",
        "Title": "Associate District Director",
        "Company": "Huttons Asia Pte Ltd",
        "License": "L3008899K",
        "RES_No": "R059451F", 
        "Mobile": "+65 8808 6086",
        "Email": "henry.guo@huttons.com"
    }

try:
    project_config = dict(st.secrets["projects"])
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

# ==================== 3. 业务算法 (V61 启发式修正版) ====================

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
        
        # 1. 检测整栋楼的物理高度
        min_f = int(blk_df['Floor_Num'].min())
        max_f = int(blk_df['Floor_Num'].max())
        if min_f < 1: min_f = 1
        
        # 🟢 2. 强力步长推断 (Heuristic Step Detection)
        # 默认步长
        step = 1 
        
        # 证据A: 楼层间隔
        floors = sorted(blk_df['Floor_Num'].dropna().unique())
        if len(floors) >= 2:
            diffs = np.diff(floors)
            valid_diffs = [d for d in diffs if d <= 3]
            if valid_diffs:
                mode_step = int(pd.Series(valid_diffs).mode()[0])
                if mode_step > 1: step = mode_step
        
        # 证据B: 户型名称 (强制覆盖)
        # 如果数据里包含 "Maisonette" 字样，强制 Step=2
        # Braddell View 的大户型通常是 Maisonette
        avg_area = blk_df['Area (sqft)'].median() if 'Area (sqft)' in blk_df.columns else 0
        if avg_area > 1500 and step == 1:
            # 这是一个大胆的假设：如果平均面积很大且目前判断是平层，可能是误判
            # 检查是否有连续楼层 (1,2,3,4...) 
            # 如果没有连续楼层 (例如只有 2, 4, 8, 12)，那肯定是 Step=2
            has_consecutive = any(diff == 1 for diff in diffs)
            if not has_consecutive:
                step = 2
        
        # 3. 计算单列理论户数
        raw_height_count = (max_f - min_f) + 1
        
        # 如果 Step=2，则户数减半
        if step == 2:
            final_stack_count = int(raw_height_count / 2) + 1
        else:
            final_stack_count = raw_height_count

        # 4. 累加到主导户型
        unique_stacks = blk_df['Stack'].unique()
        for stack in unique_stacks:
            stack_df = blk_df[blk_df['Stack'] == stack]
            if not stack_df.empty:
                dominant_cat = stack_df[category_col].mode()[0]
                
                # 🟢 5. 单列合理性校验 (Sanity Check)
                # 如果算出来单列有 25 户，但这是一种超大户型(>1500sf)，这不科学
                # 大概率是步长判错了，强制修正为减半
                cat_avg_area = df[df[category_col] == dominant_cat]['Area (sqft)'].median()
                if final_stack_count > 20 and cat_avg_area > 1500:
                    corrected_count = int(final_stack_count / 2)
                    final_totals[dominant_cat] = final_totals.get(dominant_cat, 0) + corrected_count
                else:
                    final_totals[dominant_cat] = final_totals.get(dominant_cat, 0) + final_stack_count

    # 6. 兜底逻辑
    observed_counts = df.groupby(category_col)['Unit_ID'].nunique().to_dict()
    for cat in final_totals:
        estimated = final_totals[cat]
        observed = observed_counts.get(cat, 0)
        if estimated < observed:
            final_totals[cat] = observed
            
    return final_totals

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

def calculate_ssd_status(purchase_date):
    now, p_dt = datetime.now(), pd.to_datetime(purchase_date)
    held_years = (now - p_dt).days / 365.25
    rate, emoji, text = 0.0, "🟢", "SSD Free"
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
    df_clean = df.dropna(subset=['Sale PSF', 'Date_Ordinal']).copy()
    if len(df_clean) < 10: return None, 0 
    q1 = df_clean['Sale PSF'].quantile(0.10)
    q3 = df_clean['Sale PSF'].quantile(0.90)
    df_clean = df_clean[(df_clean['Sale PSF'] >= q1) & (df_clean['Sale PSF'] <= q3)]
    x = df_clean['Date_Ordinal'].values
    y = df_clean['Sale PSF'].values
    coeffs = np.polyfit(x, y, 1) 
    trend_func = np.poly1d(coeffs)
    y_pred = trend_func(x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    return trend_func, r2

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
    comps = df[(df['Category'] == subject_cat) & (df['Sale Date'] >= cutoff_date) & (~df['Is_Special']) & (df['Area (sqft)'] >= subject_area * 0.85) & (df['Area (sqft)'] <= subject_area * 1.15)].copy()
    if len(comps) < 3:
        comps = df[(df['Category'] == subject_cat) & (~df['Is_Special'])].sort_values('Sale Date', ascending=False).head(10)
    if comps.empty: return subject_area, 0, 0, 0, 0.005, pd.DataFrame(), subject_cat

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
        ratio = max(0.8, min(1.2, ratio))
        return row['Sale PSF'] * ratio

    comps['Adj_PSF'] = comps.apply(adjust_psf, axis=1)
    premium_rate = get_dynamic_floor_premium(df, subject_cat)
    base_psf = comps['Adj_PSF'].median()
    base_floor = comps['Floor_Num'].median()
    floor_diff = floor - base_floor
    adjustment_factor = 1 + (floor_diff * premium_rate)
    model_psf = base_psf * adjustment_factor
    final_psf = model_psf
    if last_price_psf is not None:
        years_since_tx = (last_date - last_tx_date).days / 365.25
        if years_since_tx < 3: 
            conservative_growth_factor = (1.01) ** years_since_tx
            adjusted_hist_psf = last_price_psf * conservative_growth_factor
            if model_psf < adjusted_hist_psf: final_psf = adjusted_hist_psf
    
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
    sale_type_col = next((c for c in df.columns if 'Type of Sale' in c or 'Sale Type' in c), None)
    if sale_type_col:
        mask = resales[sale_type_col].astype(str).str.strip().apply(lambda x: any(t.lower() in x.lower() for t in ['resale', 'sub sale', 'resales', 'subsales']))
        resales = resales[mask]
    if resales.empty: return pd.DataFrame()
    resales['Gain'] = resales['Sale Price'] - resales['Prev_Price']
    resales['Hold_Days'] = (resales['Sale Date'] - resales['Prev_Date']).dt.days
    resales['Hold_Years'] = resales['Hold_Days'] / 365.25
    resales['Annualized'] = (resales['Sale Price'] / resales['Prev_Price']) ** (1 / resales['Hold_Years'].replace(0, 0.01)) - 1
    return resales
