# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 页面基础配置 ---
st.set_page_config(page_title="HAO数据罗盘 Pro", layout="wide", page_icon="🧭")

# --- 2. 侧边栏：超级控制台 ---
with st.sidebar:
    st.header("1. 数据源与项目")
    
    # 2.1 数据源
    data_source = st.radio("数据来源", ["📂 手动上传 CSV", "☁️ 自动读取 Google Sheets (示例)"])
    
    # 2.2 项目名称逻辑
    project_name_input = st.text_input("项目名称 (用于标题)", value="")
    
    uploaded_file = None
    if data_source == "📂 手动上传 CSV":
        uploaded_file = st.file_uploader("拖入交易记录 CSV", type=['csv'])
        # 自动获取文件名作为项目名
        if uploaded_file is not None and project_name_input == "":
            default_name = uploaded_file.name.replace(".csv", "")
            st.caption(f"已自动识别文件名: {default_name}")
            # 这里如果不手动赋值，就在主逻辑里用 default_name
    else:
        sheet_url = st.text_input("Google Sheets CSV 链接")

    st.markdown("---")
    st.header("2. 统计维度设定")

    # 2.3 分类逻辑 (解决问题 6)
    # 既然CSV可能没有卧室数，我们提供三种分类方式
    category_method = st.selectbox(
        "选择统计分类方式",
        ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室类型 (如果有列)"]
    )
    
    st.info("👇 请在数据加载后，在下方配置各分类的总库存，以计算准确换手率。")
    
    # 库存配置容器 (稍后填充)
    inventory_container = st.container()

    st.markdown("---")
    st.header("3. 报告导出设置")
    chart_font_size = st.slider("图表字体大小", 10, 30, 16)
    chart_color = st.color_picker("图表主色调", "#F63366")

# --- 3. 核心功能函数 ---

@st.cache_data(ttl=600)
def load_data(file_or_url):
    try:
        # 智能跳过 Disclaimer 逻辑 (保留之前的修复)
        if hasattr(file_or_url, 'seek'): file_or_url.seek(0)
        
        # 先读前几行判断 Header
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

        # 清洗列名
        df.columns = df.columns.str.strip()
        
        # 清洗数值和日期
        if 'Sale Price' in df.columns:
             df['Sale Price'] = df['Sale Price'].astype(str).str.replace(r'[$,]', '', regex=True).astype(float)
        if 'Sale PSF' in df.columns:
             df['Sale PSF'] = df['Sale PSF'].astype(str).str.replace(r'[$,]', '', regex=True).astype(float)
        if 'Area (sqft)' in df.columns:
             df['Area (sqft)'] = df['Area (sqft)'].astype(str).str.replace(r'[,]', '', regex=True).astype(float)
        if 'Sale Date' in df.columns:
            df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
            df['Sale Year'] = df['Sale Date'].dt.year

        return df
    except Exception as e:
        return None

def auto_categorize(df, method):
    """智能分类引擎"""
    if method == "按楼座 (Block)":
        return df['BLK'].astype(str)
    
    elif method == "按卧室类型 (如果有列)":
        # 尝试寻找包含 Bedroom 或 Type 的列
        possible_cols = [c for c in df.columns if 'Bedroom' in c or 'Type' in c]
        if possible_cols:
            return df[possible_cols[0]].astype(str)
        else:
            return pd.Series(["未知"] * len(df))
            
    else: # 默认：按面积段自动分箱 (解决没有卧室数的问题)
        # 逻辑：<800, 800-1200, 1200-1600, >1600
        def size_bin(area):
            if area < 800: return "Small (<800sf)"
            if area < 1200: return "Medium (800-1.2k)"
            if area < 1600: return "Large (1.2k-1.6k)"
            if area < 2500: return "X-Large (1.6k-2.5k)"
            return "Giant (>2.5k)"
        return df['Area (sqft)'].apply(size_bin)

# --- 4. 主程序逻辑 ---

# 加载数据
df = None
if uploaded_file:
    df = load_data(uploaded_file)
    # 确定项目标题
    if project_name_input:
        app_title = project_name_input
    else:
        app_title = uploaded_file.name.replace(".csv", "")

elif data_source == "☁️ 自动读取 Google Sheets (示例)" and 'sheet_url' in locals() and sheet_url:
    df = load_data(sheet_url)
    app_title = project_name_input if project_name_input else "未命名项目"

# 如果数据加载成功
if df is not None:
    # 4.1 应用分类
    df['Category'] = auto_categorize(df, category_method)
    
    # 4.2 动态库存配置 (SideBar)
    # 找出所有分类
    unique_cats = sorted(df['Category'].unique())
    inventory_map = {}
    
    with inventory_container:
        st.caption(f"已识别出 {len(unique_cats)} 种分类。请设置总户数：")
        # 默认给一个大概的数字，避免除以0
        cols = st.columns(2)
        for i, cat in enumerate(unique_cats):
            # 这里的 Key 必须唯一
            with cols[i % 2]:
                val = st.number_input(f"[{cat}] 库存", value=100, min_value=1, key=f"inv_{i}")
                inventory_map[cat] = val
    
    # 计算总库存
    total_project_inventory = sum(inventory_map.values())

    # --- 5. 仪表盘展示区 ---
    
    st.title(f"🏙️ {app_title} 数据透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    # 5.1 关键指标 (KPI) - 解决问题 2 (当前时间)
    current_year = datetime.now().year # 获取真实的 2026
    
    # 逻辑：如果没有 2026 的数据，KPI 显示 0 是正确的，但为了体验，可以显示 "过去12个月"
    # 这里我们严格按照 Henry 要求的 "今年 (YTD)"
    df_this_year = df[df['Sale Year'] == current_year]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"{current_year}年 成交量", f"{len(df_this_year)} 宗")
    
    if len(df_this_year) > 0:
        avg_price = df_this_year['Sale PSF'].mean()
        max_price = df_this_year['Sale Price'].max()
        col2.metric(f"{current_year} 均尺价", f"${avg_price:,.0f} psf")
        col3.metric(f"{current_year} 最高价", f"${max_price/1e6:.2f}M")
    else:
        col2.metric(f"{current_year} 均尺价", "-")
        col3.metric(f"{current_year} 最高价", "-")
        
    # 总体换手率
    turnover_ytd = (len(df_this_year) / total_project_inventory * 100)
    col4.metric(f"{current_year} 整体换手率", f"{turnover_ytd:.2f}%")

    st.divider()

    # 5.2 超级趋势图 (解决问题 3, 4, 5)
    st.subheader("📈 价格与成交量走势 (可定制)")
    
    col_ctrl1, col_ctrl2 = st.columns([1, 3])
    with col_ctrl1:
        # 时间粒度选择
        freq_map = {"年 (Year)": "Y", "季度 (Quarter)": "Q", "月 (Month)": "M"}
        freq_sel = st.selectbox("时间粒度", list(freq_map.keys()))
        freq_code = freq_map[freq_sel]
        
        # 时间范围选择
        min_date = df['Sale Date'].min().date()
        max_date = df['Sale Date'].max().date()
        date_range = st.date_input("选择时间范围", [min_date, max_date])

    # 数据重采样 (Resampling)
    # 过滤时间
    if len(date_range) == 2:
        mask = (df['Sale Date'].dt.date >= date_range[0]) & (df['Sale Date'].dt.date <= date_range[1])
        df_filtered = df.loc[mask]
    else:
        df_filtered = df

    # 按选定粒度聚合
    trend_data = df_filtered.set_index('Sale Date').groupby('Category').resample(freq_code).agg({
        'Sale PSF': 'mean',
        'Sale Price': 'count' # 用 Price 的 count 代表成交量
    }).rename(columns={'Sale Price': 'Volume'}).reset_index()

    # 绘图
    fig = px.line(
        trend_data, 
        x='Sale Date', 
        y='Sale PSF', 
        color='Category', 
        markers=True,
        title=f"{app_title} 尺价走势 ({freq_sel})",
        color_discrete_sequence=[chart_color, "#2E86C1", "#28B463", "#D35400"]
    )
    
    # 解决问题 4 & 5: 定制化 Layout
    fig.update_layout(
        font=dict(size=chart_font_size), # 字体大小可调
        legend=dict(
            orientation="h",  # 水平排列
            yanchor="bottom",
            y=1.02,           # 放在图表顶部
            xanchor="right",
            x=1,
            title=None
        ),
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.info(f"💡 提示：调整左侧侧边栏的“字体大小”，可以改变下载图片的字号。")

    st.divider()

    # 5.3 楼栋/单元分析 (解决问题 7)
    st.subheader("🏢 楼栋与单元热度 (Block vs Stack)")
    
    analysis_dim = st.radio("分析维度", ["按楼栋 (Block)", "按具体单元 (Stack)"], horizontal=True)
    
    if analysis_dim == "按楼栋 (Block)":
        # Block 热度
        block_stats = df.groupby('BLK').agg({
            'Sale Price': 'count',
            'Sale PSF': 'mean'
        }).reset_index().rename(columns={'Sale Price': 'Volume'})
        
        fig_blk = px.bar(
            block_stats, x='BLK', y='Volume', color='Sale PSF',
            title="各楼栋历史成交量 (颜色深浅代表均价)",
            color_continuous_scale="Blues"
        )
        st.plotly_chart(fig_blk, use_container_width=True)
        
    else:
        # Stack 热度 (更细致)
        if 'Stack' in df.columns:
            stack_stats = df.groupby(['BLK', 'Stack']).size().reset_index(name='Volume')
            # 组合 BLK-Stack 作为标签
            stack_stats['Label'] = stack_stats['BLK'].astype(str) + "-" + stack_stats['Stack'].astype(str)
            
            fig_stack = px.treemap(
                stack_stats, path=['BLK', 'Stack'], values='Volume',
                title="单元热力图 (面积越大代表成交越活跃)",
                color='Volume', color_continuous_scale="Reds"
            )
            st.plotly_chart(fig_stack, use_container_width=True)
        else:
            st.warning("CSV 文件中找不到 'Stack' 列，无法进行单元分析。")

else:
    st.info("👈 请在左侧上传 CSV 文件开始分析。")