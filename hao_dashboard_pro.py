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
        # 在这里填入您的 Google Drive 直链 (https://drive.google.com/uc?id=...)
        # "🏢 Braddell View": "...", 
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
            # 智能跳过 Disclaimer
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
        # 清洗数值
        for col in ['Sale Price', 'Sale PSF', 'Area (sqft)']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'[$,]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 清洗日期
        if 'Sale Date' in df.columns:
            df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
            df['Sale Year'] = df['Sale Date'].dt.year

        # 清洗字符串
        if 'BLK' in df.columns: df['BLK'] = df['BLK'].astype(str).str.strip()
        if 'Stack' in df.columns: df['Stack'] = df['Stack'].astype(str).str.strip()
        if 'Floor' in df.columns: df['Floor_Num'] = pd.to_numeric(df['Floor'], errors='coerce')

        return df
    except Exception as e:
        st.error(f"数据读取错误: {e}")
        return None

def auto_categorize(df, method):
    """智能户型分类 (V8: 优先 Bedroom Type)"""
    # 1. 优先处理卧室类型
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

    # 2. 按楼座
    elif method == "按楼座 (Block)": 
        return df['BLK']

    # 3. 按面积
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
    """
    V10 智能库存算法 (Stack-Centric / 去重版)
    核心逻辑：
    1. 以 "Stack" 为物理实体计算库存 (物理上房子只有这么多)。
    2. 判定每个 Stack 的"主营户型" (Dominant Category)。
    3. 将 Stack 的库存仅归入其主营户型，彻底杜绝双重统计。
    """
    if 'BLK' not in df.columns or 'Floor_Num' not in df.columns:
        return {}
    
    # 如果没有 Stack 列，回退到旧逻辑（无法精确去重）
    if 'Stack' not in df.columns:
        return _estimate_inventory_legacy(df, category_col)

    df = df.dropna(subset=['Floor_Num']).copy()
    
    # --- 第一步：计算每栋楼的"物理高度" (Block Height) ---
    # 我们假设同一栋楼的所有 Stack 高度应该一致 (取该楼出现过的最高层)
    # 这一步是为了给那些交易很少的 Stack 补全层数
    block_max_floors = df.groupby('BLK')['Floor_Num'].max().to_dict()
    
    # --- 第二步：遍历每个物理 Stack，计算库存并分配归属 ---
    # 数据结构: {(BLK, Stack): {'Inventory': 25, 'Category': '3BR'}}
    stack_inventory_map = {}
    
    # 获取所有唯一的 Stack
    # 我们需要一个临时表来辅助
    unique_stacks = df[['BLK', 'Stack']].drop_duplicates()
    
    for _, row in unique_stacks.iterrows():
        blk = row['BLK']
        stack = row['Stack']
        
        # 1. 计算这个 Stack 的物理库存
        # 逻辑：取"本Stack最高层" 和 "本楼最高层" 的较大值 (保守补全)
        # 如果本楼最高层是 25，哪怕本 Stack 只卖过 5 楼，也认为它有 25 户
        
        # 获取该 Stack 的实际数据
        stack_df = df[(df['BLK'] == blk) & (df['Stack'] == stack)]
        
        # 本 Stack 实际最高
        if not stack_df.empty:
            stack_max = stack_df['Floor_Num'].max()
        else:
            stack_max = 0
            
        # 本楼最高 (Benchmark)
        blk_benchmark = block_max_floors.get(blk, 0)
        
        # 最终推算层数 (取大值，确保不漏算)
        # 注意：对于复式楼(Maisonette)，这种 max 逻辑可能偏大(比如只有2,4,6层)，
        # 但鉴于之前的 Tower View 修复，我们可以更精细，但为了总数对齐，先用 Max 统一逻辑
        # 更精准做法：计算该 Block 的 "Unique Floors Count"
        
        # --- 修正：针对复式楼的精准计数 ---
        # 不用 Max，而是用"该楼栋出现过的所有楼层集合"的大小
        blk_floors_set = set(df[df['BLK'] == blk]['Floor_Num'].unique())
        final_count = len(blk_floors_set)
        
        # 2. 判定该 Stack 的归属分类 (Dominant Category)
        # 统计该 Stack 历史上卖得最多的分类是什么
        if not stack_df.empty:
            top_cat = stack_df[category_col].mode()
            if not top_cat.empty:
                dominant_cat = top_cat[0]
            else:
                dominant_cat = "Unknown"
        else:
            dominant_cat = "Unknown"
            
        stack_inventory_map[(blk, stack)] = {
            'count': final_count,
            'category': dominant_cat
        }

    # --- 第三步：按分类汇总 ---
    category_totals = {}
    
    # 先把所有分类的坑填上 0
    for cat in df[category_col].unique():
        category_totals[cat] = 0
        
    for info in stack_inventory_map.values():
        cat = info['category']
        count = info['count']
        
        if cat in category_totals:
            category_totals[cat] += count
        else:
            # 处理可能的 Unknown 或新分类
            category_totals[cat] = category_totals.get(cat, 0) + count
            
    # 调试信息
    st.session_state['block_inv_debug'] = {f"{k[0]}-{k[1]}": v['count'] for k, v in stack_inventory_map.items()}
    
    return category_totals

def _estimate_inventory_legacy(df, category_col):
    """旧版逻辑：仅当没有 Stack 列时使用 (由 V7 简化而来)"""
    inv_map = {}
    for cat in df[category_col].unique():
        count = len(df[df[category_col] == cat]) # 极其粗略，仅作兜底
        inv_map[cat] = count
    return inv_map

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

    # === 初始化 df (关键修复 NameError 的地方) ===
    df = None
    if selected_project == "📂 手动上传 CSV":
        if uploaded_file: df = load_data(uploaded_file)
    elif sheet_url:
        df = load_data(sheet_url)

    # === 智能默认分类 ===
    default_cat_idx = 0
    if df is not None:
        possible_cols = ['Bedroom Type', 'Bedrooms', 'Type', 'Bedroom_Type']
        if any(c in df.columns for c in possible_cols) or any('Bedroom' in c for c in df.columns):
            default_cat_idx = 0 # 优先选卧室
            cat_options = ["按卧室数量 (Bedroom Type)", "按楼座 (Block)", "按户型面积段 (自动分箱)"]
        else:
            default_cat_idx = 0 # 优先选面积
            cat_options = ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室数量 (Bedroom Type)"]
    else:
        cat_options = ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室数量 (Bedroom Type)"]

    category_method = st.selectbox("分类依据", cat_options, index=0)
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

# ==========================================
# 🚀 5. 主逻辑执行
# ==========================================

if df is not None:
    # 4.1 预处理流程
    df['Category'] = auto_categorize(df, category_method)
    df['Is_Special'] = mark_penthouse(df)
    
    unique_cats = sorted(df['Category'].unique())
    inventory_map = {}

    with inventory_container:
        # 库存配置 (修复了 key 不刷新导致数字不更新的 Bug)
        if inventory_mode == "🤖 自动推定 (智能补全)" and 'Stack' in df.columns and 'Floor_Num' in df.columns:
            st.info("已启用 V7 智能库存算法")
            estimated_inv = estimate_inventory(df, 'Category')
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                est_val = int(estimated_inv.get(cat, 100))
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

    # --- 5.3 楼宇透视 (V9: Category Axis & No Gaps) ---
    st.subheader("🏢 楼宇透视 (Tower View)")
    st.caption("视觉指南：🟦 颜色越深=尺价越高 | ⬜ 浅灰=库存死筹")
    
    if 'BLK' in df.columns:
        blk_counts = df['BLK'].value_counts()
        selected_blk = st.selectbox("选择楼栋", blk_counts.index.tolist())
        
        if selected_blk:
            blk_df = df[df['BLK'] == selected_blk].copy()
            cat_this = blk_df['Category'].iloc[0]
            cat_df_all = df[df['Category'] == cat_this]
            
            # 计算库存骨架
            std_units_cat = cat_df_all[~cat_df_all['Is_Special']]
            max_cat_floor = std_units_cat['Floor_Num'].max() if not std_units_cat.empty else 1
            std_units_local = blk_df[~blk_df['Is_Special']]
            local_floors = set(std_units_local['Floor_Num'].unique())
            
            final_floors_set = local_floors.copy()
            if (len(local_floors) > 0) and (max(local_floors) < max_cat_floor - 2):
                 all_cat_floors = set(std_units_cat['Floor_Num'].unique())
                 final_floors_set = all_cat_floors

            # 准备绘图数据
            all_stacks = sorted(blk_df['Stack'].unique()) if 'Stack' in blk_df.columns else ['Unknown']
            floors_to_plot = final_floors_set.copy()
            ph_floors = blk_df[blk_df['Is_Special']]['Floor_Num'].unique()
            for f in ph_floors: floors_to_plot.add(f)
            
            sorted_floors_num = sorted([f for f in list(floors_to_plot) if f > 0])
            
            grid_data = []
            for stack in all_stacks:
                this_stack_ph = blk_df[(blk_df['Stack'] == stack) & (blk_df['Is_Special'])]['Floor_Num'].unique()
                stack_theoretical = final_floors_set.union(set(this_stack_ph))
                
                for floor in sorted_floors_num:
                    if floor in stack_theoretical:
                        match = blk_df[(blk_df['Stack'] == stack) & (blk_df['Floor_Num'] == floor)]
                        if not match.empty:
                            latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                            grid_data.append({
                                'Stack': str(stack), 'Floor': str(int(floor)), 'Floor_Int': int(floor),
                                'Type': 'Sold', 'PSF': int(latest['Sale PSF']),
                                'Price': f"${latest['Sale Price']/1e6:.2f}M", 'Year': latest['Sale Year']
                            })
                        else:
                            grid_data.append({
                                'Stack': str(stack), 'Floor': str(int(floor)), 'Floor_Int': int(floor),
                                'Type': 'Stock', 'PSF': None, 'Price': '-', 'Year': '-'
                            })

            viz_df = pd.DataFrame(grid_data)
            
            if not viz_df.empty:
                fig_tower = go.Figure()
                y_category_order = [str(f) for f in sorted_floors_num]

                # 层1：库存
                fig_tower.add_trace(go.Heatmap(
                    x=viz_df['Stack'], y=viz_df['Floor'], z=[1]*len(viz_df),
                    colorscale=[[0, '#eeeeee'], [1, '#eeeeee']], showscale=False,
                    xgap=2, ygap=2, hoverinfo='skip'
                ))

                # 层2：成交
                sold_df = viz_df[viz_df['Type'] == 'Sold']
                if not sold_df.empty:
                    fig_tower.add_trace(go.Heatmap(
                        x=sold_df['Stack'], y=sold_df['Floor'], z=sold_df['PSF'],
                        colorscale='Teal', colorbar=dict(title="成交尺价 ($psf)", len=0.5, y=0.5),
                        xgap=2, ygap=2,
                        hovertemplate="<b>Stack %{x} - #%{y}</b><br>💰 PSF: $%{z}<br>🏷️ 总价: %{customdata[0]}<br>📅 年份: %{customdata[1]}<extra></extra>",
                        customdata=sold_df[['Price', 'Year']]
                    ))

                fig_tower.update_layout(
                    title=dict(text=f"Block {selected_blk} - 楼宇库存透视", x=0.5),
                    xaxis=dict(title="Stack (单元号)", type='category', side='bottom'),
                    yaxis=dict(title="Floor (楼层)", type='category', categoryorder='array', categoryarray=y_category_order, dtick=1),
                    plot_bgcolor='white',
                    height=max(500, len(y_category_order) * 30),
                    width=min(1000, 100 * len(all_stacks) + 200),
                    margin=dict(l=50, r=50, t=60, b=50)
                )

                st.plotly_chart(fig_tower, use_container_width=True, config={
                    'toImageButtonOptions': {'format': 'png', 'height': exp_height, 'width': exp_width, 'scale': exp_scale}
                })
                
                sold_count = len(sold_df)
                total_count = len(viz_df)
                st.info(f"📊 {selected_blk}栋 看板：推算总户数 {total_count} | 历史成交 {sold_count} | 换手率 {(sold_count/total_count*100):.1f}%")
            else:
                st.warning("数据不足，无法生成透视图")
    else:
        st.warning("CSV 缺少 BLK 列，无法显示楼宇透视")

else:
    st.info("👈 请在左侧选择项目或上传 CSV 文件。")