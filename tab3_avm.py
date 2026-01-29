# tab3_avm.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
# 🟢 必须确保引入 natural_key
from utils import calculate_avm, calculate_ssd_status, natural_key
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM)")

    # --- 1. 自动定位 ---
    target_blk, target_floor, target_stack = None, None, None
    if 'avm_target' in st.session_state:
        tgt = st.session_state['avm_target']
        target_blk, target_floor, target_stack = tgt['blk'], tgt['floor'], tgt['stack']
        st.success(f"📍 已定位: {target_blk} #{target_floor}-{target_stack}")
        del st.session_state['avm_target']

    # --- 2. 输入栏 (全下拉菜单) ---
    c1, c2, c3 = st.columns(3)
    
    with c1:
        blks = sorted(df['BLK'].unique(), key=natural_key)
        b_idx = blks.index(target_blk) if target_blk in blks else 0
        s_blk = st.selectbox("1. 选择楼座 (Block)", blks, index=b_idx, key="avm_blk_v78")

    with c2:
        blk_df = df[df['BLK'] == s_blk]
        if 'Floor_Num' in blk_df.columns:
            valid_floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int))
        else:
            valid_floors = [1]
        if not valid_floors: valid_floors = [1]
        
        f_idx = valid_floors.index(target_floor) if target_floor in valid_floors else len(valid_floors)//2
        s_floor = st.selectbox("2. 选择楼层 (Floor)", valid_floors, index=f_idx, key="avm_floor_v78")

    with c3:
        relevant_stacks = sorted(blk_df[blk_df['Floor_Num'] == s_floor]['Stack'].unique(), key=natural_key)
        if not relevant_stacks:
            relevant_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
        if not relevant_stacks: relevant_stacks = ['Unknown']
        
        s_idx = relevant_stacks.index(target_stack) if target_stack in relevant_stacks else 0
        s_stack = st.selectbox("3. 选择单元 (Stack)", relevant_stacks, index=s_idx, key="avm_stack_v78")

    # --- 3. 核心计算 ---
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        area, val_psf, valuation, floor_diff, prem_rate, comps_df, subject_cat = calculate_avm(df, s_blk, s_stack, s_floor)

        if area is None:
            st.error("❌ 无法估值：数据不足")
            return

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

        st.markdown("---")
        
        # 指标卡
        m1, m2, m3 = st.columns(3)
        m1.metric("预估总价", f"${valuation/1e6:.2f}M", delta=f"{net_gain/1e6:+.2f}M" if last_price else None)
        m2.metric("预估尺价", f"${val_psf:,.0f} psf")
        m3.metric("单位面积", f"{int(area):,} sqft")

        # 仪表盘 (深蓝指针, 无红线)
        fig = go.Figure(go.Indicator(
            mode = "number+gauge", value = valuation,
            number = {'prefix': "$", 'valueformat': ",.0f"},
            gauge = {
                'axis': {'range': [valuation*0.85, valuation*1.15]},
                'bar': {'color': "#1f77b4"},
                'steps': [
                    {'range': [valuation*0.85, valuation*0.95], 'color': "#f0f2f6"},
                    {'range': [valuation*0.95, valuation*1.05], 'color': "#90EE90"},
                    {'range': [valuation*1.05, valuation*1.15], 'color': "#f0f2f6"}
                ]
            }
        ))
        fig.update_layout(height=120, margin=dict(t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

        # 历史成交 (History)
        st.subheader("📜 本单位历史 (History)")
        if not hist_df.empty:
            # 🟢 终极防崩逻辑：取交集
            # 不管你要什么列，我只给数据里实际有的列
            wanted_cols = ['Sale Date', 'Sale Price', 'Sale PSF', 'Type of Sale']
            final_cols = [c for c in wanted_cols if c in hist_df.columns]
            
            st.dataframe(
                hist_df[final_cols].style.format({'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}"}), 
                use_container_width=True
            )
            
            if ssd_rate > 0: st.warning(f"⚠️ 需付 SSD: {ssd_text}")
            else: st.success("✅ SSD Free")
        else:
            st.info("无历史记录")

        # 周边成交 (Comps)
        st.subheader("📉 周边参考 (Comps)")
        # 同样做防崩处理
        wanted_c_cols = ['Sale Date', 'Unit', 'Sale Price', 'Sale PSF', 'Area (sqft)']
        final_c_cols = [c for c in wanted_c_cols if c in comps_df.columns]
        
        st.dataframe(
            comps_df[final_c_cols].style.format({'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}", 'Area (sqft)': "{:,.0f}"}), 
            use_container_width=True
        )

        # PDF 下载
        st.markdown("---")
        if PDF_AVAILABLE:
            u_info = {'blk': s_blk, 'unit': f"{s_floor:02d}-{s_stack}"}
            v_data = {'value': valuation, 'area': area, 'psf': val_psf}
            a_data = {'net_gain': net_gain, 'ssd_cost': ssd_cost, 'last_price': last_price}
            d_cut = df['Sale Date'].max().strftime('%Y-%m-%d')
            
            # PDF 生成也可能有隐患，这里加个 try-except
            try:
                pdf = generate_pdf_report(project_name, u_info, v_data, a_data, hist_df, comps_df, d_cut)
                st.download_button("📄 下载 PDF 信函", data=pdf, file_name="valuation_letter.pdf", mime="application/pdf", type="primary", use_container_width=True)
            except Exception as e:
                st.warning(f"PDF 生成失败: {str(e)}，请检查 fpdf2 是否安装")
