# tab3_avm.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils import calculate_avm, calculate_ssd_status
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM)")

    # ================= 1. 自动定位逻辑 =================
    # 默认值
    default_blk_idx = 0
    default_floor = 10
    default_stack_idx = 0

    # 接收跳转参数
    if 'avm_target' in st.session_state:
        tgt = st.session_state['avm_target']
        try:
            blks = sorted(df['BLK'].unique())
            if tgt['blk'] in blks:
                default_blk_idx = blks.index(tgt['blk'])
            default_floor = tgt['floor']
            # Stack 的定位稍后在下拉框逻辑中处理
            st.success(f"已定位到: Block {tgt['blk']} #{tgt['floor']}-{tgt['stack']}")
            # 暂存目标 stack 以便后续匹配
            target_stack = tgt['stack']
            del st.session_state['avm_target']
        except:
            target_stack = None
    else:
        target_stack = None

    # ================= 2. 输入栏 (Block -> Floor -> Stack) =================
    c1, c2, c3 = st.columns(3)
    
    with c1:
        # 1. 选择 Block
        blks = sorted(df['BLK'].unique())
        s_blk = st.selectbox("1. 选择楼座 (Block)", blks, index=default_blk_idx, key="avm_blk")
    
    with c2:
        # 2. 输入 Floor (数字输入通常比下拉更高效，但也可用下拉)
        # 获取该 Block 的楼层范围作为提示
        blk_df = df[df['BLK'] == s_blk]
        min_f, max_f = 1, 50
        if 'Floor_Num' in blk_df.columns:
            valid_floors = blk_df['Floor_Num'].dropna()
            if not valid_floors.empty:
                min_f, max_f = int(valid_floors.min()), int(valid_floors.max())
        
        s_floor = st.number_input(f"2. 输入楼层 (Floor {min_f}-{max_f})", min_value=1, max_value=max(50, max_f), value=default_floor, step=1, key="avm_floor")

    with c3:
        # 3. 选择 Stack (根据 Block 和 Floor 智能筛选)
        # 逻辑：优先显示该 Block 该 Floor 实际成交过的 Stack
        relevant_stacks = sorted(blk_df[blk_df['Floor_Num'] == s_floor]['Stack'].unique())
        if not relevant_stacks:
            # 如果该层没交易过，则显示该 Block 所有 Stack
            relevant_stacks = sorted(blk_df['Stack'].unique())
        
        if not relevant_stacks: relevant_stacks = ['Unknown']
        
        # 尝试匹配跳转过来的 Stack
        stack_index = 0
        if target_stack in relevant_stacks:
            stack_index = relevant_stacks.index(target_stack)
            
        s_stack = st.selectbox("3. 选择单元 (Stack)", relevant_stacks, index=stack_index, key="avm_stack")

    # ================= 3. 核心计算与显示 =================
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        
        # 调用核心算法
        area, val_psf, valuation, floor_diff, prem_rate, comps_df, subject_cat = calculate_avm(df, s_blk, s_stack, s_floor)

        if area is None:
            st.error("❌ 数据不足，无法估值。")
            return

        # 准备数据
        hist_df = df[(df['BLK'] == s_blk) & (df['Stack'] == s_stack) & (df['Floor_Num'] == s_floor)].sort_values('Sale Date')
        
        last_price = 0
        net_gain = 0
        ssd_cost = 0
        last_date_str = "-"
        
        if not hist_df.empty:
            last_tx = hist_df.iloc[-1]
            last_price = last_tx['Sale Price']
            last_date = last_tx['Sale Date']
            last_date_str = last_date.strftime('%Y-%m-%d')
            
            ssd_rate, ssd_emoji, ssd_text = calculate_ssd_status(last_date)
            ssd_cost = valuation * ssd_rate
            net_gain = valuation - last_price - ssd_cost
        else:
            ssd_rate, ssd_emoji, ssd_text = 0, "", ""

        # --- 界面渲染 ---
        st.markdown("---")
        
        # [Section 1] 核心指标
        m1, m2, m3 = st.columns(3)
        m1.metric("预估总价 (Valuation)", f"${valuation/1e6:.2f}M", delta=f"{net_gain/1e6:+.2f}M (Gain)" if last_price else None)
        m2.metric("预估尺价 (Est. PSF)", f"${val_psf:,.0f} psf")
        m3.metric("单位面积 (Area)", f"{int(area):,} sqft")
        
        # [Section 2] 估值区间仪表盘 (新增)
        # 使用 Plotly 绘制一个简单的 Gauge Bar
        fig_gauge = go.Figure(go.Indicator(
            mode = "number+gauge",
            value = valuation,
            number = {'prefix': "$", 'valueformat': ",.0f", 'font': {'size': 20}},
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Valuation Confidence Range (95%-105%)", 'font': {'size': 14}},
            gauge = {
                'shape': "bullet",
                'axis': {'range': [valuation*0.85, valuation*1.15]},
                'bar': {'color': "#F63366"}, # Streamlit Red
                'steps': [
                    {'range': [valuation*0.85, valuation*0.95], 'color': "lightgray"},
                    {'range': [valuation*0.95, valuation*1.05], 'color': "#90EE90"}, # Green Zone
                    {'range': [valuation*1.05, valuation*1.15], 'color': "lightgray"}
                ],
            }
        ))
        fig_gauge.update_layout(height=120, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

        # [Section 3] 本单位历史成交 (History) - 放在上面
        st.subheader("📜 本单位历史成交 (Unit History)")
        if not hist_df.empty:
            st.dataframe(
                hist_df[['Sale Date', 'Sale Price', 'Sale PSF', 'Type of Sale']].style.format({
                    'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}"
                }),
                use_container_width=True
            )
            # SSD 提示
            if ssd_rate > 0:
                st.warning(f"⚠️ **SSD 风险提示**: 若现在出售，预计需缴纳 {ssd_text} 约 ${ssd_cost/1e6:.2f}M")
            else:
                st.success("✅ **SSD Free**: 该单位已过禁售期，无需缴纳卖家印花税。")
        else:
            st.info("ℹ️ 该单位在数据库中暂无历史交易记录。")

        # [Section 4] 周边参考成交 (Comps) - 放在下面
        st.subheader("📉 周边参考成交 (Comparables)")
        st.dataframe(
            comps_df[['Sale Date', 'Unit', 'Sale Price', 'Sale PSF', 'Area (sqft)']].style.format({
                'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}", 'Area (sqft)': "{:,.0f}"
            }),
            use_container_width=True
        )

        # [Section 5] PDF 下载
        st.markdown("---")
        if PDF_AVAILABLE:
            # 数据打包
            unit_info = {'blk': s_blk, 'unit': f"{s_floor:02d}-{s_stack}"}
            valuation_data = {'value': valuation, 'area': area, 'psf': val_psf}
            analysis_data = {'net_gain': net_gain, 'ssd_cost': ssd_cost, 'last_price': last_price}
            data_cutoff = df['Sale Date'].max().strftime('%Y-%m-%d')
            
            # 生成 PDF
            pdf_bytes = generate_pdf_report(
                project_name, 
                unit_info, 
                valuation_data, 
                analysis_data, 
                hist_df, 
                comps_df, 
                data_cutoff
            )
            
            st.download_button(
                label="📄 下载正式估值信函 (PDF Letter)",
                data=pdf_bytes,
                file_name=f"Letter_{project_name}_{s_blk}_{s_floor}-{s_stack}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.warning("⚠️ PDF 生成组件不可用 (请检查 requirements.txt 是否包含 fpdf2)")
