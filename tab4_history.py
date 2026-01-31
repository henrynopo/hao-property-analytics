import streamlit as st
import pandas as pd
from utils import render_transaction_table

def render(df):
    st.subheader("📜 历年交易详情 (Transaction Details)")

    # 1. 筛选逻辑
    with st.expander("🔍 筛选 (Filter)", expanded=True): 
        c1, c2 = st.columns(2)
        all_blks = sorted(df['BLK'].unique())
        try:
            sel_blks = c1.pills("楼座 (Block)", options=all_blks, selection_mode="multi", key="filter_blk_pills")
        except AttributeError:
            sel_blks = c1.multiselect("楼座 (Block)", all_blks, key="filter_blk_multi")
        
        type_col = 'Type' if 'Type' in df.columns else 'Category'
        all_types = sorted(df[type_col].unique())
        try:
            sel_types = c2.pills("户型 (Type)", options=all_types, selection_mode="multi", key="filter_type_pills")
        except AttributeError:
            sel_types = c2.multiselect("户型 (Type)", all_types, key="filter_type_multi")
        
    filtered_df = df.copy()
    if sel_blks: filtered_df = filtered_df[filtered_df['BLK'].isin(sel_blks)]
    if sel_types: filtered_df = filtered_df[filtered_df[type_col].isin(sel_types)]
    
    # 2. 调用通用组件渲染 (V216)
    render_transaction_table(filtered_df)