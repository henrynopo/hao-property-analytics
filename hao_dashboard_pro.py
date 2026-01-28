# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar
import re 

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

def calculate_avm(df, blk, stack, floor):
    """🤖 AVM 自动估值模型"""
    # 1. 确定目标单元面积
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
            return None, None, None, pd.DataFrame()

    # 2. 确定市场参考 PSF
    last_date = df['Sale Date'].max()
    cutoff_date = last_date - timedelta(days=365)
    
    comps = df[
        (df['Category'] == subject_cat) & 
        (df['Sale Date'] >= cutoff_date) &
        (~df['Is_Special']) 
    ].copy()
    
    if len(comps) < 3:
        comps = df[(df['Category'] == subject_cat)].sort_values('Sale Date', ascending=False).head(10)

    if comps.empty:
        return subject_area, 0, 0, pd.DataFrame()

    market_psf = comps['Sale PSF'].median()
    valuation = subject_area * market_psf
    comps_display = comps.sort_values('Sale Date', ascending=False).head(5)
    
    # --- 🟢 修复日期格式 (只保留日期) ---
    comps_display['Sale Date'] = comps_display['Sale Date'].dt.date
    
    comps_display = comps_display[['Sale Date', 'BLK', 'Stack', 'Floor', 'Area (sqft)', 'Sale PSF', 'Sale Price']]
    
    return subject_area, market_psf, valuation, comps_display

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
    
    # --- 5.1 KPI ---
    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

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

    # --- 5.2 趋势图 ---
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
    st.plotly_chart(fig, use_container_width=True, config={
        'displayModeBar': True,
        'toImageButtonOptions': {'format': 'png', 'filename': f'{project_name}_trend', 'height': exp_height, 'width': exp_width, 'scale': exp_scale},
        'displaylogo': False
    })

    st.divider()

# 5.3 楼宇透视 (Tower View) - V18 格式美化版
    st.subheader("🏢 楼宇透视 (Tower View)")
    st.caption("👈 **操作指南**：直接点击图表方格，或者在下方下拉菜单中选择单元，查看估值报告。")
    
    if 'BLK' in df.columns:
        all_blks = sorted(df['BLK'].unique(), key=natural_key)
        try:
            selected_blk = st.pills("选择楼栋:", all_blks, selection_mode="single", default=all_blks[0])
        except AttributeError:
            selected_blk = st.radio("选择楼栋:", all_blks, horizontal=True)

        if selected_blk:
            blk_df = df[df['BLK'] == selected_blk].copy()
            
            # --- 构建物理骨架 ---
            valid_floors = blk_df.dropna(subset=['Floor_Num'])
            block_floors_set = set(valid_floors['Floor_Num'].unique())
            floors_to_plot = {f for f in block_floors_set if f > 0}
            sorted_floors_num = sorted(list(floors_to_plot))
            all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key) if 'Stack' in blk_df.columns else ['Unknown']
            
            # --- 填充数据 ---
            grid_data = []
            for stack in all_stacks:
                for floor in sorted_floors_num:
                    match = blk_df[(blk_df['Stack'] == stack) & (blk_df['Floor_Num'] == floor)]
                    
                    # --- 🟢 格式修复：#Floor-Stack (例如 #03-12) ---
                    # floor:02d 保证楼层是个位数时前面补0
                    unit_label = f"#{int(floor):02d}-{stack}"
                    
                    if not match.empty:
                        latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                        grid_data.append({
                            'Stack': str(stack), 'Floor': str(int(floor)), 'Type': 'Sold',
                            'PSF': int(latest['Sale PSF']), 'Price': f"${latest['Sale Price']/1e6:.2f}M", 
                            'Year': latest['Sale Year'],
                            'Raw_Floor': int(floor), 'Label': unit_label
                        })
                    else:
                        grid_data.append({
                            'Stack': str(stack), 'Floor': str(int(floor)), 'Type': 'Stock',
                            'PSF': None, 'Price': '-', 'Year': '-',
                            'Raw_Floor': int(floor), 'Label': unit_label
                        })
            
            viz_df = pd.DataFrame(grid_data)
            
            if not viz_df.empty:
                fig_tower = go.Figure()
                y_category_order = [str(f) for f in sorted_floors_num]
                
                # 层1：库存
                stock_df = viz_df[viz_df['Type'] == 'Stock']
                if not stock_df.empty:
                    fig_tower.add_trace(go.Heatmap(
                        x=stock_df['Stack'], y=stock_df['Floor'], z=[1]*len(stock_df),
                        colorscale=[[0, '#eeeeee'], [1, '#eeeeee']], showscale=False, xgap=2, ygap=2, hoverinfo='text',
                        text=stock_df['Label'] + "<br>库存 (点击估值)",
                        customdata=stock_df[['Stack', 'Raw_Floor']]
                    ))

                # 层2：成交
                sold_df = viz_df[viz_df['Type'] == 'Sold']
                if not sold_df.empty:
                    fig_tower.add_trace(go.Heatmap(
                        x=sold_df['Stack'], y=sold_df['Floor'], z=sold_df['PSF'],
                        colorscale='Teal', colorbar=dict(title="成交尺价 ($psf)", len=0.5, y=0.5),
                        xgap=2, ygap=2,
                        hovertemplate="<b>%{customdata[2]}</b><br>💰 PSF: $%{z}<br>🏷️ 总价: %{customdata[3]}<br>📅 年份: %{customdata[4]}<extra></extra>",
                        # 注意：Label 在 index 2
                        customdata=sold_df[['Stack', 'Raw_Floor', 'Label', 'Price', 'Year']]
                    ))

                fig_tower.update_layout(
                    title=dict(text=f"Block {selected_blk} - 物理透视图", x=0.5),
                    xaxis=dict(title="Stack", type='category', side='bottom'),
                    yaxis=dict(title="Floor", type='category', categoryorder='array', categoryarray=y_category_order, dtick=1),
                    plot_bgcolor='white',
                    height=max(400, len(y_category_order) * 35), width=min(1000, 100 * len(all_stacks) + 200),
                    margin=dict(l=50, r=50, t=60, b=50),
                    clickmode='event+select'
                )
                
                event = st.plotly_chart(
                    fig_tower, 
                    use_container_width=True, 
                    on_select="rerun", 
                    selection_mode="points", 
                    key=f"chart_v18_{selected_blk}", 
                    config={'toImageButtonOptions': {'format': 'png', 'height': exp_height, 'width': exp_width, 'scale': exp_scale}}
                )
                
                # --- 🛡️ 兜底方案：手动选择器 ---
                st.markdown("---")
                c_sel1, c_sel2 = st.columns([1, 3])
                
                with c_sel1:
                    st.write("#### 🔎 单元估值查询")
                    st.caption("如果无法点击图表，请在此处手动选择：")
                
                with c_sel2:
                    unit_options = sorted(viz_df['Label'].unique(), key=natural_key)
                    default_idx = 0
                    
                    # 尝试解析图表点击事件
                    click_stack, click_floor = None, None
                    if event and "selection" in event and event["selection"]["points"]:
                        point = event["selection"]["points"][0]
                        if "customdata" in point:
                            click_stack = str(point["customdata"][0])
                            click_floor = int(point["customdata"][1])
                            # 🟢 格式修复：匹配新的 #Floor-Stack 格式
                            click_label = f"#{click_floor:02d}-{click_stack}"
                            if click_label in unit_options:
                                default_idx = unit_options.index(click_label)
                    
                    selected_unit_label = st.selectbox(
                        "选择要估值的单元:", 
                        unit_options, 
                        index=default_idx,
                        key=f"manual_sel_{selected_blk}"
                    )

                # --- 统一执行估值逻辑 ---
                if selected_unit_label:
                    try:
                        # 🟢 格式解析修复：解析 #05-12 这种格式
                        # 逻辑：#(\d+) 匹配楼层，-(.*) 匹配 Stack
                        parts = re.search(r"#(\d+)-(.*)", selected_unit_label)
                        
                        if parts:
                            sel_floor = int(parts.group(1))
                            sel_stack = parts.group(2)
                            
                            st.divider()
                            st.markdown(f"### 💎 AVM 智能估值报告: {selected_blk} {selected_unit_label}")
                            
                            # 运行估值模型
                            area, mkt_psf, value, comps_df = calculate_avm(df, selected_blk, sel_stack, sel_floor)
                            
                            if area:
                                c1, c2, c3 = st.columns(3)
                                c1.metric("📐 单元面积", f"{int(area):,} sqft")
                                c2.metric("📊 市场指导 PSF", f"${int(mkt_psf):,} psf")
                                c3.metric("💰 银行估值 (Est. Value)", f"${value/1e6:.2f}M")
                                
                                st.write("##### 📜 该单元历史交易")
                                history = df[(df['BLK'] == selected_blk) & (df['Stack'] == sel_stack) & (df['Floor_Num'] == sel_floor)].copy()
                                if not history.empty:
                                    # 🟢 日期格式修复
                                    history['Sale Date'] = history['Sale Date'].dt.date
                                    st.dataframe(history[['Sale Date', 'Sale Price', 'Sale PSF', 'Area (sqft)']].sort_values('Sale Date', ascending=False), hide_index=True)
                                else:
                                    st.info("该单元历史上暂无交易记录 (New/Stock)")
                                    
                                st.write(f"##### ⚖️ 估值参考依据 (最近 {len(comps_df)} 笔相似交易)")
                                if not comps_df.empty:
                                    st.dataframe(comps_df, use_container_width=True, hide_index=True)
                                else:
                                    st.warning("数据量不足，无法找到相似对标。")
                            else:
                                st.error("无法获取该单元的面积数据，无法估值。")
                    except Exception as e:
                        st.error(f"解析单元数据出错: {e}")

            else:
                st.warning(f"Block {selected_blk} 没有有效的楼层数据。")
    else:
        st.warning("CSV 缺少 BLK 列，无法显示楼宇透视")
