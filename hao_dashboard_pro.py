# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar

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
        # "🏢 Braddell View": "https://docs.google.com/spreadsheets/d/e/...", 
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

def auto_categorize(df, method):
    """智能户型分类"""
    if method == "按楼座 (Block)": 
        return df['BLK']
    elif method == "按卧室类型 (如果数据有)":
        cols = [c for c in df.columns if 'Bedroom' in c or 'Type' in c]
        return df[cols[0]].astype(str) if cols else pd.Series(["未知"] * len(df))
    else: 
        def size_bin(area):
            if area < 800: return "Small (<800sf)"
            if area < 1200: return "Medium (800-1.2k)"
            if area < 1600: return "Large (1.2k-1.6k)"
            if area < 2500: return "X-Large (1.6k-2.5k)"
            return "Giant (>2.5k)"
        return df['Area (sqft)'].apply(size_bin)

def mark_penthouse(df):
    """全局标记 Penthouse (解决 KeyError 核心)"""
    if 'Area (sqft)' not in df.columns or 'Category' not in df.columns:
        return pd.Series([False] * len(df))
    
    # 计算每个分类的中位数面积
    medians = df.groupby('Category')['Area (sqft)'].median()
    
    def check(row):
        med = medians.get(row['Category'], 0)
        # 超过中位数 1.4 倍视为特殊户型
        return row['Area (sqft)'] > (med * 1.4)
    
    return df.apply(check, axis=1)

def estimate_inventory(df, category_col='Category'):
    """V7 智能库存算法 (Category Fallback Mode)"""
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns:
        return {}

    df = df.dropna(subset=['Floor_Num']).copy()
    
    # 计算每个分类的"基准最高层数"
    cat_benchmark_floors = {}
    for cat in df[category_col].unique():
        cat_df = df[df[category_col] == cat]
        std_df = cat_df[~cat_df['Is_Special']] # 这里直接使用全局计算好的 Is_Special
        max_floor = std_df['Floor_Num'].max() if not std_df.empty else 1
        cat_benchmark_floors[cat] = max_floor

    block_inventory_map = {} 
    category_total_map = {}

    # 逐栋计算
    for cat in df[category_col].unique():
        cat_df = df[df[category_col] == cat]
        cat_total_inv = 0
        benchmark_floor = cat_benchmark_floors.get(cat, 1)
        
        for blk in cat_df['BLK'].unique():
            blk_df = cat_df[cat_df['BLK'] == blk]
            
            num_stacks = blk_df['Stack'].nunique() if 'Stack' in blk_df.columns else 1
            std_units = blk_df[~blk_df['Is_Special']]
            local_max = std_units['Floor_Num'].max() if not std_units.empty else 0
            
            final_floors_count = len(std_units['Floor_Num'].unique()) 
            
            # 智能补全逻辑
            if local_max < (benchmark_floor - 2):
                best_blk_floors = 0
                for b_temp in cat_df['BLK'].unique():
                    f_set = set(cat_df[(cat_df['BLK']==b_temp) & (~cat_df['Is_Special'])]['Floor_Num'].unique())
                    if len(f_set) > best_blk_floors:
                        best_blk_floors = len(f_set)
                final_floors_count = best_blk_floors
            
            base_inv = num_stacks * final_floors_count
            
            ph_inv = 0
            if 'Stack' in blk_df.columns:
                ph_inv = blk_df[blk_df['Is_Special']].groupby(['Stack', 'Floor_Num']).ngroups
            else:
                ph_inv = len(blk_df[blk_df['Is_Special']])
            
            total_blk_inv = int(base_inv + ph_inv)
            block_inventory_map[blk] = total_blk_inv
            cat_total_inv += total_blk_inv

        category_total_map[cat] = int(cat_total_inv)
            
    st.session_state['block_inv_debug'] = block_inventory_map
    return category_total_map

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

    category_method = st.selectbox("分类依据", ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室类型"])
    inventory_mode = st.radio("库存计算模式", ["🤖 自动推定 (智能补全)", "🖐 手动输入"], index=0)
    inventory_container = st.container()

    st.markdown("---")
    st.header("3. 导出设置")
    chart_font_size = st.number_input("图表字号", value=16, min_value=10)
    chart_color = st.color_picker("主色调", "#F63366")
    
    st.caption("📷 图片下载尺寸")
    exp_width = st.number_input("宽度 (px)", value=1200, step=100)
    exp_height = st.number_input("高度 (px)", value=675, step=100)
    exp_scale = st.slider("清晰度", 1, 5, 2)

# --- 数据加载 ---
df = None
if selected_project == "📂 手动上传 CSV":
    if uploaded_file: df = load_data(uploaded_file)
elif sheet_url:
    df = load_data(sheet_url)

if df is not None:
    # 4.1 预处理流程 (关键修复步骤)
    df['Category'] = auto_categorize(df, category_method)
    # --- 修复点：在这里全局计算 Is_Special，后续所有功能都可以直接用 ---
    df['Is_Special'] = mark_penthouse(df)
    
    unique_cats = sorted(df['Category'].unique())
    inventory_map = {}

    with inventory_container:
        if inventory_mode == "🤖 自动推定 (智能补全)" and 'Stack' in df.columns and 'Floor_Num' in df.columns:
            st.info("已启用 V7 智能库存算法 (自动补全冷门楼栋)")
            estimated_inv = estimate_inventory(df, 'Category')
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                est_val = int(estimated_inv.get(cat, 100))
                with cols[i % 2]:
                    # 关键修改：key 中加入 category_method，确保切换分类时强制刷新
                    val = st.number_input(
                        f"[{cat}] 库存", 
                        value=est_val, 
                        min_value=1, 
                        key=f"inv_{category_method}_{i}"  # <--- 改了这里
                    )
                    inventory_map[cat] = val
        else:
            # ... (手动模式同理) ...
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                with cols[i % 2]:
                    val = st.number_input(
                        f"[{cat}]", 
                        value=100, 
                        min_value=1, 
                        key=f"inv_manual_{category_method}_{i}" # <--- 改了这里
                    )
                    inventory_map[cat] = val

    total_project_inventory = sum(inventory_map.values())
    
    # 🕵️‍♀️ 库存审计
    if inventory_mode == "🤖 自动推定 (智能补全)" and 'block_inv_debug' in st.session_state:
        with st.expander(f"🕵️‍♀️ 查看每栋楼的具体推定数据 (Debug) - 总计: {total_project_inventory}户"):
            debug_map = st.session_state['block_inv_debug']
            debug_df = pd.DataFrame(list(debug_map.items()), columns=['Block', 'Est. Inventory'])
            if 'BLK' in df.columns:
                actual_vol = df['BLK'].value_counts().reset_index()
                actual_vol.columns = ['Block', 'Sold Volume']
                audit_df = pd.merge(debug_df, actual_vol, on='Block', how='left').fillna(0)
                audit_df['Sold Volume'] = audit_df['Sold Volume'].astype(int)
                audit_df['Coverage %'] = (audit_df['Sold Volume'] / audit_df['Est. Inventory'] * 100)
                st.dataframe(audit_df.sort_values('Block'), use_container_width=True, 
                             column_config={"Coverage %": st.column_config.ProgressColumn("已售占比", format="%.1f%%", min_value=0, max_value=100)})

    # --- 5. 仪表盘展示 ---
    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    # 5.1 KPI
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

    # 5.2 趋势图
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

    # 5.3 楼宇透视 (Tower View)
    st.subheader("🏢 楼宇透视 (Tower View)")
    st.caption("X轴=Stack(单元), Y轴=Floor(楼层)。灰色=理论存在但未交易(库存), 彩色=历史交易")
    
    if 'BLK' in df.columns:
        blk_counts = df['BLK'].value_counts()
        selected_blk = st.selectbox("选择楼栋", blk_counts.index.tolist())
        
        if selected_blk:
            blk_df = df[df['BLK'] == selected_blk].copy()
            
            # --- 可视化数据准备 ---
            cat_this = blk_df['Category'].iloc[0]
            cat_df_all = df[df['Category'] == cat_this]
            
            # 1. 寻找基准层数
            std_units_cat = cat_df_all[~cat_df_all['Is_Special']]
            max_cat_floor = std_units_cat['Floor_Num'].max() if not std_units_cat.empty else 1
            
            # 2. 本地标准层
            std_units_local = blk_df[~blk_df['Is_Special']]
            local_floors = set(std_units_local['Floor_Num'].unique())
            
            # 3. 智能补全
            final_floors_set = local_floors.copy()
            if (len(local_floors) > 0) and (max(local_floors) < max_cat_floor - 2):
                all_cat_floors = set(std_units_cat['Floor_Num'].unique())
                final_floors_set = all_cat_floors
            
            all_stacks = sorted(blk_df['Stack'].unique()) if 'Stack' in blk_df.columns else ['Unknown']
            
            grid_data = []
            for stack in all_stacks:
                ph_floors = blk_df[(blk_df['Stack'] == stack) & (blk_df['Is_Special'])]['Floor_Num'].unique()
                theoretical_floors = final_floors_set.union(set(ph_floors))
                
                for floor in theoretical_floors:
                    match = blk_df[(blk_df['Stack'] == stack) & (blk_df['Floor_Num'] == floor)]
                    if not match.empty:
                        latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                        grid_data.append({
                            'Stack': stack, 'Floor': floor, 'Status': 'Sold',
                            'PSF': int(latest['Sale PSF']), 'Date': latest['Sale Date'].strftime('%Y-%m')
                        })
                    else:
                        grid_data.append({
                            'Stack': stack, 'Floor': floor, 'Status': 'Stock',
                            'PSF': 0, 'Date': '-'
                        })
            
            viz_df = pd.DataFrame(grid_data)
            
            if not viz_df.empty:
                fig_tower = go.Figure()
                
                # 库存层
                df_stock = viz_df[viz_df['Status'] == 'Stock']
                fig_tower.add_trace(go.Scatter(
                    x=df_stock['Stack'], y=df_stock['Floor'], mode='markers',
                    marker=dict(symbol='square', size=18, color='lightgrey', line=dict(width=1, color='grey')),
                    name='库存 (未售)', hoverinfo='text',
                    text=[f"Stack {s} #{f}<br>库存" for s, f in zip(df_stock['Stack'], df_stock['Floor'])]
                ))
                
                # 交易层
                df_sold = viz_df[viz_df['Status'] == 'Sold']
                fig_tower.add_trace(go.Scatter(
                    x=df_sold['Stack'], y=df_sold['Floor'], mode='markers',
                    marker=dict(
                        symbol='square', size=18, color=df_sold['PSF'], colorscale='RdBu_r',
                        colorbar=dict(title="最新 PSF"), line=dict(width=1, color='black')
                    ),
                    name='已售', hoverinfo='text',
                    text=[f"Stack {s} #{f}<br>${p} psf<br>{d}" for s, f, p, d in zip(df_sold['Stack'], df_sold['Floor'], df_sold['PSF'], df_sold['Date'])]
                ))
                
                fig_tower.update_layout(
                    title=f"Block {selected_blk} 库存透视 (补全后)",
                    xaxis=dict(title="Stack", type='category'),
                    yaxis=dict(title="Floor", dtick=1),
                    height=600, width=800, plot_bgcolor='white'
                )
                st.plotly_chart(fig_tower, use_container_width=True, config={
                    'toImageButtonOptions': {'format': 'png', 'height': exp_height, 'width': exp_width, 'scale': exp_scale}
                })
                
                sold_count = len(df_sold)
                total_count = len(viz_df)
                st.info(f"📊 面板数据：总推算 {total_count} 户 | 历史成交 {sold_count} 户 | 覆盖率 {(sold_count/total_count*100):.1f}%")
            else:
                st.warning("数据不足，无法生成透视图")
    else:
        st.warning("CSV 缺少 BLK 列，无法显示楼宇透视")

else:
    st.info("👈 请在左侧选择项目或上传 CSV 文件。")