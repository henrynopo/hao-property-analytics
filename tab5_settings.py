import streamlit as st
import utils_address
import time

def render():
    st.header("⚙️ 系统设定 (System Settings)")
    
    st.markdown("---")
    
    st.subheader("📍 地址库管理 (Address Registry)")
    st.caption("""
    在此配置 **项目 + 楼座** 维度的详细地址。
    * **Block No**: 输入具体楼号（如 '10A'），或输入 'DEFAULT' 作为该小区的通用默认值。
    * **Post Code**: 输入完整邮编（如 '579720'）。
    """)
    
    # 1. 获取当前数据
    current_df = utils_address.get_address_df()
    
    # 2. 显示编辑器 (适配新的 4 列结构)
    edited_df = st.data_editor(
        current_df,
        num_rows="dynamic",
        column_config={
            "Condo Name": st.column_config.TextColumn(
                "Condo Name (CSV文件名)", 
                help="对应上传文件的项目名",
                required=True
            ),
            "Block No": st.column_config.TextColumn(
                "Block No", 
                help="具体楼号。若适用全小区，可填 DEFAULT",
                required=True
            ),
            "Road Name": st.column_config.TextColumn(
                "Road Name", 
                required=True
            ),
            "Post Code": st.column_config.TextColumn(
                "Post Code", 
                help="6位邮政编码"
            )
        },
        use_container_width=True,
        hide_index=True,
        key="address_editor_tab5_v2"
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
