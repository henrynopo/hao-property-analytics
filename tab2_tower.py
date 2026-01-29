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
        # Streamlit 新版组件
        selected_blk = st.pills("选择楼栋:", all_blks, selection_mode="single", default=all_blks[0], key="tw_blk")
    except AttributeError:
        # 旧版兼容
        selected_blk = st.radio("选择楼栋:", all_blks, horizontal=True, key="tw_blk_radio")

    if selected_blk:
        blk_df = df[df['BLK'] == selected_blk].copy()
        
        # 确定楼层范围
        if 'Floor_Num' not in blk_df.columns:
            st.error("数据缺少 Floor_Num 列，无法绘制楼宇图")
            return

        valid_floors = blk_df.dropna(subset=['Floor_Num'])
        block_floors_set = set(valid_floors['Floor_Num'].unique())
        # 过滤掉 0 层或异常值
        sorted_floors_num = sorted(list({f for f in block_floors_set if f > 0}))
        
        if not sorted_floors_num:
            st.warning("该楼栋没有有效的楼层数据")
            return

        all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key) if 'Stack' in blk_df.columns else ['Unknown']
        
        grid_data = []
        for stack in all_stacks:
            for floor in sorted_floors_num:
                # 查找是否有交易记录
                match = blk_df[(blk_df['Stack'] == stack) & (blk_df['Floor_Num'] == floor)]
                
                # 格式化显示的 Stack (例如 01)
                stack_str = str(stack).strip()
                stack_fmt = stack_str.zfill(2) if stack_str.isdigit() else stack_str
                unit_label = f"#{int(floor):02d}-{stack_fmt}"
                
                if not match.empty:
                    # === 已售单位 (Sold) ===
                    latest = match.sort_values('Sale Date', ascending=False).iloc[0]
                    hold_days = (datetime.now() - latest['Sale Date']).days
                    hold_years = hold_days / 365.25
                    
                    # 计算 SSD 状态
                    _, ssd_emoji, _ = calculate_ssd_status(latest['Sale Date'])
                    
                    grid_data.append({
                        'Stack': str(stack), 
                        'Floor': str(int(floor)), 
                        'Type': 'Sold',
                        'PSF': int(latest['Sale PSF']), 
                        'Price': f"${latest['Sale Price']/1e6:.2f}M", 
                        'Year': latest['Sale Year'], 
                        'Raw_Floor': int(floor), 
                        # 显示: 单位号 + Emoji + 持有年限
                        'Label': f"{unit_label}<br>{ssd_emoji} {hold_years:.1f}y", 
                        'Fmt_Stack': stack_fmt 
                    })
                else:
                    # === 🟢 库存单位 (Stock) ===
                    # 既然不在交易记录里，视为长期持有 SSD Free
                    grid_data.append({
                        'Stack': str(stack), 
                        'Floor': str(int(floor)), 
                        'Type': 'Stock',
                        'PSF': None, 
                        'Price': '-', 
                        'Year': '-', 
                        'Raw_Floor': int(floor), 
                        # 显示: 单位号 + 绿灯
                        'Label': f"{unit_label}<br>🟢", 
                        'Fmt_Stack': stack_fmt
                    })
        
        viz_df = pd.DataFrame(grid_data)
        
        if not viz_df.empty:
            fig_tower = go.Figure()
            # 确保 Y 轴楼层排序正确
            y_cat_order = [str(f) for f in sorted_floors_num]
            
            # --- 1. 绘制库存层 (Stock) ---
            stock_df = viz_df[viz_df['Type'] == 'Stock']
            if not stock_df.empty:
                fig_tower.add_trace(go.Heatmap(
                    x=stock_df['Stack'], 
                    y=stock_df['Floor'], 
                    z=[1]*len(stock_df), # 伪数据用于生成格子
                    colorscale=[[0, '#eeeeee'], [1, '#eeeeee']], # 固定灰色
                    showscale=False, 
                    xgap=2, ygap=2, 
                    
                    # 🟢 核心修复: 必须加上 texttemplate 才会把字印在格子上
                    text=stock_df['Label'],
                    texttemplate="%{text}",
                    
                    # 鼠标悬停显示更详细的信息
                    hovertemplate="<b>Stack %{x} - #%{y}</b><br>🟢 Status: SSD Free (No Record)<br>点击查看估值<extra></extra>",
                    
                    customdata=stock_df[['Stack', 'Raw_Floor']]
                ))

            # --- 2. 绘制已售层 (Sold) ---
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

            # --- 布局设置 ---
            fig_tower.update_layout(
                title=dict(text=f"Block {selected_blk} - 物理透视图 (SSD: 🟢Free 🟡<6m 🔴Locked)", x=0.5),
                xaxis=dict(title="Stack", type='category', side='bottom'),
                yaxis=dict(title="Floor", type='category', categoryorder='array', categoryarray=y_cat_order, dtick=1),
                plot_bgcolor='white', 
                # 动态高度计算，防止格子压扁
                height=max(400, len(y_cat_order) * 40), 
                width=min(1000, 100 * len(all_stacks) + 200), 
                margin=dict(l=50, r=50, t=60, b=50),
                clickmode='event+select'
            )
            fig_tower.update_layout(font=dict(size=chart_font_size))
            
            # --- 交互事件 ---
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
            st.warning("该楼栋数据不足，无法生成图表")
