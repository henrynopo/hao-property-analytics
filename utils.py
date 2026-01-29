# app.py
import streamlit as st
# 🟢 确保这里的导入包含了 utils.py 中定义的所有函数
from utils import PROJECTS, load_data, auto_categorize, estimate_inventory, natural_key, mark_penthouse
import tab1_market
import tab2_tower
import tab3_avm
import tab4_history

# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("1. 项目切换")
    selected_project = st.selectbox("选择要分析的项目", list(PROJECTS.keys()))
    sheet_url = PROJECTS[selected_project]
    uploaded_file = None
    project_name = selected_project

    if selected_project == "📂 手动上传 CSV":
        uploaded_file = st.file_uploader("拖入 CSV 文件", type=['csv'])
        if uploaded_file: project_name = uploaded_file.name.replace(".csv", "")
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
        cat_ops = ["按户型面积段 (自动分箱)", "按楼座 (Block)"]
        # 🟢 修复重复选项：只添加一次卧室选项
        for c in ['Bedroom Type', 'Bedrooms', 'Type']:
            if c in df.columns: 
                cat_ops.insert(0, "按卧室数量 (Bedroom Type)")
                break
        
        category_method = st.selectbox("分类依据", cat_ops, index=0)
        inventory_mode = st.radio("库存计算模式", ["🤖 自动推定 (V11智能版)", "🖐 手动输入"], index=0)
        inventory_container = st.container()

    st.markdown("---")
    st.header("3. 导出设置")
    chart_font_size = st.number_input("图表字号", value=16, min_value=10)
    chart_color = st.color_picker("主色调", "#F63366")

# ==================== 主界面 ====================
if df is not None:
    df['Category'] = auto_categorize(df, category_method)
    # 🟢 关键修复：先生成 Is_Special 列，防止后续库存计算报错
    df['Is_Special'] = mark_penthouse(df)

    inventory_map = {}
    unique_cats = sorted(df['Category'].unique(), key=natural_key)
    
    # 🟢 修复 UI：恢复库存输入框
    with inventory_container:
        cols = st.columns(2)
        for i, cat in enumerate(unique_cats):
            with cols[i % 2]:
                val = st.number_input(f"[{cat}]", value=100, min_value=1, key=f"inv_{i}")
                inventory_map[cat] = val

    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    t1, t2, t3, t4 = st.tabs(["📊 市场概览", "🏢 楼宇透视", "💎 单元估值", "📝 成交记录"])
    
    with t1: tab1_market.render(df, chart_color, chart_font_size, inventory_map)
    with t2: tab2_tower.render(df, chart_font_size)
    with t3: tab3_avm.render(df, project_name, chart_font_size)
    with t4: tab4_history.render(df)

else:
    st.info("👈 请在左侧选择项目或上传 CSV 文件。")
