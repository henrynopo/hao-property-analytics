# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar
import re 
import numpy as np

# ==========================================
# 🔧 1. 配置中心 (项目列表)
# ==========================================
try:
    project_config = dict(st.secrets["projects"])
    PROJECTS = {"📂 手动上传 CSV": None}
    PROJECTS.update(project_config)
except:
    PROJECTS = {
        "📂 手动上传 CSV": None,
        # "🏢 Braddell View": "https://drive.google.com/uc?id=...", 
    }

# ==========================================
# 🖥️ 2. 页面基础配置
# ==========================================
st.set_page_config(page_title="HAO数据中台 Pro", layout="wide", page_icon="🧭")

# ==========================================
# 🛠️ 3. 核心算法函数库
# ==========================================

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

        if 'BLK' in df.columns: df['BLK'] = df['BLK'].astype(str).str.strip()
        if 'Stack' in df.columns: df['Stack'] = df['Stack'].astype(str).str.strip()
        if 'Floor' in df.columns: df['Floor_Num'] = pd.to_numeric(df['Floor'], errors='coerce')

        # 🟢 预处理：生成标准单元号 (#Floor-Stack) 及 唯一ID
        if 'Stack' in df.columns and 'Floor_Num' in df.columns:
            def format_unit(row):
                try:
                    f = int(row['Floor_Num'])
                    s = str(row['Stack']).strip()
                    # Stack 补零 (1 -> 01)
                    s_fmt = s.zfill(2) if s.isdigit() else s
                    return f"#{f:02d}-{s_fmt}"
                except:
                    return ""
            df['Unit'] = df.apply(format_unit, axis=1)
            df['Unit_ID'] = df['BLK'].astype(str) + "-" + df['Stack'].astype(str) + "-" + df['Floor_Num'].astype(str)

        return df
    except Exception as e:
        st.error(f"数据读取错误: {e}")
        return None

def natural_key(text):
    """自然排序算法"""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]

def auto_categorize(df, method):
    """智能户型分类"""
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
    """全局标记 Penthouse"""
    if 'Area (sqft)' not in df.columns or 'Category' not in df.columns:
        return pd.Series([False] * len(df))
    medians = df.groupby('Category')['Area (sqft)'].median()
    def check(row):
        med = medians.get(row['Category'], 0)
        return row['Area (sqft)'] > (med * 1.4)
    return df.apply(check, axis=1)

def estimate_inventory(df, category_col='Category'):
    """V11 智能库存算法"""
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
            
    st.session_state['block_inv_debug'] = {f"{k[0]}-{k[1]}": v['count'] for k, v in stack_inventory_map.items()}
    return category_totals

def get_dynamic_floor_premium(df, category):
    """V20: 动态楼层溢价"""
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

def calculate_avm(df, blk, stack, floor):
    """
    🤖 AVM 自动估值模型 (V5)
    """
    target_unit = df[(df['BLK'] == blk) & (df['Stack'] == stack) & (df['Floor_Num'] == floor)]
    
    if not target_unit.empty:
        subject_area = target_unit['Area (sqft)'].iloc[0]
        subject_cat = target_unit['Category'].iloc[0]
    else:
        neighbors = df[(df['BLK'] == blk) & (df['Stack'] == stack)]
        if not neighbors.empty:
            subject_area = neighbors['Area (sqft)'].mode()[0]
            subject_cat = neighbors['Category'].iloc[0]
        else:
            return None, None, None, None, None, pd.DataFrame(), None

    last_date = df['Sale Date'].max()
    cutoff_date = last_date - timedelta(days=365)
    
    comps = df[(df['Category'] == subject_cat) & (df['Sale Date'] >= cutoff_date) & (~df['Is_Special'])].copy()
    
    if len(comps) < 3:
        comps = df[(df['Category'] == subject_cat) & (~df['Is_Special'])].sort_values('Sale Date', ascending=False).head(10)

    if comps.empty:
        return subject_area, 0, 0, 0, 0.005, pd.DataFrame(), subject_cat

    premium_rate = get_dynamic_floor_premium(df, subject_cat)
    base_psf = comps['Sale PSF'].median()      
    base_floor = comps['Floor_Num'].median()   
    
    floor_diff = floor - base_floor
    adjustment_factor = 1 + (floor_diff * premium_rate)
    estimated_psf = base_psf * adjustment_factor
    valuation = subject_area * estimated_psf
    
    comps_display = comps.sort_values('Sale Date', ascending=False).head(5)
    comps_display['Sale Date'] = comps_display['Sale Date'].dt.date
    if 'Unit' not in comps_display.columns:
        comps_display = comps_display[['Sale Date', 'BLK', 'Stack', 'Floor', 'Area (sqft)', 'Sale PSF', 'Sale Price']]
    else:
        comps_display = comps_display[['Sale Date', 'BLK', 'Unit', 'Area (sqft)', 'Sale PSF', 'Sale Price']]
    
    return subject_area, estimated_psf, valuation, floor_diff, premium_rate, comps_display, subject_cat

def calculate_resale_metrics(df):
    """
    📊 计算转售利润 
    """
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

def format_currency(val):
    """🟢 强制货币格式化 (字符串)"""
    try:
        return f"${val:,.0f}"
    except:
        return val

# ==========================================
# 🎨 4. 侧边栏与主界面逻辑
# ==========================================

with st.sidebar:
    st.header("1. 项目切换")
    selected_project = st.selectbox("选择要分析的项目", list(PROJECTS.keys()))
    sheet_url = PROJECTS[selected_project]
    uploaded_file = None
    project_name = selected_project

    if selected_project == "📂 手动上传 CSV":
        uploaded_file = st.file_uploader("拖入 CSV 文件", type=['csv'])
        if uploaded_file:
            project_name = uploaded_file.name.replace(".csv", "")
    else:
        st.success(f"☁️ 已连接云端: {selected_project}")

    st.markdown("---")
    st.header("2. 统计设定")

    df = None
    if selected_project == "📂 手动上传 CSV":
        if uploaded_file: df = load_data(uploaded_file)
    elif sheet_url:
        df = load_data(sheet_url)

    if df is not None:
        possible_cols = ['Bedroom Type', 'Bedrooms', 'Type', 'Bedroom_Type']
        if any(c in df.columns for c in possible_cols) or any('Bedroom' in c for c in df.columns):
            cat_options = ["按卧室数量 (Bedroom Type)", "按楼座 (Block)", "按户型面积段 (自动分箱)"]
        else:
            cat_options = ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室数量 (Bedroom Type)"]
    else:
        cat_options = ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室数量 (Bedroom Type)"]

    category_method = st.selectbox("分类依据", cat_options, index=0)
    inventory_mode = st.radio("库存计算模式", ["🤖 自动推定 (V11智能版)", "🖐 手动输入"], index=0)
    inventory_container = st.container()

    st.markdown("---")
    st.header("3. 导出设置")
    chart_font_size = st.number_input("图表字号", value=16, min_value=10)
    chart_color = st.color_picker("主色调", "#F63366")
    exp_width = st.number_input("宽度 (px)", value=1200, step=100)
    exp_height = st.number_input("高度 (px)", value=675, step=100)
    exp_scale = st.slider("清晰度", 1, 5, 2)

# ==========================================
# 🚀 5. 主逻辑执行
# ==========================================

if df is not None:
    df['Category'] = auto_categorize(df, category_method)
    df['Is_Special'] = mark_penthouse(df)
    unique_cats = sorted(df['Category'].unique(), key=natural_key)
    inventory_map = {}

    with inventory_container:
        if inventory_mode == "🤖 自动推定 (V11智能版)" and 'Stack' in df.columns and 'Floor_Num' in df.columns:
            st.info("已启用 V11 智能库存算法")
            estimated_inv = estimate_inventory(df, 'Category')
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                est_val = int(estimated_inv.get(cat, 100))
                if est_val < 1: est_val = 1 
                with cols[i % 2]:
                    val = st.number_input(f"[{cat}]", value=est_val, min_value=1, key=f"inv_{category_method}_{i}")
                    inventory_map[cat] = val
        else:
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                with cols[i % 2]:
                    val = st.number_input(f"[{cat}]", value=100, min_value=1, key=f"inv_manual_{category_method}_{i}")
                    inventory_map[cat] = val

    total_project_inventory = sum(inventory_map.values())
    
    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    # === Tab 布局 ===
    tab1, tab2, tab3, tab4 = st.tabs(["📊 市场概览 (Deep Dive)", "🏢 楼宇透视 (Visual)", "💎 单元估值 (AVM)", "📝 详细成交记录"])

    # --- Tab 1: 市场概览 ---
    with tab1:
        st.subheader("1. 基础数据概览")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📦 单位总数 (Est.)", f"{total_project_inventory} 户")
        c2.metric("📐 户型总数", f"{df['Category'].nunique()} 类")
        date_span = f"{df['Sale Date'].min().strftime('%Y-%m')} ~ {df['Sale Date'].max().strftime('%Y-%m')}"
        c3.metric("📅 交易周期", date_span)
        total_vol = df['Sale Price'].sum()
        c4.metric("💰 历史总成交额", f"${total_vol/1e9:.2f}B" if total_vol > 1e9 else f"${total_vol/1e6:.1f}M")

        st.markdown("---")
        st.subheader("2. 历年交易趋势")
        yearly_stats = df.groupby('Sale Year').agg({'Sale Price': 'sum', 'BLK': 'count'}).rename(columns={'BLK': 'Count'})
        
        c_chart1, c_chart2 = st.columns(2)
        with c_chart1:
            fig_vol = px.bar(yearly_stats, x=yearly_stats.index, y='Count', title="历年成交量 (宗)", color_discrete_sequence=[chart_color])
            fig_vol.update_layout(font=dict(size=chart_font_size))
            st.plotly_chart(fig_vol, use_container_width=True)
        with c_chart2:
            fig_val = px.line(yearly_stats, x=yearly_stats.index, y='Sale Price', title="历年成交金额 ($)", markers=True)
            fig_val.update_layout(font=dict(size=chart_font_size))
            st.plotly_chart(fig_val, use_container_width=True)

        st.markdown("---")
        st.subheader("3. 活跃度热点分析 (Most Active)")
        
        def show_activity_stats(group_col, label):
            counts = df[group_col].value_counts()
            if counts.empty: return
            top_name = counts.idxmax()
            top_val = counts.max()
            avg_val = counts.mean()
            col_a, col_b = st.columns(2)
            col_a.metric(f"🔥 最活跃 {label}", f"{top_name}", f"{top_val} 宗交易")
            col_b.metric(f"📊 平均每{label}交易量", f"{avg_val:.1f} 宗")

        with st.expander("展开查看详细活跃度对比", expanded=True):
            st.markdown("##### 🏢 按楼栋 (Block)")
            if 'BLK' in df.columns: show_activity_stats('BLK', '楼栋')
            st.markdown("##### 📍 按单元 (Stack)")
            if 'Stack' in df.columns: show_activity_stats('Stack', 'Stack')
            st.markdown("##### 🪜 按楼层 (Floor)")
            if 'Floor_Num' in df.columns: show_activity_stats('Floor_Num', '楼层')
            st.markdown("##### 🏠 按户型 (Category)")
            show_activity_stats('Category', '户型')

        st.markdown("---")
        st.subheader("4. 投资回报深度分析 (Resale Analysis)")
        
        df_resale = calculate_resale_metrics(df)
        
        if not df_resale.empty:
            unit_counts = df['Unit_ID'].value_counts()
            avg_turns = unit_counts.mean() - 1
            kp1, kp2, kp3, kp4 = st.columns(4)
            kp1.metric("🔄 平均转售次数", f"{max(0, avg_turns):.2f} 次")
            kp2.metric("⏳ 平均持有时间", f"{df_resale['Hold_Years'].mean():.1f} 年")
            profit_count = len(df_resale[df_resale['Gain'] > 0])
            kp3.metric("💸 盈利交易占比", f"{(profit_count/len(df_resale)*100):.1f}%", f"{profit_count} 宗")
            
            recent5y = df_resale[df_resale['Sale Date'] > (datetime.now() - timedelta(days=365*5))]
            loss_5y = len(recent5y[recent5y['Gain'] < 0]) if not recent5y.empty else 0
            den = len(recent5y) if not recent5y.empty else 1
            kp4.metric("📉 近5年亏损占比", f"{(loss_5y/den*100):.1f}%" if not recent5y.empty else "无数据")

            st.write("##### 📊 各户型投资表现")
            cat_stats = df_resale.groupby('Category').agg({
                'Hold_Years': ['mean', 'min', 'max'],
                'Gain': ['mean', 'min', 'max'],
                'Annualized': ['mean']
            }).reset_index()
            cat_stats.columns = ['Category', 'Avg Hold', 'Min Hold', 'Max Hold', 'Avg Gain', 'Max Loss/Min Gain', 'Max Gain', 'Avg Annualized']
            
            cat_stats['Avg Gain'] = cat_stats['Avg Gain'].apply(format_currency)
            cat_stats['Max Loss/Min Gain'] = cat_stats['Max Loss/Min Gain'].apply(format_currency)
            cat_stats['Max Gain'] = cat_stats['Max Gain'].apply(format_currency)
            
            st.dataframe(cat_stats, use_container_width=True, column_config={
                "Avg Hold": st.column_config.NumberColumn("平均持有 (年)", format="%.1f yrs"),
                "Min Hold": st.column_config.NumberColumn("最短", format="%.1f"),
                "Max Hold": st.column_config.NumberColumn("最长", format="%.1f"),
                "Avg Annualized": st.column_config.NumberColumn("平均年化", format="%.2%"),
            })
        else:
            st.info("暂未发现转售记录 (需至少有2笔历史交易，且最新一笔不为 New Sale)。")

    # --- Tab 2: 楼宇透视 ---
    with tab2:
        st.subheader("🏢 楼宇透视")
        
        if 'BLK' in df.columns:
            all_blks = sorted(df['BLK'].unique(), key=natural_key)
            try:
                selected_blk = st.pills("选择楼栋:", all_blks, selection_mode="single", default=all_blks[0], key="tw_blk")
            except AttributeError:
                selected_blk = st.radio("选择楼栋:", all_blks, horizontal=True, key="tw_blk_radio")

            if selected_blk:
                blk_df = df[df['BLK'] == selected_blk].copy()
                valid_floors = blk_df.dropna(subset=['Floor_Num'])
                block_floors_set = set(valid_floors['Floor_Num'].unique())
                floors_to_plot = {f for f in block_floors_set if f > 0}
                sorted_floors_num = sorted(list(floors_to_plot))
                all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key) if 'Stack' in blk_df.columns else ['Unknown']
                
                grid_data = []
                for stack in all_stacks:
                    for floor in sorted_floors_num:
                        match = blk_df[(blk_df['Stack'] == stack) & (blk_df['Floor_Num'] == floor)]
                        stack_str = str(stack).strip()
                        stack_fmt = stack_str.zfill(2) if stack_str.isdigit() else stack_str
                        unit_label = f"#{int(floor):02d}-{stack_fmt}"
                        
                        if not match.empty:
                            latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                            # 🟢 V36 增强: 计算持有时长
                            hold_days = (datetime.now() - latest['Sale Date']).days
                            hold_years = hold_days / 365.25
                            display_text = f"{unit_label}<br>{hold_years:.1f}y"
                            
                            grid_data.append({
                                'Stack': str(stack), 'Floor': str(int(floor)), 'Type': 'Sold',
                                'PSF': int(latest['Sale PSF']), 'Price': f"${latest['Sale Price']/1e6:.2f}M", 
                                'Year': latest['Sale Year'], 'Raw_Floor': int(floor), 
                                'Label': display_text, # 使用带年份的文本
                                'Fmt_Stack': stack_fmt 
                            })
                        else:
                            grid_data.append({
                                'Stack': str(stack), 'Floor': str(int(floor)), 'Type': 'Stock',
                                'PSF': None, 'Price': '-', 'Year': '-', 'Raw_Floor': int(floor), 
                                'Label': unit_label, 
                                'Fmt_Stack': stack_fmt
                            })
                
                viz_df = pd.DataFrame(grid_data)
                
                if not viz_df.empty:
                    fig_tower = go.Figure()
                    y_category_order = [str(f) for f in sorted_floors_num]
                    
                    stock_df = viz_df[viz_df['Type'] == 'Stock']
                    if not stock_df.empty:
                        fig_tower.add_trace(go.Heatmap(
                            x=stock_df['Stack'], y=stock_df['Floor'], z=[1]*len(stock_df),
                            colorscale=[[0, '#eeeeee'], [1, '#eeeeee']], showscale=False, xgap=2, ygap=2, hoverinfo='text',
                            text=stock_df['Label'] + "<br>点击查看估值", customdata=stock_df[['Stack', 'Raw_Floor']]
                        ))

                    sold_df = viz_df[viz_df['Type'] == 'Sold']
                    if not sold_df.empty:
                        fig_tower.add_trace(go.Heatmap(
                            x=sold_df['Stack'], y=sold_df['Floor'], z=sold_df['PSF'],
                            colorscale='Teal', colorbar=dict(title="成交尺价 ($psf)", len=0.5, y=0.5),
                            xgap=2, ygap=2,
                            # 直接展示 text (Label 已经包含了 unit_label + years)
                            text=sold_df['Label'],
                            texttemplate="%{text}",
                            hovertemplate="<b>Stack %{x} - #%{y}</b><br>💰 PSF: $%{z}<br>🏷️ 总价: %{customdata[2]}<br>📅 年份: %{customdata[3]}<extra></extra>",
                            customdata=sold_df[['Stack', 'Raw_Floor', 'Price', 'Year']]
                        ))

                    fig_tower.update_layout(
                        title=dict(text=f"Block {selected_blk} - 物理透视图", x=0.5),
                        xaxis=dict(title="Stack", type='category', side='bottom'),
                        yaxis=dict(title="Floor", type='category', categoryorder='array', categoryarray=y_category_order, dtick=1),
                        plot_bgcolor='white', height=max(400, len(y_category_order) * 35), 
                        width=min(1000, 100 * len(all_stacks) + 200), margin=dict(l=50, r=50, t=60, b=50),
                        clickmode='event+select'
                    )
                    
                    fig_tower.update_layout(font=dict(size=chart_font_size))
                    
                    event = st.plotly_chart(
                        fig_tower, use_container_width=True, on_select="rerun", selection_mode="points", 
                        key=f"chart_v36_{selected_blk}", config={'displayModeBar': False}
                    )
                    
                    if event and "selection" in event and event["selection"]["points"]:
                        point = event["selection"]["points"][0]
                        if "customdata" in point:
                            clk_stack = str(point["customdata"][0])
                            clk_floor = int(point["customdata"][1])
                            st.session_state['avm_target'] = {
                                'blk': selected_blk,
                                'stack': clk_stack,
                                'floor': clk_floor
                            }
                else:
                    st.warning("数据不足")
        else:
            st.warning("缺少 BLK 列")

    # --- Tab 3: AVM 单元估值 ---
    with tab3:
        st.subheader("💎 AVM 智能估值计算器")
        
        c_sel_1, c_sel_2, c_sel_3 = st.columns(3)
        def_blk_idx, def_floor_idx, def_stack_idx = 0, 0, 0
        
        all_blks = sorted(df['BLK'].unique(), key=natural_key) if 'BLK' in df.columns else []
        current_target = st.session_state.get('avm_target', {})
        if current_target and current_target.get('blk') in all_blks:
            def_blk_idx = all_blks.index(current_target['blk'])
        
        with c_sel_1:
            sel_blk = st.selectbox("Block (楼栋)", all_blks, index=def_blk_idx, key="avm_blk")
        
        if sel_blk:
            blk_df = df[df['BLK'] == sel_blk]
            max_floor_num = int(blk_df['Floor_Num'].max())
            all_possible_floors = sorted(list(range(1, max_floor_num + 1)))
            
            if current_target.get('blk') == sel_blk and current_target.get('floor') in all_possible_floors:
                def_floor_idx = all_possible_floors.index(current_target['floor'])
            
            with c_sel_2:
                sel_floor = st.selectbox("Floor (楼层)", all_possible_floors, index=def_floor_idx, key="avm_floor_sel")
                
            if sel_floor:
                all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
                if current_target.get('stack') and str(current_target.get('stack')) in [str(s) for s in all_stacks]:
                    stack_str_list = [str(s) for s in all_stacks]
                    def_stack_idx = stack_str_list.index(str(current_target['stack']))
                
                with c_sel_3:
                    sel_stack = st.selectbox("Stack (单元)", all_stacks, index=def_stack_idx, key="avm_stack")
        
        st.divider()

        if sel_blk and sel_stack and sel_floor:
            s_str = str(sel_stack).strip()
            s_fmt = s_str.zfill(2) if s_str.isdigit() else s_str
            unit_label = f"#{int(sel_floor):02d}-{s_fmt}"
            
            st.markdown(f"#### 🏠 估值对象：{sel_blk}, {unit_label}")
            
            try:
                area, est_psf, value, floor_diff, premium_rate, comps_df, subject_cat = calculate_avm(df, sel_blk, sel_stack, sel_floor)
                
                if area:
                    val_low = value * 0.9
                    val_high = value * 1.1
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("📐 单元面积", f"{int(area):,} sqft")
                    premium_txt = f"{premium_rate*100:.1f}%"
                    delta_c = "normal" if floor_diff > 0 else "inverse"
                    m2.metric(f"📊 估算 PSF ({premium_txt} 溢价)", f"${int(est_psf):,} psf", f"{floor_diff:+.0f} 层 (vs 均值)", delta_color=delta_c)
                    m3.metric("💰 HAO 估值 (Est. Value)", f"${value/1e6:.2f}M")
                    
                    history_unit = df[(df['BLK'] == sel_blk) & (df['Stack'] == sel_stack) & (df['Floor_Num'] == sel_floor)].sort_values('Sale Date', ascending=False)
                    
                    if not history_unit.empty:
                        last_price = history_unit.iloc[0]['Sale Price']
                        est_gain = value - last_price
                        est_gain_pct = est_gain / last_price
                        gain_color = "normal" if est_gain > 0 else "inverse"
                        m4.metric("🚀 预估增值 (vs 上次)", f"${est_gain/1e6:.2f}M", f"{est_gain_pct:+.1%}", delta_color=gain_color)
                    else:
                        earliest_year = int(df['Sale Year'].min())
                        base_recs = df[(df['Sale Year'] == earliest_year) & (df['Category'] == subject_cat)]
                        if not base_recs.empty:
                            base_psf_avg = base_recs['Sale PSF'].mean()
                            est_cost = area * base_psf_avg
                            sim_gain = value - est_cost
                            sim_pct = sim_gain / est_cost
                            m4.metric(f"🔮 模拟增值 (自{earliest_year}年)", f"${sim_gain/1e6:.2f}M", f"{sim_pct:+.1%} (基于当年均价)", delta_color="off")
                            st.caption(f"*注：该单元无历史交易。模拟增值假设以 {earliest_year} 年同户型均价 (${int(base_psf_avg):,} psf) 购入。")
                        else:
                            m4.metric("🚀 预估增值", "-", "无同期基准")
                    
                    st.write("") 

                    fig_range = go.Figure()
                    fig_range.add_trace(go.Scatter(
                        x=[val_low, val_high], y=[0, 0], mode='lines',
                        line=dict(color='#E0E0E0', width=12), showlegend=False, hoverinfo='skip'
                    ))
                    fig_range.add_trace(go.Scatter(
                        x=[val_low, val_high], y=[0, 0], mode='markers+text',
                        marker=dict(color=['#FF6B6B', '#4ECDC4'], size=18),
                        text=[f"<b>${val_low/1e6:.2f}M</b><br>-10%", f"<b>${val_high/1e6:.2f}M</b><br>+10%"],
                        textposition=["bottom center", "bottom center"], showlegend=False, hoverinfo='skip'
                    ))
                    fig_range.add_trace(go.Scatter(
                        x=[value], y=[0], mode='markers+text',
                        marker=dict(color='#2C3E50', size=25, symbol='diamond'),
                        text=[f"<b>${value/1e6:.2f}M</b><br>估值中心"],
                        textposition="top center", showlegend=False, hoverinfo='x'
                    ))
                    fig_range.update_layout(
                        title=dict(text="⚖️ 估值区间 (Price Range)", x=0.5, xanchor='center', y=0.9),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[val_low*0.9, val_high*1.1]),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.5, 0.8]),
                        height=180, margin=dict(l=20, r=20, t=40, b=10),
                        plot_bgcolor='white'
                    )
                    fig_range.update_layout(font=dict(size=chart_font_size))
                    st.plotly_chart(fig_range, use_container_width=True)
                    
                    # 🟢 V36 布局修改：历史交易在上方，参考交易在下方
                    st.write("##### 📜 该单元历史交易")
                    if not history_unit.empty:
                        hist_display = history_unit.copy()
                        hist_display['Sale Date'] = hist_display['Sale Date'].dt.date
                        hist_display['Sale Price'] = hist_display['Sale Price'].apply(format_currency)
                        hist_display['Sale PSF'] = hist_display['Sale PSF'].apply(format_currency)
                        st.dataframe(
                            hist_display[['Sale Date', 'Unit', 'Sale Price', 'Sale PSF']], 
                            hide_index=True, use_container_width=True,
                            column_config={
                                "Sale Price": st.column_config.TextColumn("成交价"),
                                "Sale PSF": st.column_config.TextColumn("尺价")
                            }
                        )
                    else:
                        st.info("暂无历史交易记录")
                    
                    st.divider() # 分隔线
                    
                    st.write(f"##### ⚖️ 估值参考 ({len(comps_df)} 笔相似成交)")
                    if not comps_df.empty:
                        comps_df['Sale Price'] = comps_df['Sale Price'].apply(format_currency)
                        comps_df['Sale PSF'] = comps_df['Sale PSF'].apply(format_currency)
                        st.dataframe(
                            comps_df[['Sale Date', 'BLK', 'Unit', 'Category', 'Area (sqft)', 'Sale Price', 'Sale PSF']], 
                            hide_index=True, use_container_width=True,
                            column_config={
                                "Sale Price": st.column_config.TextColumn("成交价"),
                                "Sale PSF": st.column_config.TextColumn("尺价"),
                                "Category": st.column_config.TextColumn("户型"),
                                "Area (sqft)": st.column_config.NumberColumn("面积", format="%d"),
                            }
                        )
                    else:
                        st.warning("数据量不足，无法找到相似对标。")
                else:
                    st.error("无法获取该单元的面积数据 (Missing Area)，无法估值。")
            except Exception as e:
                st.error(f"计算出错: {e}")

    # --- Tab 4: 详细成交记录 ---
    with tab4:
        st.subheader("📝 详细成交记录")
        display_df = df.copy()
        if 'Unit' not in display_df.columns:
            display_df['Unit'] = display_df.apply(lambda x: f"#{int(x['Floor_Num']):02d}-{x['Stack']}", axis=1)

        bed_col = 'Category' 
        potential_bed_cols = ['No. of Bedrooms', 'Bedrooms', 'Bedroom Type', 'Bedroom_Type', 'Type']
        for c in potential_bed_cols:
            if c in display_df.columns:
                bed_col = c
                break
        
        display_df['Sale Price'] = display_df['Sale Price'].apply(format_currency)
        display_df['Sale PSF'] = display_df['Sale PSF'].apply(format_currency)
        
        show_cols = ['Sale Date', 'BLK', 'Unit', bed_col, 'Area (sqft)', 'Sale Price', 'Sale PSF']
        
        st.dataframe(
            display_df[show_cols].sort_values('Sale Date', ascending=False), 
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sale Date": st.column_config.DateColumn("成交日期"),
                "Area (sqft)": st.column_config.NumberColumn("面积 (sqft)", format="%d"),
                bed_col: st.column_config.TextColumn("卧室 (Bedrooms)"),
                "Sale Price": st.column_config.TextColumn("成交价 ($)"),
                "Sale PSF": st.column_config.TextColumn("尺价 ($psf)"),
            }
        )

else:
    st.info("👈 请在左侧选择项目或上传 CSV 文件。")
