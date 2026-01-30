import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import streamlit as st
import plotly.graph_objects as go 

# ==================== 1. 全局配置与常量 ====================

CUSTOM_DISCLAIMER = "Disclaimer: Estimates (AVM) for reference only. Not certified valuations. Source: URA/Huttons. No warranty on accuracy."

# [V207] 增强版列名映射表 (兼容多种常见 CSV 格式)
COLUMN_RENAME_MAP = {
    'Transacted Price ($)': 'Sale Price',
    'Sale Price ($)': 'Sale Price',
    'Price ($)': 'Sale Price',
    
    'Area (SQFT)': 'Area (sqft)',
    'Area(sqft)': 'Area (sqft)',
    
    'Unit Price ($ psf)': 'Unit Price ($ psf)',
    'Sale PSF': 'Unit Price ($ psf)',
    'Unit Price ($ psm)': 'Unit Price ($ psm)',
    
    'Sale Date': 'Sale Date',
    'Date of Sale': 'Sale Date',
    
    'Bedroom Type': 'Type',   
    'No. of Bedroom': 'Type', 
    'Property Type': 'Sub Type',
    'Building Type': 'Sub Type',
    
    'Tenure': 'Tenure',
    'Lease Commencement Date': 'Tenure From',
    'Tenure Start Date': 'Tenure From'
}

# [V207 FIX] 健壮的 Agent Profile 加载逻辑
# 无论 Secrets 里是用 "Company" 还是 "agency"，大写还是小写，这里都会标准化
def get_agent_profile():
    # 1. 尝试从 Secrets 读取
    try:
        raw = dict(st.secrets["agent"])
    except Exception:
        raw = {}
        
    # 2. 定义默认值
    defaults = {
        "name": "Henry", 
        "title": "Associate Division Director",
        "agency": "Huttons Asia Pte Ltd",
        "license": "L3008899K",
        "contact": "+65 9123 4567",
        "email": "henry@huttons.com"
    }
    
    # 3. 标准化构建 (优先用 Secrets，支持别名映射)
    profile = {}
    profile['name'] = raw.get('name', raw.get('Name', defaults['name']))
    profile['title'] = raw.get('title', raw.get('Title', defaults['title']))
    # 关键修复: 兼容 Company / agency
    profile['agency'] = raw.get('agency', raw.get('Company', raw.get('company', defaults['agency']))) 
    profile['license'] = raw.get('license', raw.get('License', defaults['license']))
    # 关键修复: 兼容 Mobile / contact
    profile['contact'] = raw.get('contact', raw.get('Mobile', raw.get('mobile', defaults['contact'])))
    profile['email'] = raw.get('email', raw.get('Email', defaults['email']))
    
    return profile

AGENT_PROFILE = get_agent_profile()

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
        # 1. 读取数据
        if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
        try:
            # 智能探测表头行
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

        # 2. 清洗列名
        df.columns = df.columns.str.strip()
        df.rename(columns=COLUMN_RENAME_MAP, inplace=True) # 应用映射
        
        # 3. 清洗数值列
        numeric_cols = ['Sale Price', 'Unit Price ($ psf)', 'Area (sqft)']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'[$,]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 4. 清洗日期
        if 'Sale Date' in df.columns:
            df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
            df['Sale Year'] = df['Sale Date'].dt.year
            df['Date_Ordinal'] = df['Sale Date'].map(datetime.toordinal)

        # 5. 清洗地址信息
        if 'BLK' in df.columns: df['BLK'] = df['BLK'].astype(str).str.strip()
        if 'Stack' in df.columns: df['Stack'] = df['Stack'].astype(str).str.strip()
        if 'Floor' in df.columns: df['Floor_Num'] = pd.to_numeric(df['Floor'], errors='coerce')
        
        # 补全缺失的基础列
        for col in ['Type', 'Tenure', 'Tenure From', 'Sub Type']:
            if col not in df.columns: df[col] = "N/A"

        # 6. 生成衍生列
        if 'Stack' in df.columns and 'Floor_Num' in df.columns:
            df['Unit'] = df.apply(lambda row: format_unit(row['Floor_Num'], row['Stack']), axis=1)
            df['Unit_ID'] = df['BLK'].astype(str) + "-" + df['Stack'].astype(str) + "-" + df['Floor_Num'].astype(str)
            
        return df
    except Exception as e:
        # st.error(f"Data Load Error: {str(e)}") # 可选：屏蔽详细错误
        return None

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
    x = trend_data['Date_Ord']
    y = trend_data['Unit Price ($ psf)']
    
    try:
        slope, intercept = np.polyfit(x, y, 1)
        avg_price = y.mean()
        if avg_price == 0: return 0.0
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

def render(df, project_name, chart_font_size):
    import streamlit as st

    st.subheader(f"💎 单元估值 - {project_name}")
    st.caption("AVM demo – 尚未实现完整估值模型。")

    # 简单示例：显示最近成交与一个仪表盘
    if 'Unit Price ($ psf)' in df.columns:
        latest_psf = df['Unit Price ($ psf)'].dropna().iloc[-1]
        st.write("最近一笔成交单价 (psf):", int(latest_psf))
        fig = render_gauge(latest_psf, font_size=chart_font_size)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("当前数据中缺少 `Unit Price ($ psf)` 列，无法生成 AVM 仪表盘。")
