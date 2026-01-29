# 文件名: tab2_tower.py
import streamlit as st
import pandas as pd
import re

# 自然排序函数 (保留，为了列顺序正常)
def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

# 接口兼容 (保留 chart_font_size 防止报错，但内部不乱用它干扰布局)
def render(df, chart_font_size=12):
    st.subheader("🏢 楼宇透视 (Building View)")

    # 1. 筛选
    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    selected_blk = st.selectbox("选择楼座 (Block)", all_blks, key="tab2_blk_select")

    # 2. 数据准备
    blk_df = df[df['BLK'] == selected_blk].copy()

    # 3. 处理楼层排序
    if 'Floor_Num' in blk_df.columns:
        blk_df['Floor_Sort'] = blk_df['Floor_Num'].fillna(0).astype(int)
    else:
        blk_df['Floor_Sort'] = blk_df['Floor'].astype(str).str.extract(r'(\d+)')[0].fillna(0).astype(int)

    # 取每个格子最新的一笔交易
    latest_tx = blk_df.sort_values('Sale Date').groupby(['Floor_Sort', 'Stack']).tail(1)

    # 4. 构造 HTML 内容 (回归经典简洁样式)
    def make_cell_html(row):
        price = f"${row['Sale Price']/1e6:.2f}M"
        psf = f"${row['Sale PSF']:,.0f}"
        date = row['Sale Date'].strftime('%y-%m') if isinstance(row['Sale Date'], pd.Timestamp) else str(row['Sale Date'])[:7]
        
        # 简洁的三行布局
        return f"""
        <div style="text-align: center; line-height: 1.3;">
            <div style="font-weight: bold; font-size: 14px; color: #333;">{price}</div>
            <div style="font-size: 12px; color: #666;">{psf} psf</div>
            <div style="font-size: 11px; color: #999;">{date}</div>
        </div>
        """
    
    latest_tx['display_html'] = latest_tx.apply(make_cell_html, axis=1)

    if not latest_tx.empty:
        # 生成透视表
        unit_grid = latest_tx.pivot(index='Floor_Sort', columns='Stack', values='display_html')
        
        # 严谨排序列 (Stack)
        sorted_cols = sorted(unit_grid.columns.tolist(), key=natural_key)
        unit_grid = unit_grid.reindex(columns=sorted_cols)
        
        # 倒序排列行 (楼层高在下 -> 实际上通常楼宇图是高层在上，即倒序索引)
        unit_grid = unit_grid.sort_index(ascending=False)
        
        # 5. 渲染网格 (使用 Streamlit Columns)
        # 表头
        cols = st.columns([1] + [2] * len(unit_grid.columns))
        with cols[0]:
            st.markdown("**Floor**")
        for i, stack_name in enumerate(unit_grid.columns):
            with cols[i+1]:
                st.markdown(f"<div style='text-align: center; font-weight: bold;'>{stack_name}</div>", unsafe_allow_html=True)
            
        st.markdown("---")

        # 表体
        for floor_num, row in unit_grid.iterrows():
            c_row = st.columns([1] + [2] * len(unit_grid.columns))
            
            # 楼层号
            with c_row[0]:
                st.markdown(f"**L{floor_num}**")
                
            # 单元格
            for i, stack_name in enumerate(unit_grid.columns):
                content = row[stack_name]
                with c_row[i+1]:
                    if pd.isna(content):
                        # 空白格样式
                        st.markdown("""
                        <div style="
                            background-color: #f8f9fa; 
                            border: 1px dashed #dee2e6; 
                            border-radius: 4px; 
                            height: 60px; 
                            display: flex; 
                            align-items: center; 
                            justify-content: center;
                            color: #adb5bd;
                            font-size: 12px;
                            margin-bottom: 6px;
                        ">
                            -
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        # 交易格样式 (白底阴影卡片)
                        st.markdown(f"""
                        <div style="
                            background-color: #ffffff; 
                            border: 1px solid #e9ecef; 
                            border-radius: 6px; 
                            padding: 4px; 
                            margin-bottom: 6px;
                            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                            transition: transform 0.1s;
                        ">
                            {content}
                        </div>
                        """, unsafe_allow_html=True)
    else:
        st.info("该楼座暂无交易数据")

    st.caption(f"显示 Block {selected_blk} 最新成交。")
