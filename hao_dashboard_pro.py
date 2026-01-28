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

        # 🟢 预处理：生成标准单元号 (#Floor-Stack)
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
    """🤖 AVM 自动估值模型 (V4: Unit列优化)"""
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
            return None, None, None, None, None, pd.DataFrame()

    last_date = df['Sale Date'].max()
    cutoff_date = last_date - timedelta(days=365)
    
    comps = df[(df['Category'] == subject_cat) & (df['Sale Date'] >= cutoff_date) & (~df['Is_Special'])].copy()
    
    if len(comps) < 3:
        comps = df[(df['Category'] == subject_cat) & (~df['Is_Special'])].sort_values('Sale Date', ascending=False).head(10)

    if comps.empty:
        return subject_area, 0, 0, 0, 0.005, pd.DataFrame()

    premium_rate = get_dynamic_floor_premium(df, subject_cat)
    base_psf = comps['Sale PSF'].median()      
    base_floor = comps['Floor_Num'].median()   
    
    floor_diff = floor - base_floor
    adjustment_factor = 1 + (floor_diff * premium_rate)
    
    estimated_psf = base_psf * adjustment_factor
    valuation = subject_area * estimated_psf
    
    comps_display = comps.sort_values('Sale Date', ascending=False).head(5)
    comps_display['Sale Date'] = comps_display['Sale Date'].dt.date
    # 🟢 优化：使用 Unit 列，移除 Stack/Floor 分开的列
    if 'Unit' not in comps_display.columns:
        # Fallback if Unit wasn't created
        comps_display = comps_display[['Sale Date', 'BLK', 'Stack', 'Floor', 'Area (sqft)', 'Sale PSF', 'Sale Price']]
    else:
        comps_display = comps_display[['Sale Date', 'BLK', 'Unit', 'Area (sqft)', 'Sale PSF', 'Sale Price']]
    
    return subject_area, estimated_psf, valuation, floor_diff, premium_rate, comps_display

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
            if inventory_mode == "🤖 自动推定..." and 'Stack' not in df.columns:
                st.warning("缺少 Stack 列，无法自动推定。")
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                with cols[i % 2]:
                    val = st.number_input(f"[{cat}]", value=100, min_value=1, key=f"inv_manual_{category_method}_{i}")
                    inventory_map[cat] = val

    total_project_inventory = sum(inventory_map.values())
    
    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    # === Tab 布局重构 (V22) ===
    # 将 AVM 独立为 Tab 3
    tab1, tab2, tab3, tab4 = st.tabs(["📊 市场概览", "🏢 楼宇透视 (Visual)", "💎 单元估值 (AVM)", "📝 详细成交记录"])

    # --- Tab 1: 市场概览 ---
    with tab1:
        current_year = datetime.now().year 
        df_this_year = df[df['Sale Year'] == current_year]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"{current_year}年 成交量", f"{len(df_this_year)} 宗")
        if len(df_this_year) > 0:
            col2.metric(f"{current_year} 均尺价", f"${df_this_year['Sale PSF'].mean():,.0f} psf")
            col3.metric(f"{current_year} 最高价", f"${df_this_year['Sale Price'].max()/1e6:.2f}M")
        else:
            col2.metric(f"{current_year} 均尺价", "-")
            col3.metric(f"{current_year} 最高价", "-")
        
        turnover_ytd = (len(df_this_year) / total_project_inventory * 100) if total_project_inventory > 0 else 0
        col4.metric(f"{current_year} 整体换手率", f"{turnover_ytd:.2f}%")

        st.divider()
        st.subheader("📈 价格与成交量趋势")
        
        col_ctrl1, col_ctrl2 = st.columns([1, 3])
        with col_ctrl1:
            freq_map = {"年 (Year)": "Y", "季度 (Quarter)": "Q", "月 (Month)": "M"}
            freq_sel = st.selectbox("时间粒度", list(freq_map.keys()))
            freq_code = freq_map[freq_sel]
            
            min_d = df['Sale Date'].min().date().replace(day=1)
            max_d_raw = df['Sale Date'].max().date()
            last_day = calendar.monthrange(max_d_raw.year, max_d_raw.month)[1]
            max_d = max_d_raw.replace(day=last_day)
            date_range = st.date_input("选择时间范围", [min_d, max_d])

        if len(date_range) == 2:
            start_d = pd.to_datetime(date_range[0])
            end_d = pd.to_datetime(date_range[1]) + timedelta(days=1) - timedelta(seconds=1)
            mask = (df['Sale Date'] >= start_d) & (df['Sale Date'] <= end_d)
            df_filtered = df.loc[mask]
        else:
            df_filtered = df

        trend_data = df_filtered.set_index('Sale Date').groupby('Category').resample(freq_code).agg({
            'Sale PSF': 'mean', 'Sale Price': 'count'
        }).rename(columns={'Sale Price': 'Volume'}).reset_index()

        fig = px.line(
            trend_data, x='Sale Date', y='Sale PSF', color='Category', 
            markers=True, symbol='Category',
            title=f"{project_name} 尺价走势 ({freq_sel})",
            color_discrete_sequence=[chart_color, "#2E86C1", "#28B463", "#D35400", "#8E44AD"]
        )
        fig.update_traces(connectgaps=True)
        fig.update_layout(
            font=dict(size=chart_font_size, family="Arial"),
            title=dict(font=dict(size=chart_font_size + 4)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None),
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # --- Tab 2: 楼宇透视 ---
    with tab2:
        st.subheader("🏢 楼宇透视")
        st.caption("👈 **点击方格**，自动跳转至 AVM Tab 查看详情。")
        
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
                        # Unit Label
                        stack_str = str(stack).strip()
                        s_fmt = stack_str.zfill(2) if stack_str.isdigit() else stack_str
                        unit_label = f"#{int(floor):02d}-{s_fmt}"
                        
                        if not match.empty:
                            latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                            grid_data.append({
                                'Stack': str(stack), 'Floor': str(int(floor)), 'Type': 'Sold',
                                'PSF': int(latest['Sale PSF']), 'Price': f"${latest['Sale Price']/1e6:.2f}M", 
                                'Year': latest['Sale Year'], 'Raw_Floor': int(floor), 'Label': unit_label
                            })
                        else:
                            grid_data.append({
                                'Stack': str(stack), 'Floor': str(int(floor)), 'Type': 'Stock',
                                'PSF': None, 'Price': '-', 'Year': '-', 'Raw_Floor': int(floor), 'Label': unit_label
                            })
                
                viz_df = pd.DataFrame(grid_data)
                
                if not viz_df.empty:
                    fig_tower = go.Figure()
                    y_category_order = [str(f) for f in sorted_floors_num]
                    
                    # 库存
                    stock_df = viz_df[viz_df['Type'] == 'Stock']
                    if not stock_df.empty:
                        fig_tower.add_trace(go.Heatmap(
                            x=stock_df['Stack'], y=stock_df['Floor'], z=[1]*len(stock_df),
                            colorscale=[[0, '#eeeeee'], [1, '#eeeeee']], showscale=False, xgap=2, ygap=2, hoverinfo='text',
                            text=stock_df['Label'] + "<br>点击查看估值", 
                            customdata=stock_df[['Stack', 'Raw_Floor']]
                        ))

                    # 成交
                    sold_df = viz_df[viz_df['Type'] == 'Sold']
                    if not sold_df.empty:
                        fig_tower.add_trace(go.Heatmap(
                            x=sold_df['Stack'], y=sold_df['Floor'], z=sold_df['PSF'],
                            colorscale='Teal', colorbar=dict(title="成交尺价 ($psf)", len=0.5, y=0.5),
                            xgap=2, ygap=2,
                            hovertemplate="<b>%{customdata[2]}</b><br>💰 PSF: $%{z}<br>🏷️ 总价: %{customdata[3]}<br>📅 年份: %{customdata[4]}<extra></extra>",
                            customdata=sold_df[['Stack', 'Raw_Floor', 'Label', 'Price', 'Year']]
                        ))

                    fig_tower.update_layout(
                        title=dict(text=f"Block {selected_blk} - 物理透视图", x=0.5),
                        xaxis=dict(title="Stack", type='category', side='bottom'),
                        yaxis=dict(title="Floor", type='category', categoryorder='array', categoryarray=y_category_order, dtick=1),
                        plot_bgcolor='white', height=max(400, len(y_category_order) * 35), 
                        width=min(1000, 100 * len(all_stacks) + 200), margin=dict(l=50, r=50, t=60, b=50),
                        clickmode='event+select'
                    )
                    
                    event = st.plotly_chart(
                        fig_tower, use_container_width=True, on_select="rerun", selection_mode="points", 
                        key=f"chart_v22_{selected_blk}", config={'displayModeBar': False}
                    )
                    
                    # 🟢 捕捉点击并写入 Session State
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
                            st.success(f"已选中 {selected_blk} Stack {clk_stack} #{clk_floor}，请切换至 [💎 单元估值] Tab 查看报告。")
                else:
                    st.warning("数据不足")
        else:
            st.warning("缺少 BLK 列")

    # --- Tab 3: AVM 单元估值 (独立 Tab) ---
    with tab3:
        st.subheader("💎 AVM 智能估值计算器")
        
        # 1. 估值对象选择器
        c_sel_1, c_sel_2, c_sel_3 = st.columns(3)
        
        # 默认值逻辑 (从 Session State 读取)
        def_blk_idx, def_stack_idx, def_floor_val = 0, 0, 1
        
        # 获取所有选项
        all_blks = sorted(df['BLK'].unique(), key=natural_key) if 'BLK' in df.columns else []
        
        # 如果有缓存的点击目标，尝试对齐
        current_target = st.session_state.get('avm_target', {})
        if current_target and current_target.get('blk') in all_blks:
            def_blk_idx = all_blks.index(current_target['blk'])
        
        with c_sel_1:
            sel_blk = st.selectbox("Block (楼栋)", all_blks, index=def_blk_idx, key="avm_blk")
        
        # 级联更新 Stack
        if sel_blk:
            blk_df = df[df['BLK'] == sel_blk]
            all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key) if 'Stack' in blk_df.columns else []
            
            # 尝试对齐 Stack
            if current_target.get('blk') == sel_blk and str(current_target.get('stack')) in [str(s) for s in all_stacks]:
                # 找到对应 index
                stack_str_list = [str(s) for s in all_stacks]
                def_stack_idx = stack_str_list.index(str(current_target['stack']))
            
            with c_sel_2:
                sel_stack = st.selectbox("Stack (单元)", all_stacks, index=def_stack_idx, key="avm_stack")
                
            # 级联更新 Floor
            if sel_stack:
                stack_floors = sorted(blk_df[blk_df['Stack'] == sel_stack]['Floor_Num'].dropna().unique())
                # 尝试对齐 Floor (Number Input)
                if current_target.get('stack') == str(sel_stack) and current_target.get('floor'):
                    def_floor_val = int(current_target['floor'])
                elif stack_floors:
                    def_floor_val = int(stack_floors[0])
                
                with c_sel_3:
                    sel_floor = st.number_input("Floor (楼层)", min_value=1, max_value=99, value=def_floor_val, key="avm_floor")
        
        st.divider()

        # 2. 执行计算
        if sel_blk and sel_stack and sel_floor:
            # 构造 Label
            s_str = str(sel_stack).strip()
            s_fmt = s_str.zfill(2) if s_str.isdigit() else s_str
            unit_label = f"#{int(sel_floor):02d}-{s_fmt}"
            
            st.markdown(f"#### 🏠 估值对象：{sel_blk}, {unit_label}")
            
            try:
                area, est_psf, value, floor_diff, premium_rate, comps_df = calculate_avm(df, sel_blk, sel_stack, sel_floor)
                
                if area:
                    # A. 核心指标
                    val_low = value * 0.9
                    val_high = value * 1.1
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("📐 单元面积", f"{int(area):,} sqft")
                    premium_txt = f"{premium_rate*100:.1f}%"
                    delta_c = "normal" if floor_diff > 0 else "inverse"
                    m2.metric(f"📊 估算 PSF ({premium_txt} 溢价)", f"${int(est_psf):,} psf", f"{floor_diff:+.0f} 层 (vs 均值)", delta_color=delta_c)
                    m3.metric("💰 银行估值 (Est. Value)", f"${value/1e6:.2f}M")
                    
                    st.write("") 

                    # B. 估值区间图 (无刻度 X 轴)
                    fig_range = go.Figure()
                    # 背景条
                    fig_range.add_trace(go.Scatter(
                        x=[val_low, val_high], y=[0, 0], mode='lines',
                        line=dict(color='#E0E0E0', width=12), showlegend=False, hoverinfo='skip'
                    ))
                    # 标记点
                    fig_range.add_trace(go.Scatter(
                        x=[val_low, val_high], y=[0, 0], mode='markers+text',
                        marker=dict(color=['#FF6B6B', '#4ECDC4'], size=18),
                        text=[f"<b>${val_low/1e6:.2f}M</b><br>-10%", f"<b>${val_high/1e6:.2f}M</b><br>+10%"],
                        textposition=["bottom center", "bottom center"],
                        showlegend=False, hoverinfo='skip'
                    ))
                    # 中心估值
                    fig_range.add_trace(go.Scatter(
                        x=[value], y=[0], mode='markers+text',
                        marker=dict(color='#2C3E50', size=25, symbol='diamond'),
                        text=[f"<b>${value/1e6:.2f}M</b><br>估值中心"],
                        textposition="top center", showlegend=False, hoverinfo='x'
                    ))
                    fig_range.update_layout(
                        title=dict(text="⚖️ 估值区间 (Price Range)", x=0.5, y=0.9),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[val_low*0.9, val_high*1.1]),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.5, 0.8]),
                        height=180, margin=dict(l=20, r=20, t=40, b=10),
                        plot_bgcolor='white'
                    )
                    st.plotly_chart(fig_range, use_container_width=True)
                    
                    # C. 表格展示
                    c_info1, c_info2 = st.columns(2)
                    
                    # 格式化配置
                    currency_fmt = st.column_config.NumberColumn(format="$%d")
                    
                    with c_info1:
                        st.write("##### 📜 该单元历史交易")
                        history = df[(df['BLK'] == sel_blk) & (df['Stack'] == sel_stack) & (df['Floor_Num'] == sel_floor)].copy()
                        if not history.empty:
                            history['Sale Date'] = history['Sale Date'].dt.date
                            # 🟢 格式化表格
                            st.dataframe(
                                history[['Sale Date', 'Unit', 'Sale Price', 'Sale PSF']], 
                                hide_index=True, use_container_width=True,
                                column_config={
                                    "Sale Price": currency_fmt,
                                    "Sale PSF": currency_fmt
                                }
                            )
                        else:
                            st.info("暂无历史交易记录")
                    
                    with c_info2:
                        st.write(f"##### ⚖️ 估值参考 ({len(comps_df)} 笔相似成交)")
                        if not comps_df.empty:
                            st.dataframe(
                                comps_df[['Sale Date', 'BLK', 'Unit', 'Sale Price', 'Sale PSF']], 
                                hide_index=True, use_container_width=True,
                                column_config={
                                    "Sale Price": currency_fmt,
                                    "Sale PSF": currency_fmt
                                }
                            )
                        else:
                            st.warning("数据量不足，无法找到相似对标。")
                else:
                    st.error("无法获取该单元的面积数据 (Missing Area)，无法估值。")
            except Exception as e:
                st.error(f"计算出错: {e}")

    # --- Tab 4: 详细成交记录 (优化版) ---
    with tab4:
        st.subheader("📝 详细成交记录")
        
        # 🟢 确保 Unit 列存在
        display_df = df.copy()
        if 'Unit' not in display_df.columns:
            # Fallback formatting if pre-calc failed
            display_df['Unit'] = display_df.apply(lambda x: f"#{int(x['Floor_Num']):02d}-{x['Stack']}", axis=1)

        st.dataframe(
            display_df[['Sale Date', 'BLK', 'Unit', 'Area (sqft)', 'Sale Price', 'Sale PSF', 'Category']].sort_values('Sale Date', ascending=False), 
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sale Date": st.column_config.DateColumn("成交日期"),
                "Sale Price": st.column_config.NumberColumn("成交价 ($)", format="$%d"),
                "Sale PSF": st.column_config.NumberColumn("尺价 ($psf)", format="$%d"),
                "Area (sqft)": st.column_config.NumberColumn("面积 (sqft)", format="%d"),
            }
        )

else:
    st.info("👈 请在左侧选择项目或上传 CSV 文件。")
