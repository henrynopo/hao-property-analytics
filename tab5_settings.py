import streamlit as st
import utils_address  # 确保您已经创建了 utils_address.py

def render():
    st.header("⚙️ 系统设定 (System Settings)")
    
    st.markdown("---")
    
    st.subheader("📍 地址库管理 (Project Address Registry)")
    st.caption("""
    在此维护各公寓项目的标准地址格式。
    当您上传 CSV 时，系统会根据 **CSV文件名** 在此查找对应的街道和邮编，
    用于生成 Tab 3 (AVM) 的 PDF 报告。
    """)
    
    # 1. 获取当前数据
    current_df = utils_address.get_address_df()
    
    # 2. 显示编辑器
    edited_df = st.data_editor(
        current_df,
        num_rows="dynamic",
        column_config={
            "Project Name": st.column_config.TextColumn(
                "Project Name (CSV文件名)", 
                help="必须与上传的CSV文件名完全一致 (不含 .csv 后缀)",
                required=True
            ),
            "Street Name": st.column_config.TextColumn(
                "Street Name", 
                help="例如: Braddell Hill",
                required=True
            ),
            "Postal Prefix": st.column_config.TextColumn(
                "Postal Prefix", 
                help="邮编前4位，例如 5797。后两位通常由系统自动补XX或留空"
            )
        },
        use_container_width=True,
        hide_index=True,
        key="address_editor_tab5"
    )
    
    # 3. 保存按钮
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 保存配置", type="primary"):
            utils_address.save_from_df(edited_df)
            st.success("配置已保存！")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    # 未来可以在这里添加其他设置，例如:
    # st.subheader("🔑 API Keys")
    # st.subheader("🎨 报告配色")
