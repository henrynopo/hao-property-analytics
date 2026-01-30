import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st
import plotly.graph_objects as go # [新增] 用于渲染仪表盘

# ==================== 1. 全局配置与常量 ====================

# [V202] 免责声明 (全局共享)
CUSTOM_DISCLAIMER = "Disclaimer: Estimates (AVM) for reference only. Not certified valuations. Source: URA/Huttons. No warranty on accuracy."

# [V202] 标准列名映射 (统一数据清洗口径)
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

# ==================== 2. 通用格式化工具 ====================

def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]

def format_currency(val):
    try: return f"${val:,.0f}"
    except: return val

# [V202] 提取为独立函数，供 load_data 和各 Tab 使用
def format_unit(floor, stack):
    try:
        # 尝试转换为数字以去除前导零或处理浮点
        f_num = int(float(floor))
        s_str = str(stack).strip()
        # Stack 如果是纯数字，补齐2位；如果是 10A 这种，保持原样
        s_fmt = s_str.zfill(2) if s_str.isdigit() else s_str
        return f"#{f_num:02d}-{s_fmt}"
    except:
        # 出错时回退到原始字符串拼接
        return f"#{floor}-{stack}"

# [V202] 新增脱敏格式化
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
        
        # [V202] 使用统一映射清洗列名 (可选，这里先保留您的原始逻辑，避免改动太大)
        # df.rename(columns=COLUMN_RENAME_MAP, inplace=True) 
        
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
            # [V202] 使用上方定义的全局函数
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

def get_dynamic_floor_premium(df, category):
    # (保持原样...)
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
    # (保持原样...)
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
    # (保持原样...)
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

# ==================== 5. 共享图表组件 ====================

# [V202] 提取自 tab3_avm.py，供多处复用
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

# ... (Calculate AVM 和 Resale Metrics 保持原样，未改动)
def calculate_avm(df, blk, stack, floor):
    # (代码省略，保持您原文件的内容，此处不做改动)
    # ... 请确保保留原文件后续的 calculate_avm 代码 ...
    # 为节省篇幅，这里假定您只替换上半部分，或者您复制原 utils.py 的后半部分接在 render_gauge 后面
    # 如果您直接全选覆盖，请务必把原 utils.py 最后的 calculate_avm 和 calculate_resale_metrics 拷回来
    # 或者让我知道，我为您提供包含所有内容的完整代码。
    
    # ⚠️ 临时占位，请替换为原代码
    target_unit = df[(df['BLK'] == blk) & (df['Stack'] == stack) & (df['Floor_Num'] == floor)]
    # ... (原有逻辑)
    return None, None, None, None, None, pd.DataFrame(), None # 占位

def calculate_resale_metrics(df):
    # (原有逻辑)
    return pd.DataFrame()
