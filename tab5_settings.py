import streamlit as st
import utils_address
import time

def render():
    st.header("⚙️ 系统设定 (System Settings)")
    st.markdown("---")
    
    st.subheader("📍 地址库管理 (Address Registry)")
    st.caption("在此维护各项目的标准地址。Tab 3 (AVM) 的 PDF 报告将自动引用此处的配置。")
    
    # 1. 读取数据
    current_df = utils_address.get_address_df()
    
    # 2. 编辑器
    edited_df = st.data_editor(
        current_df,
        num_rows="dynamic",
        column_config={
            "Project Name": st.column_config.TextColumn("Project Name (CSV文件名)", required=True),
            "Street Name": st.column_config.TextColumn("Street Name", required=True),
            "Postal Prefix": st.column_config.TextColumn("Postal Prefix (e.g. 5797)")
        },
        use_container_width=True,
        hide_index=True,
        key="address_editor_tab5"
    )
    
    # 3. 保存
    if st.button("💾 保存配置", type="primary"):
        utils_address.save_from_df(edited_df)
        st.success("配置已保存！")
        time.sleep(1)
        st.rerun()
