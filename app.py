import streamlit as st
from utils import PROJECTS, load_data, auto_categorize, estimate_inventory, natural_key, mark_penthouse

# --- Import Modules ---
import tab1_market
import tab2_tower
import tab3_avm
import tab4_history
import tab5_settings  # [新增] 引入 Tab 5

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
        has_bedroom = False
        for c in ['Bedroom Type', 'Bedrooms', 'Type']:
            if c in df.columns: has_bedroom = True; break
        if has_bedroom: cat_ops.insert(0, "按卧室数量 (Bedroom Type)")
        
        category_method = st.selectbox("分类依据", cat_ops, index=0)
        inventory_mode = st.radio("库存计算模式", ["🤖 自动推定 (V11智能版)", "🖐 手动输入"], index=0)
        inventory_container = st.container()

    st.markdown("---")
    st.header("3. 导出设置")
    chart_font_size = st.number_input("图表字号", value=16, min_value=10)
    chart_color = st.color_picker("主色调", "#F63366")

# ==================== 主界面 ====================
if df is not None:
    # 1. 基础处理
    df['Category'] = auto_categorize(df, category_method)
    df['Is_Special'] = mark_penthouse(df)

    # 2. 库存数据准备
    unique_cats = sorted(df['Category'].unique(), key=natural_key)
    inventory_map = {}
    
    estimated_counts = {}
    if inventory_mode.startswith("🤖") and 'Stack' in df.columns:
        with st.spinner("正在智能推算全盘库存..."):
            estimated_counts = estimate_inventory(df, 'Category')

    # 3. 渲染侧边栏输入框 (数据回填)
    with inventory_container:
        st.write("---") 
        st.caption(f"📊 各分类总库存设定 ({len(unique_cats)} 类)")
        cols = st.columns(2)
        
        for i, cat in enumerate(unique_cats):
            if inventory_mode.startswith("🤖"):
                default_val = int(estimated_counts.get(cat, 100))
                if default_val < 1: default_val = 1
            else:
                default_val = 100 
            
            with cols[i % 2]:
                val = st.number_input(
                    f"[{cat}]", 
                    value=default_val, 
                    min_value=1, 
                    key=f"inv_input_{i}_{category_method}"
                )
                inventory_map[cat] = val

    # 4. 渲染主界面 Tabs
    st.title(f"🏙️ {project_name} 市场透视")
    st.caption(f"数据范围: {df['Sale Date'].min().date()} 至 {df['Sale Date'].max().date()} | 总交易: {len(df)} 宗")

    # [修改] 增加第 5 个 Tab: "⚙️ 设定"
    t1, t2, t3, t4, t5 = st.tabs([
        "📊 市场概览", 
        "🏢 楼宇透视", 
        "💎 单元估值", 
        "📝 成交记录", 
        "⚙️ 设定"
    ])
    
    with t1: tab1_market.render(df, chart_color, chart_font_size, inventory_map)
    with t2: tab2_tower.render(df, chart_font_size)
    with t3: tab3_avm.render(df, project_name, chart_font_size)
    with t4: tab4_history.render(df)
    with t5: tab5_settings.render()  # [新增] 渲染 Tab 5

else:
    st.info("👈 请在左侧选择项目或上传 CSV 文件。")
