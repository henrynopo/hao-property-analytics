# tab3_avm.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils import calculate_avm, calculate_ssd_status
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM)")

    # ================= 1. 自动定位逻辑 =================
    target_blk = None
    target_floor = None
    target_stack = None

    if 'avm_target' in st.session_state:
        tgt = st.session_state['avm_target']
        target_blk = tgt['blk']
        target_floor = tgt['floor']
        target_stack = tgt['stack']
        
        st.success(f"已定位到: Block {target_blk} #{target_floor}-{target_stack}")
        del st.session_state['avm_target']

    # ================= 2. 输入栏 (全下拉菜单) =================
    c1, c2, c3 = st.columns(3)
    
    # 1. Block
    with c1:
        blks = sorted(df['BLK'].unique())
        b_idx = 0
        if target_blk in blks:
            b_idx = blks.index(target_blk)
        s_blk = st.selectbox("1. 选择楼座 (Block)", blks, index=b_idx, key="avm_blk")
    
    # 2. Floor
    with c2:
        blk_df = df[df['BLK'] == s_blk]
        if 'Floor_Num' in blk_df.columns:
            valid_floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int))
        else:
            valid_floors = list(range(1, 26))
            
        if not valid_floors: valid_floors = [1]
        
        f_idx = 0
        if target_floor in valid_floors:
            f_idx = valid_floors.index(target_floor)
        else:
            if 10 in valid_floors: f_idx = valid_floors.index(10)
            else: f_idx = len(valid_floors) // 2
                
        s_floor = st.selectbox("2. 选择楼层 (Floor)", valid_floors, index=f_idx, key="avm_floor")

    # 3. Stack
    with c3:
        relevant_stacks = sorted(blk_df[blk_df['Floor_Num'] == s_floor]['Stack'].unique())
        if not relevant_stacks:
            relevant_stacks = sorted(blk_df['Stack'].unique())
        if not relevant_stacks: relevant_stacks = ['Unknown']
        
        s_idx = 0
        if target_stack in relevant_stacks:
            s_idx = relevant_stacks.index(target_stack)
            
        s_stack = st.selectbox("3. 选择单元 (Stack)", relevant_stacks, index=s_idx, key="avm_stack")

    # ================= 3. 核心计算与显示 =================
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        
        area, val_psf, valuation, floor_diff, prem_rate, comps_df, subject_cat = calculate_avm(df, s_blk, s_stack, s_floor)

        if area is None:
            st.error("❌ 数据不足，无法估值。")
            return

        # 准备数据
        hist_df = df[(df['BLK'] == s_blk) & (df['Stack'] == s_stack) & (df['Floor_Num'] == s_floor)].sort_values('Sale Date')
        
        last_price = 0
        net_gain = 0
        ssd_cost = 0
        
        if not hist_df.empty:
            last_tx = hist_df.iloc[-1]
            last_price = last_tx['Sale Price']
            last_date = last_tx['Sale Date']
            
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
        
        # [Section 2] 估值区间仪表盘
        fig_gauge = go.Figure(go.Indicator(
            mode = "number+gauge",
            value = valuation,
            number = {'prefix': "$", 'valueformat': ",.0f", 'font': {'size': 20}},
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Valuation Confidence Range (95%-105%)", 'font': {'size': 14}},
            gauge = {
                'shape': "bullet",
                'axis': {'range': [valuation*0.85, valuation*1.15]},
                'bar': {'color': "#F63366"}, 
                'steps': [
                    {'range': [valuation*0.85, valuation*0.95], 'color': "lightgray"},
                    {'range': [valuation*0.95, valuation*1.05], 'color': "#90EE90"}, 
                    {'range': [valuation*1.05, valuation*1.15], 'color': "lightgray"}
                ],
            }
        ))
        fig_gauge.update_layout(height=120, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

        # [Section 3] 本单位历史成交 (History)
        st.subheader("📜 本单位历史成交 (Unit History)")
        if not hist_df.empty:
            # 🟢 修复核心: 动态检查列名，防止 KeyError
            target_cols = ['Sale Date', 'Sale Price', 'Sale PSF', 'Type of Sale']
            # 只取数据中实际存在的列
            available_cols = [c for c in target_cols if c in hist_df.columns]
            
            st.dataframe(
                hist_df[available_cols].style.format({
                    'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}"
                }),
                use_container_width=True
            )
            
            if ssd_rate > 0:
                st.warning(f"⚠️ **SSD 风险提示**: 若现在出售，预计需缴纳 {ssd_text} 约 ${ssd_cost/1e6:.2f}M")
            else:
                st.success("✅ **SSD Free**: 该单位已过禁售期，无需缴纳卖家印花税。")
        else:
            st.info("ℹ️ 该单位在数据库中暂无历史交易记录。")

        # [Section 4] 周边参考成交 (Comps)
        st.subheader("📉 周边参考成交 (Comparables)")
        
        # 同样做一次列检查，防止 Comps 表格也崩
        comps_target_cols = ['Sale Date', 'Unit', 'Sale Price', 'Sale PSF', 'Area (sqft)']
        comps_avail_cols = [c for c in comps_target_cols if c in comps_df.columns]
        
        st.dataframe(
            comps_df[comps_avail_cols].style.format({
                'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}", 'Area (sqft)': "{:,.0f}"
            }),
            use_container_width=True
        )

        # [Section 5] PDF 下载
        st.markdown("---")
        if PDF_AVAILABLE:
            unit_info = {'blk': s_blk, 'unit': f"{s_floor:02d}-{s_stack}"}
            valuation_data = {'value': valuation, 'area': area, 'psf': val_psf}
            analysis_data = {'net_gain': net_gain, 'ssd_cost': ssd_cost, 'last_price': last_price}
            data_cutoff = df['Sale Date'].max().strftime('%Y-%m-%d')
            
            pdf_bytes = generate_pdf_report(
                project_name, unit_info, valuation_data, analysis_data, hist_df, comps_df, data_cutoff
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
            st.warning("⚠️ PDF 生成组件不可用")
