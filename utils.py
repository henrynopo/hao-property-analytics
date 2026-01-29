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

# ==================== 3. 业务算法 (V59 全局网格推断版) ====================

def estimate_inventory(df, category_col='Category'):
    # 1. 基础检查
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns:
        return {}
    if 'Stack' not in df.columns:
        # 如果没有 Stack 列，退化为简单计数
        inv_map = {}
        for cat in df[category_col].unique():
            inv_map[cat] = len(df[df[category_col] == cat])
        return inv_map

    # 使用 copy 防止影响原始数据
    df = df.dropna(subset=['Floor_Num']).copy()
    
    # 初始化统计字典
    final_totals = {cat: 0 for cat in df[category_col].unique()}
    
    # 🟢 V59 核心逻辑：按 Block 遍历，实施“网格化”统计
    # 这与 Tower View (Tab 2) 的渲染逻辑完全一致
    
    unique_blocks = df['BLK'].unique()
    
    for blk in unique_blocks:
        blk_df = df[df['BLK'] == blk]
        
        # 1. 获取该栋楼的“物理高度” (Min 到 Max)
        min_f = int(blk_df['Floor_Num'].min())
        max_f = int(blk_df['Floor_Num'].max())
        if min_f < 1: min_f = 1
        
        # 计算该栋楼每列应有的层数 (例如 1~25楼 = 25层)
        block_height = max_f - min_f + 1
        
        # 2. 获取该栋楼的所有 Stack
        unique_stacks = blk_df['Stack'].unique()
        
        for stack in unique_stacks:
            stack_df = blk_df[blk_df['Stack'] == stack]
            
            # 确定该 Stack 的户型 (Category)
            if not stack_df.empty:
                # 取出现次数最多的户型作为该列的代表
                dominant_cat = stack_df[category_col].mode()[0]
            else:
                continue # 理论上不会发生，因为是从 unique_stacks 取的
            
            # 🟢 统计：直接使用“栋楼高度”作为该 Stack 的库存
            # 即使该 Stack 只有几条成交记录，也认为它拥有完整的楼层
            final_totals[dominant_cat] = final_totals.get(dominant_cat, 0) + block_height

    # 🟢 兜底检查
    # 防止因为数据清洗导致某些 Category 变为 0
    # 规则：统计值不能小于实际观测到的 Unit_ID 数量
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
        return max(0.0
