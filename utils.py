import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st
import plotly.graph_objects as go 

# ==================== 1. 全局配置与常量 ====================

CUSTOM_DISCLAIMER = "Disclaimer: Estimates (AVM) for reference only. Not certified valuations. Source: URA/Huttons. No warranty on accuracy."

# [V222 Fix] 超级兼容列名映射表 (覆盖常见的 CSV 变体)
COLUMN_RENAME_MAP = {
    # 价格类
    'Transacted Price ($)': 'Sale Price', 'Sale Price ($)': 'Sale Price', 'Price ($)': 'Sale Price', 'Price': 'Sale Price', 'Transacted Price': 'Sale Price',
    
    # 面积类
    'Area (SQFT)': 'Area (sqft)', 'Area(sqft)': 'Area (sqft)', 'Area (sqm)': 'Area (sqm)', 'Land Area (SQFT)': 'Area (sqft)',
    
    # 单价类
    'Unit Price ($ psf)': 'Unit Price ($ psf)', 'Sale PSF': 'Unit Price ($ psf)', 'Unit Price ($ psm)': 'Unit Price ($ psm)', 'PSF': 'Unit Price ($ psf)',
    
    # 日期类
    'Sale Date': 'Sale Date', 'Date of Sale': 'Sale Date', 'Contract Date': 'Sale Date', 'Date': 'Sale Date',
    
    # 楼座 Block (解决 KeyError: 'BLK')
    'Block': 'BLK', 'Blk': 'BLK', 'BLOCK': 'BLK', 'House No': 'BLK',
    
    # 楼层 Floor
    'Floor': 'Floor', 'Storey': 'Floor', 'Level': 'Floor', 'Floor Level': 'Floor',
    
    # 单元号/Stack
    'Stack': 'Stack', 'Unit Number': 'Stack', 'Unit': 'Stack', # 若 Unit 是完整号，后续会拆分
    
    # 户型/属性
    'Bedroom Type': 'Type', 'No. of Bedroom': 'Type', 'Bedrooms': 'Type',
    'Property Type': 'Sub Type', 'Building Type': 'Sub Type', 'Type': 'Type',
    
    # 地契
    'Tenure': 'Tenure', 'Lease Commencement Date': 'Tenure From', 'Tenure Start Date': 'Tenure From'
}

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

# 强制保留手动上传入口
try:
    project_config = dict(st.secrets["projects"])
    cleaned_config = {k: (None if v == "None" else v) for k, v in project_config.items()}
    PROJECTS = cleaned_config
except Exception:
    PROJECTS = {}

if "📂 手动上传 CSV" not in PROJECTS:
    PROJECTS["📂 手动上传 CSV"] = None

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
        # 1. 智能读取 (支持传文件对象或路径)
        if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
        try:
            # 探测表头：只要包含常见列名之一，就认定为 Header
            df_temp = pd.read_csv(file_or_url, header=None, nrows=20)
            header_row = -1
            keywords = ["Sale Date", "Date of Sale", "BLK", "Block", "Transacted Price", "Sale Price", "Price"]
            
            for i, row in df_temp.iterrows():
                row_str = row.astype(str).str.cat(sep=',')
                if any(k in row_str for k in keywords):
                    header_row = i; break
            
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url, header=header_row if header_row != -1 else 0)
        except:
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url)

        # 2. 标准化列名
        df.columns = df.columns.str.strip()
        df.rename(columns=COLUMN_RENAME_MAP, inplace=True)
        
        # 3. 清洗数值列
        for col in ['Sale Price', 'Unit Price ($ psf)', 'Area (sqft)']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'[$,]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 4. 清洗日期
        if 'Sale Date' in df.columns:
            df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
            df['Sale Year'] = df['Sale Date'].dt.year
            df['Date_Ordinal'] = df['Sale Date'].map(datetime.toordinal)

        # 5. 清洗核心字段 (Block/Stack/Floor)
        if 'BLK' in df.columns: df['BLK'] = df['BLK'].astype(str).str.strip()
        if 'Stack' in df.columns: df['Stack'] = df['Stack'].astype(str).str.strip()
        
        # [增强] 处理 Floor 可能是 "01-05" 这种范围格式的情况
        if 'Floor' in df.columns: 
            # 尝试直接转数字，如果失败(如范围)，则取第一部分
            df['Floor_Num'] = pd.to_numeric(df['Floor'], errors='coerce')
            # 修复那些变成 NaN 的范围数据 (例如 "02 to 05")
            mask_nan = df['Floor_Num'].isna() & df['Floor'].notna()
            if mask_nan.any():
                def extract_floor(val):
                    try: return int(re.search(r'\d+', str(val)).group())
                    except: return np.nan
                df.loc[mask_nan, 'Floor_Num'] = df.loc[mask_nan, 'Floor'].apply(extract_floor)

        # 补全缺失列
        for col in ['Type', 'Tenure', 'Tenure From', 'Sub Type']:
            if col not in df.columns: df[col] = "N/A"

        # 6. 生成 Unit (如果缺失 Stack，尝试从 Unit 拆分?)
        # 暂时保持简单，如果都有才生成
        if 'Stack' in df.columns and 'Floor_Num' in df.columns:
            df['Unit'] = df.apply(lambda row: format_unit(row['Floor_Num'], row['Stack']), axis=1)
            df['Unit_ID'] = df['BLK'].astype(str) + "-" + df['Stack'].astype(str) + "-" + df['Floor_Num'].astype(str)
            
        return df
    except Exception as e:
        # st.error(f"Data Load Error: {str(e)}")
        return None

def auto_categorize(df, method):
    if method == "按卧室数量 (Bedroom Type)":
        target_cols = ['Type', 'Bedroom Type', 'Bedrooms']
        found = next((c for c in df.columns if c in target_cols), None)
        return df[found].astype(str).str.strip().str.upper() if found else pd.Series(["Unknown"] * len(df))
    elif method == "按楼座 (Block)": return df['BLK'] if 'BLK' in df.columns else pd.Series(["Unknown"] * len(df))
    else: return df['Area (sqft)'].apply(lambda x: "Small" if x<800 else "Medium" if x<1200 else "Large" if x<1600 else "X-Large" if x<2500 else "Giant")

def mark_penthouse(df):
    if 'Area (sqft)' not in df.columns or 'Category' not in df.columns: return pd.Series([False] * len(df))
    medians = df.groupby('Category')['Area (sqft)'].median()
    return df.apply(lambda row: row['Area (sqft)'] > (medians.get(row['Category'], 0) * 1.4), axis=1)

# ==================== 4. 业务逻辑与算法 ====================

def calculate_market_trend(full_df):
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

def detect_block_step(blk_df):
    if blk_df.empty: return 1
    # 如果没有 Stack 列，无法判断复式，默认1
    if 'Stack' not in blk_df.columns: return 1
    
    unique_stacks = blk_df['Stack'].unique()
    if len(unique_stacks) == 0: return 1
    votes_simplex, votes_maisonette = 0, 0
    for stack in unique_stacks:
        stack_df = blk_df[blk_df['Stack'] == stack]
        floors = sorted(stack_df['Floor_Num'].dropna().unique())
        if len(floors) < 2: continue
        has_odd = any(f % 2 != 0 for f in floors)
        has_even = any(f % 2 == 0 for f in floors)
        if (has_odd and not has_even) or (not has_odd and has_even): votes_maisonette += 1
        else: votes_simplex += 1
    return 2 if votes_maisonette > votes_simplex else 1

def get_stack_start_floor(stack_df, block_min_f, step):
    if step == 1: return block_min_f
    floors = sorted(stack_df['Floor_Num'].dropna().unique())
    if not floors: return block_min_f
    odd_count = sum(1 for f in floors if f % 2 != 0)
    even_count = sum(1 for f in floors if f % 2 == 0)
    is_odd_stack = odd_count > even_count
    start = block_min_f
    while True:
        if (start % 2 != 0) == is_odd_stack: return start
        start += 1

def estimate_inventory(df, category_col='Category'):
    # 必须有 BLK 和 Floor_Num 才能估算，否则直接返回当前统计
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns: 
        return df[category_col].value_counts().to_dict() if category_col in df.columns else {}
        
    if 'Stack' not in df.columns: return df[category_col].value_counts().to_dict()
    
    df = df.dropna(subset=['Floor_Num']).copy()
    final_totals = {cat: 0 for cat in df[category_col].unique()}
    unique_blocks = df['BLK'].unique()
    
    for blk in unique_blocks:
        blk_df = df[df['BLK'] == blk]
        step = detect_block_step(blk_df)
        
        # 安全获取最小最大楼层
        if blk_df['Floor_Num'].empty: continue
        min_f, max_f = int(blk_df['Floor_Num'].min()), int(blk_df['Floor_Num'].max())
        if min_f < 1: min_f = 1
        
        for stack in blk_df['Stack'].unique():
            stack_df = blk_df[blk_df['Stack'] == stack]
            if not stack_df.empty:
                dominant_cat = stack_df[category_col].mode()[0]
                start_f = get_stack_start_floor(stack_df, min_f, step)
                final_totals[dominant_cat] = final_totals.get(dominant_cat, 0) + len(range(start_f, max_f + 1, step))
                
    observed_counts = df.groupby(category_col)['Unit_ID'].nunique().to_dict()
    for cat in final_totals:
        if final_totals[cat] < observed_counts.get(cat, 0): final_totals[cat] = observed_counts.get(cat, 0)
    return final_totals

def get_dynamic_floor_premium(df, category):
    cat_df = df[df['Category'] == category].copy()
    if cat_df.empty: return 0.005
    recent_limit = cat_df['Sale Date'].max() - timedelta(days=365*5)
    recent_df = cat_df[cat_df['Sale Date'] >= recent_limit]
    # 必须有 Stack 才能计算垂直溢价
    if 'Stack' not in recent_df.columns: return 0.005
    
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
    else: return 0.005

def calculate_ssd_status(purchase_date):
    """Returns: rate(float), emoji(str), text(str), months_left(int)"""
    if pd.isna(purchase_date): return 0.0, "", "", 0
    p_dt = pd.to_datetime(purchase_date)
    now = datetime.now()
    
    POLICY_2017 = pd.Timestamp("2017-03-11")
    POLICY_2025 = pd.Timestamp("2025-07-04")
    
    if p_dt >= POLICY_2025:
        lock_years = 4; rates_map = {0: 0.16, 1: 0.12, 2: 0.08, 3: 0.04}
    elif p_dt >= POLICY_2017:
        lock_years = 3; rates_map = {0: 0.12, 1: 0.08, 2: 0.04}
    else:
        lock_years = 0; rates_map = {}

    ssd_deadline = p_dt + relativedelta(years=lock_years)
    
    if now >= ssd_deadline: return 0.0, "🟩", "SSD Free", 0
        
    days_left = (ssd_deadline - now).days
    months_left = int(days_left / 30) + 1
    
    years_held = relativedelta(now, p_dt).years
    rate = rates_map.get(years_held, 0.0)
    pct_text = f"{int(rate*100)}%"
    
    if rate >= 0.12: base_emoji = "⛔"
    elif rate >= 0.08: base_emoji = "🛑"
    else: base_emoji = "🟥"
    
    if days_left <= 90: emoji = "🟨"   
    elif days_left <= 180: emoji = "🟧" 
    else: emoji = base_emoji
    
    return rate, emoji, f"SSD {pct_text}", months_left

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

def render_transaction_table(df):
    display_df = df.copy()
    if 'Sale Date' in display_df.columns:
        display_df = display_df.sort_values('Sale Date', ascending=False)
        display_df['Sale Date Str'] = display_df['Sale Date'].dt.strftime('%Y-%m-%d')
    else: display_df['Sale Date Str'] = "-"
    if 'Unit' not in display_df.columns:
        display_df['Unit'] = display_df.apply(lambda row: format_unit(row.get('Floor_Num'), row.get('Stack')), axis=1)
    display_df['Sale Price Str'] = display_df['Sale Price'].apply(lambda x: f"${x/1e6:.2f}M" if pd.notnull(x) else "-")
    display_df['Unit Price Str'] = display_df['Unit Price ($ psf)'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "-")
    type_col = 'Type' if 'Type' in display_df.columns else 'Category'
    if 'BLK' not in display_df.columns: display_df['BLK'] = "-"
    cols = ['Sale Date Str', 'BLK', 'Unit', type_col, 'Area (sqft)', 'Sale Price Str', 'Unit Price Str']
    st.dataframe(display_df[cols], use_container_width=True, hide_index=True, column_config={"Sale Date Str": "日期", "BLK": "楼座", "Unit": "单位", type_col: "户型", "Area (sqft)": "面积 (sqft)", "Sale Price Str": "总价", "Unit Price Str": "尺价 (psf)"})