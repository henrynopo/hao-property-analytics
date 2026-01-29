# tab2_tower.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from utils import natural_key, calculate_ssd_status, detect_block_step, get_stack_start_floor # 🟢 引入新函数

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

        min_f = int(valid_floors['Floor_Num'].min())
        max_f = int(valid_floors['Floor_Num'].max())
        if min_f < 1: min_f = 1
        
        # 1. 决定整栋楼的 Step
        step = detect_block_step(blk_df)
        
        all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key) if 'Stack' in blk_df.columns else ['Unknown']
        
        grid_data = []
        # 用于 Y 轴显示的并集集合
        all_visible_floors = set()

        for stack in all_stacks:
            # 获取该 Stack 的数据
            stack_df = blk_df[blk_df['Stack'] == stack]
            
            # 🟢 2. 决定该 Stack 的起始楼层
            start_f = get_stack_start_floor(stack_df, min_f, step)
            
            # 生成该 Stack 应有的楼层列表
            stack_floors = list(range(start_f, max_f + 1, step))
            all_visible_floors.update(stack_floors)
            
            for floor in stack_floors:
                match = blk_df[
                    (blk_df['Stack'].astype(str) == str(stack)) & 
                    (blk_df['Floor_Num'] == floor)
                ]
                
                stack_str = str(stack).strip()
                stack_fmt = stack_str.zfill(2) if stack_str.isdigit() else stack_str
                unit_label = f"#{int(floor):02d}-{stack_fmt}"
                
                if not match.empty:
                    # === 已售 ===
                    latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                    hold_days = (datetime.now() - latest['Sale Date']).days
                    hold_years = hold_days / 365.25
                    _, ssd_emoji, _ = calculate_ssd_status(latest['Sale Date'])
                    
                    grid_data.append({
                        'Stack': str(stack), 'Floor_Val': int(floor), 'Type': 'Sold',
                        'PSF': int(latest['Sale PSF']), 'Price': f"${latest['Sale Price']/1e6:.2f}M", 
                        'Year': latest['Sale Year'], 'Raw_Floor': int(floor), 
                        'Label': f"{unit_label}<br>{ssd_emoji} {hold_years:.1f}y", 
                        'Fmt_Stack': stack_fmt 
                    })
                else:
                    # === 库存 ===
                    grid_data.append({
                        'Stack': str(stack), 'Floor_Val': int(floor), 'Type': 'Stock',
                        'PSF': None, 'Price': '-', 'Year': '-', 'Raw_Floor': int(floor), 
                        'Label': f"{unit_label}<br>🟢", 
                        'Fmt_Stack': stack_fmt
                    })
        
        viz_df = pd.DataFrame(grid_data)
        
        if not viz_df.empty:
            fig_tower = go.Figure()
            
            # Layer 1: Stock
            stock_df = viz_df[viz_df['Type'] == 'Stock']
            if not stock_df.empty:
                fig_tower.add_trace(go.Heatmap(
                    x=stock_df['Stack'], y=stock_df['Floor_Val'], z=[1]*len(stock_df), 
                    colorscale=[[0, '#eeeeee'], [1, '#eeeeee']], showscale=False, 
                    xgap=2, ygap=2, text=stock_df['Label'], texttemplate="%{text}", 
                    hovertemplate="<b>Stack %{x} - #%{y}</b><br>🟢 SSD Free (Stock)<br>点击估值<extra></extra>",
                    customdata=stock_df[['Stack', 'Raw_Floor']]
                ))

            # Layer 2: Sold
            sold_df = viz_df[viz_df['Type'] == 'Sold']
            if not sold_df.empty:
                fig_tower.add_trace(go.Heatmap(
                    x=sold_df['Stack'], y=sold_df['Floor_Val'], z=sold_df['PSF'],
                    colorscale='Teal', colorbar=dict(title="成交尺价 ($psf)", len=0.5, y=0.5),
                    xgap=2, ygap=2, text=sold_df['Label'], texttemplate="%{text}",
                    hovertemplate="<b>Stack %{x} - #%{y}</b><br>💰 PSF: $%{z}<br>🏷️ 总价: %{customdata[2]}<br>📅 年份: %{customdata[3]}<extra></extra>",
                    customdata=sold_df[['Stack', 'Raw_Floor', 'Price', 'Year']]
                ))

            # Y轴刻度设置: 显示所有可见的楼层
            y_tick_vals = sorted(list(all_visible_floors))
            y_tick_text = [str(f) for f in y_tick_vals]

            fig_tower.update_layout(
                title=dict(text=f"Block {selected_blk} (SSD: 🟢Free 🟡<6m 🔴Locked)", x=0.5),
                xaxis=dict(title="Stack", type='category', side='bottom'),
                yaxis=dict(
                    title="Floor", tickmode='array', tickvals=y_tick_vals, ticktext=y_tick_text, dtick=1, # 强制显示所有刻度
                    range=[min_f - 0.5, max_f + 0.5]
                ),
                plot_bgcolor='white', 
                height=max(500, len(y_tick_vals) * 45), 
                width=min(1200, 120 * len(all_stacks) + 200), 
                margin=dict(l=50, r=50, t=60, b=50),
                clickmode='event+select'
            )
            fig_tower.update_layout(font=dict(size=chart_font_size))
            
            event = st.plotly_chart(fig_tower, use_container_width=True, on_select="rerun", selection_mode="points", key=f"chart_{selected_blk}", config={'displayModeBar': False})
            
            if event and "selection" in event and event["selection"]["points"]:
                point = event["selection"]["points"][0]
                if "customdata" in point:
                    st.session_state['avm_target'] = {
                        'blk': selected_blk, 'stack': str(point["customdata"][0]), 'floor': int(point["customdata"][1])
                    }
                    st.toast(f"已选中 {selected_blk} #{point['customdata'][1]}-{point['customdata'][0]}", icon="✅")
        else:
            st.warning("无数据可绘制")
