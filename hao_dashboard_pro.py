# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar

# ==========================================
# 🔧 安全配置中心 (从 Secrets 读取)
# ==========================================
try:
    # 尝试从 Streamlit Secrets 读取项目列表
    # dict() 将其转换为标准字典，方便后续操作
    project_config = dict(st.secrets["projects"])
    
    # 将"手动上传"添加到选项的最前面
    PROJECTS = {"📂 手动上传 CSV": None}
    PROJECTS.update(project_config)
    
except FileNotFoundError:
    # 如果没找到 secrets (比如刚下载还没配置时)，只保留手动上传
    st.warning("⚠️ 未检测到云端配置文件 (Secrets)。仅支持手动上传模式。")
    PROJECTS = {"📂 手动上传 CSV": None}
except Exception as e:
    st.error(f"配置文件读取错误: {e}")
    PROJECTS = {"📂 手动上传 CSV": None}

# --- 1. 页面基础配置 ---
st.set_page_config(page_title="HAO数据中台 Pro", layout="wide", page_icon="🧭")

# --- 2. 侧边栏：项目控制台 ---
with st.sidebar:
    st.header("1. 项目切换")
    
    # 项目选择器
    selected_project = st.selectbox("选择要分析的项目", list(PROJECTS.keys()))
    
    sheet_url = PROJECTS[selected_project]
    uploaded_file = None
    project_name = selected_project

    # 如果选了手动上传
    if selected_project == "📂 手动上传 CSV":
        uploaded_file = st.file_uploader("拖入交易记录 CSV", type=['csv'])
        if uploaded_file:
            project_name = uploaded_file.name.replace(".csv", "")
    else:
        st.success(f"已连接云端数据源: {selected_project}")

    st.markdown("---")
    st.header("2. 统计逻辑设定")

    # 分类逻辑
    category_method = st.selectbox(
        "户型分类依据",
        ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室类型 (如果数据有)"]
    )
    
    # 库存计算模式
    inventory_mode = st.radio("库存计算模式", ["🤖 自动推定 (基于Stack最高楼层)", "🖐 手动输入"], index=0)
    inventory_container = st.container() # 占位符

    st.markdown("---")
    st.header("3. 导出/显示设置")
    
    # 字体与颜色
    chart_font_size = st.number_input("图表字号 (Font Size)", value=16, min_value=10, max_value=50)
    chart_color = st.color_picker("主色调", "#F63366")
    
    # 图片尺寸控制
    st.subheader("🖼️ 图片下载尺寸")
    exp_width = st.number_input("图片宽度 (px)", value=1200, step=100)
    exp_height = st.number_input("图片高度 (px)", value=675, step=100)
    exp_scale = st.slider("清晰度倍数 (Scale)", 1, 5, 2)

# --- 3. 核心功能函数 ---

@st.cache_data(ttl=300) # 5分钟缓存，确保数据较新
def load_data(file_or_url):
    try:
        # 处理手动上传的文件指针
        if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
        
        # 智能 Header 识别 (跳过 Disclaimer)
        try:
            # 先读前20行找关键字
            df_temp = pd.read_csv(file_or_url, header=None, nrows=20)
            header_row = -1
            for i, row in df_temp.iterrows():
                row_str = row.astype(str).str.cat(sep=',')
                if "Sale Date" in row_str or "BLK" in row_str:
                    header_row = i
                    break
            
            # 重置指针并读取
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url, header=header_row if header_row != -1 else 0)
        except:
            # 如果上面失败，尝试直接读取
            if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
            df = pd.read_csv(file_or_url)

        # 基础清洗
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

        return df
    except Exception as e:
        st.error(f"数据读取错误: {e}")
        return None

def auto_categorize(df, method):
    if method == "按楼座 (Block)": return df['BLK']
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

def estimate_inventory(df, category_col='Category'):
    """
    V2 升级版库存推定算法：基于同楼栋最大历史成交密度
    解决 Maisonette 跳层编号导致的库存高估问题
    """
    # 1. 基础检查
    if 'BLK' not in df.columns:
        return {}
    
    # 确保 Stack 存在，如果没有 Stack 列，尝试从 Unit_ID 或其他方式无法推定，只能退回手动
    if 'Stack' not in df.columns:
        return {}

    # 2. 计算每个 Stack 的"历史可见容量" (Observed Capacity)
    # 逻辑：统计每个 Block-Stack 组合下，有多少个唯一的单位被交易过
    # 注意：这里用 Unit_ID (BLK-Stack-Floor) 去重，或者直接根据 Floor 去重
    if 'Floor' in df.columns:
        # 统计每个 stack 卖过多少个不同的楼层
        stack_counts = df.groupby([category_col, 'BLK', 'Stack'])['Floor'].nunique().reset_index(name='Observed_Count')
    else:
        # 如果没有 Floor 列，按行数估算（不太准，但比没有好）
        stack_counts = df.groupby([category_col, 'BLK', 'Stack']).size().reset_index(name='Observed_Count')

    # 3. 寻找每栋楼的"标准容量" (Block Capacity)
    # 假设：同一栋楼里，所有 Stack 的高度应该是一样的。
    # 我们取该栋楼里所有 Stack 中，Observed_Count 最大的那个值，作为该楼的标准层数。
    # (这能有效解决某些 Stack 交易少导致被低估的问题)
    block_max_density = stack_counts.groupby([category_col, 'BLK'])['Observed_Count'].max().reset_index(name='Max_Stack_Capacity')

    # 4. 统计每栋楼有多少个 Stack
    # 逻辑：看历史上该 Block 出现过多少个不同的 Stack 编号
    block_stack_counts = stack_counts.groupby([category_col, 'BLK'])['Stack'].nunique().reset_index(name='Num_Stacks')

    # 5. 合并计算
    block_estimates = pd.merge(block_max_density, block_stack_counts, on=[category_col, 'BLK'])
    
    # 单栋楼库存 = Stack数量 * 标准Stack容量
    block_estimates['Est_Block_Inv'] = block_estimates['Num_Stacks'] * block_estimates['Max_Stack_Capacity']
    
    # 6. 按户型分类汇总
    final_estimates = block_estimates.groupby(category_col)['Est_Block_Inv'].sum().to_dict()
    
    return final_estimates

# --- 4. 主程序逻辑 ---

df = None

# 加载逻辑
if selected_project == "📂 手动上传 CSV":
    if uploaded_file:
        df = load_data(uploaded_file)
elif sheet_url:
    df = load_data(sheet_url)

if df is not None:
    # 4.1 分类与库存
    df['Category'] = auto_categorize(df, category_method)
    unique_cats = sorted(df['Category'].unique())
    inventory_map = {}

    with inventory_container:
        if inventory_mode == "🤖 自动推定 (基于Stack最高楼层)" and 'Stack' in df.columns and 'Floor' in df.columns:
            st.success("AI 库存推定已激活")
            estimated_inv = estimate_inventory(df, 'Category')
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                est_val = int(estimated_inv.get(cat, 100))
                with cols[i % 2]:
                    # 允许在推定基础上修改
                    val = st.number_input(f"[{cat}] 库存", value=est_val, min_value=1, key=f"inv_{i}")
                    inventory_map[cat] = val
        else:
            st.info("请输入各户型总户数：")
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                with cols[i % 2]:
                    val = st.number_input(f"[{cat}] 总户数", value=100, min_value=1, key=f"inv_{i}")
                    inventory_map[cat] = val

    total_project_inventory = sum(inventory_map.values())

    # --- 5. 仪表盘展示 ---
    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    # 5.1 KPI (YTD)
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

    # 5.2 趋势图 (Trend Chart)
    st.subheader("📈 价格与成交量趋势")
    
    col_ctrl1, col_ctrl2 = st.columns([1, 3])
    with col_ctrl1:
        freq_map = {"年 (Year)": "Y", "季度 (Quarter)": "Q", "月 (Month)": "M"}
        freq_sel = st.selectbox("时间粒度", list(freq_map.keys()))
        freq_code = freq_map[freq_sel]
        
        # 智能时间范围 (锁定首尾)
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

    # Plotly 绘图
    fig = px.line(
        trend_data, x='Sale Date', y='Sale PSF', color='Category', 
        markers=True, symbol='Category',
        title=f"{project_name} 尺价走势 ({freq_sel})",
        color_discrete_sequence=[chart_color, "#2E86C1", "#28B463", "#D35400", "#8E44AD"]
    )
    
    fig.update_traces(connectgaps=True) # 自动连接断点
    fig.update_layout(
        font=dict(size=chart_font_size, family="Arial"),
        title=dict(font=dict(size=chart_font_size + 4)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None),
        hovermode="x unified"
    )
    
    # 强力下载配置
    st.plotly_chart(
        fig, use_container_width=True,
        config={
            'displayModeBar': True,
            'toImageButtonOptions': {
                'format': 'png', 'filename': f'{project_name}_chart',
                'height': exp_height, 'width': exp_width, 'scale': exp_scale
            },
            'displaylogo': False
        }
    )

    st.divider()

    # 5.3 楼栋/单元热力图
    st.subheader("🏢 楼栋与单元热度")
    analysis_dim = st.radio("分析维度", ["按楼栋 (Block)", "按具体单元 (Stack)"], horizontal=True, label_visibility="collapsed")
    
    if analysis_dim == "按楼栋 (Block)":
        block_stats = df.groupby('BLK').agg({'Sale Price': 'count','Sale PSF': 'mean'}).reset_index().rename(columns={'Sale Price': 'Volume'})
        fig_blk = px.bar(block_stats, x='BLK', y='Volume', color='Sale PSF', title="各楼栋历史成交量", color_continuous_scale="Blues")
        fig_blk.update_layout(font=dict(size=chart_font_size))
        st.plotly_chart(fig_blk, use_container_width=True, config={'toImageButtonOptions': {'height': exp_height, 'width': exp_width, 'scale': exp_scale}})
    else:
        if 'Stack' in df.columns:
            stack_stats = df.groupby(['BLK', 'Stack']).size().reset_index(name='Volume')
            stack_stats['Label'] = stack_stats['BLK'].astype(str) + "-" + stack_stats['Stack'].astype(str)
            fig_stack = px.treemap(stack_stats, path=['BLK', 'Stack'], values='Volume', title="单元热力图", color='Volume', color_continuous_scale="Reds")
            fig_stack.update_layout(font=dict(size=chart_font_size))
            st.plotly_chart(fig_stack, use_container_width=True, config={'toImageButtonOptions': {'height': exp_height, 'width': exp_width, 'scale': exp_scale}})
        else:
            st.warning("CSV 文件中找不到 'Stack' 列。")

else:
    st.info("👈 请在左侧选择项目或上传 CSV 文件。")