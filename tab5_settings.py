import streamlit as st
import utils_address
import time
import pandas as pd

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
    
    # 2. 显示编辑器
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
    if st.button("💾 保存配置 (Save Changes)", type="primary"):
        utils_address.save_from_df(edited_df)
        st.success("配置已保存！")
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    
    # 4. [新增] 复制功能区域
    st.subheader("🛠️ 快捷工具 (Quick Tools)")
    st.caption("从现有记录复制一行，以便快速添加相似楼栋。")
    
    if not current_df.empty:
        # 创建人性化的选项列表: "Index: Condo - Block"
        # 使用 format_func 在界面上显示友好的字符串
        copy_options = current_df.apply(
            lambda x: f"{x['Condo Name']} | Blk {x['Block No']} | {x['Road Name']}", axis=1
        ).tolist()
        
        c1, c2 = st.columns([3, 1])
        with c1:
            # 使用 index 来定位，防止字符串重复导致的问题
            selected_idx = st.selectbox(
                "选择要复制的源行 (Select Source Row)", 
                options=range(len(copy_options)),
                format_func=lambda i: copy_options[i]
            )
        with c2:
            st.write("") # 占位符，对齐按钮
            st.write("")
            if st.button("📋 复制并新增 (Copy & Add)"):
                # A. 获取源数据 (DataFrame Row)
                source_row = current_df.iloc[selected_idx]
                
                # B. 构造新数据字典 (映射回 utils_address 底层需要的 keys: project, block, street, postal)
                new_entry = {
                    "project": source_row["Condo Name"],
                    "block": f"{source_row['Block No']} (Copy)", # 自动添加后缀，提示用户修改
                    "street": source_row["Road Name"],
                    "postal": source_row["Post Code"]
                }
                
                # C. 读取现有列表(List of Dicts)，追加新行，并保存
                # 注意：我们必须直接操作底层 JSON 数据，而不是操作 UI 上的 DataFrame
                current_list = utils_address.load_addresses()
                current_list.append(new_entry)
                utils_address.save_addresses(current_list)
                
                # D. 提示并刷新
                st.toast(f"✅ 已复制！新增行: {new_entry['block']}")
                time.sleep(1)
                st.rerun()
    else:
        st.info("暂无数据可复制，请先在上方添加一行。")
