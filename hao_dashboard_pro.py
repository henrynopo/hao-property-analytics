# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar

# --- 1. 页面基础配置 ---
st.set_page_config(page_title="HAO数据罗盘 V3", layout="wide", page_icon="🧭")

# --- 2. 侧边栏：超级控制台 ---
with st.sidebar:
    st.header("1. 数据源与项目")
    
    # 数据源选择
    data_source = st.radio("数据来源", ["📂 手动上传 CSV", "☁️ 自动读取 Google Sheets"], label_visibility="collapsed")
    
    uploaded_file = None
    if data_source == "📂 手动上传 CSV":
        uploaded_file = st.file_uploader("拖入交易记录 CSV", type=['csv'])
        project_name_default = uploaded_file.name.replace(".csv", "") if uploaded_file else ""
    else:
        sheet_url = st.text_input("Google Sheets CSV 链接")
        project_name_default = "未命名项目"

    # 项目名称 (允许修改)
    project_name = st.text_input("项目名称", value=project_name_default)

    st.markdown("---")
    st.header("2. 统计逻辑设定")

    # 分类逻辑
    category_method = st.selectbox(
        "户型分类依据",
        ["按户型面积段 (自动分箱)", "按楼座 (Block)", "按卧室类型 (如果数据有)"]
    )
    
    # [新功能] 库存计算模式
    inventory_mode = st.radio("库存计算模式", ["🤖 自动推定 (基于Stack最高楼层)", "🖐 手动输入"], index=0)
    
    inventory_container = st.container() # 占位符

    st.markdown("---")
    st.header("3. 导出/显示设置 (解决问题 4, 6, 7)")
    
    # 字体与颜色
    chart_font_size = st.number_input("图表字号 (Font Size)", value=16, min_value=10, max_value=50)
    chart_color = st.color_picker("主色调", "#F63366")
    
    # 图片尺寸控制 (WYSIWYG)
    st.subheader("🖼️ 图片下载尺寸")
    exp_width = st.number_input("图片宽度 (px)", value=1200, step=100)
    exp_height = st.number_input("图片高度 (px)", value=675, step=100) # 默认 16:9
    exp_scale = st.slider("清晰度倍数 (Scale)", 1, 5, 2, help="2x 代表 2倍高清，适合打印")

# --- 3. 核心功能函数 ---

@st.cache_data(ttl=600)
def load_data(file_or_url):
    try:
        # 智能 Header 识别 (保留之前的逻辑)
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

        # 清洗列名
        df.columns = df.columns.str.strip()
        
        # 清洗数值和日期
        for col in ['Sale Price', 'Sale PSF', 'Area (sqft)']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'[$,]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if 'Sale Date' in df.columns:
            df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
            df['Sale Year'] = df['Sale Date'].dt.year

        # 清洗 BLK 和 Stack (确保是字符串，方便分组)
        if 'BLK' in df.columns: df['BLK'] = df['BLK'].astype(str).str.strip()
        if 'Stack' in df.columns: df['Stack'] = df['Stack'].astype(str).str.strip()

        return df
    except Exception as e:
        return None

def auto_categorize(df, method):
    """智能分类引擎"""
    if method == "按楼座 (Block)":
        return df['BLK']
    elif method == "按卧室类型 (如果数据有)":
        possible_cols = [c for c in df.columns if 'Bedroom' in c or 'Type' in c]
        return df[possible_cols[0]].astype(str) if possible_cols else pd.Series(["未知"] * len(df))
    else: 
        # 按面积段
        def size_bin(area):
            if area < 800: return "Small (<800sf)"
            if area < 1200: return "Medium (800-1.2k)"
            if area < 1600: return "Large (1.2k-1.6k)"
            if area < 2500: return "X-Large (1.6k-2.5k)"
            return "Giant (>2.5k)"
        return df['Area (sqft)'].apply(size_bin)

# [新功能] 库存 AI 推定逻辑 (解决问题 1)
def estimate_inventory(df, category_col='Category'):
    # 逻辑：同一个 BLK + Stack，认为是一个垂直的单元列。
    # 该 Stack 的库存量 ≈ 该 Stack 出现过的最大楼层数 (Max Floor)。
    # 这是一个估算，假设没有地下室，且顶层就是总层数。
    
    # 必须要有 Floor 列
    if 'Floor' not in df.columns:
        return df['Category'].value_counts() # 如果没有楼层，只能瞎猜，返回成交量(不准确)

    # 清洗楼层，转为数字
    df['Floor_Num'] = pd.to_numeric(df['Floor'], errors='coerce').fillna(1)
    
    # 核心算法：按分类 -> Block -> Stack 分组，找最大楼层
    # 假设：如果某 Stack 卖过最高 25 楼，那这个 Stack 至少有 25 户
    # 修正：有些项目 1 楼没有，或者有些楼层跳过 (如 4, 13, 14)。
    # 更保守算法：计算 unique 的 (Block, Stack, Floor) 组合，但这只是"卖过的"。
    # "推定算法"：Sum(Max Floor for each unique Stack)
    
    if 'Stack' in df.columns:
        # 分组：先按分类，再按 Block，再按 Stack
        stack_stats = df.groupby([category_col, 'BLK', 'Stack'])['Floor_Num'].max().reset_index()
        # 汇总：每个分类下的所有 Stack 的最大楼层之和
        estimated_inv = stack_stats.groupby(category_col)['Floor_Num'].sum().to_dict()
    else:
        # 如果没有 Stack 列，退化为按 Block 估算 (假设每个 Block 每层平均 4-8 户? 很难估)
        # 这种情况下，建议回退到手动输入
        estimated_inv = {} 
        
    return estimated_inv

# --- 4. 主程序逻辑 ---

df = None
if uploaded_file:
    df = load_data(uploaded_file)
elif data_source == "☁️ 自动读取 Google Sheets" and 'sheet_url' in locals() and sheet_url:
    df = load_data(sheet_url)

if df is not None:
    # 4.1 应用分类
    df['Category'] = auto_categorize(df, category_method)
    unique_cats = sorted(df['Category'].unique())
    inventory_map = {}

    # 4.2 库存配置 (自动 vs 手动)
    with inventory_container:
        if inventory_mode == "🤖 自动推定 (基于Stack最高楼层)" and 'Stack' in df.columns and 'Floor' in df.columns:
            st.success("已启动 AI 推定：(库存 = 各 Stack 最高成交楼层之和)")
            estimated_inv = estimate_inventory(df, 'Category')
            
            # 显示推定结果并允许微调
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                est_val = int(estimated_inv.get(cat, 100))
                # 允许用户在推定的基础上修改
                with cols[i % 2]:
                    val = st.number_input(f"[{cat}] 库存 (AI推定)", value=est_val, min_value=1, key=f"inv_{i}")
                    inventory_map[cat] = val
        else:
            if inventory_mode == "🤖 自动推定..." and 'Stack' not in df.columns:
                st.warning("数据缺少 'Stack' 或 'Floor' 列，无法自动推定，请手动输入。")
            st.info("请手动输入各户型总户数：")
            cols = st.columns(2)
            for i, cat in enumerate(unique_cats):
                with cols[i % 2]:
                    val = st.number_input(f"[{cat}] 总户数", value=100, min_value=1, key=f"inv_{i}")
                    inventory_map[cat] = val

    total_project_inventory = sum(inventory_map.values())

    # --- 5. 仪表盘展示区 ---
    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    # 5.1 关键指标 (YTD) - 解决问题 2
    current_year = datetime.now().year 
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
        
    turnover_ytd = (len(df_this_year) / total_project_inventory * 100)
    col4.metric(f"{current_year} 整体换手率", f"{turnover_ytd:.2f}%")

    st.divider()

    # 5.2 超级趋势图 (解决问题 2, 3, 4, 5)
    st.subheader("📈 价格与成交量趋势")
    
    col_ctrl1, col_ctrl2 = st.columns([1, 3])
    with col_ctrl1:
        freq_map = {"年 (Year)": "Y", "季度 (Quarter)": "Q", "月 (Month)": "M"}
        freq_sel = st.selectbox("时间粒度", list(freq_map.keys()))
        freq_code = freq_map[freq_sel]
        
        # 解决问题 5: 智能时间范围 (锁定首尾)
        min_date = df['Sale Date'].min().date().replace(day=1) # 锁定1号
        # 锁定当月最后一天
        max_date_raw = df['Sale Date'].max().date()
        last_day = calendar.monthrange(max_date_raw.year, max_date_raw.month)[1]
        max_date = max_date_raw.replace(day=last_day)
        
        date_range = st.date_input("选择时间范围", [min_date, max_date])

    # 数据过滤与处理
    if len(date_range) == 2:
        # 强制将选中的结束日期延展到当天的最后一刻，确保包含当天数据
        start_d = pd.to_datetime(date_range[0])
        end_d = pd.to_datetime(date_range[1]) + timedelta(days=1) - timedelta(seconds=1)
        mask = (df['Sale Date'] >= start_d) & (df['Sale Date'] <= end_d)
        df_filtered = df.loc[mask]
    else:
        df_filtered = df

    # 重采样
    trend_data = df_filtered.set_index('Sale Date').groupby('Category').resample(freq_code).agg({
        'Sale PSF': 'mean',
        'Sale Price': 'count'
    }).rename(columns={'Sale Price': 'Volume'}).reset_index()

    # 绘图逻辑
    fig = px.line(
        trend_data, 
        x='Sale Date', 
        y='Sale PSF', 
        color='Category', 
        markers=True,
        symbol='Category', # 解决问题 3: 不同的 Symbol
        title=f"{project_name} 尺价走势 ({freq_sel})",
        color_discrete_sequence=[chart_color, "#2E86C1", "#28B463", "#D35400", "#8E44AD"]
    )
    
    # 解决问题 2: 自动连接断点
    fig.update_traces(connectgaps=True)

    # 解决问题 4, 6, 7: 定制化 Layout 和 下载配置
    fig.update_layout(
        font=dict(size=chart_font_size, family="Arial"), # 全局字体
        title=dict(font=dict(size=chart_font_size + 4)), # 标题稍大
        legend=dict(
            orientation="h", 
            yanchor="bottom", y=1.02, 
            xanchor="right", x=1, 
            title=None,
            font=dict(size=chart_font_size) # Legend 字体
        ),
        hovermode="x unified",
        xaxis=dict(title_font=dict(size=chart_font_size), tickfont=dict(size=chart_font_size)),
        yaxis=dict(title_font=dict(size=chart_font_size), tickfont=dict(size=chart_font_size))
    )
    
    # 强力下载配置 (ModeBar)
    st.plotly_chart(
        fig, 
        use_container_width=True,
        config={
            'displayModeBar': True,
            'toImageButtonOptions': {
                'format': 'png', # one of png, svg, jpeg, webp
                'filename': f'{project_name}_trend_chart',
                'height': exp_height, # 使用侧边栏设置的高度
                'width': exp_width,   # 使用侧边栏设置的宽度
                'scale': exp_scale    # 使用侧边栏设置的倍数
            },
            'displaylogo': False
        }
    )
    st.caption(f"💡 提示：点击图表右上角的相机图标 📷，即可按照宽 {exp_width}px / 高 {exp_height}px 下载高清图片。")

    st.divider()

    # 5.3 楼栋/单元热力图 (保留之前的逻辑)
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
    st.info("👈 请在左侧上传 CSV 文件开始分析。")