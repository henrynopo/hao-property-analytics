# tab2_tower.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from utils import natural_key, calculate_ssd_status

def render(df, chart_font_size):
    st.subheader("🏢 楼宇透视")
    if 'BLK' not in df.columns:
        st.warning("缺少 BLK 列")
        return

    all_blks = sorted(df['BLK'].unique(), key=natural_key)
    try:
        selected_blk = st.pills("选择楼栋:", all_blks, selection_mode="single", default=all_blks[0], key="tw_blk")
    except AttributeError:
        selected_blk = st.radio("选择楼栋:", all_blks, horizontal=True, key="tw_blk_radio")

    if selected_blk:
        blk_df = df[df['BLK'] == selected_blk].copy()
        
        if 'Floor_Num' not in blk_df.columns:
            st.error("数据缺少 Floor_Num 列")
            return

        valid_floors = blk_df.dropna(subset=['Floor_Num'])
        if valid_floors.empty:
            st.warning("该楼栋没有有效的楼层数据")
            return

        # 🟢 核心修复：不再只取 unique()，而是强制生成连续的楼层范围
        # 找出最低和最高层，强制填补中间的空缺
        min_f = int(valid_floors['Floor_Num'].min())
        max_f = int(valid_floors['Floor_Num'].max())
        
        # 保护逻辑：防止 floor 为 0 或负数
        if min_f < 1: min_f = 1
        
        # 生成连续的楼层列表 (例如: 1, 2, 3, 4, ... 25)
        # 这样即使 第4层 从未交易过，也会被强制画出来
        sorted_floors_num = list(range(min_f, max_f + 1))

        all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key) if 'Stack' in blk_df.columns else ['Unknown']
        
        grid_data = []
        for stack in all_stacks:
            for floor in sorted_floors_num:
                # 查找交易记录
                match = blk_df[(blk_df['Stack'] == stack) & (blk_df['Floor_Num'] == floor)]
                
                stack_str = str(stack).strip()
                stack_fmt = stack_str.zfill(2) if stack_str.isdigit() else stack_str
                unit_label = f"#{int(floor):02d}-{stack_fmt}"
                
                if not match.empty:
                    # === 已售单位 ===
                    latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                    hold_days = (datetime.now() - latest['Sale Date']).days
                    hold_years = hold_days / 365.25
                    _, ssd_emoji, _ = calculate_ssd_status(latest['Sale Date'])
                    
                    grid_data.append({
                        'Stack': str(stack), 
                        'Floor': str(int(floor)), 
                        'Type': 'Sold',
                        'PSF': int(latest['Sale PSF']), 
                        'Price': f"${latest['Sale Price']/1e6:.2f}M", 
                        'Year': latest['Sale Year'], 
                        'Raw_Floor': int(floor), 
                        'Label': f"{unit_label}<br>{ssd_emoji} {hold_years:.1f}y", 
                        'Fmt_Stack': stack_fmt 
                    })
                else:
                    # === 🟢 空缺填补 (Stock) ===
                    # 无论是没有记录，还是中间断层，统统视为 Stock
                    grid_data.append({
                        'Stack': str(stack), 
                        'Floor': str(int(floor)), 
                        'Type': 'Stock',
                        'PSF': None, 
                        'Price': '-', 
                        'Year': '-', 
                        'Raw_Floor': int(floor), 
                        'Label': f"{unit_label}<br>🟢", 
                        'Fmt_Stack': stack_fmt
                    })
        
        viz_df = pd.DataFrame(grid_data)
        
        if not viz_df.empty:
            fig_tower = go.Figure()
            # 保证 Y 轴从低到高排序
            y_cat_order = [str(f) for f in sorted_floors_num]
            
            # 1. 绘制库存层 (Stock)
            stock_df = viz_df[viz_df['Type'] == 'Stock']
            if not stock_df.empty:
                fig_tower.add_trace(go.Heatmap(
                    x=stock_df['Stack'], 
                    y=stock_df['Floor'], 
                    z=[1]*len(stock_df), 
                    colorscale=[[0, '#eeeeee'], [1, '#eeeeee']], 
                    showscale=False, 
                    xgap=2, ygap=2, 
                    text=stock_df['Label'],
                    texttemplate="%{text}", # 🟢 确保文字显示在格子上
                    hovertemplate="<b>Stack %{x} - #%{y}</b><br>🟢 Status: SSD Free (No Record)<br>点击查看估值<extra></extra>",
                    customdata=stock_df[['Stack', 'Raw_Floor']]
                ))

            # 2. 绘制已售层 (Sold)
            sold_df = viz_df[viz_df['Type'] == 'Sold']
            if not sold_df.empty:
                fig_tower.add_trace(go.Heatmap(
                    x=sold_df['Stack'], 
                    y=sold_df['Floor'], 
                    z=sold_df['PSF'],
                    colorscale='Teal', 
                    colorbar=dict(title="成交尺价 ($psf)", len=0.5, y=0.5),
                    xgap=2, ygap=2,
                    text=sold_df['Label'], 
                    texttemplate="%{text}",
                    hovertemplate="<b>Stack %{x} - #%{y}</b><br>💰 PSF: $%{z}<br>🏷️ 总价: %{customdata[2]}<br>📅 年份: %{customdata[3]}<extra></extra>",
                    customdata=sold_df[['Stack', 'Raw_Floor', 'Price', 'Year']]
                ))

            # 3. 布局优化
            fig_tower.update_layout(
                title=dict(text=f"Block {selected_blk} - 物理透视图 (SSD: 🟢Free 🟡<6m 🔴Locked)", x=0.5),
                xaxis=dict(title="Stack", type='category', side='bottom'),
                yaxis=dict(title="Floor", type='category', categoryorder='array', categoryarray=y_cat_order, dtick=1),
                plot_bgcolor='white', 
                height=max(500, len(y_cat_order) * 45), # 🟢 增加高度，让格子不那么扁
                width=min(1200, 120 * len(all_stacks) + 200), 
                margin=dict(l=50, r=50, t=60, b=50),
                clickmode='event+select'
            )
            fig_tower.update_layout(font=dict(size=chart_font_size))
            
            event = st.plotly_chart(
                fig_tower, 
                use_container_width=True, 
                on_select="rerun", 
                selection_mode="points", 
                key=f"chart_{selected_blk}", 
                config={'displayModeBar': False}
            )
            
            if event and "selection" in event and event["selection"]["points"]:
                point = event["selection"]["points"][0]
                if "customdata" in point:
                    st.session_state['avm_target'] = {
                        'blk': selected_blk, 
                        'stack': str(point["customdata"][0]), 
                        'floor': int(point["customdata"][1])
                    }
                    st.toast(f"已选中 {selected_blk} #{point['customdata'][1]}-{point['customdata'][0]}", icon="✅")
        else:
            st.warning("该楼栋数据不足")
