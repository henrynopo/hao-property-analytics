import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 页面配置：设置为宽屏模式，适合看大图 ---
st.set_page_config(page_title="HAO数据中台", layout="wide", page_icon="🏢")

# --- 侧边栏：控制中心 ---
with st.sidebar:
    st.title("🎛️ 报告控制台")
    
    # 1. 数据源选择 (支持手动上传或自动连接)
    data_source = st.radio("数据来源", ["📂 手动上传 CSV", "☁️ 自动读取 Google Sheets"])
    
    uploaded_file = None
    if data_source == "📂 手动上传 CSV":
        uploaded_file = st.file_uploader("拖入最新的交易记录", type=['csv'])
    else:
        # 这里填入您的 Google Sheet CSV 导出链接
        # 实际使用时，您可以配置 secrets 里的链接
        sheet_url = st.text_input("输入 Google Sheets CSV 链接", 
                                  value="https://docs.google.com/spreadsheets/d/e/YOUR_SHEET_ID/pub?output=csv")
    
    st.markdown("---")
    
    # 2. 库存配置 (关键参数)
    st.header("🏗️ 项目库存设定")
    col1, col2 = st.columns(2)
    with col1:
        inv_high = st.number_input("高层总户数", value=768)
        inv_low = st.number_input("低层总户数", value=72)
    with col2:
        inv_maison = st.number_input("复式总户数", value=60)
        inv_shop = st.number_input("商铺/其他", value=10)
    
    total_inventory_map = {
        "High-Rise": inv_high, "Low-Rise": inv_low, 
        "Maisonette": inv_maison, "Other": inv_shop
    }

    st.markdown("---")
    
    # 3. 报告定制 (用于做 Flyer/PPT)
    st.header("🎨 图表定制 (Export)")
    chart_color = st.color_picker("主色调 (品牌色)", "#F63366")
    chart_template = st.selectbox("图表风格", ["plotly_white", "ggplot2", "seaborn"])
    download_format = st.radio("下载格式", ["高清图片 (PNG)", "交互式网页 (HTML)"])

# --- 数据处理函数 ---
@st.cache_data(ttl=600) # 缓存10分钟，避免频繁读取
# --- 数据处理函数 (智能修复版) ---
@st.cache_data(ttl=600)
def load_data(source_type, file_or_url):
    try:
        # 1. 初步读取
        if source_type == "📂 手动上传 CSV":
            if file_or_url is None: return None
            # 手动上传的文件对象需要重置指针，防止读取空文件
            file_or_url.seek(0)
            df = pd.read_csv(file_or_url)
        else:
            df = pd.read_csv(file_or_url)
            
        # 2. 智能寻找表头 (关键修复步骤!)
        # 如果第一列里没有 'BLK' 也没有 'Sale Date'，说明读到了 Disclaimer
        # 我们往下找 10 行，看看哪一行才是真的表头
        if 'Sale Date' not in df.columns and 'BLK' not in df.columns:
            # 重新读取前20行，不带表头
            if source_type == "📂 手动上传 CSV":
                file_or_url.seek(0)
            
            # 临时读一下，找 Header 行号
            df_temp = pd.read_csv(file_or_url, header=None, nrows=20)
            
            # 遍历寻找包含 "Sale Date" 或 "BLK" 的行
            header_row_index = -1
            for i, row in df_temp.iterrows():
                row_str = row.astype(str).str.cat(sep=',')
                if "Sale Date" in row_str or "BLK" in row_str:
                    header_row_index = i
                    break
            
            # 如果找到了真正的表头行，重新读取
            if header_row_index != -1:
                if source_type == "📂 手动上传 CSV":
                    file_or_url.seek(0)
                df = pd.read_csv(file_or_url, header=header_row_index)
        
        # 3. 再次确认列名 (去除空格，防止 ' Sale Price' 这种错误)
        df.columns = df.columns.str.strip()
        
        # 4. 数据清洗 (保持不变)
        if 'Sale Price' in df.columns:
             df['Sale Price'] = df['Sale Price'].astype(str).str.replace(r'[$,]', '', regex=True)
             df['Sale Price'] = pd.to_numeric(df['Sale Price'], errors='coerce')
             
        if 'Sale PSF' in df.columns:
             df['Sale PSF'] = df['Sale PSF'].astype(str).str.replace(r'[$,]', '', regex=True)
             df['Sale PSF'] = pd.to_numeric(df['Sale PSF'], errors='coerce')
             
        if 'Area (sqft)' in df.columns:
             df['Area (sqft)'] = df['Area (sqft)'].astype(str).str.replace(r'[,]', '', regex=True)
             df['Area (sqft)'] = pd.to_numeric(df['Area (sqft)'], errors='coerce')
             
        if 'Sale Date' in df.columns:
            df['Sale Date'] = pd.to_datetime(df['Sale Date'], errors='coerce')
            df['Sale Year'] = df['Sale Date'].dt.year

        # 5. 最终检查：如果还是没有 Sale Year，那就是文件格式太奇怪了
        if 'Sale Year' not in df.columns:
            st.error("错误：无法在文件中找到 'Sale Date' 列。请检查 CSV 文件格式。")
            return None
            
        return df
        
    except Exception as e:
        st.error(f"数据加载失败: {e}")
        return None

# --- 户型分类逻辑 ---
def classify_unit(row):
    # 简单分类逻辑，您可根据实际调整
    blk = str(row.get('BLK', ''))
    if any(x in blk for x in ['N','P','Q','R']): return "Low-Rise"
    if any(x in blk for x in ['J','K','L','M']): return "Maisonette"
    return "High-Rise"

# --- 主界面 ---

# 加载数据
df = None
if data_source == "📂 手动上传 CSV":
    df = load_data(data_source, uploaded_file)
else:
    # 这里的 URL 需要替换为您真实的 Google Sheet CSV 链接
    if st.sidebar.button("刷新数据 (从云端)"):
        st.cache_data.clear() # 清除缓存，强制刷新
    df = load_data(data_source, st.session_state.get('sheet_url', ''))

if df is not None:
    # 应用分类
    if 'Category' not in df.columns:
        df['Category'] = df.apply(classify_unit, axis=1)

    st.title(f"📊 {df['Sale Year'].max()}年 Braddell View 市场深度分析")
    st.caption(f"数据更新至: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 总交易记录: {len(df)}")

    # === 模块：核心指标卡片 (适合手机看) ===
    cols = st.columns(4)
    latest_year = df['Sale Year'].max()
    latest_df = df[df['Sale Year'] == latest_year]
    
    cols[0].metric("今年成交量", f"{len(latest_df)} 宗")
    cols[1].metric("今年最高价", f"${latest_df['Sale Price'].max()/1e6:.2f}M")
    cols[2].metric("今年均尺价", f"${latest_df['Sale PSF'].mean():.0f} psf")
    cols[3].metric("今年换手率 (High-Rise)", f"{len(latest_df[latest_df['Category']=='High-Rise'])/inv_high*100:.1f}%")

    # === 模块：定制化图表生成器 (用于报告) ===
    st.markdown("### 📈 趋势分析 (可下载用于报告)")
    
    # 数据准备：年度均价
    trend_data = df.groupby(['Sale Year', 'Category'])['Sale PSF'].mean().reset_index()
    
    fig = px.line(trend_data, x='Sale Year', y='Sale PSF', color='Category', 
                  title="三大户型历史尺价走势 (1995-Present)",
                  template=chart_template,
                  color_discrete_sequence=[chart_color, "#00CC96", "#636EFA"]) # 使用自定义颜色
    
    # 针对 Flyer 优化的图表布局
    fig.update_layout(font=dict(size=14), title_font=dict(size=20))
    
    st.plotly_chart(fig, use_container_width=True)

    # === 下载中心 ===
    col_dl1, col_dl2 = st.columns([1, 4])
    with col_dl1:
        # 下载 Excel 数据
        csv = trend_data.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 下载表格数据 (Excel)",
            data=csv,
            file_name='trend_data.csv',
            mime='text/csv',
        )
    with col_dl2:
        st.info("💡 提示：将鼠标移动到图表右上角，点击相机图标 📷 即可直接下载透明背景的高清 PNG 图片用于 Flyer。")

    # === 模块：换手率热力表 (表格模式) ===
    st.markdown("### 🔥 5年周期换手率 (详细数据)")
    
    # 计算逻辑 (复用之前的逻辑)
    df['Period'] = (df['Sale Year'] // 5 * 5).astype(str) + "s" # 2020s, 2025s
    period_stats = df.groupby(['Period', 'Category']).size().reset_index(name='Volume')
    period_stats['Total_Inv'] = period_stats['Category'].map(total_inventory_map)
    period_stats['Turnover %'] = (period_stats['Volume'] / period_stats['Total_Inv'] * 100).round(1)
    
    pivot_table = period_stats.pivot(index='Period', columns='Category', values='Turnover %')
    
    # 使用 Pandas Styler 进行着色 (类似 Excel 条件格式)
    st.dataframe(pivot_table.style.background_gradient(cmap='Reds', axis=None).format("{:.1f}%"), use_container_width=True)

else:
    st.info("👋 欢迎回来，Henry。请在左侧上传数据或连接 Google Sheets 开始工作。")
